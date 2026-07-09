"""Unit tests for structured boolean semantic helpers."""

from __future__ import annotations

import pytest

from sva2rtl.bool_semantics import (
    collect_bool_signals,
    deserialize_bool_expr,
    eval_bool_expr,
    render_bool_expr,
    serialize_bool_expr,
)
from sva2rtl.ir import (
    BoolBinary,
    BoolBitSelect,
    BoolCompare,
    BoolConst,
    BoolIdent,
    BoolNode,
    BoolUnary,
    SourceLoc,
)

_LOC = SourceLoc("bool.sv", 7, 9)


def _ident(name: str) -> BoolIdent:
    return BoolIdent(name=name, source_loc=_LOC)


def test_render_and_eval_nested_logical_nodes() -> None:
    """AND, OR, NOT, and nesting have independent truth-table behavior."""
    expr = BoolBinary(
        op="and",
        left=_ident("a"),
        right=BoolBinary(
            op="or",
            left=BoolUnary(op="not", operand=_ident("b"), source_loc=_LOC),
            right=_ident("c"),
            source_loc=_LOC,
        ),
        source_loc=_LOC,
    )

    assert render_bool_expr(expr) == "(a && ((!b) || c))"
    assert eval_bool_expr(expr, {"a": True, "b": True, "c": False}) is False
    assert eval_bool_expr(expr, {"a": True, "b": True, "c": True}) is True
    assert eval_bool_expr(expr, {"a": True, "b": False, "c": False}) is True
    assert eval_bool_expr(expr, {"a": False, "b": False, "c": True}) is False


def test_constants_render_from_raw_and_evaluate_as_ints() -> None:
    """Constants preserve source spelling while evaluating by integer value."""
    one = BoolConst(value=1, width=1, raw="1'b1", source_loc=_LOC)
    zero = BoolConst(value=0, source_loc=_LOC)

    assert render_bool_expr(one) == "1'b1"
    assert render_bool_expr(zero) == "0"
    assert eval_bool_expr(one, {}) == 1
    assert eval_bool_expr(zero, {}) == 0


def test_comparisons_support_vector_equality_and_inequality() -> None:
    """Equality and inequality compare evaluated integer scalar/vector values."""
    expected = BoolConst(value=3, width=2, raw="2'd3", source_loc=_LOC)
    eq_expr = BoolCompare(op="eq", left=_ident("data"), right=expected, source_loc=_LOC)
    ne_expr = BoolCompare(op="ne", left=_ident("data"), right=expected, source_loc=_LOC)

    assert render_bool_expr(eq_expr) == "(data == 2'd3)"
    assert render_bool_expr(ne_expr) == "(data != 2'd3)"
    assert eval_bool_expr(eq_expr, {"data": 3}) is True
    assert eval_bool_expr(eq_expr, {"data": 2}) is False
    assert eval_bool_expr(ne_expr, {"data": 2}) is True
    assert eval_bool_expr(ne_expr, {"data": 3}) is False


def test_bit_select_reads_integer_vectors_and_missing_values_as_zero() -> None:
    """Supported single-bit selects read integer vectors with deterministic default zero."""
    expr = BoolBitSelect(value=_ident("data"), index=2, source_loc=_LOC)

    assert render_bool_expr(expr) == "data[2]"
    assert eval_bool_expr(expr, {"data": 0b100}) == 1
    assert eval_bool_expr(expr, {"data": 0b010}) == 0
    assert eval_bool_expr(expr, {}) == 0


def test_missing_identifiers_evaluate_false() -> None:
    """Absent scalar identifiers evaluate as false rather than raising."""
    assert eval_bool_expr(_ident("missing"), {}) is False


def test_collect_bool_signals_preserves_first_seen_order_and_deduplicates() -> None:
    """Signal collection returns composer-style observed pairs without duplicates."""
    expr = BoolBinary(
        op="and",
        left=BoolBinary(
            op="or",
            left=_ident("a"),
            right=BoolBitSelect(value=_ident("data"), index=0, source_loc=_LOC),
            source_loc=_LOC,
        ),
        right=_ident("a"),
        source_loc=_LOC,
    )

    assert collect_bool_signals(expr) == (("a", "a"), ("data", "data"))


def test_serialize_deserialize_round_trips_supported_nodes_deterministically() -> None:
    """Every supported node shape survives deterministic JSON round-trip."""
    expr: BoolNode = BoolCompare(
        op="ne",
        left=BoolBinary(
            op="and",
            left=BoolBitSelect(value=_ident("data"), index=1, source_loc=_LOC),
            right=BoolUnary(op="not", operand=_ident("mask"), source_loc=_LOC),
            source_loc=_LOC,
        ),
        right=BoolConst(value=0, width=1, raw="1'b0", source_loc=_LOC),
        source_loc=_LOC,
    )

    payload = serialize_bool_expr(expr)
    restored = deserialize_bool_expr(payload)

    assert restored == expr
    assert serialize_bool_expr(restored) == payload
    assert render_bool_expr(restored) == "((data[1] && (!mask)) != 1'b0)"


def test_deserialize_rejects_invalid_payload() -> None:
    """Malformed semantic payloads fail before producing partial IR."""
    with pytest.raises(ValueError, match="invalid boolean semantic JSON"):
        deserialize_bool_expr("{")
