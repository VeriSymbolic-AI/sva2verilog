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
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    DisableIff,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SignalFunc,
    SourceLoc,
    SVANode,
)

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

# Supported SVA signal function names (subroutineName in slang CallExpression).
_SUPPORTED_SIGNAL_FUNCS: frozenset[str] = frozenset(
    {"$rose", "$fell", "$stable", "$past"}
)

# Phase 1 unsupported node kinds; value is a human-readable construct name.
UNSUPPORTED_KINDS_PHASE1: dict[str, str] = {}

# Implication operators are now handled natively (Phase 2).
_UNSUPPORTED_BINARY_OPS: dict[str, str] = {}

# ── Named sequence/property declarations (Phase 3) ─────────────────────────
# Populated by import_assertion() from the current AST's module body members.
# Maps declaration name -> raw slang AST member dict.
# Single-threaded compiler; module-level state is safe.
_DECLARATIONS: dict[str, dict[str, Any]] = {}


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

    # First pass: collect named sequence/property declarations from each
    # InstanceBody so that _dispatch_expr_to_ir can inline SequenceInstance refs.
    global _DECLARATIONS
    for member in members:
        if member.get("kind") == "Instance":
            body = member.get("body", {})
            if body.get("kind") == "InstanceBody":
                _DECLARATIONS = _collect_declarations(body.get("members", []))

    # Second pass: locate and import the ConcurrentAssertion.
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


def import_all_assertions(
    ast: dict[str, Any],
) -> list[tuple[SVANode, ClockSpec, str, str | None]]:
    """Walk *ast* and return IR for ALL ConcurrentAssertions found.

    Parameters
    ----------
    ast:
        Parsed slang ``--ast-json`` dict (top-level key ``"design"``).

    Returns
    -------
    list of (ir_node, clock_spec, original_sva_text, label)
        One tuple per concurrent assertion found, in source order.

    Raises
    ------
    SvaCompileError
        When no ConcurrentAssertion is found in the AST (SVA-E001).
    UnsupportedConstruct
        When an unsupported SVA construct is encountered.
    """
    design = ast.get("design", {})
    members: list[dict[str, Any]] = design.get("members", [])

    # First pass: collect named sequence/property declarations.
    global _DECLARATIONS
    for member in members:
        if member.get("kind") == "Instance":
            body = member.get("body", {})
            if body.get("kind") == "InstanceBody":
                _DECLARATIONS = _collect_declarations(body.get("members", []))

    # Second pass: collect ALL ConcurrentAssertions.
    results: list[tuple[SVANode, ClockSpec, str, str | None]] = []
    for member in members:
        if member.get("kind") == "Instance":
            body = member.get("body", {})
            if body.get("kind") == "InstanceBody":
                results.extend(
                    _find_all_assertions_in_members(body.get("members", []))
                )

    if not results:
        raise SvaCompileError(
            message="No concurrent assertion found in the slang AST. "
            "Ensure the input file contains an 'assert property (...)' statement."
        )

    return results


def extract_dut_module(ast: dict[str, Any]) -> str:
    """Extract the top-level DUT module name from a slang ``--ast-json`` dict.

    Returns the ``name`` field of the first ``Instance`` member in
    ``design.members``.  This is the module name that the bind statement
    will target.

    Parameters
    ----------
    ast:
        Parsed slang ``--ast-json`` dict (top-level key ``"design"``).

    Returns
    -------
    str
        The DUT module instance name (e.g. ``"my_module"``), or
        ``"<unknown>"`` when no ``Instance`` member is found.
    """
    design = ast.get("design", {})
    members: list[dict[str, Any]] = design.get("members", [])
    for member in members:
        if member.get("kind") == "Instance":
            name = str(member.get("name", ""))
            if name:
                return name
    return "<unknown>"


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

        case "CallExpression":
            func_name = str(node.get("subroutineName", ""))
            if func_name in _SUPPORTED_SIGNAL_FUNCS:
                sf = _build_signal_func(node, source_loc)
                return _reconstruct_signal_func_text(sf)
            raise UnsupportedConstruct(
                message=f"Unsupported system function: '{func_name}'",
                construct_name=func_name,
                source_loc=source_loc,
            )

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


def _collect_declarations(members: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Scan module body *members* for named sequence/property declarations.

    Returns
    -------
    dict[str, dict[str, Any]]
        Mapping of declaration name → body expression AST dict.
        Only members with ``kind == "Sequence"`` or ``kind == "Property"``
        are collected; all other member kinds are silently ignored.
    """
    decls: dict[str, dict[str, Any]] = {}
    for member in members:
        kind = member.get("kind", "")
        if kind in ("Sequence", "Property"):
            name = str(member.get("name", ""))
            if name:
                body = member.get("body", {})
                decls[name] = body
    return decls


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


def _find_all_assertions_in_members(
    members: list[dict[str, Any]],
) -> list[tuple[SVANode, ClockSpec, str, str | None]]:
    """Recursively search *members* and return ALL ConcurrentAssertions found."""
    results: list[tuple[SVANode, ClockSpec, str, str | None]] = []
    for member in members:
        kind = member.get("kind", "")

        if kind == "ConcurrentAssertion":
            results.append(_import_concurrent_assertion(member, label=None))

        # Labeled block: { "kind": "Block", "block": "ADDRESS my_check", ... }
        if kind == "Block":
            label = _extract_label(member)
            body = member.get("body", {})
            stmts: list[dict[str, Any]] = body.get("statements", [])
            for stmt in stmts:
                if stmt.get("kind") == "ConcurrentAssertion":
                    results.append(_import_concurrent_assertion(stmt, label=label))
            # Recurse into nested members if present
            sub = body.get("members", [])
            results.extend(_find_all_assertions_in_members(sub))

    return results


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
        case "SimpleAssertionExpr" if expr_node.get("repetition", {}).get("kind") == "Consecutive":
            rep_ir = _build_seq_repetition(expr_node, source_loc)
            ir_node = rep_ir
            text = _reconstruct_rep_text(rep_ir)
        case "CallExpression" if expr_node.get("subroutineName") in _SUPPORTED_SIGNAL_FUNCS:
            sf_ir = _build_signal_func(expr_node, source_loc)
            ir_node = sf_ir
            text = _reconstruct_signal_func_text(sf_ir)
        case "BinaryPropertyExpr" if expr_node.get("op") in (
            "OverlappedImplication",
            "NonOverlappedImplication",
        ):
            prop_ir = _build_prop_implication(expr_node, source_loc)
            ir_node = prop_ir
            text = _reconstruct_impl_text(prop_ir)
        case "SequenceInstance":
            expanded = _expand_named_sequence(expr_node, source_loc, frozenset())
            ir_node = expanded
            text = _reconstruct_node_text(expanded)
        case _:
            _check_unsupported(expr_node, extract_source_loc(expr_node))
            text = expr_to_sv(expr_node)
            ir_node = BoolExpr(text=text, source_loc=source_loc)

    # ── disable iff wrapping ────────────────────────────────────────────────
    # slang puts the disable condition in PropertySpec.disableIff when the
    # property uses ``disable iff (cond) <body>`` syntax.
    disable_node: dict[str, Any] | None = body.get("disableIff")
    if disable_node is not None:
        disable_loc = extract_source_loc(disable_node)
        cond_text = expr_to_sv(disable_node)
        cond_ir = BoolExpr(text=cond_text, source_loc=disable_loc)
        ir_node = DisableIff(condition=cond_ir, body=ir_node, source_loc=source_loc)
        text = f"disable iff ({cond_text}) {text}"

    return ir_node, clock_spec, text, label


def _dispatch_expr_to_ir(node: dict[str, Any], _visited: frozenset[str] = frozenset()) -> SVANode:
    """Convert an expression node to an SVANode (BoolExpr or SeqConcat).

    Used when building child elements of a SequenceConcat.  *_visited* is the
    frozenset of named sequence names currently being expanded; it is threaded
    through recursive calls for cycle detection (SVA-E003).
    """
    source_loc = extract_source_loc(node)
    match node.get("kind"):
        case "SequenceConcat":
            return _build_seq_concat(node, source_loc, _visited)
        case "SimpleAssertionExpr" if node.get("repetition", {}).get("kind") == "Consecutive":
            return _build_seq_repetition(node, source_loc, _visited)
        case "CallExpression" if node.get("subroutineName") in _SUPPORTED_SIGNAL_FUNCS:
            return _build_signal_func(node, source_loc)
        case "SequenceInstance":
            return _expand_named_sequence(node, source_loc, _visited)
        case _:
            _check_unsupported(node, source_loc)
            text = expr_to_sv(node)
            return BoolExpr(text=text, source_loc=source_loc)


def _build_seq_repetition(
    node: dict[str, Any],
    source_loc: SourceLoc,
    _visited: frozenset[str] = frozenset(),
) -> SeqRepetition:
    """Build a SeqRepetition IR node from a slang SimpleAssertionExpr JSON node.

    The ``repetition`` sub-dict must have ``kind == "Consecutive"``.
    Raises ``SvaCompileError`` (SVA-E002) for unbounded repetition (max = "$").
    """
    rep = node.get("repetition", {})
    rep_min = int(rep.get("min", 1))
    max_val = rep.get("max", 1)
    if max_val == "$":
        raise SvaCompileError(
            message=(
                f"SVA-E002: unbounded repetition [*0:$] at {source_loc} is not "
                "synthesizable; use a finite upper bound."
            )
        )
    rep_max = int(max_val)
    inner_node = node.get("expr", {})
    inner = _dispatch_expr_to_ir(inner_node, _visited) if inner_node else BoolExpr(
        text="<expr>", source_loc=source_loc
    )
    return SeqRepetition(expr=inner, rep_min=rep_min, rep_max=rep_max, source_loc=source_loc)


def _reconstruct_rep_text(node: SeqRepetition) -> str:
    """Reconstruct an SVA text representation from a SeqRepetition IR node."""
    if isinstance(node.expr, BoolExpr):
        inner_text = node.expr.text
    elif isinstance(node.expr, SeqConcat):
        inner_text = _reconstruct_seq_text(node.expr)
    else:
        inner_text = "<expr>"
    if node.rep_min == node.rep_max:
        return f"{inner_text} [*{node.rep_min}]"
    return f"{inner_text} [*{node.rep_min}:{node.rep_max}]"


def _build_signal_func(node: dict[str, Any], source_loc: SourceLoc) -> SignalFunc:
    """Build a SignalFunc IR node from a slang CallExpression JSON node.

    Supports ``$rose``, ``$fell``, ``$stable``, ``$past``.
    For ``$past(sig, N)``, N must be an ``IntegerLiteral``; otherwise raises
    ``UnsupportedConstruct`` (non-compile-time depth is not synthesizable).

    Raises ``SvaCompileError`` when the first argument signal cannot be extracted.
    """
    raw_name: str = str(node.get("subroutineName", ""))
    func_name = raw_name.lstrip("$")  # "$rose" -> "rose", "$past" -> "past"

    arguments: list[dict[str, Any]] = node.get("arguments", [])
    if not arguments:
        raise SvaCompileError(
            message=(
                f"SVA-E004: signal function '{raw_name}' at {source_loc} "
                "requires at least one argument."
            )
        )

    # Extract signal name from first argument (expected NamedValue)
    arg0 = arguments[0]
    if arg0.get("kind") == "NamedValue":
        symbol: str = str(arg0.get("symbol", " "))
        signal = symbol.split(" ", 1)[-1]
    else:
        signal_text = expr_to_sv(arg0)
        signal = signal_text

    # Extract depth from second argument (only for $past)
    depth: int = 1
    if func_name == "past" and len(arguments) >= 2:
        arg1 = arguments[1]
        if arg1.get("kind") != "IntegerLiteral":
            arg1_loc = extract_source_loc(arg1)
            raise UnsupportedConstruct(
                message=(
                    f"$past depth must be a compile-time integer literal at {arg1_loc}; "
                    "non-literal depth is not synthesizable."
                ),
                construct_name="$past_dynamic_depth",
                source_loc=arg1_loc,
            )
        depth = int(arg1.get("value", 1))

    return SignalFunc(
        func_name=func_name,
        signal=signal,
        depth=depth,
        source_loc=source_loc,
    )


def _reconstruct_signal_func_text(node: SignalFunc) -> str:
    """Reconstruct SVA text for a SignalFunc IR node (e.g. ``$rose(sig)`` or ``$past(sig, 3)``)."""
    if node.func_name == "past" and node.depth != 1:
        return f"${node.func_name}({node.signal}, {node.depth})"
    return f"${node.func_name}({node.signal})"


def _build_seq_concat(
    node: dict[str, Any],
    source_loc: SourceLoc,
    _visited: frozenset[str] = frozenset(),
) -> SeqConcat:
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
        elements.append(_dispatch_expr_to_ir(seq_node, _visited))

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
        elif isinstance(elem, SeqRepetition):
            parts.append(_reconstruct_rep_text(elem))
        elif isinstance(elem, SignalFunc):
            parts.append(_reconstruct_signal_func_text(elem))
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
    _visited: frozenset[str] = frozenset(),
) -> PropImplication:
    """Build a PropImplication IR node from a slang BinaryPropertyExpr JSON node."""
    ant = _dispatch_expr_to_ir(node["left"], _visited)
    con = _dispatch_expr_to_ir(node["right"], _visited)
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


def _reconstruct_node_text(node: SVANode) -> str:
    """Return a human-readable SVA text string for any IR node type.

    Used when a named sequence is inline-expanded and its text needs to be
    reconstructed for the generated module header comment.
    """
    if isinstance(node, BoolExpr):
        return node.text
    if isinstance(node, SeqConcat):
        return _reconstruct_seq_text(node)
    if isinstance(node, SeqRepetition):
        return _reconstruct_rep_text(node)
    if isinstance(node, SignalFunc):
        return _reconstruct_signal_func_text(node)
    if isinstance(node, PropImplication):
        return _reconstruct_impl_text(node)
    return "<expr>"


def _expand_named_sequence(
    node: dict[str, Any],
    source_loc: SourceLoc,
    visited: frozenset[str],
) -> SVANode:
    """Inline-expand a ``SequenceInstance`` reference to its IR node.

    Looks up the sequence body in ``_DECLARATIONS``, recursively dispatches
    it through ``_dispatch_expr_to_ir``, and returns the resulting IR node.

    Parameters
    ----------
    node:
        The ``SequenceInstance`` slang AST dict.
    source_loc:
        Source location of the reference site (used in error messages).
    visited:
        Frozenset of sequence names currently being expanded.  When *seq_name*
        is already present, a circular reference has been detected.

    Raises
    ------
    SvaCompileError
        SVA-E003 on circular reference or when the declaration is not found.
    """
    seq_name = str(node.get("sequenceName", ""))
    if seq_name in visited:
        raise SvaCompileError(
            message=(
                f"SVA-E003: circular sequence reference: '{seq_name}' at "
                f"{source_loc}; recursive/mutually-recursive sequences are "
                "not synthesizable."
            )
        )
    decl_body = _DECLARATIONS.get(seq_name)
    if decl_body is None:
        raise SvaCompileError(
            message=(
                f"SVA-E003: named sequence/property '{seq_name}' referenced at "
                f"{source_loc} is not defined in the current compilation unit."
            )
        )
    new_visited = visited | frozenset({seq_name})
    return _dispatch_expr_to_ir(decl_body, new_visited)


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
