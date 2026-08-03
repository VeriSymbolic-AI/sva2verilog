"""Unit tests for structured boolean semantic helpers."""

from __future__ import annotations

import json

import pytest

from sva2rtl.bool_semantics import (
    collect_bool_signal_types,
    collect_bool_signal_widths,
    collect_bool_signals,
    deserialize_bool_expr,
    eval_bool_expr,
    rename_bool_signals,
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


def test_signal_widths_and_renames_preserve_vector_metadata() -> None:
    """Identifier width metadata follows deterministic port aliases."""
    expr = BoolBinary(
        op="and",
        left=BoolIdent(name="start", width=1, source_loc=_LOC),
        right=BoolIdent(name="data", width=4, source_loc=_LOC),
        source_loc=_LOC,
    )

    renamed = rename_bool_signals(expr, {"start": "dut_start"})

    assert render_bool_expr(renamed) == "(dut_start && data)"
    assert collect_bool_signal_widths(renamed) == (("dut_start", 1), ("data", 4))
    assert deserialize_bool_expr(serialize_bool_expr(renamed)) == renamed


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("reduce_and", 0b1111, True),
        ("reduce_and", 0b1101, False),
        ("reduce_or", 0b0000, False),
        ("reduce_or", 0b0100, True),
        ("reduce_xor", 0b1011, True),
        ("reduce_xor", 0b1010, False),
    ],
)
def test_vector_reductions_use_every_declared_bit(
    op: str, value: int, expected: bool
) -> None:
    data = BoolIdent(name="data", width=4, signed=False, source_loc=_LOC)
    expr = BoolUnary(op=op, operand=data, source_loc=_LOC)

    rendered_op = {"reduce_and": "&", "reduce_or": "|", "reduce_xor": "^"}[op]
    assert render_bool_expr(expr) == f"({rendered_op}data)"
    assert eval_bool_expr(expr, {"data": value}) is expected


@pytest.mark.parametrize(
    ("op", "expected"),
    [("lt", True), ("le", True), ("gt", False), ("ge", False)],
)
def test_signed_relational_comparisons_use_width_aware_twos_complement(
    op: str, expected: bool
) -> None:
    left = BoolIdent(name="left", width=8, signed=True, source_loc=_LOC)
    right = BoolIdent(name="right", width=8, signed=True, source_loc=_LOC)
    expr = BoolCompare(op=op, left=left, right=right, source_loc=_LOC)

    # 8'hff is -1 only because both operands retain signed 8-bit metadata.
    assert eval_bool_expr(expr, {"left": 0xFF, "right": 1}) is expected
    assert collect_bool_signal_types(expr) == (
        ("left", 8, True),
        ("right", 8, True),
    )
    assert deserialize_bool_expr(serialize_bool_expr(expr)) == expr


def test_mixed_signed_relational_comparison_is_unsigned() -> None:
    signed_left = BoolIdent(name="left", width=8, signed=True, source_loc=_LOC)
    unsigned_right = BoolIdent(name="right", width=8, signed=False, source_loc=_LOC)
    expr = BoolCompare(op="lt", left=signed_left, right=unsigned_right, source_loc=_LOC)

    assert eval_bool_expr(expr, {"left": 0xFF, "right": 1}) is False


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


@pytest.mark.parametrize("optional_value", ["missing", None])
def test_deserialize_const_accepts_absent_or_null_optional_fields(
    optional_value: str | None,
) -> None:
    payload = json.loads(
        serialize_bool_expr(BoolConst(value=1, width=1, raw="1'b1", source_loc=_LOC))
    )
    for key in ("width", "raw"):
        if optional_value == "missing":
            del payload[key]
        else:
            payload[key] = None

    restored = deserialize_bool_expr(json.dumps(payload))

    assert isinstance(restored, BoolConst)
    assert restored.width is None
    assert restored.raw == ""


@pytest.mark.parametrize(("field", "value"), [("value", True), ("width", True)])
def test_deserialize_const_rejects_boolean_integer_fields(
    field: str,
    value: bool,
) -> None:
    payload = json.loads(
        serialize_bool_expr(BoolConst(value=1, width=1, raw="1'b1", source_loc=_LOC))
    )
    payload[field] = value

    with pytest.raises(ValueError, match="must be an integer"):
        deserialize_bool_expr(json.dumps(payload))
