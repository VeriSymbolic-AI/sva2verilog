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
    "collect_bool_signals",
    "deserialize_bool_expr",
    "eval_bool_expr",
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
        case BoolBinary(op="and", left=left, right=right):
            return f"({render_bool_expr(left)} && {render_bool_expr(right)})"
        case BoolBinary(op="or", left=left, right=right):
            return f"({render_bool_expr(left)} || {render_bool_expr(right)})"
        case BoolCompare(op="eq", left=left, right=right):
            return f"({render_bool_expr(left)} == {render_bool_expr(right)})"
        case BoolCompare(op="ne", left=left, right=right):
            return f"({render_bool_expr(left)} != {render_bool_expr(right)})"
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
        case BoolBinary(op="and", left=left, right=right):
            return bool(eval_bool_expr(left, signals)) and bool(eval_bool_expr(right, signals))
        case BoolBinary(op="or", left=left, right=right):
            return bool(eval_bool_expr(left, signals)) or bool(eval_bool_expr(right, signals))
        case BoolCompare(op="eq", left=left, right=right):
            return _to_int(eval_bool_expr(left, signals)) == _to_int(eval_bool_expr(right, signals))
        case BoolCompare(op="ne", left=left, right=right):
            return _to_int(eval_bool_expr(left, signals)) != _to_int(eval_bool_expr(right, signals))
        case BoolBitSelect(value=BoolIdent(name=name), index=index):
            return (_to_int(signals.get(name, 0)) >> index) & 1
    _unsupported(expr)


def collect_bool_signals(expr: BoolNode) -> tuple[tuple[str, str], ...]:
    """Return observed signal pairs in first-seen order, deduplicated by name."""
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    _collect_bool_signals(expr, ordered, seen)
    return tuple(ordered)


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
        case BoolIdent(name=name, source_loc=source_loc):
            return {
                "kind": "ident",
                "name": name,
                "source_loc": _source_loc_to_json(source_loc),
            }
        case BoolConst(value=value, width=width, raw=raw, source_loc=source_loc):
            return {
                "kind": "const",
                "raw": raw,
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
        return BoolIdent(name=_require_str(obj, "name"), source_loc=source_loc)
    if kind == "const":
        return BoolConst(
            value=_require_int(obj, "value"),
            width=_optional_int(obj, "width"),
            raw=_optional_str(obj, "raw"),
            source_loc=source_loc,
        )
    if kind == "unary":
        op = _require_str(obj, "op")
        if op != "not":
            raise ValueError(f"unsupported unary boolean op: {op}")
        return BoolUnary(
            op=cast(Literal["not"], op),
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
        if op not in {"eq", "ne"}:
            raise ValueError(f"unsupported compare boolean op: {op}")
        return BoolCompare(
            op=cast(Literal["eq", "ne"], op),
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


def _to_int(value: SignalValue) -> int:
    return int(value)


def _unsupported(expr: BoolNode) -> NoReturn:
    raise TypeError(f"unsupported boolean expression node: {type(expr).__name__}")
