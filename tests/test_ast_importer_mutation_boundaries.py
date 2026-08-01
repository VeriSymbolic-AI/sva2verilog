"""Focused accepted/rejected boundaries for mutation-sensitive AST import paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import (
    _build_bounded_always,
    _build_bounded_eventually,
    _build_goto_rep,
    _build_nonconsec_rep,
    _build_seq_concat,
    _build_seq_repetition,
    _build_signal_func,
    _reconstruct_signal_func_text,
    build_bool_expr,
    import_all_assertions,
)
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import BoolConst, SourceLoc

_LOC = SourceLoc("importer_boundaries.sv", 1, 1)
_SIGNAL = {"kind": "NamedValue", "symbol": "1 a"}
_FIXTURES = Path(__file__).parent / "fixtures"


def test_import_all_assertions_recurses_elaborated_instance_hierarchy_once() -> None:
    """Nested cached InstanceBody nodes are visible but never duplicated."""
    leaf_ast = json.loads((_FIXTURES / "fell.json").read_text(encoding="utf-8"))
    leaf_instance = leaf_ast["design"]["members"][0]
    ast = {
        "design": {
            "members": [
                {
                    "kind": "Instance",
                    "name": "top",
                    "body": {
                        "kind": "InstanceBody",
                        "addr": 100,
                        "members": [leaf_instance, leaf_instance],
                    },
                }
            ]
        }
    }

    assertions = import_all_assertions(ast)

    assert len(assertions) == 1
    assert assertions[0][2] == "$fell(sig)"


def test_import_all_assertions_ignores_malformed_instance_body_shape() -> None:
    """Malformed non-object Instance bodies fail closed without attribute errors."""
    ast = {"design": {"members": [{"kind": "Instance", "body": []}]}}

    with pytest.raises(SvaCompileError, match="No concurrent assertion"):
        import_all_assertions(ast)


def test_named_parameter_value_uses_slang_elaborated_constant() -> None:
    """A -G-specialized parameter is a constant, never an observed RTL port."""
    node = {
        "kind": "NamedValue",
        "symbol": "1 EXPECTED_PARAM",
        "type": "bit",
        "constant": "1'b1",
        "source_file_start": "importer_boundaries.sv",
        "source_line_start": 1,
        "source_column_start": 1,
    }

    result = build_bool_expr(node)

    assert result == BoolConst(value=1, width=1, raw="1'b1", source_loc=_LOC)


def test_named_parameter_four_state_constant_is_rejected() -> None:
    """Elaborated X/Z parameters do not enter the two-state monitor subset."""
    node = {
        "kind": "NamedValue",
        "symbol": "1 EXPECTED_PARAM",
        "type": "logic",
        "constant": "1'bx",
        "source_file_start": "importer_boundaries.sv",
        "source_line_start": 1,
        "source_column_start": 1,
    }

    with pytest.raises(UnsupportedConstruct, match="Four-state literal"):
        build_bool_expr(node)


@pytest.mark.parametrize("builder", [_build_goto_rep, _build_nonconsec_rep])
@pytest.mark.parametrize(("minimum", "maximum"), [(0, 2), (2, 0)])
def test_nonconsecutive_repetition_requires_each_bound_to_be_positive(
    builder: object,
    minimum: int,
    maximum: int,
) -> None:
    node = {
        "repetition": {"min": minimum, "max": maximum},
        "expr": _SIGNAL,
    }

    with pytest.raises(SvaCompileError, match="requires positive bounds"):
        builder(node, _LOC)  # type: ignore[operator]


def test_consecutive_zero_lower_bound_range_is_not_zero_length_match() -> None:
    node = {
        "repetition": {"min": 0, "max": 1},
        "expr": _SIGNAL,
    }

    repetition = _build_seq_repetition(node, _LOC)

    assert (repetition.rep_min, repetition.rep_max) == (0, 1)


@pytest.mark.parametrize(
    ("builder", "node"),
    [
        (
            _build_bounded_eventually,
            {"kind": "Unary", "op": "SEventually", "max": 3, "expr": _SIGNAL},
        ),
        (
            _build_bounded_always,
            {"kind": "Unary", "op": "Always", "min": 1, "expr": _SIGNAL},
        ),
    ],
)
def test_liveness_requires_both_range_endpoints(builder: object, node: dict[str, object]) -> None:
    with pytest.raises(UnsupportedConstruct, match="unbounded"):
        builder(node, _LOC)  # type: ignore[operator]


def test_past_without_explicit_depth_keeps_default_rendering() -> None:
    node = {
        "kind": "Call",
        "subroutineName": "$past",
        "arguments": [_SIGNAL],
    }

    signal_func = _build_signal_func(node, _LOC)

    assert signal_func.depth == 1
    assert _reconstruct_signal_func_text(signal_func) == "$past(a)"


def test_sampled_value_rejects_packed_vector_operand() -> None:
    node = {
        "kind": "CallExpression",
        "subroutineName": "$rose",
        "arguments": [{"kind": "NamedValue", "symbol": "1 data", "type": "logic[7:0]"}],
    }

    with pytest.raises(UnsupportedConstruct, match="width 8"):
        _build_signal_func(node, _LOC)


def test_sampled_value_rejects_expression_operand() -> None:
    node = {
        "kind": "CallExpression",
        "subroutineName": "$stable",
        "arguments": [
            {
                "kind": "ElementSelect",
                "value": {"kind": "NamedValue", "symbol": "1 data"},
                "selector": {"kind": "IntegerLiteral", "value": "0"},
            }
        ],
    }

    with pytest.raises(UnsupportedConstruct, match="scalar identifier"):
        _build_signal_func(node, _LOC)


def test_sampled_value_rejects_optional_arguments() -> None:
    node = {
        "kind": "CallExpression",
        "subroutineName": "$rose",
        "arguments": [_SIGNAL, {"kind": "NamedValue", "symbol": "1 clk"}],
    }

    with pytest.raises(UnsupportedConstruct, match="optional sampled-value"):
        _build_signal_func(node, _LOC)


def test_past_rejects_nonpositive_depth() -> None:
    node = {
        "kind": "CallExpression",
        "subroutineName": "$past",
        "arguments": [_SIGNAL, {"kind": "IntegerLiteral", "value": "0"}],
    }

    with pytest.raises(UnsupportedConstruct, match="at least 1"):
        _build_signal_func(node, _LOC)


def test_sequence_concat_rejects_either_negative_delay_endpoint() -> None:
    node = {
        "elements": [
            {"sequence": _SIGNAL, "min": "0", "max": "0"},
            {
                "sequence": {"kind": "NamedValue", "symbol": "1 b"},
                "min": "-1",
                "max": "2",
            },
        ]
    }

    with pytest.raises(SvaCompileError, match="negative delay"):
        _build_seq_concat(node, _LOC)
