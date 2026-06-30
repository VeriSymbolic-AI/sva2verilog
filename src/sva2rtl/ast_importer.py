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

import logging
from typing import Any

from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    DisableIff,
    PropBoundedAlways,
    PropBoundedEventually,
    PropIfElse,
    PropImplication,
    PropNot,
    SeqAnd,
    SeqConcat,
    SeqFirstMatch,
    SeqGotoRep,
    SeqIntersect,
    SeqNonconsecRep,
    SeqOr,
    SeqRepetition,
    SeqThroughout,
    SeqWithin,
    SignalFunc,
    SourceLoc,
    SVANode,
)

_LOG = logging.getLogger(__name__)

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
    {"$rose", "$fell", "$stable", "$past", "$changed"}
)

# Phase 1 unsupported node kinds; value is a human-readable construct name.
UNSUPPORTED_KINDS_PHASE1: dict[str, str] = {"StrongWeakAssertionExpr": "strong()/weak()"}

# Node kinds that legitimately reduce to a boolean expression (BoolExpr leaf).
# This set is exactly the set of kinds ``expr_to_sv`` can handle without raising.
# When a dispatcher's default ``case _`` is reached with a kind NOT in this set,
# it means an unrecognized (almost always temporal/property) construct slipped
# through every explicit case — we MUST raise rather than silently flatten it to
# a boolean expression (the project's "never fail silently" charter, and the
# direct cause of the kind of latent semantic bug RISK-01 warns about).
_BOOLEAN_EXPR_KINDS: frozenset[str] = frozenset(
    {
        "NamedValue",
        "BinaryOp",
        "UnaryOp",
        "IntegerLiteral",
        "SequenceExpr",
        "Simple",
        "CallExpression",
        "Call",
        "BinaryPropertyExpr",
        "UnaryPropertyExpr",
    }
)

# Readable names for common temporal/property kinds that may reach a default
# dispatch case. Used only to make the error message helpful; any kind absent
# here is reported by its raw slang kind string.
_TEMPORAL_KIND_NAMES: dict[str, str] = {
    "NexttimePropertyExpr": "nexttime",
    "AlwaysPropertyExpr": "always",
    "SAlwaysPropertyExpr": "s_always",
    "EventuallyPropertyExpr": "eventually",
    "SEventuallyPropertyExpr": "s_eventually",
    "UntilPropertyExpr": "until",
    "SUntilPropertyExpr": "s_until",
    "UntilWithPropertyExpr": "until_with",
    "SUntilWithPropertyExpr": "s_until_with",
    "ImpliesPropertyExpr": "implies",
    "IffPropertyExpr": "iff",
    "AcceptOnPropertyExpr": "accept_on",
    "RejectOnPropertyExpr": "reject_on",
    "CaseAssertionExpr": "case",
    "AbortPropertyExpr": "abort",
    "DisableIffAssertionExpr": "disable iff (nested)",
}

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
    _DECLARATIONS.clear()
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

        case "Simple":
            # v11.0: unwrap Simple wrapper
            return expr_to_sv(node["expr"])

        case "CallExpression" | "Call":
            func_name = str(node.get("subroutineName", node.get("subroutine", "")))
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

    Supports both slang v7.0 (``source_file_start`` etc.) and v11.0
    (``source_file`` etc.) field names.  Falls back to ``"<unknown>"``
    / ``0`` when fields are absent.
    """
    file = str(
        node.get("source_file_start")
        or node.get("source_file")
        or "<unknown>"
    )
    line = int(
        node.get("source_line_start")
        or node.get("source_line")
        or 0
    )
    col = int(
        node.get("source_column_start")
        or node.get("source_column")
        or 0
    )
    return SourceLoc(file=file, line=line, col=col)


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


def _reject_non_boolean_kind(node: dict[str, Any], source_loc: SourceLoc) -> None:
    """Raise UnsupportedConstruct unless *node* is a boolean-expression kind.

    Called from the dispatchers' default ``case _`` BEFORE falling back to
    ``BoolExpr``.  Without this guard, an unrecognized temporal/property node
    whose ``kind`` is not in the small Phase-1 unsupported whitelist would be
    silently treated as a boolean expression, producing a compilable but
    semantically wrong monitor with no diagnostic — a silent-failure class bug
    that directly violates the "never fail silently" charter (and is exactly the
    failure mode RISK-01 cautions about).  Only kinds in ``_BOOLEAN_EXPR_KINDS``
    (the set ``expr_to_sv`` can faithfully render as a boolean) are allowed to
    fall through; everything else errors with a precise source location.
    """
    kind = node.get("kind", "")
    if kind not in _BOOLEAN_EXPR_KINDS:
        raise UnsupportedConstruct(
            message=(
                f"unsupported SVA construct '{kind}' — sva2rtl will not silently "
                "treat it as a boolean expression. See SUPPORTED_CONSTRUCTS.md for "
                "the list of supported operators."
            ),
            construct_name=_TEMPORAL_KIND_NAMES.get(kind, kind),
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
    pending_label: str | None = None
    for member in members:
        kind = member.get("kind", "")

        if kind == "ConcurrentAssertion":
            return _import_concurrent_assertion(member, label=None)

        # v7.0: Labeled block: { "kind": "Block", "block": "ADDRESS my_check", ... }
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

        # v11.0: StatementBlock carries the label before a ProceduralBlock
        if kind == "StatementBlock":
            label = _extract_label(member)
            if label is not None:
                pending_label = label

        # ProceduralBlock (slang v11.0): wraps ConcurrentAssertion inside
        # an always block at the module level.
        # v7.0: body → ConcurrentAssertion directly.
        # v11.0: body → Block → body → ConcurrentAssertion.
        if kind == "ProceduralBlock":
            proc_body = member.get("body", {})
            label = pending_label
            pending_label = None
            if proc_body.get("kind") == "ConcurrentAssertion":
                # v7.0: direct wrapping
                return _import_concurrent_assertion(proc_body, label=label)
            if proc_body.get("kind") == "Block":
                # v11.0: Block wrapping
                block_body = proc_body.get("body", {})
                if block_body.get("kind") == "ConcurrentAssertion":
                    return _import_concurrent_assertion(block_body, label=label)
                # Check statements
                stmts: list[dict[str, Any]] = proc_body.get("statements", [])
                for stmt in stmts:
                    if stmt.get("kind") == "ConcurrentAssertion":
                        return _import_concurrent_assertion(stmt, label=label)
                # Recurse into Block members if present
                sub = proc_body.get("members", [])
                result = _find_assertion_in_members(sub)
                if result is not None:
                    return result

    return None


def _find_all_assertions_in_members(
    members: list[dict[str, Any]],
) -> list[tuple[SVANode, ClockSpec, str, str | None]]:
    """Recursively search *members* and return ALL ConcurrentAssertions found."""
    results: list[tuple[SVANode, ClockSpec, str, str | None]] = []
    pending_label: str | None = None
    for member in members:
        kind = member.get("kind", "")

        if kind == "ConcurrentAssertion":
            results.append(_import_concurrent_assertion(member, label=None))

        # v7.0: Labeled block: { "kind": "Block", "block": "ADDRESS my_check", ... }
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

        # v11.0: StatementBlock carries the label before a ProceduralBlock
        if kind == "StatementBlock":
            label = _extract_label(member)
            if label is not None:
                pending_label = label

        # ProceduralBlock (slang v11.0): wraps ConcurrentAssertion inside
        # an always block at the module level.
        # v7.0: body → ConcurrentAssertion directly.
        # v11.0: body → Block → body → ConcurrentAssertion.
        if kind == "ProceduralBlock":
            proc_body = member.get("body", {})
            label = pending_label
            pending_label = None
            if proc_body.get("kind") == "ConcurrentAssertion":
                # v7.0: direct wrapping
                results.append(_import_concurrent_assertion(proc_body, label=label))
            elif proc_body.get("kind") == "Block":
                # v11.0: Block wrapping
                block_body = proc_body.get("body", {})
                if block_body.get("kind") == "ConcurrentAssertion":
                    results.append(_import_concurrent_assertion(block_body, label=label))
                # Check statements
                stmts: list[dict[str, Any]] = proc_body.get("statements", [])
                for stmt in stmts:
                    if stmt.get("kind") == "ConcurrentAssertion":
                        results.append(_import_concurrent_assertion(stmt, label=label))
                # Recurse into Block members if present
                sub = proc_body.get("members", [])
                results.extend(_find_all_assertions_in_members(sub))

    return results


def _extract_label(block: dict[str, Any]) -> str | None:
    """Extract label name from a Block/StatementBlock node.

    v7.0 Block: uses ``block`` field (format: ``"ADDRESS label_name"``).
    v11.0 StatementBlock: uses ``name`` field directly.
    """
    # v11.0: StatementBlock uses "name" for the label
    name = block.get("name", "")
    if block.get("kind") == "StatementBlock" and name:
        return name
    # v7.0: Block uses "block" field with "ADDRESS label_name" format
    raw = block.get("block", "")
    if raw:
        parts = str(raw).split(" ", 1)
        if len(parts) == 2:
            return parts[1]
    return None


def _import_concurrent_assertion(
    node: dict[str, Any],
    label: str | None,
) -> tuple[SVANode, ClockSpec, str, str | None]:
    """Convert a ConcurrentAssertion node to IR.

    Supports both slang v7.0 (``body`` → ``PropertySpec``) and v11.0
    (``propertySpec`` → ``Clocking``) AST formats.
    """
    source_loc = extract_source_loc(node)

    # ── Resolve the property container (v7.0 body vs v11.0 propertySpec) ────
    body = node.get("body") or node.get("propertySpec")
    if body is None:
        raise SvaCompileError(
            message=f"ConcurrentAssertion at {source_loc} has neither "
            f"'body' (v7.0) nor 'propertySpec' (v11.0) field"
        )
    body_kind = body.get("kind", "")

    # v7.0: body.kind == "PropertySpec", body.clocking
    # v11.0: body.kind == "Clocking", body.clocking (or body.clk)
    if body_kind in ("PropertySpec", "Clocking"):
        clock_spec = _extract_clock(body)
        expr_node: dict[str, Any] = body.get("expr", {})
    else:
        raise SvaCompileError(
            message=f"Expected PropertySpec or Clocking inside "
            f"ConcurrentAssertion, got '{body_kind}' at {source_loc}"
        )

    match expr_node.get("kind"):
        case "Simple":
            # v11.0: property is wrapped in Simple → unwrap
            inner = expr_node.get("expr", {})
            inner_kind = inner.get("kind", "")

            # v11.0: repetition (GoTo/Nonconsecutive) sits directly on
            # the Simple node, not on a nested SimpleAssertionExpr child.
            rep = expr_node.get("repetition", {})
            rep_kind = rep.get("kind", "")
            if rep_kind == "GoTo":
                rep_ir = _build_goto_rep(expr_node, source_loc)
                ir_node = rep_ir
                text = _reconstruct_rep_text(rep_ir)
            elif rep_kind == "Nonconsecutive":
                rep_ir = _build_nonconsec_rep(expr_node, source_loc)
                ir_node = rep_ir
                text = _reconstruct_rep_text(rep_ir)
            elif inner_kind in ("CallExpression", "Call"):
                # Signal functions can appear as "CallExpression" (v7.0)
                # or "Call" (v11.0) inside Simple wrappers
                func_name = str(inner.get("subroutineName", inner.get("subroutine", "")))
                if func_name in _SUPPORTED_SIGNAL_FUNCS:
                    sf_ir = _build_signal_func(inner, source_loc)
                    ir_node = sf_ir
                    text = _reconstruct_signal_func_text(sf_ir)
                else:
                    text = expr_to_sv(inner)
                    ir_node: SVANode = BoolExpr(text=text, source_loc=source_loc)
            elif inner_kind == "SimpleAssertionExpr":
                # v7.0 legacy: repetition inside SimpleAssertionExpr sub-node
                rep_kind2 = inner.get("repetition", {}).get("kind", "")
                if rep_kind2 in ("GoTo", "Nonconsecutive"):
                    if rep_kind2 == "GoTo":
                        rep_ir = _build_goto_rep(inner, source_loc)
                    else:
                        rep_ir = _build_nonconsec_rep(inner, source_loc)
                    ir_node = rep_ir
                    text = _reconstruct_rep_text(rep_ir)
                else:
                    text = expr_to_sv(inner)
                    ir_node: SVANode = BoolExpr(text=text, source_loc=source_loc)
            else:
                text = expr_to_sv(inner)
                ir_node: SVANode = BoolExpr(text=text, source_loc=source_loc)
        case "SequenceConcat":
            seq_ir = _build_seq_concat(expr_node, source_loc)
            ir_node = seq_ir
            text = _reconstruct_seq_text(seq_ir)
        case "SimpleAssertionExpr" if expr_node.get("repetition", {}).get("kind") == "Consecutive":
            rep_ir = _build_seq_repetition(expr_node, source_loc)
            ir_node = rep_ir
            text = _reconstruct_rep_text(rep_ir)
        case "SimpleAssertionExpr" if expr_node.get("repetition", {}).get("kind") == "GoTo":
            rep_ir = _build_goto_rep(expr_node, source_loc)
            ir_node = rep_ir
            text = _reconstruct_rep_text(rep_ir)
        case "SimpleAssertionExpr" if (
            expr_node.get("repetition", {}).get("kind") == "Nonconsecutive"
        ):
            rep_ir = _build_nonconsec_rep(expr_node, source_loc)
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
        case "BinaryPropertyExpr" if (
            expr_node.get("op") == "And" and not _is_boolean_binary(expr_node)
        ):
            ir_node, text = _build_binary_seq_op(expr_node, source_loc, "and")
        case "BinaryPropertyExpr" if (
            expr_node.get("op") == "Or" and not _is_boolean_binary(expr_node)
        ):
            ir_node, text = _build_binary_seq_op(expr_node, source_loc, "or")
        # ── slang v11.0 uses plain Binary/Unary (not *PropertyExpr) for
        #     simple sequence-level operators.  Children are wrapped in Simple.
        case "Binary" if expr_node.get("op") == "Or" and not _is_boolean_binary(expr_node):
            ir_node, text = _build_binary_seq_op(expr_node, source_loc, "or")
        case "Binary" if expr_node.get("op") == "And" and not _is_boolean_binary(expr_node):
            ir_node, text = _build_binary_seq_op(expr_node, source_loc, "and")
        case "Binary" if expr_node.get("op") == "Intersect":
            ir_node, text = _build_intersect(expr_node, source_loc)
        case "Binary" if expr_node.get("op") == "Within":
            ir_node, text = _build_within(expr_node, source_loc)
        case "Binary" if expr_node.get("op") == "Throughout":
            ir_node, text = _build_throughout(expr_node, source_loc)
        case "Unary" if expr_node.get("op") == "Not":
            ir_node, text = _build_prop_not(expr_node, source_loc)
        case "Unary" if expr_node.get("op") in ("SEventually", "Eventually"):
            ir_node, text = _build_bounded_eventually(expr_node, source_loc)
        case "Unary" if expr_node.get("op") in ("Always", "SAlways"):
            ir_node, text = _build_bounded_always(expr_node, source_loc)
        case "Conditional":
            ir_node, text = _build_prop_if_else(expr_node, source_loc)
        case "FirstMatch":
            # v11.0: first_match(seq) wraps a sequence
            inner_expr = expr_node.get("seq", expr_node.get("expr", {}))
            inner_ir = _dispatch_expr_to_ir(inner_expr)
            ir_node = SeqFirstMatch(body=inner_ir, source_loc=source_loc)
            inner_text = _reconstruct_node_text(inner_ir)
            text = f"first_match({inner_text})"
        case "UnaryPropertyExpr" if expr_node.get("op") == "Not":
            ir_node, text = _build_prop_not(expr_node, source_loc)
        case "IfElsePropertyExpr" | "ConditionalPropertyExpr":
            ir_node, text = _build_prop_if_else(expr_node, source_loc)
        case "IntersectPropertyExpr" | "Intersect":
            ir_node, text = _build_intersect(expr_node, source_loc)
        case "WithinPropertyExpr" | "Within":
            ir_node, text = _build_within(expr_node, source_loc)
        case "ThroughoutPropertyExpr" | "Throughout":
            ir_node, text = _build_throughout(expr_node, source_loc)
        case "SequenceInstance":
            expanded = _expand_named_sequence(expr_node, source_loc, frozenset())
            ir_node = expanded
            text = _reconstruct_node_text(expanded)
        case _:
            _check_unsupported(expr_node, extract_source_loc(expr_node))
            _reject_non_boolean_kind(expr_node, extract_source_loc(expr_node))
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
        case "Simple":
            # v11.0: unwrap Simple wrapper, recurse into inner expression
            return _dispatch_expr_to_ir(node.get("expr", {}), _visited)
        case "SequenceConcat":
            return _build_seq_concat(node, source_loc, _visited)
        case "SimpleAssertionExpr" if node.get("repetition", {}).get("kind") == "Consecutive":
            return _build_seq_repetition(node, source_loc, _visited)
        case "SimpleAssertionExpr" if node.get("repetition", {}).get("kind") == "GoTo":
            return _build_goto_rep(node, source_loc)
        case "SimpleAssertionExpr" if node.get("repetition", {}).get("kind") == "Nonconsecutive":
            return _build_nonconsec_rep(node, source_loc)
        case "CallExpression" | "Call" if (
            (node.get("subroutineName") or node.get("subroutine", ""))
            in _SUPPORTED_SIGNAL_FUNCS
        ):
            return _build_signal_func(node, source_loc)
        case "SequenceInstance":
            return _expand_named_sequence(node, source_loc, _visited)
        case "BinaryPropertyExpr" if node.get("op") == "And" and not _is_boolean_binary(node):
            ir_node, _text = _build_binary_seq_op(node, source_loc, "and")
            return ir_node
        case "BinaryPropertyExpr" if node.get("op") == "Or" and not _is_boolean_binary(node):
            ir_node, _text = _build_binary_seq_op(node, source_loc, "or")
            return ir_node
        case "UnaryPropertyExpr" if node.get("op") == "Not":
            ir_node, _text = _build_prop_not(node, source_loc)
            return ir_node
        case "Unary" if node.get("op") in ("SEventually", "Eventually"):
            ir_node, _text = _build_bounded_eventually(node, source_loc)
            return ir_node
        case "Unary" if node.get("op") in ("Always", "SAlways"):
            ir_node, _text = _build_bounded_always(node, source_loc)
            return ir_node
        case "IntersectPropertyExpr" | "Intersect":
            ir_node, _text = _build_intersect(node, source_loc)
            return ir_node
        case "WithinPropertyExpr" | "Within":
            ir_node, _text = _build_within(node, source_loc)
            return ir_node
        case "ThroughoutPropertyExpr" | "Throughout":
            ir_node, _text = _build_throughout(node, source_loc)
            return ir_node
        case _:
            _check_unsupported(node, source_loc)
            _reject_non_boolean_kind(node, source_loc)
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
    # HARDEN-03: reject invalid repetition bounds
    if rep_min > rep_max:
        raise SvaCompileError(
            message=(
                f"SVA-E002: invalid repetition range [*{rep_min}:{rep_max}] at "
                f"{source_loc} — min must be <= max"
            )
        )
    if rep_min == 0 and rep_max == 0:
        raise SvaCompileError(
            message=(
                f"SVA-E002: [*0] repetition (zero-length match) at {source_loc} "
                "is not supported"
            )
        )
    inner_node = node.get("expr", {})
    if not inner_node:
        raise SvaCompileError(
            message=(
                f"SVA-E002: repetition at {source_loc} has no expression. "
                "Consecutive repetition requires an expression, e.g. sig[*3]."
            )
        )
    inner = _dispatch_expr_to_ir(inner_node, _visited)
    return SeqRepetition(expr=inner, rep_min=rep_min, rep_max=rep_max, source_loc=source_loc)


def _build_goto_rep(
    node: dict[str, Any],
    source_loc: SourceLoc,
) -> SeqGotoRep:
    """Build a SeqGotoRep IR node for expr[->N] (GoTo repetition)."""
    rep = node.get("repetition", {})
    rep_min = int(rep.get("min", 1))
    rep_max = int(rep.get("max", 1))
    inner_node = node.get("expr", {})
    if not inner_node:
        raise SvaCompileError(
            message=f"Goto repetition [->N] requires an expression at {source_loc}"
        )
    inner = _dispatch_expr_to_ir(inner_node)
    return SeqGotoRep(expr=inner, rep_min=rep_min, rep_max=rep_max, source_loc=source_loc)


def _build_nonconsec_rep(
    node: dict[str, Any],
    source_loc: SourceLoc,
) -> SeqNonconsecRep:
    """Build a SeqNonconsecRep IR node for expr[=N] (Nonconsecutive repetition)."""
    rep = node.get("repetition", {})
    rep_min = int(rep.get("min", 1))
    rep_max = int(rep.get("max", 1))
    inner_node = node.get("expr", {})
    if not inner_node:
        raise SvaCompileError(
            message=f"Non-consecutive repetition [=N] requires an expression at {source_loc}"
        )
    inner = _dispatch_expr_to_ir(inner_node)
    return SeqNonconsecRep(expr=inner, rep_min=rep_min, rep_max=rep_max, source_loc=source_loc)


# ── Phase 3: Complex sequence operator builders (v1.3) ─────────────────────


def _build_binary_seq_op(
    node: dict[str, Any], source_loc: SourceLoc, op_name: str,
) -> tuple[SVANode, str]:
    """Build SeqAnd or SeqOr from a BinaryPropertyExpr with And/Or op."""
    left_node: dict[str, Any] = node.get("left", {})
    right_node: dict[str, Any] = node.get("right", {})
    left_ir = _dispatch_expr_to_ir(left_node)
    right_ir = _dispatch_expr_to_ir(right_node)
    left_text = _reconstruct_node_text(left_ir)
    right_text = _reconstruct_node_text(right_ir)
    text = f"({left_text} {op_name} {right_text})"
    if op_name == "and":
        ir_node = SeqAnd(left=left_ir, right=right_ir, source_loc=source_loc)
    else:
        ir_node = SeqOr(left=left_ir, right=right_ir, source_loc=source_loc)
    return ir_node, text


def _build_intersect(
    node: dict[str, Any], source_loc: SourceLoc,
) -> tuple[SVANode, str]:
    """Build SeqIntersect from IntersectPropertyExpr."""
    left_node = node.get("left", node.get("lhs", {}))
    right_node = node.get("right", node.get("rhs", {}))
    left_ir = _dispatch_expr_to_ir(left_node)
    right_ir = _dispatch_expr_to_ir(right_node)
    left_text = _reconstruct_node_text(left_ir)
    right_text = _reconstruct_node_text(right_ir)
    text = f"({left_text} intersect {right_text})"
    return SeqIntersect(left=left_ir, right=right_ir, source_loc=source_loc), text


def _build_within(
    node: dict[str, Any], source_loc: SourceLoc,
) -> tuple[SVANode, str]:
    """Build SeqWithin from WithinPropertyExpr."""
    inner_node = node.get("left", node.get("inner", node.get("lhs", {})))
    outer_node = node.get("right", node.get("outer", node.get("rhs", {})))
    inner_ir = _dispatch_expr_to_ir(inner_node)
    outer_ir = _dispatch_expr_to_ir(outer_node)
    inner_text = _reconstruct_node_text(inner_ir)
    outer_text = _reconstruct_node_text(outer_ir)
    text = f"({inner_text} within {outer_text})"
    return SeqWithin(inner=inner_ir, outer=outer_ir, source_loc=source_loc), text


def _build_throughout(
    node: dict[str, Any], source_loc: SourceLoc,
) -> tuple[SVANode, str]:
    """Build SeqThroughout from ThroughoutPropertyExpr."""
    cond_node = node.get("left", node.get("condition", node.get("lhs", {})))
    body_node = node.get("right", node.get("body", node.get("rhs", {})))
    cond_ir = _dispatch_expr_to_ir(cond_node)
    body_ir = _dispatch_expr_to_ir(body_node)
    cond_text = _reconstruct_node_text(cond_ir)
    body_text = _reconstruct_node_text(body_ir)
    text = f"({cond_text} throughout {body_text})"
    return SeqThroughout(condition=cond_ir, body=body_ir, source_loc=source_loc), text


def _build_bounded_eventually(
    node: dict[str, Any], source_loc: SourceLoc,
) -> tuple[SVANode, str]:
    """Build PropBoundedEventually from a v11 Unary SEventually/Eventually node.

    Bounded form requires ``min``/``max`` (the ``[lo:hi]`` range). Unbounded forms
    (no range) and non-boolean operands are rejected — honesty-first: unbounded
    liveness is not synthesizable on finite state, and sequence operands need the
    v1.5 NFA engine. See SUPPORTED_CONSTRUCTS.md.
    """
    op = node.get("op", "")
    strong = op == "SEventually"
    kw = "s_eventually" if strong else "eventually"
    if "min" not in node or "max" not in node:
        raise UnsupportedConstruct(
            message=(
                f"unbounded '{kw}' is not synthesizable on finite state — use the "
                f"bounded form '{kw} [m:n] p' with an explicit cycle range."
            ),
            construct_name=f"unbounded {kw}",
            source_loc=source_loc,
        )
    lo = int(node["min"])
    hi = int(node["max"])
    if lo < 0 or hi < lo:
        raise SvaCompileError(
            message=(
                f"invalid bounded-liveness range [{lo}:{hi}] for '{kw}' at "
                f"{source_loc}: require 0 <= m <= n."
            )
        )
    body_ir = _dispatch_expr_to_ir(node.get("expr", {}))
    if not isinstance(body_ir, BoolExpr):
        raise UnsupportedConstruct(
            message=(
                f"'{kw} [m:n]' currently supports only a boolean-expression "
                "operand; sequence/property operands are deferred to the v1.5 NFA "
                "engine."
            ),
            construct_name=f"{kw} with non-boolean operand",
            source_loc=source_loc,
        )
    body_text = _reconstruct_node_text(body_ir)
    text = f"{kw} [{lo}:{hi}] ({body_text})"
    return (
        PropBoundedEventually(
            body=body_ir, lo=lo, hi=hi, strong=strong, source_loc=source_loc
        ),
        text,
    )


def _build_bounded_always(
    node: dict[str, Any], source_loc: SourceLoc,
) -> tuple[SVANode, str]:
    """Build PropBoundedAlways from a v11 Unary Always/SAlways node.

    Bounded form requires ``min``/``max`` (the ``[lo:hi]`` range). Unbounded forms
    (no range) and non-boolean operands are rejected — honesty-first: unbounded
    ``always`` is not synthesizable on finite state, and sequence operands need
    the v1.5 NFA engine. See SUPPORTED_CONSTRUCTS.md.
    """
    op = node.get("op", "")
    strong = op == "SAlways"
    kw = "s_always" if strong else "always"
    if "min" not in node or "max" not in node:
        raise UnsupportedConstruct(
            message=(
                f"unbounded '{kw}' is not synthesizable on finite state — use the "
                f"bounded form '{kw} [m:n] p' with an explicit cycle range."
            ),
            construct_name=f"unbounded {kw}",
            source_loc=source_loc,
        )
    lo = int(node["min"])
    hi = int(node["max"])
    if lo < 0 or hi < lo:
        raise SvaCompileError(
            message=(
                f"invalid bounded-liveness range [{lo}:{hi}] for '{kw}' at "
                f"{source_loc}: require 0 <= m <= n."
            )
        )
    body_ir = _dispatch_expr_to_ir(node.get("expr", {}))
    if not isinstance(body_ir, BoolExpr):
        raise UnsupportedConstruct(
            message=(
                f"'{kw} [m:n]' currently supports only a boolean-expression "
                "operand; sequence/property operands are deferred to the v1.5 NFA "
                "engine."
            ),
            construct_name=f"{kw} with non-boolean operand",
            source_loc=source_loc,
        )
    body_text = _reconstruct_node_text(body_ir)
    text = f"{kw} [{lo}:{hi}] ({body_text})"
    return (
        PropBoundedAlways(
            body=body_ir, lo=lo, hi=hi, strong=strong, source_loc=source_loc
        ),
        text,
    )


def _build_prop_not(
    node: dict[str, Any], source_loc: SourceLoc,
) -> tuple[SVANode, str]:
    """Build PropNot from UnaryPropertyExpr with Not op."""
    inner_node = node.get("operand", node.get("expr", {}))
    inner_ir = _dispatch_expr_to_ir(inner_node)
    inner_text = _reconstruct_node_text(inner_ir)
    text = f"not ({inner_text})"
    return PropNot(body=inner_ir, source_loc=source_loc), text


def _build_prop_if_else(
    node: dict[str, Any], source_loc: SourceLoc,
) -> tuple[SVANode, str]:
    """Build PropIfElse from IfElsePropertyExpr or v11 Conditional node."""
    cond_node = node.get("condition", node.get("cond", {}))
    true_node = node.get("ifTrue", node.get("trueBranch", node.get("if", {})))
    false_node = node.get("ifFalse", node.get("falseBranch", node.get("else", None)))
    cond_ir = _dispatch_expr_to_ir(cond_node)
    true_ir = _dispatch_expr_to_ir(true_node)
    false_ir = _dispatch_expr_to_ir(false_node) if false_node else None
    cond_text = _reconstruct_node_text(cond_ir)
    true_text = _reconstruct_node_text(true_ir)
    if false_ir:
        false_text = _reconstruct_node_text(false_ir)
        text = f"if ({cond_text}) {true_text} else {false_text}"
    else:
        text = f"if ({cond_text}) {true_text}"
    return (
        PropIfElse(
            condition=cond_ir,
            true_branch=true_ir,
            false_branch=false_ir,
            source_loc=source_loc,
        ),
        text,
    )


def _is_boolean_binary(node: dict[str, Any]) -> bool:
    """Check if a BinaryPropertyExpr And/Or is boolean-level (has SequenceExpr wrapper).

    In slang JSON, boolean-level And/Or operands are always wrapped in
    SequenceExpr.  Sequence-level And/Or operands are direct sequence nodes
    (SequenceConcat, Simple, etc.) without the SequenceExpr indirection.
    """
    left: dict[str, Any] = node.get("left", {})
    right: dict[str, Any] = node.get("right", {})
    lk = left.get("kind", "")
    rk = right.get("kind", "")
    # Either operand being SequenceExpr indicates boolean-level
    if lk == "SequenceExpr" or rk == "SequenceExpr":
        return True
    # Either operand being NamedValue means boolean-level
    if lk == "NamedValue" or rk == "NamedValue":
        return True
    # Recursively check nested BinaryPropertyExpr
    if lk == "BinaryPropertyExpr" and _is_boolean_binary(left):
        return True
    if rk == "BinaryPropertyExpr" and _is_boolean_binary(right):
        return True
    return False


def _reconstruct_rep_text(node: SeqRepetition | SeqGotoRep | SeqNonconsecRep) -> str:
    """Reconstruct an SVA text representation from a SeqRepetition IR node."""
    if isinstance(node.expr, BoolExpr):
        inner_text = node.expr.text
    elif isinstance(node.expr, SeqConcat):
        inner_text = _reconstruct_seq_text(node.expr)
    else:
        inner_text = "<expr>"
    # Determine bracket syntax based on node type
    if isinstance(node, SeqGotoRep):
        bracket = "[->"
    elif isinstance(node, SeqNonconsecRep):
        bracket = "[="
    else:
        bracket = "[*"
    if node.rep_min == node.rep_max:
        return f"{inner_text} {bracket}{node.rep_min}]"
    return f"{inner_text} {bracket}{node.rep_min}:{node.rep_max}]"


def _build_signal_func(node: dict[str, Any], source_loc: SourceLoc) -> SignalFunc:
    """Build a SignalFunc IR node from a slang CallExpression JSON node.

    Supports ``$rose``, ``$fell``, ``$stable``, ``$past``.
    For ``$past(sig, N)``, N must be an ``IntegerLiteral``; otherwise raises
    ``UnsupportedConstruct`` (non-compile-time depth is not synthesizable).

    Raises ``SvaCompileError`` when the first argument signal cannot be extracted.
    """
    raw_name: str = str(node.get("subroutineName", node.get("subroutine", "")))
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

    # NYQ-22: warn when $past depth exceeds practical hardware bound
    if func_name == "past" and depth > 100:
        _LOG.warning(
            "$past(%s, %s) at %s — depth > 100 may exceed practical "
            "hardware depth; consider reducing",
            signal,
            depth,
            source_loc,
        )

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
    if isinstance(node, (SeqGotoRep, SeqNonconsecRep)):
        return _reconstruct_rep_text(node)
    if isinstance(node, SeqFirstMatch):
        return f"first_match({_reconstruct_node_text(node.body)})"
    if isinstance(node, SignalFunc):
        return _reconstruct_signal_func_text(node)
    if isinstance(node, PropImplication):
        return _reconstruct_impl_text(node)
    if isinstance(node, SeqAnd):
        return f"({_reconstruct_node_text(node.left)} and {_reconstruct_node_text(node.right)})"
    if isinstance(node, SeqOr):
        return f"({_reconstruct_node_text(node.left)} or {_reconstruct_node_text(node.right)})"
    if isinstance(node, SeqIntersect):
        return (
            f"({_reconstruct_node_text(node.left)} intersect "
            f"{_reconstruct_node_text(node.right)})"
        )
    if isinstance(node, SeqWithin):
        return f"({_reconstruct_node_text(node.inner)} within {_reconstruct_node_text(node.outer)})"
    if isinstance(node, SeqThroughout):
        return (
            f"({_reconstruct_node_text(node.condition)} throughout "
            f"{_reconstruct_node_text(node.body)})"
        )
    if isinstance(node, PropNot):
        return f"not ({_reconstruct_node_text(node.body)})"
    if isinstance(node, PropIfElse):
        cond = _reconstruct_node_text(node.condition)
        true_t = _reconstruct_node_text(node.true_branch)
        if node.false_branch is not None:
            false_t = _reconstruct_node_text(node.false_branch)
            return f"if ({cond}) {true_t} else {false_t}"
        return f"if ({cond}) {true_t}"
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

    Supports both slang v7.0 (TimingControl wrapper) and v11.0 (SignalEvent
    directly).  Raises SvaCompileError when the clocking annotation is absent or
    malformed.
    """
    clocking = prop_spec.get("clocking")
    if clocking is None:
        source_loc = extract_source_loc(prop_spec)
        raise SvaCompileError(
            message=(
                f"Property at {source_loc} has no clock annotation. "
                "Use @(posedge clk) to specify a clock event."
            )
        )

    # v7.0: clocking.kind == "TimingControl" → clocking.event is SignalEvent
    # v11.0: clocking.kind == "SignalEvent" directly
    if clocking.get("kind") == "SignalEvent":
        event = clocking
    else:
        event = clocking.get("event", {})

    if event.get("kind") != "SignalEvent":
        source_loc = extract_source_loc(clocking)
        raise SvaCompileError(
            message=f"Expected SignalEvent in clocking at {source_loc}, "
            f"got '{event.get('kind', '<missing>')}'"
        )

    edge_raw = event.get("edge")
    if edge_raw is None:
        source_loc = extract_source_loc(event)
        raise SvaCompileError(
            message=(
                f"Clock event at {source_loc} has no edge field. "
                "Use @(posedge clk) or @(negedge clk)."
            )
        )
    edge = str(edge_raw).lower()
    if edge not in ("posedge", "negedge"):
        source_loc = extract_source_loc(event)
        raise SvaCompileError(
            message=(
                f"Unsupported clock edge '{edge}' at {source_loc}. "
                "Expected 'PosEdge' (posedge) or 'NegEdge' (negedge)."
            )
        )
    clk_expr: dict[str, Any] = event.get("expr", {})
    signal = clk_expr.get("symbol", " clk").split(" ", 1)[-1]
    clock_source_loc = extract_source_loc(event)

    return ClockSpec(edge=edge, signal=signal, source_loc=clock_source_loc)
