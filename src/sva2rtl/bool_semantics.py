"""Semantic helpers for structured boolean expression IR nodes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal, NoReturn, cast

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

SignalValue = bool | int
JsonMap = dict[str, object]

__all__ = [
    "collect_bool_signal_types",
    "collect_bool_signal_widths",
    "collect_bool_signals",
    "deserialize_bool_expr",
    "eval_bool_expr",
    "rename_bool_signals",
    "render_bool_expr",
    "serialize_bool_expr",
]


def render_bool_expr(expr: BoolNode) -> str:
    """Render a structured boolean expression as canonical SystemVerilog text."""
    match expr:
        case BoolIdent(name=name):
            return name
        case BoolConst(value=value, raw=raw):
            return raw or str(value)
        case BoolUnary(op="not", operand=operand):
            return f"(!{render_bool_expr(operand)})"
        case BoolUnary(op="reduce_and", operand=operand):
            return f"(&{render_bool_expr(operand)})"
        case BoolUnary(op="reduce_or", operand=operand):
            return f"(|{render_bool_expr(operand)})"
        case BoolUnary(op="reduce_xor", operand=operand):
            return f"(^{render_bool_expr(operand)})"
        case BoolBinary(op="and", left=left, right=right):
            return f"({render_bool_expr(left)} && {render_bool_expr(right)})"
        case BoolBinary(op="or", left=left, right=right):
            return f"({render_bool_expr(left)} || {render_bool_expr(right)})"
        case BoolCompare(op="eq", left=left, right=right):
            return f"({render_bool_expr(left)} == {render_bool_expr(right)})"
        case BoolCompare(op="ne", left=left, right=right):
            return f"({render_bool_expr(left)} != {render_bool_expr(right)})"
        case BoolCompare(op=op, left=left, right=right) if op in {
            "lt",
            "le",
            "gt",
            "ge",
        }:
            symbol = {"lt": "<", "le": "<=", "gt": ">", "ge": ">="}[op]
            return f"({render_bool_expr(left)} {symbol} {render_bool_expr(right)})"
        case BoolBitSelect(value=value, index=index):
            return f"{render_bool_expr(value)}[{index}]"
    _unsupported(expr)


def eval_bool_expr(expr: BoolNode, signals: Mapping[str, SignalValue]) -> bool | int:
    """Evaluate a structured boolean expression against two-state stimulus values."""
    match expr:
        case BoolIdent(name=name):
            return signals.get(name, False)
        case BoolConst(value=value):
            return value
        case BoolUnary(op="not", operand=operand):
            return not bool(eval_bool_expr(operand, signals))
        case BoolUnary(op=op, operand=operand) if op in {
            "reduce_and",
            "reduce_or",
            "reduce_xor",
        }:
            width = _expr_width(operand)
            value = _masked_value(eval_bool_expr(operand, signals), width)
            if op == "reduce_and":
                return value == (1 << width) - 1
            if op == "reduce_or":
                return value != 0
            return value.bit_count() % 2 == 1
        case BoolBinary(op="and", left=left, right=right):
            return bool(eval_bool_expr(left, signals)) and bool(eval_bool_expr(right, signals))
        case BoolBinary(op="or", left=left, right=right):
            return bool(eval_bool_expr(left, signals)) or bool(eval_bool_expr(right, signals))
        case BoolCompare(op="eq", left=left, right=right):
            return _to_int(eval_bool_expr(left, signals)) == _to_int(eval_bool_expr(right, signals))
        case BoolCompare(op="ne", left=left, right=right):
            return _to_int(eval_bool_expr(left, signals)) != _to_int(eval_bool_expr(right, signals))
        case BoolCompare(op=op, left=left, right=right) if op in {
            "lt",
            "le",
            "gt",
            "ge",
        }:
            left_value, right_value = _comparison_values(left, right, signals)
            if op == "lt":
                return left_value < right_value
            if op == "le":
                return left_value <= right_value
            if op == "gt":
                return left_value > right_value
            return left_value >= right_value
        case BoolBitSelect(value=BoolIdent(name=name), index=index):
            return (_to_int(signals.get(name, 0)) >> index) & 1
    _unsupported(expr)


def collect_bool_signals(expr: BoolNode) -> tuple[tuple[str, str], ...]:
    """Return observed signal pairs in first-seen order, deduplicated by name."""
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    _collect_bool_signals(expr, ordered, seen)
    return tuple(ordered)


def collect_bool_signal_widths(expr: BoolNode) -> tuple[tuple[str, int], ...]:
    """Return identifier widths in first-seen order, rejecting inconsistent IR."""
    widths: dict[str, int] = {}
    for ident in _walk_bool_idents(expr):
        previous = widths.get(ident.name)
        if previous is not None and previous != ident.width:
            raise ValueError(
                f"inconsistent widths for boolean identifier {ident.name!r}: "
                f"{previous} and {ident.width}"
            )
        widths.setdefault(ident.name, ident.width)
    return tuple(widths.items())


def collect_bool_signal_types(expr: BoolNode) -> tuple[tuple[str, int, bool], ...]:
    """Return identifier width and signedness in deterministic first-seen order."""
    types: dict[str, tuple[int, bool]] = {}
    for ident in _walk_bool_idents(expr):
        metadata = (ident.width, ident.signed)
        previous = types.get(ident.name)
        if previous is not None and previous != metadata:
            raise ValueError(
                f"inconsistent type for boolean identifier {ident.name!r}: "
                f"{previous} and {metadata}"
            )
        types.setdefault(ident.name, metadata)
    return tuple((name, width, signed) for name, (width, signed) in types.items())


def rename_bool_signals(expr: BoolNode, aliases: Mapping[str, str]) -> BoolNode:
    """Return a semantic expression whose identifiers use generated port aliases."""
    match expr:
        case BoolIdent(name=name, width=width, signed=signed, source_loc=source_loc):
            return BoolIdent(
                name=aliases.get(name, name),
                width=width,
                signed=signed,
                source_loc=source_loc,
            )
        case BoolConst():
            return expr
        case BoolUnary(op=op, operand=operand, source_loc=source_loc):
            return BoolUnary(
                op=op,
                operand=rename_bool_signals(operand, aliases),
                source_loc=source_loc,
            )
        case BoolBinary(op=op, left=left, right=right, source_loc=source_loc):
            return BoolBinary(
                op=op,
                left=rename_bool_signals(left, aliases),
                right=rename_bool_signals(right, aliases),
                source_loc=source_loc,
            )
        case BoolCompare(op=op, left=left, right=right, source_loc=source_loc):
            return BoolCompare(
                op=op,
                left=rename_bool_signals(left, aliases),
                right=rename_bool_signals(right, aliases),
                source_loc=source_loc,
            )
        case BoolBitSelect(value=value, index=index, source_loc=source_loc):
            renamed = rename_bool_signals(value, aliases)
            if not isinstance(renamed, BoolIdent):
                raise ValueError("bit-select base must remain an identifier")
            return BoolBitSelect(value=renamed, index=index, source_loc=source_loc)
    _unsupported(expr)


def serialize_bool_expr(expr: BoolNode) -> str:
    """Serialize a structured boolean expression to deterministic JSON."""
    return json.dumps(_to_json_obj(expr), sort_keys=True, separators=(",", ":"))


def deserialize_bool_expr(payload: str) -> BoolNode:
    """Deserialize a structured boolean expression from deterministic JSON."""
    try:
        raw: object = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid boolean semantic JSON") from exc
    return _from_json_obj(_as_json_map(raw, "root"))


def _collect_bool_signals(
    expr: BoolNode,
    ordered: list[tuple[str, str]],
    seen: set[str],
) -> None:
    match expr:
        case BoolIdent(name=name):
            if name not in seen:
                seen.add(name)
                ordered.append((name, name))
        case BoolConst():
            return
        case BoolUnary(operand=operand):
            _collect_bool_signals(operand, ordered, seen)
        case BoolBinary(left=left, right=right) | BoolCompare(left=left, right=right):
            _collect_bool_signals(left, ordered, seen)
            _collect_bool_signals(right, ordered, seen)
        case BoolBitSelect(value=value):
            _collect_bool_signals(value, ordered, seen)
        case _:
            _unsupported(expr)


def _to_json_obj(expr: BoolNode) -> JsonMap:
    match expr:
        case BoolIdent(name=name, width=width, signed=signed, source_loc=source_loc):
            return {
                "kind": "ident",
                "name": name,
                "source_loc": _source_loc_to_json(source_loc),
                "signed": signed,
                "width": width,
            }
        case BoolConst(
            value=value,
            width=width,
            raw=raw,
            signed=signed,
            source_loc=source_loc,
        ):
            return {
                "kind": "const",
                "raw": raw,
                "signed": signed,
                "source_loc": _source_loc_to_json(source_loc),
                "value": value,
                "width": width,
            }
        case BoolUnary(op=op, operand=operand, source_loc=source_loc):
            return {
                "kind": "unary",
                "op": op,
                "operand": _to_json_obj(operand),
                "source_loc": _source_loc_to_json(source_loc),
            }
        case BoolBinary(op=op, left=left, right=right, source_loc=source_loc):
            return {
                "kind": "binary",
                "left": _to_json_obj(left),
                "op": op,
                "right": _to_json_obj(right),
                "source_loc": _source_loc_to_json(source_loc),
            }
        case BoolCompare(op=op, left=left, right=right, source_loc=source_loc):
            return {
                "kind": "compare",
                "left": _to_json_obj(left),
                "op": op,
                "right": _to_json_obj(right),
                "source_loc": _source_loc_to_json(source_loc),
            }
        case BoolBitSelect(value=value, index=index, source_loc=source_loc):
            return {
                "index": index,
                "kind": "bit_select",
                "source_loc": _source_loc_to_json(source_loc),
                "value": _to_json_obj(value),
            }
    _unsupported(expr)


def _from_json_obj(obj: JsonMap) -> BoolNode:
    kind = _require_str(obj, "kind")
    source_loc = _source_loc_from_json(_require_map(obj, "source_loc"))

    if kind == "ident":
        return BoolIdent(
            name=_require_str(obj, "name"),
            width=_optional_int(obj, "width") or 1,
            signed=_optional_bool(obj, "signed"),
            source_loc=source_loc,
        )
    if kind == "const":
        return BoolConst(
            value=_require_int(obj, "value"),
            width=_optional_int(obj, "width"),
            raw=_optional_str(obj, "raw"),
            signed=_optional_bool(obj, "signed"),
            source_loc=source_loc,
        )
    if kind == "unary":
        op = _require_str(obj, "op")
        if op not in {"not", "reduce_and", "reduce_or", "reduce_xor"}:
            raise ValueError(f"unsupported unary boolean op: {op}")
        return BoolUnary(
            op=cast(Literal["not", "reduce_and", "reduce_or", "reduce_xor"], op),
            operand=_from_json_obj(_require_map(obj, "operand")),
            source_loc=source_loc,
        )
    if kind == "binary":
        op = _require_str(obj, "op")
        if op not in {"and", "or"}:
            raise ValueError(f"unsupported binary boolean op: {op}")
        return BoolBinary(
            op=cast(Literal["and", "or"], op),
            left=_from_json_obj(_require_map(obj, "left")),
            right=_from_json_obj(_require_map(obj, "right")),
            source_loc=source_loc,
        )
    if kind == "compare":
        op = _require_str(obj, "op")
        if op not in {"eq", "ne", "lt", "le", "gt", "ge"}:
            raise ValueError(f"unsupported compare boolean op: {op}")
        return BoolCompare(
            op=cast(Literal["eq", "ne", "lt", "le", "gt", "ge"], op),
            left=_from_json_obj(_require_map(obj, "left")),
            right=_from_json_obj(_require_map(obj, "right")),
            source_loc=source_loc,
        )
    if kind == "bit_select":
        value = _from_json_obj(_require_map(obj, "value"))
        if not isinstance(value, BoolIdent):
            raise ValueError("bit_select value must be a BoolIdent")
        return BoolBitSelect(
            value=value,
            index=_require_int(obj, "index"),
            source_loc=source_loc,
        )

    raise ValueError(f"unsupported boolean semantic node kind: {kind}")


def _walk_bool_idents(expr: BoolNode) -> tuple[BoolIdent, ...]:
    match expr:
        case BoolIdent():
            return (expr,)
        case BoolConst():
            return ()
        case BoolUnary(operand=operand):
            return _walk_bool_idents(operand)
        case BoolBinary(left=left, right=right) | BoolCompare(left=left, right=right):
            return _walk_bool_idents(left) + _walk_bool_idents(right)
        case BoolBitSelect(value=value):
            return (value,)
    _unsupported(expr)


def _source_loc_to_json(source_loc: SourceLoc) -> JsonMap:
    return {"col": source_loc.col, "file": source_loc.file, "line": source_loc.line}


def _source_loc_from_json(obj: JsonMap) -> SourceLoc:
    return SourceLoc(
        file=_require_str(obj, "file"),
        line=_require_int(obj, "line"),
        col=_require_int(obj, "col"),
    )


def _as_json_map(value: object, context: str) -> JsonMap:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object")
    return cast(JsonMap, value)


def _require_map(obj: JsonMap, key: str) -> JsonMap:
    if key not in obj:
        raise ValueError(f"missing key: {key}")
    return _as_json_map(obj[key], key)


def _require_str(obj: JsonMap, key: str) -> str:
    if key not in obj:
        raise ValueError(f"missing key: {key}")
    value = obj[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_str(obj: JsonMap, key: str) -> str:
    if key not in obj or obj[key] is None:
        return ""
    value = obj[key]
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _require_int(obj: JsonMap, key: str) -> int:
    if key not in obj:
        raise ValueError(f"missing key: {key}")
    value = obj[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _optional_int(obj: JsonMap, key: str) -> int | None:
    if key not in obj or obj[key] is None:
        return None
    value = obj[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer or null")
    return value


def _optional_bool(obj: JsonMap, key: str) -> bool:
    if key not in obj or obj[key] is None:
        return False
    value = obj[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean or null")
    return value


def _expr_width(expr: BoolNode) -> int:
    match expr:
        case BoolIdent(width=width):
            return max(1, width)
        case BoolConst(value=value, width=width):
            return max(1, width if width is not None else max(1, value.bit_length()))
        case BoolBitSelect() | BoolCompare():
            return 1
        case BoolUnary():
            return 1
        case BoolBinary():
            return 1
    _unsupported(expr)


def _expr_signed(expr: BoolNode) -> bool:
    match expr:
        case BoolIdent(signed=signed) | BoolConst(signed=signed):
            return signed
        case _:
            return False


def _masked_value(value: SignalValue, width: int) -> int:
    return _to_int(value) & ((1 << width) - 1)


def _signed_value(value: int, width: int) -> int:
    sign_bit = 1 << (width - 1)
    return value - (1 << width) if value & sign_bit else value


def _comparison_values(
    left: BoolNode,
    right: BoolNode,
    signals: Mapping[str, SignalValue],
) -> tuple[int, int]:
    width = max(_expr_width(left), _expr_width(right))
    left_value = _masked_value(eval_bool_expr(left, signals), width)
    right_value = _masked_value(eval_bool_expr(right, signals), width)
    if _expr_signed(left) and _expr_signed(right):
        return _signed_value(left_value, width), _signed_value(right_value, width)
    return left_value, right_value


def _to_int(value: SignalValue) -> int:
    return int(value)


def _unsupported(expr: BoolNode) -> NoReturn:
    raise TypeError(f"unsupported boolean expression node: {type(expr).__name__}")
