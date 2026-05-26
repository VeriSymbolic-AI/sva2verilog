"""JSON AST → SVA IR translator.

Walks the slang --ast-json dict and produces a (SVANode, ClockSpec, str, str | None)
tuple for the first ConcurrentAssertion found:

    (ir_node, clock_spec, original_sva_text, label_or_None)

Design decisions (from Research Q1, Q6, pitfalls P5.1, P8.1, P8.2, P8.4):
- extract_source_loc() is called on *every* node visited (P5.1 prevention).
- _check_unsupported() is called before dispatch so Phase 2+ node kinds are
  rejected with precise source locations rather than crashing with KeyError.
- expr_to_sv() wraps all binary subexpressions in parentheses (P8.2 prevention).
- Clock is extracted from PropertySpec.clocking, never guessed from ports (P8.4).
- Default case in _dispatch_property_expr raises UnsupportedConstruct — never
  silent skip (P8.1 prevention).
"""

from __future__ import annotations

from typing import Any

from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import BoolExpr, ClockSpec, PropImplication, SeqConcat, SourceLoc, SVANode

# ── Operator tables ────────────────────────────────────────────────────────

_BINARY_OPS: dict[str, str] = {
    "BinaryAnd": "&",
    "BinaryOr": "|",
    "BinaryXor": "^",
    "LogicalAnd": "&&",
    "LogicalOr": "||",
    "Equality": "==",
    "Inequality": "!=",
    "LessThan": "<",
    "LessThanEqual": "<=",
    "GreaterThan": ">",
    "GreaterThanEqual": ">=",
}

_UNARY_OPS: dict[str, str] = {
    "LogicalNot": "!",
    "BitwiseNot": "~",
    "UnaryMinus": "-",
    "UnaryPlus": "+",
}

# Phase 1 unsupported node kinds; value is a human-readable construct name.
UNSUPPORTED_KINDS_PHASE1: dict[str, str] = {
    "SequenceRepetition": "[*N] consecutive repetition (Phase 2)",
}

# Implication operators are now handled natively (Phase 2).
_UNSUPPORTED_BINARY_OPS: dict[str, str] = {}


# ── Public API ─────────────────────────────────────────────────────────────


def import_assertion(
    ast: dict[str, Any],
) -> tuple[SVANode, ClockSpec, str, str | None]:
    """Walk *ast* and return IR for the first ConcurrentAssertion found.

    Parameters
    ----------
    ast:
        Parsed slang ``--ast-json`` dict (top-level key ``"design"``).

    Returns
    -------
    (ir_node, clock_spec, original_sva_text, label)
        * ``ir_node`` — SVANode (Phase 1: always BoolExpr)
        * ``clock_spec`` — ClockSpec extracted from PropertySpec.clocking
        * ``original_sva_text`` — reconstructed SV expression text
        * ``label`` — assertion label string or None

    Raises
    ------
    SvaCompileError
        When no ConcurrentAssertion is found in the AST, or required fields
        are missing.
    UnsupportedConstruct
        When an unsupported SVA construct is encountered (e.g. SequenceConcat).
    """
    design = ast.get("design", {})
    members: list[dict[str, Any]] = design.get("members", [])

    # Flatten members from all Instance/InstanceBody nodes
    for member in members:
        if member.get("kind") == "Instance":
            body = member.get("body", {})
            if body.get("kind") == "InstanceBody":
                result = _find_assertion_in_members(body.get("members", []))
                if result is not None:
                    return result

    raise SvaCompileError(
        message="No concurrent assertion found in the slang AST. "
        "Ensure the input file contains an 'assert property (...)' statement."
    )


def expr_to_sv(node: dict[str, Any]) -> str:
    """Recursively convert a slang JSON expression node to an SV text string.

    All binary sub-expressions are wrapped in parentheses to preserve
    precedence unambiguously in the generated RTL (prevents P8.2).

    Parameters
    ----------
    node:
        A slang AST expression dict with a ``"kind"`` field.

    Returns
    -------
    str
        Equivalent SV expression text.

    Raises
    ------
    UnsupportedConstruct
        For any expression node kind not handled in Phase 1.
    """
    source_loc = extract_source_loc(node)
    _check_unsupported(node, source_loc)

    match node["kind"]:
        case "NamedValue":
            symbol: str = str(node.get("symbol", " "))
            return symbol.split(" ", 1)[-1]

        case "BinaryOp":
            op_str = node.get("op", "")
            if op_str in _UNSUPPORTED_BINARY_OPS:
                raise UnsupportedConstruct(
                    message="Use a future version of sva2rtl for this feature",
                    construct_name=_UNSUPPORTED_BINARY_OPS[op_str],
                    source_loc=source_loc,
                )
            if op_str not in _BINARY_OPS:
                raise UnsupportedConstruct(
                    message=f"Unknown binary operator: '{op_str}'",
                    construct_name=op_str,
                    source_loc=source_loc,
                )
            op = _BINARY_OPS[op_str]
            left = expr_to_sv(node["left"])
            right = expr_to_sv(node["right"])
            return f"({left} {op} {right})"

        case "UnaryOp":
            op_str = node.get("op", "")
            if op_str not in _UNARY_OPS:
                raise UnsupportedConstruct(
                    message=f"Unknown unary operator: '{op_str}'",
                    construct_name=op_str,
                    source_loc=source_loc,
                )
            op = _UNARY_OPS[op_str]
            operand = expr_to_sv(node["operand"])
            return f"({op}{operand})"

        case "IntegerLiteral":
            return str(node.get("value", "0"))

        case "SequenceExpr":
            return expr_to_sv(node["expr"])

        case "BinaryPropertyExpr":
            op_str = node.get("op", "")
            _prop_op_map = {"And": "&&", "Or": "||"}
            if op_str not in _prop_op_map:
                raise UnsupportedConstruct(
                    message=f"Unsupported BinaryPropertyExpr op: '{op_str}'",
                    construct_name=op_str,
                    source_loc=source_loc,
                )
            op = _prop_op_map[op_str]
            left = expr_to_sv(node["left"])
            right = expr_to_sv(node["right"])
            return f"({left} {op} {right})"

        case "UnaryPropertyExpr":
            op_str = node.get("op", "")
            if op_str == "Not":
                inner = expr_to_sv(node["expr"])
                return f"(!{inner})"
            raise UnsupportedConstruct(
                message=f"Unsupported UnaryPropertyExpr op: '{op_str}'",
                construct_name=op_str,
                source_loc=source_loc,
            )

        case _:
            raise UnsupportedConstruct(
                message=f"Unsupported expression kind: '{node['kind']}'",
                construct_name=node["kind"],
                source_loc=source_loc,
            )


def extract_source_loc(node: dict[str, Any]) -> SourceLoc:
    """Extract a SourceLoc from a slang JSON node.

    Uses ``source_file_start``, ``source_line_start``, ``source_column_start``
    fields added by ``--ast-json-source-info``.  Falls back to ``"<unknown>"``
    / ``0`` when fields are absent.
    """
    return SourceLoc(
        file=str(node.get("source_file_start", "<unknown>")),
        line=int(node.get("source_line_start", 0)),
        col=int(node.get("source_column_start", 0)),
    )


# ── Private helpers ────────────────────────────────────────────────────────


def _check_unsupported(node: dict[str, Any], source_loc: SourceLoc) -> None:
    """Raise UnsupportedConstruct if *node* has a Phase 1-unsupported kind."""
    kind = node.get("kind", "")
    if kind in UNSUPPORTED_KINDS_PHASE1:
        raise UnsupportedConstruct(
            message="Use a future version of sva2rtl for this feature",
            construct_name=UNSUPPORTED_KINDS_PHASE1[kind],
            source_loc=source_loc,
        )


def _find_assertion_in_members(
    members: list[dict[str, Any]],
) -> tuple[SVANode, ClockSpec, str, str | None] | None:
    """Recursively search *members* for a ConcurrentAssertion.

    Returns the first found result or None.
    """
    for member in members:
        kind = member.get("kind", "")

        if kind == "ConcurrentAssertion":
            return _import_concurrent_assertion(member, label=None)

        # Labeled block: { "kind": "Block", "block": "ADDRESS my_check", ... }
        if kind == "Block":
            label = _extract_label(member)
            body = member.get("body", {})
            stmts: list[dict[str, Any]] = body.get("statements", [])
            for stmt in stmts:
                if stmt.get("kind") == "ConcurrentAssertion":
                    return _import_concurrent_assertion(stmt, label=label)
            # Recurse into nested members if present
            sub = body.get("members", [])
            result = _find_assertion_in_members(sub)
            if result is not None:
                return result

    return None


def _extract_label(block: dict[str, Any]) -> str | None:
    """Extract label name from a Block node's ``block`` field."""
    raw = block.get("block", "")
    if raw:
        # Format: "ADDRESS label_name" — we want just the label name
        parts = str(raw).split(" ", 1)
        if len(parts) == 2:
            return parts[1]
    return None


def _import_concurrent_assertion(
    node: dict[str, Any],
    label: str | None,
) -> tuple[SVANode, ClockSpec, str, str | None]:
    """Convert a ConcurrentAssertion node to IR."""
    source_loc = extract_source_loc(node)
    body = node.get("body", {})
    if body.get("kind") != "PropertySpec":
        raise SvaCompileError(
            message=f"Expected PropertySpec inside ConcurrentAssertion, "
            f"got '{body.get('kind', '<missing>')}' at {source_loc}"
        )

    clock_spec = _extract_clock(body)
    expr_node: dict[str, Any] = body.get("expr", {})

    match expr_node.get("kind"):
        case "SequenceConcat":
            seq_ir = _build_seq_concat(expr_node, source_loc)
            ir_node: SVANode = seq_ir
            text = _reconstruct_seq_text(seq_ir)
        case "BinaryPropertyExpr" if expr_node.get("op") in (
            "OverlappedImplication",
            "NonOverlappedImplication",
        ):
            prop_ir = _build_prop_implication(expr_node, source_loc)
            ir_node = prop_ir
            text = _reconstruct_impl_text(prop_ir)
        case _:
            _check_unsupported(expr_node, extract_source_loc(expr_node))
            text = expr_to_sv(expr_node)
            ir_node = BoolExpr(text=text, source_loc=source_loc)

    return ir_node, clock_spec, text, label


def _dispatch_expr_to_ir(node: dict[str, Any]) -> SVANode:
    """Convert an expression node to an SVANode (BoolExpr or SeqConcat).

    Used when building child elements of a SequenceConcat.
    """
    source_loc = extract_source_loc(node)
    match node.get("kind"):
        case "SequenceConcat":
            return _build_seq_concat(node, source_loc)
        case _:
            _check_unsupported(node, source_loc)
            text = expr_to_sv(node)
            return BoolExpr(text=text, source_loc=source_loc)


def _build_seq_concat(node: dict[str, Any], source_loc: SourceLoc) -> SeqConcat:
    """Build a SeqConcat IR node from a slang SequenceConcat JSON node.

    In slang JSON each element carries the delay AFTER that element
    (before the next one).  The last element always has min=0, max=0 as a
    trailing sentinel and MUST be skipped.
    """
    elements_raw: list[dict[str, Any]] = node.get("elements", [])
    elements: list[SVANode] = []
    delays: list[tuple[int, int]] = []

    for i, elem in enumerate(elements_raw):
        seq_node = elem.get("sequence", {})
        elements.append(_dispatch_expr_to_ir(seq_node))

        # Skip last element's delay — always (0, 0) sentinel in slang JSON
        if i < len(elements_raw) - 1:
            d_min = int(elem.get("min", "0"))
            d_max = int(elem.get("max", "0"))

            if d_min < 0 or d_max < 0:
                elem_loc = extract_source_loc(elem)
                raise SvaCompileError(
                    message=(
                        f"SVA-E003: Invalid delay range [{d_min}:{d_max}] — "
                        f"negative delay value at {elem_loc}"
                    )
                )
            if d_min > d_max:
                elem_loc = extract_source_loc(elem)
                raise SvaCompileError(
                    message=(
                        f"SVA-E003: Invalid delay range [{d_min}:{d_max}] — "
                        f"minimum exceeds maximum at {elem_loc}"
                    )
                )
            delays.append((d_min, d_max))

    return SeqConcat(
        elements=tuple(elements),
        delays=tuple(delays),
        source_loc=source_loc,
    )


def _reconstruct_seq_text(node: SeqConcat) -> str:
    """Reconstruct an SVA text representation from a SeqConcat IR node."""
    parts: list[str] = []
    for i, elem in enumerate(node.elements):
        if isinstance(elem, BoolExpr):
            parts.append(elem.text)
        elif isinstance(elem, SeqConcat):
            parts.append(_reconstruct_seq_text(elem))
        else:
            parts.append("<expr>")
        if i < len(node.delays):
            d_min, d_max = node.delays[i]
            if d_min == d_max:
                parts.append(f"##{d_min}")
            else:
                parts.append(f"##[{d_min}:{d_max}]")
    return " ".join(parts)


def _build_prop_implication(
    node: dict[str, Any],
    source_loc: SourceLoc,
) -> PropImplication:
    """Build a PropImplication IR node from a slang BinaryPropertyExpr JSON node."""
    ant = _dispatch_expr_to_ir(node["left"])
    con = _dispatch_expr_to_ir(node["right"])
    overlapping = node.get("op") == "OverlappedImplication"
    return PropImplication(
        antecedent=ant,
        consequent=con,
        overlapping=overlapping,
        source_loc=source_loc,
    )


def _reconstruct_impl_text(node: PropImplication) -> str:
    """Reconstruct SVA text for a PropImplication IR node."""
    op = "|->" if node.overlapping else "|=>"
    if isinstance(node.antecedent, BoolExpr):
        ant_text = node.antecedent.text
    elif isinstance(node.antecedent, SeqConcat):
        ant_text = _reconstruct_seq_text(node.antecedent)
    else:
        ant_text = "<ant>"
    if isinstance(node.consequent, BoolExpr):
        con_text = node.consequent.text
    elif isinstance(node.consequent, SeqConcat):
        con_text = _reconstruct_seq_text(node.consequent)
    else:
        con_text = "<con>"
    return f"{ant_text} {op} {con_text}"


def _extract_clock(prop_spec: dict[str, Any]) -> ClockSpec:
    """Extract ClockSpec from a PropertySpec node's ``clocking`` field.

    Raises SvaCompileError when the clocking annotation is absent or malformed.
    """
    clocking = prop_spec.get("clocking")
    if clocking is None:
        source_loc = extract_source_loc(prop_spec)
        raise SvaCompileError(
            message=(
                f"Property at {source_loc} has no clock annotation. "
                "Use @(posedge clk) or --default-clock flag."
            )
        )

    event = clocking.get("event", {})
    if event.get("kind") != "SignalEvent":
        source_loc = extract_source_loc(clocking)
        raise SvaCompileError(
            message=f"Expected SignalEvent in clocking at {source_loc}, "
            f"got '{event.get('kind', '<missing>')}'"
        )

    edge = str(event.get("edge", "posedge"))
    clk_expr: dict[str, Any] = event.get("expr", {})
    signal = clk_expr.get("symbol", " clk").split(" ", 1)[-1]
    clock_source_loc = extract_source_loc(event)

    return ClockSpec(edge=edge, signal=signal, source_loc=clock_source_loc)
