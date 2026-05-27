"""Composer: transforms SVA IR nodes into CheckerNode instances ready for the emitter.

For Phase 1, only ``BoolExpr`` nodes are supported.  All other node kinds raise
``UnsupportedConstruct`` with a precise source location.

Design decisions:
- ``module_name_from_label`` centralises the naming convention (OUT-07).
- ``extract_signals`` is regex-based for Phase 1 simplicity; it excludes the full
  set of SV reserved words so that operator tokens embedded in expression text
  cannot masquerade as signal names.
- The ``params`` dict is typed ``dict[str, str]`` to match ``CheckerNode``; all
  values that are rendered verbatim by the Jinja2 template are plain strings.
"""

from __future__ import annotations

import hashlib
import math
import re

from sva2rtl import __version__
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockSpec,
    DisableIff,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SignalFunc,
    SourceLoc,
    SVANode,
)

# ── SV keyword table ──────────────────────────────────────────────────────

# Complete IEEE 1800-2017 reserved word list.  Signal names extracted from
# boolean expression text are filtered against this set so that no keyword
# leaks into the generated port list.
_SV_KEYWORDS: frozenset[str] = frozenset(
    {
        "accept_on",
        "alias",
        "always",
        "and",
        "assert",
        "assign",
        "assume",
        "automatic",
        "before",
        "begin",
        "bind",
        "bins",
        "binsof",
        "bit",
        "break",
        "buf",
        "bufif0",
        "bufif1",
        "byte",
        "case",
        "casex",
        "casez",
        "cell",
        "chandle",
        "checker",
        "class",
        "clocking",
        "cmos",
        "config",
        "const",
        "constraint",
        "context",
        "continue",
        "cover",
        "covergroup",
        "coverpoint",
        "cross",
        "deassign",
        "default",
        "defparam",
        "design",
        "disable",
        "dist",
        "do",
        "edge",
        "else",
        "end",
        "endcase",
        "endchecker",
        "endclass",
        "endclocking",
        "endconfig",
        "endfunction",
        "endgenerate",
        "endgroup",
        "endinterface",
        "endmodule",
        "endpackage",
        "endprimitive",
        "endprogram",
        "endproperty",
        "endsequence",
        "endspecify",
        "endtable",
        "endtask",
        "enum",
        "event",
        "eventually",
        "expect",
        "export",
        "extends",
        "extern",
        "final",
        "first_match",
        "for",
        "force",
        "foreach",
        "forever",
        "fork",
        "forkjoin",
        "function",
        "generate",
        "genvar",
        "global",
        "highz0",
        "highz1",
        "if",
        "iff",
        "ifnone",
        "ignore_bins",
        "illegal_bins",
        "implements",
        "implies",
        "import",
        "incdir",
        "include",
        "initial",
        "inout",
        "input",
        "inside",
        "instance",
        "int",
        "integer",
        "interconnect",
        "interface",
        "intersect",
        "join",
        "join_any",
        "join_none",
        "large",
        "let",
        "liblist",
        "library",
        "local",
        "localparam",
        "logic",
        "longint",
        "macromodule",
        "matches",
        "medium",
        "modport",
        "module",
        "nand",
        "negedge",
        "nettype",
        "new",
        "nexttime",
        "nmos",
        "nor",
        "noshowcancelled",
        "not",
        "notif0",
        "notif1",
        "null",
        "or",
        "output",
        "package",
        "packed",
        "parameter",
        "pmos",
        "posedge",
        "primitive",
        "priority",
        "program",
        "property",
        "protected",
        "pull0",
        "pull1",
        "pulldown",
        "pullup",
        "pulsestyle_ondetect",
        "pulsestyle_onevent",
        "pure",
        "rand",
        "randc",
        "randcase",
        "randsequence",
        "rcmos",
        "real",
        "realtime",
        "ref",
        "reg",
        "reject_on",
        "release",
        "repeat",
        "restrict",
        "return",
        "rnmos",
        "rpmos",
        "rtran",
        "rtranif0",
        "rtranif1",
        "s_always",
        "s_eventually",
        "s_nexttime",
        "s_until",
        "s_until_with",
        "scalared",
        "sequence",
        "shortint",
        "shortreal",
        "showcancelled",
        "signed",
        "small",
        "soft",
        "solve",
        "specify",
        "specparam",
        "static",
        "string",
        "strong",
        "strong0",
        "strong1",
        "struct",
        "super",
        "supply0",
        "supply1",
        "sync_accept_on",
        "sync_reject_on",
        "table",
        "tagged",
        "task",
        "this",
        "throughout",
        "time",
        "timeprecision",
        "timeunit",
        "tran",
        "tranif0",
        "tranif1",
        "tri",
        "tri0",
        "tri1",
        "triand",
        "trior",
        "trireg",
        "type",
        "typedef",
        "union",
        "unique",
        "unique0",
        "unsigned",
        "until",
        "until_with",
        "untyped",
        "use",
        "uwire",
        "var",
        "vectored",
        "virtual",
        "void",
        "wait",
        "wait_order",
        "wand",
        "weak",
        "weak0",
        "weak1",
        "while",
        "wildcard",
        "wire",
        "with",
        "within",
        "wor",
        "xnor",
        "xor",
    }
)

# Matches any SV identifier token within an expression string.
_IDENT_RE: re.Pattern[str] = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")


# ── Public API ────────────────────────────────────────────────────────────


def module_name_from_label(label: str | None, property_text: str) -> str:
    """Derive a valid SV module name from an assertion label or property text.

    Parameters
    ----------
    label:
        The assertion label string (e.g. ``"my_check"`` from
        ``my_check: assert property (...)``), or ``None`` when the assertion has
        no label.
    property_text:
        The reconstructed SV expression text.  Used to compute a deterministic
        8-character SHA-256 hex digest when ``label`` is ``None``.

    Returns
    -------
    str
        ``"sva_{safe_label}"`` when a label is provided (non-alphanumeric /
        non-underscore characters replaced with ``_``), or
        ``"sva_prop_{hash8}"`` otherwise.
    """
    if label is not None:
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", label)
        return f"sva_{safe}"
    h = hashlib.sha256(property_text.encode()).hexdigest()[:8]
    return f"sva_prop_{h}"


def extract_signals(expr_text: str) -> tuple[tuple[str, str], ...]:
    """Extract unique signal names from a boolean expression text string.

    Uses a word-boundary regex to find all identifiers in *expr_text*, then
    removes SystemVerilog reserved words.  Preserves first-appearance order.
    For Phase 1, ``port_name == signal_name`` (1:1 mapping — no renaming).

    Parameters
    ----------
    expr_text:
        The SV boolean expression string, e.g. ``"(a && b)"``.

    Returns
    -------
    tuple[tuple[str, str], ...]
        Deduplicated ``(port_name, signal_name)`` pairs in first-appearance
        order.
    """
    seen: dict[str, None] = {}  # insertion-order dict used as an ordered set
    for m in _IDENT_RE.finditer(expr_text):
        name = m.group(1)
        if name not in _SV_KEYWORDS:
            seen[name] = None
    return tuple((name, name) for name in seen)


def compose(
    node: SVANode,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Transform a top-level SVA IR node into an emittable ``CheckerNode``.

    Supports ``BoolExpr`` (Phase 1) and ``SeqConcat`` (Phase 2).  All other
    node kinds raise ``UnsupportedConstruct`` with a precise source location.

    Parameters
    ----------
    node:
        The SVA IR node to compile.
    clock:
        Clock event extracted from the property's ``@(posedge ...)`` annotation.
    label:
        Assertion label string or ``None``.
    original_text:
        The reconstructed SV expression text.  Embedded verbatim in the
        generated module header comment (requirement OUT-08).
    cse_origin:
        Optional named-sequence label for CSE provenance tagging.  Set to the
        sequence declaration name when the node was expanded from a named
        sequence reference.  Default ``None``.

    Returns
    -------
    CheckerNode
        Fully populated ``CheckerNode`` ready for the Jinja2 emitter.

    Raises
    ------
    UnsupportedConstruct
        When *node* is an unsupported IR type (e.g. ``PropImplication``).
    """
    match node:
        case BoolExpr():
            return _compose_bool_expr(node, clock, label, original_text, cse_origin)
        case SeqConcat():
            return _compose_seq_concat(node, clock, label, original_text, cse_origin)
        case SeqRepetition():
            return _compose_repetition(node, clock, label, original_text, cse_origin)
        case SignalFunc():
            return _compose_signal_func(node, clock, label, original_text, cse_origin)
        case PropImplication():
            return _compose_implication(node, clock, label, original_text, cse_origin)
        case DisableIff():
            return _compose_disable_iff(node, clock, label, original_text, cse_origin)
        case _:
            raise UnsupportedConstruct(
                message=(
                    f"No composer for IR node '{type(node).__name__}'. "
                    "Use a future version of sva2rtl for this construct."
                ),
                construct_name=type(node).__name__,
                source_loc=node.source_loc,
            )


# ── Private helpers ────────────────────────────────────────────────────────


def _compose_bool_expr(
    node: BoolExpr,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a leaf CheckerNode for a BoolExpr."""
    module_name = module_name_from_label(label, original_text)
    observed = extract_signals(node.text)

    params: dict[str, str] = {
        "module_name": module_name,
        "bool_expr": node.text,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name="bool_expr",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )


def _compose_seq_concat(
    node: SeqConcat,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a hierarchical CheckerNode tree for a SeqConcat.

    Structure: seq_concat_top wrapper → interleaved (bool_expr, delay) children
    following token-passing wiring: A.pass → delay.start → B.start.
    """
    module_name = module_name_from_label(label, original_text)
    # Build a base name (without leading "sva_") for child sub-labels so that
    # module_name_from_label doesn't double-prefix with "sva_sva_".
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    children: list[CheckerNode] = []

    for i, elem in enumerate(node.elements):
        # Use a hash-based sub-label so each child gets a unique module name
        child_label = f"{base}_e{i}"
        elem_checker = compose(elem, clock, child_label, original_text)
        children.append(elem_checker)

        if i < len(node.delays):
            delay_min, delay_max = node.delays[i]
            delay_checker = _make_delay_node(delay_min, delay_max, clock, node.source_loc)
            children.append(delay_checker)

    all_signals = _collect_signals(children)

    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name="seq_concat_top",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=tuple(children),
        cse_origin=cse_origin,
    )


def _compose_repetition(
    node: SeqRepetition,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a leaf CheckerNode for a consecutive repetition expr[*M:N]."""
    module_name = module_name_from_label(label, original_text)
    cnt_width = max(1, math.ceil(math.log2(node.rep_max + 1))) if node.rep_max > 0 else 1

    if isinstance(node.expr, BoolExpr):
        observed = extract_signals(node.expr.text)
        signal_expr = node.expr.text
    else:
        observed = ()
        signal_expr = "<expr>"

    params: dict[str, str] = {
        "module_name": module_name,
        "rep_min": str(node.rep_min),
        "rep_max": str(node.rep_max),
        "cnt_width": str(cnt_width),
        "signal_expr": signal_expr,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name="rep_consecutive",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )


def _compose_signal_func(
    node: SignalFunc,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a leaf CheckerNode for a signal function ($rose/$fell/$stable/$past).

    Each function maps directly to a template of the same name:
      rose -> rose.sv.j2, fell -> fell.sv.j2, etc.
    """
    module_name = module_name_from_label(label, original_text)
    # Single observed signal: (port_name, dut_signal_name)
    observed: tuple[tuple[str, str], ...] = ((node.signal, node.signal),)

    params: dict[str, str] = {
        "module_name": module_name,
        "signal_name": node.signal,
        "depth": str(node.depth),
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name=node.func_name,  # "rose", "fell", "stable", or "past"
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )


def _make_delay_node(    delay_min: int,
    delay_max: int,
    clock: ClockSpec,
    source_loc: SourceLoc,
) -> CheckerNode:
    """Build a leaf CheckerNode for a counter-encoded delay module."""
    cnt_width = max(1, math.ceil(math.log2(delay_max + 1))) if delay_max > 0 else 1
    mod_name = f"sva_delay_{delay_min}_{delay_max}"

    if delay_min == delay_max:
        orig = f"##{delay_min}"
    else:
        orig = f"##[{delay_min}:{delay_max}]"

    params: dict[str, str] = {
        "module_name": mod_name,
        "delay_min": str(delay_min),
        "delay_max": str(delay_max),
        "cnt_width": str(cnt_width),
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(source_loc),
        "sva2rtl_version": __version__,
        "original_text": orig,
    }

    return CheckerNode(
        template_name="concat_delay",
        module_name=mod_name,
        params=params,
        observed_signals=(),
        source_loc=source_loc,
        children=(),
    )


def _compute_bv_width(consequent: SVANode) -> int:
    """Compute BV_WIDTH = max(max_delay_in_consequent + 1, 1).

    max_delay = sum of all delay_max values in the consequent chain.
    Each bit position in the shift register represents one cycle of thread age,
    so we need enough positions for the longest possible consequent evaluation
    window.
    """
    match consequent:
        case BoolExpr():
            return 1  # single-cycle: max_delay=0, width=1
        case SeqConcat():
            max_delay = sum(d_max for _, d_max in consequent.delays)
            return max(max_delay + 1, 1)
        case _:
            return 8  # safe default for unknown structures


def _compose_implication(
    node: PropImplication,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a hierarchical CheckerNode for a PropImplication (|-> or |=>)."""
    module_name = module_name_from_label(label, original_text)
    template = "overlap_bitvec" if node.overlapping else "nonoverlap"

    # Give each child a unique sub-label so their module names never collide
    # with the parent wrapper (or each other) when label is None and both
    # antecedent and consequent hash the same original_text.  Same pattern as
    # _compose_seq_concat uses for _e{i} children.
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    ant_checker = compose(node.antecedent, clock, f"{base}_ant", original_text)
    con_checker = compose(node.consequent, clock, f"{base}_con", original_text)

    bv_width = _compute_bv_width(node.consequent)
    all_signals = _collect_signals([ant_checker, con_checker])

    params: dict[str, str] = {
        "module_name": module_name,
        "bv_width": str(bv_width),
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name=template,
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(ant_checker, con_checker),
        cse_origin=cse_origin,
    )


def _collect_signals(
    children: list[CheckerNode],
) -> tuple[tuple[str, str], ...]:
    """Collect all unique observed signals from a list of child CheckerNodes."""
    seen: dict[str, None] = {}
    for child in children:
        for port_name, sig_name in child.observed_signals:
            if port_name not in seen:
                seen[port_name] = None
    return tuple((name, name) for name in seen)


def _compose_disable_iff(
    node: DisableIff,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a wrapper CheckerNode for ``disable iff (cond) body``.

    The wrapper evaluates the disable condition combinationally and OR-combines
    it with the incoming ``disable_i``, feeding the result into the body
    checker's ``disable_i`` port.  All outputs are passed through directly
    from the body checker.

    Parameters
    ----------
    node:
        The ``DisableIff`` IR node.
    clock:
        Clock spec for the child instantiation.
    label:
        Assertion label or ``None`` for hash-based naming.
    original_text:
        Reconstructed SVA expression text for the header comment.
    cse_origin:
        Optional named-sequence label for CSE provenance tagging.
    """
    module_name = module_name_from_label(label, original_text)
    # Build a unique sub-label for the body so it never collides with the
    # disable_iff_top wrapper when label is None (both would otherwise hash
    # the same original_text → same module_name).
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    body_label = f"{base}_body"

    # Compose the body (wrapped property / sequence)
    body_checker = compose(node.body, clock, body_label, original_text)

    # Extract the condition expression text from the condition node
    if isinstance(node.condition, BoolExpr):
        cond_expr = node.condition.text
    else:
        cond_expr = "<cond>"

    # Collect signals: condition signals + body signals (no duplicates)
    # Exclude rst_n and clock_signal — these are always hardcoded ports in every
    # generated module and must not appear again in the observed_signals loop.
    _reserved_ports = {"rst_n", clock.signal}
    cond_signals = tuple(
        (p, s) for p, s in extract_signals(cond_expr) if p not in _reserved_ports
    )
    cond_seen = {p for p, _ in cond_signals}
    body_extra = tuple(
        (p, s) for p, s in body_checker.observed_signals
        if p not in cond_seen and p not in _reserved_ports
    )
    all_signals = cond_signals + body_extra

    params: dict[str, str] = {
        "module_name": module_name,
        "cond_expr": cond_expr,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name="disable_iff_top",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(body_checker,),
        cse_origin=cse_origin,
    )
