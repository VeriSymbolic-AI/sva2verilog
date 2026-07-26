"""Focused accepted/rejected boundaries for mutation-sensitive AST import paths."""

from __future__ import annotations

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
)
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import SourceLoc

_LOC = SourceLoc("importer_boundaries.sv", 1, 1)
_SIGNAL = {"kind": "NamedValue", "symbol": "1 a"}


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
