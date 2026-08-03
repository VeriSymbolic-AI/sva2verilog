"""Focused accepted/rejected boundaries for mutation-sensitive AST import paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sva2rtl.ast_importer import (
    _build_bounded_always,
    _build_bounded_eventually,
    _build_goto_rep,
    _build_nonconsec_rep,
    _build_seq_concat,
    _build_seq_repetition,
    _build_signal_func,
    _dispatch_expr_to_ir,
    _extract_label,
    _find_all_assertions_in_members,
    _find_assertion_in_members,
    _import_concurrent_assertion,
    _reconstruct_signal_func_text,
    build_bool_expr,
    import_all_assertions,
)
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import (
    BoolConst,
    PropNot,
    SeqAnd,
    SeqIntersect,
    SeqOr,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
)

_LOC = SourceLoc("importer_boundaries.sv", 1, 1)
_SIGNAL = {"kind": "NamedValue", "symbol": "1 a"}
_FIXTURES = Path(__file__).parent / "fixtures"


def _simple(name: str) -> dict[str, Any]:
    return {"kind": "Simple", "expr": {"kind": "NamedValue", "symbol": f"1 {name}"}}


def _clocked_assertion(expr: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "ConcurrentAssertion",
        "source_file_start": "importer_boundaries.sv",
        "source_line_start": 1,
        "source_column_start": 1,
        "propertySpec": {
            "kind": "Clocking",
            "clocking": {
                "kind": "SignalEvent",
                "edge": "PosEdge",
                "expr": {"kind": "NamedValue", "symbol": "1 clk"},
            },
            "expr": expr,
        },
    }


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


def test_unnamed_unsupported_call_reports_its_ast_kind() -> None:
    """An absent function name must not produce an empty diagnostic identity."""
    with pytest.raises(UnsupportedConstruct) as exc_info:
        build_bool_expr({"kind": "CallExpression"})

    assert exc_info.value.construct_name == "CallExpression"


def test_statement_block_label_is_consumed_by_single_assertion_search() -> None:
    assertion = _clocked_assertion(_simple("a"))
    members: list[dict[str, Any]] = [
        {"kind": "StatementBlock", "name": "single_label"},
        {"kind": "ProceduralBlock", "body": {"kind": "Block", "body": assertion}},
    ]

    result = _find_assertion_in_members(members)

    assert result is not None
    assert result[3] == "single_label"


def test_statement_block_label_is_consumed_by_all_assertion_search() -> None:
    assertion = _clocked_assertion(_simple("a"))
    members: list[dict[str, Any]] = [
        {"kind": "StatementBlock", "name": "all_label"},
        {"kind": "ProceduralBlock", "body": {"kind": "Block", "body": assertion}},
    ]

    results = _find_all_assertions_in_members(members)

    assert len(results) == 1
    assert results[0][3] == "all_label"


def test_non_statement_block_name_is_never_treated_as_a_label() -> None:
    assert _extract_label({"kind": "Block", "name": "wrong_field"}) is None


@pytest.mark.parametrize(
    ("kind", "expected_type"),
    [
        ("Intersect", SeqIntersect),
        ("Within", SeqWithin),
        ("Throughout", SeqThroughout),
    ],
)
def test_v11_binary_operator_dispatch_is_exact(
    kind: str,
    expected_type: type[SeqIntersect] | type[SeqWithin] | type[SeqThroughout],
) -> None:
    expr: dict[str, Any] = {
        "kind": "Binary",
        "op": kind,
        "left": _simple("a"),
        "right": _simple("b"),
    }

    ir, _clock, _text, _label = _import_concurrent_assertion(_clocked_assertion(expr), None)

    assert type(ir) is expected_type


def test_v11_unary_not_dispatch_is_exact() -> None:
    expr: dict[str, Any] = {"kind": "Unary", "op": "Not", "operand": _simple("a")}

    ir, _clock, _text, _label = _import_concurrent_assertion(_clocked_assertion(expr), None)

    assert type(ir) is PropNot


def test_legacy_unary_property_not_dispatch_is_exact() -> None:
    expr: dict[str, Any] = {
        "kind": "UnaryPropertyExpr",
        "op": "Not",
        "operand": _simple("a"),
    }

    ir, _clock, _text, _label = _import_concurrent_assertion(_clocked_assertion(expr), None)

    assert type(ir) is PropNot


def test_simple_wrapper_preserves_legacy_nonconsecutive_repetition() -> None:
    expr: dict[str, Any] = {
        "kind": "Simple",
        "expr": {
            "kind": "SimpleAssertionExpr",
            "expr": {"kind": "NamedValue", "symbol": "1 a"},
            "repetition": {"kind": "Nonconsecutive", "min": 2, "max": 2},
        },
    }

    ir, _clock, _text, _label = _import_concurrent_assertion(_clocked_assertion(expr), None)

    assert ir.__class__.__name__ == "SeqNonconsecRep"


def test_simple_wrapper_expands_inlined_assertion_instance() -> None:
    expr: dict[str, Any] = {
        "kind": "Simple",
        "expr": {
            "kind": "AssertionInstance",
            "body": {
                "kind": "SequenceConcat",
                "elements": [
                    {"sequence": _simple("a"), "min": 0, "max": 0},
                    {"sequence": _simple("b"), "min": 1, "max": 1},
                ],
            },
        },
    }

    ir, _clock, _text, _label = _import_concurrent_assertion(_clocked_assertion(expr), None)

    assert ir.__class__.__name__ == "SeqConcat"


@pytest.mark.parametrize(
    ("op", "expected_type"),
    [("And", SeqAnd), ("Or", SeqOr)],
)
def test_nested_binary_property_dispatch_is_exact(
    op: str,
    expected_type: type[SeqAnd] | type[SeqOr],
) -> None:
    node = {
        "kind": "BinaryPropertyExpr",
        "op": op,
        "left": _simple("a"),
        "right": _simple("b"),
    }

    assert type(_dispatch_expr_to_ir(node)) is expected_type


def test_nested_unary_property_not_dispatch_is_exact() -> None:
    node = {"kind": "UnaryPropertyExpr", "op": "Not", "operand": _simple("a")}

    assert type(_dispatch_expr_to_ir(node)) is PropNot


def test_nested_intersect_cannot_be_captured_by_or_dispatch() -> None:
    node = {
        "kind": "IntersectPropertyExpr",
        "left": _simple("a"),
        "right": _simple("b"),
    }

    assert type(_dispatch_expr_to_ir(node)) is SeqIntersect


def test_unknown_binary_property_operator_is_not_captured_as_or() -> None:
    node = {
        "kind": "BinaryPropertyExpr",
        "op": "Intersect",
        "left": _simple("a"),
        "right": _simple("b"),
    }

    with pytest.raises(UnsupportedConstruct, match="Unsupported BinaryPropertyExpr"):
        _dispatch_expr_to_ir(node)


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
    with pytest.raises(UnsupportedConstruct, match="both range endpoints"):
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
