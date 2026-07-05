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
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockedSeq,
    ClockSpec,
    DisableIff,
    PropBoundedAlways,
    PropBoundedEventually,
    PropIfElse,
    PropImplication,
    PropNot,
    PropUntil,
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


# ── Structural hashing (Phase 4) ─────────────────────────────────────────

# Params excluded from structural hash — positional/presentation metadata
# that should NOT affect whether two CheckerNodes are structurally identical.
_VOLATILE_PARAMS: frozenset[str] = frozenset(
    {"module_name", "source_loc", "sva2rtl_version", "original_text"}
)


def structural_hash(node: CheckerNode) -> str:
    """Compute a deterministic structural hash for a CheckerNode.

    Uses SHA-256 (via hashlib) to avoid PYTHONHASHSEED randomization.
    Returns an 8-character hex digest for compact display.

    The hash reflects the *semantic structure* of the node: template type,
    non-volatile params, and all children (recursively).  Two nodes that
    produce identical hardware — regardless of module name or source location —
    will produce the same hash.

    Parameters
    ----------
    node
        The CheckerNode to hash.

    Returns
    -------
    str
        8-character lowercase hex string (first 32 bits of SHA-256).
    """
    h = hashlib.sha256()
    h.update(node.template_name.encode())
    for k, v in sorted(node.params.items()):
        if k not in _VOLATILE_PARAMS:
            h.update(f"{k}={v}".encode())
    for child in node.children:
        h.update(structural_hash(child).encode())
    return h.hexdigest()[:8]


def compute_hash_map(root: CheckerNode) -> dict[str, str]:
    """Walk a CheckerNode tree and return {module_name: structural_hash} for all nodes.

    Parameters
    ----------
    root
        Root of the CheckerNode tree.

    Returns
    -------
    dict[str, str]
        Mapping from module_name to its 8-char structural hash, for the root
        and all descendants.
    """
    result: dict[str, str] = {}
    _collect_hashes(root, result)
    return result


def _collect_hashes(node: CheckerNode, out: dict[str, str]) -> None:
    """Recursive helper for compute_hash_map."""
    out[node.module_name] = structural_hash(node)
    for child in node.children:
        _collect_hashes(child, out)


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
        case SeqFirstMatch():
            return _compose_first_match(node, clock, label, original_text, cse_origin)
        case SeqGotoRep():
            return _compose_goto_rep(node, clock, label, original_text, cse_origin)
        case SeqNonconsecRep():
            return _compose_nonconsec_rep(node, clock, label, original_text, cse_origin)
        case SeqOr():
            return _compose_seq_or(node, clock, label, original_text, cse_origin)
        case SeqAnd():
            return _compose_seq_and(node, clock, label, original_text, cse_origin)
        case SeqIntersect():
            return _compose_intersect(node, clock, label, original_text, cse_origin)
        case SeqWithin():
            return _compose_within(node, clock, label, original_text, cse_origin)
        case SeqThroughout():
            return _compose_throughout(node, clock, label, original_text, cse_origin)
        case PropNot():
            return _compose_prop_not(node, clock, label, original_text, cse_origin)
        case PropIfElse():
            return _compose_prop_if_else(node, clock, label, original_text, cse_origin)
        case PropBoundedEventually():
            return _compose_bounded_eventually(node, clock, label, original_text, cse_origin)
        case PropBoundedAlways():
            return _compose_bounded_always(node, clock, label, original_text, cse_origin)
        case PropUntil():
            return _compose_until(node, clock, label, original_text, cse_origin)
        case ClockedSeq():
            return _compose_clocked_seq(node, clock, label, original_text, cse_origin)
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

    Single-clock (no ClockedSeq elements): delegates to
    ``_compose_seq_concat_sc`` (byte-identical to pre-v1.4.1).

    Multi-clock (has ClockedSeq elements): delegates to
    ``_compose_seq_concat_mc`` — per-domain sub-checkers connected by 2-DFF
    synchronizers.
    """
    has_mc = any(isinstance(e, ClockedSeq) for e in node.elements)
    if has_mc:
        return _compose_seq_concat_mc(node, clock, label, original_text, cse_origin)
    return _compose_seq_concat_sc(node, clock, label, original_text, cse_origin)


def _compose_seq_concat_sc(
    node: SeqConcat,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a single-clock SeqConcat hierarchy (byte-identical to pre-v1.4.1).

    Structure: seq_concat_top wrapper → interleaved (bool_expr, delay) children
    following token-passing wiring: A.pass → delay.start → B.start.
    """
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    children: list[CheckerNode] = []

    for i, elem in enumerate(node.elements):
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


def _compose_seq_concat_mc(
    node: SeqConcat,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a multi-clock SeqConcat: per-domain sub-checkers + 2-DFF syncs.

    Each ClockedSeq element marks a clock-domain switch. Its body is compiled as
    a single-clock sub-checker on its OWN clock (compiling through
    ``_compose_clocked_seq``), and a ``sync_2dff`` CheckerNode is inserted at
    the boundary to carry the token (match → start) across domains.
    """
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    children: list[CheckerNode] = []
    # Collect unique clock domains for the top module
    clock_signals: list[str] = [clock.signal]
    sync_index = 0

    for i, elem in enumerate(node.elements):
        child_label = f"{base}_e{i}"
        if isinstance(elem, ClockedSeq):
            # Cross-domain boundary: compile the ClockedSeq body on its own
            # clock (which compose dispatches via the ClockedSeq arm), then
            # insert a 2-DFF synchronizer to connect the previous domain's
            # output to this domain's start.
            sync_name = f"{module_name}_sync_{sync_index}"
            src_clk, dst_clk = clock_signals[-1], elem.clock.signal
            if dst_clk not in clock_signals:
                clock_signals.append(dst_clk)

            sync = _make_sync_2dff(sync_name, src_clk, dst_clk, node.source_loc, sync_index)
            children.append(sync)
            sync_index += 1

            # Compile the body on the destination clock
            elem_checker = compose(elem, clock, child_label, original_text)
            children.append(elem_checker)
        else:
            # Same domain (or the first element before any switch)
            elem_checker = compose(elem, clock, child_label, original_text)
            children.append(elem_checker)

        # Inter-element delays: compiled on the CURRENT domain's clock.
        if i < len(node.delays):
            delay_min, delay_max = node.delays[i]
            cur_clk_signal = clock_signals[-1]
            if cur_clk_signal == clock.signal:
                cur_clock = clock
            else:
                cur_clock = ClockSpec(
                    edge="posedge", signal=cur_clk_signal, source_loc=node.source_loc
                )
            delay_checker = _make_delay_node(delay_min, delay_max, cur_clock, node.source_loc)
            children.append(delay_checker)

    all_signals = _collect_signals(children)
    # Remove clock signals from observed_signals (they are not data inputs)
    all_signals = tuple((p, s) for p, s in all_signals if s not in clock_signals)

    params: dict[str, str] = {
        "module_name": module_name,
        "clocks": ",".join(clock_signals),
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name="mc_seq_top",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=tuple(children),
        cse_origin=cse_origin,
    )


def _compose_clocked_seq(
    node: ClockedSeq,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose a ClockedSeq body on its own (inner) clock domain.

    The outer *clock* is intentionally ignored — the ClockedSeq carries its own
    domain clock. The label and original_text pass through verbatim.
    """
    return compose(node.body, node.clock, label, original_text, cse_origin)


def _make_sync_2dff(
    module_name: str,
    src_clock: str,
    dst_clock: str,
    source_loc: SourceLoc,
    index: int,
) -> CheckerNode:
    """Create a 2-DFF synchronizer CheckerNode for a clock-domain crossing."""
    return CheckerNode(
        template_name="sync_2dff",
        module_name=module_name,
        params={
            "module_name": module_name,
            "src_clock": src_clock,
            "dst_clock": dst_clock,
            "source_loc": str(source_loc),
            "sva2rtl_version": __version__,
            "original_text": f"sync_2dff #{index} ({src_clock} → {dst_clock})",
        },
        observed_signals=(),
        source_loc=source_loc,
        children=(),
        cse_origin=None,
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
        raise SvaCompileError(
            message=(
                f"Repetition expression is not a simple boolean expression "
                f"(got {type(node.expr).__name__}). "
                "Repetition requires a boolean expression, e.g. sig[*3]."
            ),
            source_loc=node.source_loc,
        )

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
    """Build a leaf CheckerNode for a signal function ($rose/$fell/$stable/$past/$changed).

    Each function maps directly to a template of the same name:
      rose -> rose.sv.j2, fell -> fell.sv.j2, changed -> changed.sv.j2, etc.
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


def _make_delay_node(
    delay_min: int,
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

    All v1.3 IR node types are now handled explicitly so that implication
    bit-vector sizing is accurate (was defaulting to 8 for all new types).
    """
    match consequent:
        case BoolExpr():
            return 1  # single-cycle: max_delay=0, width=1
        case SeqConcat():
            max_delay = sum(d_max for _, d_max in consequent.delays)
            return max(max_delay + 1, 1)
        case SeqOr() | SeqAnd() | SeqIntersect():
            return max(_compute_bv_width(consequent.left), _compute_bv_width(consequent.right))
        case SeqWithin():
            return max(_compute_bv_width(consequent.inner), _compute_bv_width(consequent.outer))
        case SeqThroughout():
            return _compute_bv_width(consequent.body)
        case SeqFirstMatch():
            return _compute_bv_width(consequent.body)
        case SignalFunc():
            return 1  # single-cycle evaluation
        case SeqGotoRep() | SeqNonconsecRep():
            # RISK-04: occurrence-based repetition has an unbounded cycle window
            # (occurrences need not be consecutive), so the exact bit-vector
            # width cannot be computed statically.  We size the window to a
            # conservative lower bound derived from rep_max (each occurrence may
            # take >= 1 cycle, so at minimum rep_max cycles are needed) and never
            # below the historical default of 8.  Any runtime overrun is caught
            # explicitly by the generated ``overflow_flag`` (never silently
            # truncated), preserving the "never fail silently" contract.
            return max(consequent.rep_max + 1, 8)
        case PropNot():
            return _compute_bv_width(consequent.body)
        case PropIfElse():
            tw = _compute_bv_width(consequent.true_branch)
            if consequent.false_branch is not None:
                tw = max(tw, _compute_bv_width(consequent.false_branch))
            return tw
        case SeqRepetition():
            return max(consequent.rep_max, 1)
        case _:
            return 8  # safe default for unknown structures


def _compose_implication(
    node: PropImplication,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a hierarchical CheckerNode for a PropImplication (|-> or |=>).

    Single-clock: delegates to ``_compose_implication_sc``.

    Multi-clock (consequent is ClockedSeq, v1.4.1 Part B): delegates to
    ``_compose_implication_mc`` — antecedent in clk1 domain, consequent in clk2
    domain, 2-DFF synchronizer on the token.
    """
    if isinstance(node.consequent, ClockedSeq):
        return _compose_implication_mc(node, clock, label, original_text, cse_origin)
    return _compose_implication_sc(node, clock, label, original_text, cse_origin)


def _compose_implication_sc(
    node: PropImplication,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a single-clock PropImplication.

    - BV_WIDTH == 1 (boolean / sampled-value consequent): **direct path**
      via ``overlap_bitvec`` / ``nonoverlap`` template. Single-cycle
      consequent is formally proven correct against IEEE-1800 semantics
      (see ``test_formal_sva_equiv.py``).

    - BV_WIDTH > 1 (multi-cycle sequence consequent, v1.5.1 P2):
      **NFA path** via ``_compose_implication_nfa`` when the consequent
      is NFA-liftable (``SeqConcat`` fixed delays, ``SeqRepetition``
      fixed count). Antecedent bool_expr matches gate the consequent
      NFA start; multi-thread slots handle overlapping attempts.
      Consequent NFA runs as nfa_kind="property" (dead-end = fail).

    - Non-NFA-liftable consequent shape: still rejected
      (``UnsupportedConstruct``, honesty boundary).
    """
    bv_width = _compute_bv_width(node.consequent)
    if bv_width > 1:
        if _is_nfa_liftable(node.consequent):
            return _compose_implication_nfa(
                node,
                clock,
                label,
                original_text,
                cse_origin,
            )
        raise UnsupportedConstruct(
            message=(
                "implication ('|->' / '|=>') with a multi-cycle sequence "
                "consequent is not yet supported: the consequent must be a "
                "single-cycle boolean expression or sampled-value function "
                "($rose/$fell/$stable/$past/$changed). Multi-cycle sequence "
                "consequents with fixed-delay ``SeqConcat`` or fixed-count "
                "``SeqRepetition`` (e.g. 'a |-> b ##2 c', 'a |-> b[*3]') "
                "are supported via the v1.5 NFA composition engine. "
                "Ranged delays, SeqOr, goto/nonconsec repetition in the "
                "consequent are deferred to a later version."
            ),
            construct_name="implication with non-NFA-liftable sequence consequent",
            source_loc=node.source_loc,
        )

    module_name = module_name_from_label(label, original_text)
    template = "overlap_bitvec" if node.overlapping else "nonoverlap"
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    ant_checker = compose(node.antecedent, clock, f"{base}_ant", original_text)
    con_checker = compose(node.consequent, clock, f"{base}_con", original_text)

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


def _compose_implication_nfa(
    node: PropImplication,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose implication with a multi-cycle consequent via NFA (v1.5.1 P2).

    Antecedent is evaluated COMBINATIONALLY in the wrapper template
    (``ant_match = start & (ant_guard)``), eliminating the registered
    pipeline latency that the old overlap_bitvec bv_q path suffered from
    (BUG-IMPL-01).

    Consequent is composed as a property-kind NFA with multi-thread slots.
    Thread budget: T = min(K, 4), capped by K·T ≤ 32.
    """
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name

    # Antecedent guard — raw boolean expression text (e.g. "a", "a && b").
    assert isinstance(node.antecedent, BoolExpr), "implication antecedent must be BoolExpr"
    ant_guard = node.antecedent.text
    ant_sigs = tuple(sorted({s for s, _ in extract_signals(ant_guard)}))

    # Consequent → sub-NFA (property-kind: dead-end = fail after attempt).
    cons_states, cons_trans, cons_accept, cons_sigs = _lift_to_nfa(
        node.consequent,
    )

    # Thread budget: worst-case concurrent = K (ant fires every cycle).
    nfa_t = min(cons_states, 4)
    if cons_states * nfa_t > 32:
        nfa_t = max(1, 32 // cons_states)

    cons_checker = _emit_nfa_checker(
        "implication consequent",
        cons_states,
        cons_trans,
        cons_accept,
        cons_sigs,
        "property",
        clock,
        f"{base}_con",
        original_text,
        node.source_loc,
        cse_origin=cse_origin,
        thread_slots=nfa_t,
    )

    all_sigs = tuple(sorted(set(ant_sigs) | set(cons_sigs)))

    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
        "overlapping": node.overlapping,  # type: ignore[dict-item]
        "op_type": "|->" if node.overlapping else "|=>",
        "nfa_thread_slots": str(nfa_t),
        "ant_guard": ant_guard,
    }

    return CheckerNode(
        template_name="implication_nfa",
        module_name=module_name,
        params=params,
        observed_signals=tuple((s, s) for s in all_sigs),
        source_loc=node.source_loc,
        children=(cons_checker,),
        cse_origin=cse_origin,
    )


def _compose_implication_mc(
    node: PropImplication,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Multi-clock implication (consequent is ClockedSeq, v1.4.1 Part B).

    Antecedent in outer clock domain; consequent in ClockedSeq inner domain;
    2-DFF sync carries ant match → con start. Reuses mc_seq_top template.
    """
    if node.overlapping:
        raise UnsupportedConstruct(
            message="overlapping '|->' across clock domains is not supported",
            construct_name="multi-clock overlapping implication",
            source_loc=node.source_loc,
        )
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name

    ant_checker = compose(node.antecedent, clock, f"{base}_ant", original_text)
    con_body = compose(
        node.consequent.body,  # type: ignore[attr-defined]
        node.consequent.clock,  # type: ignore[attr-defined]
        f"{base}_con",
        original_text,
    )
    sync = _make_sync_2dff(
        f"{module_name}_sync_0",
        clock.signal,
        node.consequent.clock.signal,  # type: ignore[attr-defined]
        node.source_loc,
        0,
    )

    all_signals = _collect_signals([ant_checker, con_body])
    clk_sigs = [clock.signal, node.consequent.clock.signal]  # type: ignore[attr-defined]
    all_signals = tuple((p, s) for p, s in all_signals if s not in clk_sigs)

    params: dict[str, str] = {
        "module_name": module_name,
        "clocks": ",".join(clk_sigs),
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="mc_seq_top",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(ant_checker, sync, con_body),
        cse_origin=cse_origin,
    )


def _collect_signals(
    children: list[CheckerNode],
) -> tuple[tuple[str, str], ...]:
    """Collect all unique observed signals from a list of child CheckerNodes."""
    # HARDEN-04: preserve original (port_name, sig_name) pairs
    result: dict[str, str] = {}
    for child in children:
        for port_name, sig_name in child.observed_signals:
            if port_name not in result:
                result[port_name] = sig_name
    return tuple((p, s) for p, s in result.items())


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
    cond_signals = tuple((p, s) for p, s in extract_signals(cond_expr) if p not in _reserved_ports)
    cond_seen = {p for p, _ in cond_signals}
    body_extra = tuple(
        (p, s)
        for p, s in body_checker.observed_signals
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


def _compose_first_match(
    node: SeqFirstMatch,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a first_match wrapper CheckerNode.

    Wraps the body sequence so that only the earliest completion is reported.
    Once the body passes, all subsequent pass/fail/active outputs are
    suppressed via a locked_q register.
    """
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    body_checker = compose(node.body, clock, f"{base}_body", original_text)

    params: dict[str, str] = {
        "module_name": module_name,
        "body_tmpl": body_checker.template_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }

    return CheckerNode(
        template_name="first_match_top",
        module_name=module_name,
        params=params,
        observed_signals=body_checker.observed_signals,
        source_loc=node.source_loc,
        children=(body_checker,),
        cse_origin=cse_origin,
    )


def _compose_goto_rep(
    node: SeqGotoRep,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a goto repetition [->N] leaf CheckerNode."""
    module_name = module_name_from_label(label, original_text)
    cnt_width = max(1, math.ceil(math.log2(node.rep_max + 1))) if node.rep_max > 0 else 1

    if isinstance(node.expr, BoolExpr):
        observed = extract_signals(node.expr.text)
        signal_expr = node.expr.text
    else:
        raise SvaCompileError(
            message=f"Goto repetition [->N] requires a boolean expression, "
            f"got {type(node.expr).__name__}",
            source_loc=node.source_loc,
        )

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
        template_name="goto_rep",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )


def _compose_nonconsec_rep(
    node: SeqNonconsecRep,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Build a non-consecutive repetition [=N] leaf CheckerNode."""
    module_name = module_name_from_label(label, original_text)
    cnt_width = max(1, math.ceil(math.log2(node.rep_max + 1))) if node.rep_max > 0 else 1

    if isinstance(node.expr, BoolExpr):
        observed = extract_signals(node.expr.text)
        signal_expr = node.expr.text
    else:
        raise SvaCompileError(
            message=f"Non-consecutive repetition [=N] requires a boolean expression, "
            f"got {type(node.expr).__name__}",
            source_loc=node.source_loc,
        )

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
        template_name="nonconsec_rep",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )


# ── Phase 3: Complex sequence operator composers (v1.3) ────────────────────


def _compose_seq_or(
    node: SeqOr,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose sequence OR: two sub-sequences, OR their pass outputs."""
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    left = compose(node.left, clock, f"{base}_left", original_text)
    right = compose(node.right, clock, f"{base}_right", original_text)
    all_signals = _collect_signals([left, right])
    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="prop_or",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(left, right),
        cse_origin=cse_origin,
    )


def _compose_seq_and(
    node: SeqAnd,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose sequence AND: two sub-sequences, AND their pass outputs."""
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    left = compose(node.left, clock, f"{base}_left", original_text)
    right = compose(node.right, clock, f"{base}_right", original_text)
    all_signals = _collect_signals([left, right])
    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="prop_and",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(left, right),
        cse_origin=cse_origin,
    )


def _is_boolean_leaf(operand: SVANode) -> bool:
    """Return True iff ``operand`` is a single-cycle boolean sequence atom.

    v1.5 G2a honesty boundary: intersect / within / throughout's current RTL
    templates compose via ``left_pass & right_pass`` (or the equivalent
    inner/outer active-window AND). This is only semantically correct when
    both operands complete on a single unambiguous cycle — i.e. they are
    plain boolean expressions. For multi-cycle sequence operands the
    "same-cycle completion" of IEEE-1800 §16.9.7/§16.9.10 requires
    tracking multiple parallel matching threads (the NFA composition
    engine landing in G2b). Compiling multi-cycle operands via the current
    templates would produce a silent-wrong monitor whose pass fires only
    when the two sub-sequences' completion cycles happen to coincide by
    accident.
    """
    return isinstance(operand, BoolExpr)


def _reject_non_boolean_composition(
    op_name: str,
    positions: tuple[tuple[str, SVANode], ...],
    source_loc: SourceLoc,
) -> None:
    """Raise UnsupportedConstruct if any operand is not a boolean leaf.

    ``positions`` = tuple of (position_label, operand) pairs used in the
    error message to point the user at the exact offending operand.
    """
    bad = [(pos, type(op).__name__) for pos, op in positions if not _is_boolean_leaf(op)]
    if not bad:
        return
    parts = ", ".join(f"{pos}={ty}" for pos, ty in bad)
    raise UnsupportedConstruct(
        message=(
            f"'{op_name}' with a multi-cycle sequence operand is not yet "
            f"supported: current RTL templates compose via a single-cycle "
            f"'same-cycle completion' AND which is only correct when both "
            f"operands are boolean atoms (BoolExpr). Offending operand(s): "
            f"{parts}. Multi-cycle operands (##N / [*N] / nested sequence "
            f"operators) are deferred to the v1.5 G2b NFA composition "
            f"engine (nfa_generic template). Workaround: split the "
            f"multi-cycle operand into a separate property whose result "
            f"feeds a single-cycle boolean into the composition."
        ),
        construct_name=f"{op_name} with multi-cycle operand",
        source_loc=source_loc,
    )


def _compose_intersect(
    node: SeqIntersect,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose intersect: both sequences complete simultaneously.

    Routing (v1.5.1):
    - Both operands are BoolExpr atoms (single-cycle sequences):
      **direct path** via the ``prop_intersect`` template (byte-identical
      to v1.5.0; goldens unchanged; verified by 8 gate tests +
      2 flipped RISK-02 xfails).
    - At least one operand is a supported multi-cycle sequence
      (``SeqConcat`` fixed delays, ``SeqRepetition`` fixed count):
      **NFA path** via ``_compose_intersect_nfa`` (product construction
      per Boulé & Zilic MBAC; see ``.gsd/milestones/v1.5/spike-notes.md``
      §G0.4).
    - Any other IR shape (``SeqOr``, ``SeqGotoRep``, ``SeqNonconsecRep``,
      nested composed operators, non-fixed bounds): still rejected with
      ``UnsupportedConstruct`` — carried over from v1.5 G2a's honesty
      boundary while those shapes await NFA support in a later slice.
    """
    if _is_boolean_leaf(node.left) and _is_boolean_leaf(node.right):
        return _compose_intersect_bool(
            node,
            clock,
            label,
            original_text,
            cse_origin=cse_origin,
        )
    if _is_nfa_liftable(node.left) and _is_nfa_liftable(node.right):
        return _compose_intersect_nfa(
            node,
            clock,
            label,
            original_text,
            cse_origin=cse_origin,
        )
    # Not liftable to NFA yet — keep the honesty boundary.
    _reject_non_boolean_composition(
        "intersect",
        (("left", node.left), ("right", node.right)),
        node.source_loc,
    )
    # unreachable — _reject_non_boolean_composition always raises for the
    # non-boolean case, but mypy/ruff want a return.
    raise AssertionError("unreachable")  # pragma: no cover


def _compose_intersect_bool(
    node: SeqIntersect,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Direct path for ``bool intersect bool`` — unchanged v1.5.0 behaviour.

    The single-cycle-completion path via the ``prop_intersect`` template is
    already verified correct (bool_expr.sv.j2 registers pass_q with
    start & bool_result, prop_intersect ANDs left_pass & right_pass, and
    the oracle gates by ``_eval_bool_leaf`` per v1.5 G1).
    """
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    left = compose(node.left, clock, f"{base}_left", original_text)
    right = compose(node.right, clock, f"{base}_right", original_text)
    all_signals = _collect_signals([left, right])
    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="prop_intersect",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(left, right),
        cse_origin=cse_origin,
    )


# ── NFA composition primitives (v1.5.1) ────────────────────────────────


def _is_nfa_liftable(operand: SVANode) -> bool:
    """Return True iff ``operand`` can be composed into an NFA.

    Supported shapes:
    - ``BoolExpr``, fixed-delay ``SeqConcat``, fixed-count ``SeqRepetition``
    - Nested ``SeqIntersect`` / ``SeqWithin`` / ``SeqThroughout`` with
      liftable operands (v1.5.1 P3 recursive composition).
    """
    if isinstance(operand, BoolExpr):
        return True
    if isinstance(operand, SeqConcat):
        if any(mn != mx for mn, mx in operand.delays):
            return False
        return all(isinstance(e, BoolExpr) for e in operand.elements)
    if isinstance(operand, SeqRepetition):
        return (
            isinstance(operand.expr, BoolExpr)
            and operand.rep_min == operand.rep_max
            and operand.rep_min >= 1
        )
    if isinstance(operand, SeqIntersect):
        return _is_nfa_liftable(operand.left) and _is_nfa_liftable(operand.right)
    if isinstance(operand, SeqWithin):
        return _is_nfa_liftable(operand.inner) and _is_nfa_liftable(operand.outer)
    if isinstance(operand, SeqThroughout):
        return isinstance(operand.condition, BoolExpr) and _is_nfa_liftable(operand.body)
    return False


def _lift_to_nfa(
    operand: SVANode,
) -> tuple[int, tuple[tuple[int, str, int], ...], frozenset[int], tuple[str, ...]]:
    """Convert a liftable operand into a small NFA (states, transitions,
    accept, observed_signals_ports).

    All returned NFAs use the invariant "state 0 is the initial state,
    accept = {states - 1}" so ``_nfa_product`` can compose them
    uniformly.
    """
    if isinstance(operand, BoolExpr):
        # 0 --expr--> 1 (accept)
        guard = f"({operand.text})"
        signals = tuple(sorted({s for s, _ in extract_signals(operand.text)}))
        return 2, ((0, guard, 1),), frozenset({1}), signals

    if isinstance(operand, SeqConcat):
        # Chain of BoolExpr elements with fixed delays.
        # Normalise the delays tuple: it may be inter-element only
        # (len=elements-1) or include a leading (0,0) for the first
        # element (len=elements). We always normalise to the latter.
        raw_delays = operand.delays
        if len(raw_delays) == len(operand.elements) - 1:
            raw_delays = ((0, 0),) + raw_delays
        elif len(raw_delays) != len(operand.elements):
            raise UnsupportedConstruct(
                message=(
                    f"SeqConcat has {len(operand.elements)} elements but "
                    f"{len(raw_delays)} delays — expected {len(operand.elements)} "
                    f"or {len(operand.elements) - 1}. This is an internal IR "
                    f"invariant violation."
                ),
                construct_name="SeqConcat delay count mismatch",
                source_loc=operand.source_loc,
            )

        trans: list[tuple[int, str, int]] = []
        signal_set: set[str] = set()
        current = 0
        for i, element in enumerate(operand.elements):
            assert isinstance(element, BoolExpr)
            guard = f"({element.text})"
            for s, _ in extract_signals(element.text):
                signal_set.add(s)
            if i == 0:
                trans.append((current, guard, current + 1))
                current += 1
                continue
            d = raw_delays[i][0]
            # d-1 wait cycles then element check. d must be >= 1 for
            # slang SeqConcat (adjacent) — d == 0 means overlap which
            # slang normalises to a single expression AND. Here we
            # assume d >= 1 (single-cycle spacing).
            wait = max(d - 1, 0)
            for _ in range(wait):
                trans.append((current, "1", current + 1))
                current += 1
            trans.append((current, guard, current + 1))
            current += 1
        return current + 1, tuple(trans), frozenset({current}), tuple(sorted(signal_set))

    if isinstance(operand, SeqRepetition):
        # a[*N]: 0 --a--> 1 --a--> ... --a--> N (accept)
        assert isinstance(operand.expr, BoolExpr)
        n = operand.rep_min
        guard = f"({operand.expr.text})"
        rep_trans: tuple[tuple[int, str, int], ...] = tuple((i, guard, i + 1) for i in range(n))
        signals = tuple(sorted({s for s, _ in extract_signals(operand.expr.text)}))
        return n + 1, rep_trans, frozenset({n}), signals

    raise ValueError(f"cannot lift {type(operand).__name__} to NFA yet")


def _extract_nfa_from_checker(
    checker: CheckerNode,
) -> tuple[int, tuple[tuple[int, str, int], ...], frozenset[int], tuple[str, ...]]:
    """Extract NFA data from an already-composed ``nfa_generic`` CheckerNode."""
    assert checker.template_name == "nfa_generic", (
        f"expected nfa_generic, got {checker.template_name}"
    )
    states = int(checker.params["nfa_states"])
    raw_trans = checker.params.get("nfa_transitions", "")
    trans = _deserialise_transitions(raw_trans.split(";") if raw_trans else [])
    raw_accept = checker.params.get("nfa_accept", "")
    accept = _deserialise_accept(raw_accept.split(",") if raw_accept else [])
    sigs = tuple(s for s, _ in checker.observed_signals)
    return states, trans, accept, sigs


def _try_lift_operand(
    operand: SVANode,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
) -> tuple[int, tuple[tuple[int, str, int], ...], frozenset[int], tuple[str, ...]] | None:
    """Try to obtain NFA data from an operand.

    - Primitive shapes (BoolExpr, SeqConcat, SeqRepetition): lifted
      directly via ``_lift_to_nfa``.
    - Nested composed shapes (SeqIntersect, SeqWithin, SeqThroughout):
      recursively lifted via their own product constructions (no
      compose() dispatch — avoids the bool-bool legacy path).
    """
    if isinstance(operand, (BoolExpr, SeqConcat, SeqRepetition)):
        return _lift_to_nfa(operand)
    if isinstance(operand, SeqIntersect):
        left = _try_lift_operand(operand.left, clock, label, original_text)
        right = _try_lift_operand(operand.right, clock, label, original_text)
        if not left or not right:
            return None
        states, trans, accept = _nfa_product_intersect(
            left[0],
            left[1],
            left[2],
            right[0],
            right[1],
            right[2],
        )
        sigs = tuple(sorted(set(left[3]) | set(right[3])))
        return states, trans, accept, sigs
    if isinstance(operand, SeqWithin):
        inner = _try_lift_operand(operand.inner, clock, label, original_text)
        outer = _try_lift_operand(operand.outer, clock, label, original_text)
        if not inner or not outer:
            return None
        states, trans, accept = _nfa_product_within(
            inner[0],
            inner[1],
            inner[2],
            outer[0],
            outer[1],
            outer[2],
        )
        sigs = tuple(sorted(set(inner[3]) | set(outer[3])))
        return states, trans, accept, sigs
    if isinstance(operand, SeqThroughout):
        body = _try_lift_operand(operand.body, clock, label, original_text)
        if not body or not isinstance(operand.condition, BoolExpr):
            return None
        states, trans, accept = _nfa_product_throughout(
            operand.condition.text,
            body[0],
            body[1],
            body[2],
            tuple(sorted({s for s, _ in extract_signals(operand.condition.text)})),
        )
        sigs = tuple(sorted(set(body[3]) | {s for s, _ in extract_signals(operand.condition.text)}))
        return states, trans, accept, sigs
    return None


def _nfa_product_intersect(
    n_left: int,
    t_left: tuple[tuple[int, str, int], ...],
    acc_left: frozenset[int],
    n_right: int,
    t_right: tuple[tuple[int, str, int], ...],
    acc_right: frozenset[int],
) -> tuple[int, tuple[tuple[int, str, int], ...], frozenset[int]]:
    """Cross-product NFA for ``intersect`` — see spike-notes §G0.4.

    State ID mapping: ``sid(i, j) = i * n_right + j``.
    Transition: for every (i, gL, i') in T_L and (j, gR, j') in T_R, the
    product has ``(sid(i,j), gL & gR, sid(i',j'))``.
    Accept: ``{sid(i,j) : i ∈ acc_L, j ∈ acc_R}``.
    """

    def sid(i: int, j: int) -> int:
        return i * n_right + j

    trans: list[tuple[int, str, int]] = []
    for li, gl, lt in t_left:
        for rj, gr, rt in t_right:
            g = f"({gl}) & ({gr})"
            trans.append((sid(li, rj), g, sid(lt, rt)))
    accept = frozenset(sid(i, j) for i in acc_left for j in acc_right)
    return n_left * n_right, tuple(trans), accept


def _serialise_transitions(
    transitions: tuple[tuple[int, str, int], ...],
) -> str:
    """Encode NFA transitions for the ``nfa_transitions`` params string.

    Format: ``"s0,g0,t0;s1,g1,t1;..."``. Guards must not contain literal
    ``,`` or ``;`` — the composer never emits such characters (guards
    are built from operand text via ``BoolExpr.text`` which cannot contain
    them under our slang whitelist). Empty transition list encodes as
    empty string.
    """
    parts = [f"{s},{g},{t}" for s, g, t in transitions]
    return ";".join(parts)


def _serialise_accept(accept: frozenset[int]) -> str:
    """Encode accept-state set as ``"i,j,k"`` (sorted for determinism)."""
    return ",".join(str(i) for i in sorted(accept))


def _deserialise_transitions(
    raw: list[str],
) -> tuple[tuple[int, str, int], ...]:
    """Decode NFA transitions from ``serialise_transitions`` format back."""
    result: list[tuple[int, str, int]] = []
    for part in raw:
        part = part.strip()
        if not part:
            continue
        s, g, t = part.split(",", 2)
        result.append((int(s), g.strip(), int(t)))
    return tuple(result)


def _deserialise_accept(raw: list[str]) -> frozenset[int]:
    """Decode accept set from ``serialise_accept`` format back."""
    result: set[int] = set()
    for part in raw:
        part = part.strip()
        if part:
            result.add(int(part))
    return frozenset(result)


def _accept_bits(states: int, accept: frozenset[int]) -> str:
    """Render the K-bit accept mask as a binary string ``bK-1 bK-2 ... b0``
    (MSB first) for embedding in a Verilog literal ``K'b<bits>``.
    """
    return "".join("1" if i in accept else "0" for i in range(states - 1, -1, -1))


def _render_state_d_body(
    states: int,
    transitions: tuple[tuple[int, str, int], ...],
) -> str:
    """Render the combinational next-state assignments for the NFA template.

    Emits, for each bit ``b`` in ``[0, states)``, an assignment
    ``assign state_d[b] = (state_now[s0] & (g0)) | (state_now[s1] & (g1)) | ...``
    where the ORed terms are exactly the transitions whose ``to_state == b``,
    and ``state_now`` is the combinational merge of ``state_q`` and the
    start-seed pulse (see ``nfa_generic.sv.j2`` header). Using
    ``state_now`` ensures the first transition can observe operand values
    on the SAME cycle ``start`` is pulsed, matching the oracle's semantics.

    Bits with no incoming transitions get ``assign state_d[b] = 1'b0``.
    """
    incoming: dict[int, list[tuple[int, str]]] = {b: [] for b in range(states)}
    for from_s, guard, to_s in transitions:
        incoming.setdefault(to_s, []).append((from_s, guard))
    lines: list[str] = []
    for b in range(states):
        arcs = incoming.get(b, [])
        if not arcs:
            lines.append(f"    assign state_d[{b}] = 1'b0;")
            continue
        terms = " | ".join(f"(state_now[{s}] & ({g}))" for s, g in arcs)
        lines.append(f"    assign state_d[{b}] = {terms};")
    return "\n".join(lines)


def _render_multi_state_d_body(
    states: int,
    transitions: tuple[tuple[int, str, int], ...],
    thread_slots: int,
) -> str:
    """Render per-slot combinational next-state assignments for multi-thread.

    For each slot ``s`` in ``[0, thread_slots)``, emits the same transition
    logic as ``_render_state_d_body`` but with slot-offset state_d indices.
    Slot state source: ``state_q[(s+1)*K-1 : s*K]``, combined with
    ``alloc[s]`` to seed state 0. Rendered via a local wire per slot
    (``wire [K-1:0] slot_s_now``) so the guard expressions stay compact.
    """
    incoming: dict[int, list[tuple[int, str]]] = {b: [] for b in range(states)}
    for from_s, guard, to_s in transitions:
        incoming.setdefault(to_s, []).append((from_s, guard))

    lines: list[str] = []
    for s in range(thread_slots):
        base = s * states
        lines.append(f"    // Slot {s}")
        for b in range(states):
            arcs = incoming.get(b, [])
            if not arcs:
                lines.append(f"    assign state_d[{base + b}] = 1'b0;")
                continue
            terms = " | ".join(f"(slot{s}_now[{from_s}] & ({g}))" for from_s, g in arcs)
            lines.append(f"    assign state_d[{base + b}] = {terms};")
        lines.append("")
    # Remove trailing blank line.
    if lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _emit_nfa_checker(
    op_name: str,
    states: int,
    transitions: tuple[tuple[int, str, int], ...],
    accept: frozenset[int],
    signals: tuple[str, ...],
    nfa_kind: str,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    source_loc: SourceLoc,
    cse_origin: str | None,
    *,
    thread_slots: int = 1,
) -> CheckerNode:
    """Shared emitter for all NFA-composed operators.

    Encapsulates:
    - D3 budget check (K·T ≤ 32) with actionable error naming the op.
    - Serialisation of transitions / accept into ``params``.
    - Observed-signal derivation from the union of sub-NFA signal sets.
    - Multi-thread state_d body when ``thread_slots > 1`` (v1.5.1 P2).
    """
    if states * thread_slots > 32:
        raise UnsupportedConstruct(
            message=(
                f"'{op_name}' composed NFA has K={states} states × "
                f"T={thread_slots} threads = {states * thread_slots} bits, "
                f"exceeding the D3 budget K·T ≤ 32. Workaround: split the "
                f"property so operands are shorter, or reduce repetition "
                f"/ delay bounds / concurrent threads. See "
                f"SUPPORTED_CONSTRUCTS.md for the budget rationale."
            ),
            construct_name=f"{op_name} with K·T > 32",
            source_loc=source_loc,
        )
    observed = tuple((s, s) for s in signals)
    module_name = module_name_from_label(label, original_text)
    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
        "nfa_states": str(states),
        "nfa_transitions": _serialise_transitions(transitions),
        "nfa_accept": _serialise_accept(accept),
        "nfa_accept_mask": hex(sum(1 << i for i in accept)),
        "nfa_accept_bits": _accept_bits(states, accept),
        "nfa_kind": nfa_kind,
        "nfa_state_d_body": _render_state_d_body(states, transitions),
        "nfa_thread_slots": str(thread_slots),
    }
    if thread_slots > 1:
        params["nfa_state_d_body_multi"] = _render_multi_state_d_body(
            states,
            transitions,
            thread_slots,
        )
    return CheckerNode(
        template_name="nfa_generic",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=source_loc,
        children=(),
        cse_origin=cse_origin,
    )


def _compose_intersect_nfa(
    node: SeqIntersect,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose ``intersect`` via NFA product (v1.5.1 slice 1).

    Builds sub-NFAs for both operands, forms their cross-product per
    ``_nfa_product_intersect`` (Boulé & Zilic MBAC §4.3), and emits a
    single ``nfa_generic`` CheckerNode with the serialised transition
    table, accept mask and ``nfa_kind = "sequence"``.

    Requires D3 budget: composed state count K = |L| * |R| ≤ 32.
    """
    left_nfa = _try_lift_operand(node.left, clock, label, original_text)
    right_nfa = _try_lift_operand(node.right, clock, label, original_text)
    assert left_nfa and right_nfa, "pre-checked by _is_nfa_liftable"
    n_left, t_left, acc_left, sigs_left = left_nfa
    n_right, t_right, acc_right, sigs_right = right_nfa
    states, trans, accept = _nfa_product_intersect(
        n_left,
        t_left,
        acc_left,
        n_right,
        t_right,
        acc_right,
    )
    all_sigs = tuple(sorted(set(sigs_left) | set(sigs_right)))
    return _emit_nfa_checker(
        "intersect",
        states,
        trans,
        accept,
        all_sigs,
        "sequence",
        clock,
        label,
        original_text,
        node.source_loc,
        cse_origin,
    )


# ── within (v1.5.1 slice 2) ─────────────────────────────────────────────


def _nfa_reachable_states(
    states: int,
    transitions: tuple[tuple[int, str, int], ...],
) -> frozenset[int]:
    """Compute states reachable from state 0 in the NFA transition graph.

    Ignores guards (assumes all can eventually fire). Used by
    ``_nfa_product_within`` to build the "outer still alive" mask —
    the outer sub-NFA is considered "in its window" as long as it is
    in any state reachable from 0 that has outgoing transitions OR is
    in accept.
    """
    reach = {0}
    changed = True
    while changed:
        changed = False
        for from_s, _, to_s in transitions:
            if from_s in reach and to_s not in reach:
                reach.add(to_s)
                changed = True
    return frozenset(reach)


def _nfa_alive_states(
    states: int,
    transitions: tuple[tuple[int, str, int], ...],
    accept: frozenset[int],
) -> frozenset[int]:
    """Compute "alive" states for a sub-NFA: any state that either has
    outgoing transitions OR is accept. Dead states (no outgoing edges,
    not accept) are excluded — matching the ``outer_alive`` predicate
    used in the spike prototype's ``nfa_product`` (mode='within').
    """
    with_out = {from_s for from_s, _, _ in transitions}
    return frozenset(with_out | accept)


def _nfa_product_within(
    n_inner: int,
    t_inner: tuple[tuple[int, str, int], ...],
    acc_inner: frozenset[int],
    n_outer: int,
    t_outer: tuple[tuple[int, str, int], ...],
    acc_outer: frozenset[int],
) -> tuple[int, tuple[tuple[int, str, int], ...], frozenset[int]]:
    """Cross-product NFA for ``within`` — spike-notes §G0.4 (mode='within').

    Same transition composition as ``_nfa_product_intersect``; the
    difference is in the accept set:

        accept = { sid(i, j) : i ∈ acc_inner, j ∈ alive(outer) }

    where alive(outer) = outer states that have outgoing edges OR are
    themselves accept. This encodes IEEE 1800 §16.9.10: the inner
    match cycle must fall inside the outer's active window.
    """

    def sid(i: int, j: int) -> int:
        return i * n_outer + j

    trans: list[tuple[int, str, int]] = []
    for li, gl, lt in t_inner:
        for rj, gr, rt in t_outer:
            g = f"({gl}) & ({gr})"
            trans.append((sid(li, rj), g, sid(lt, rt)))
    alive_outer = _nfa_alive_states(n_outer, t_outer, acc_outer)
    accept = frozenset(sid(i, j) for i in acc_inner for j in alive_outer)
    return n_inner * n_outer, tuple(trans), accept


def _compose_within_nfa(
    node: SeqWithin,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose ``within`` via NFA product (v1.5.1 slice 2).

    Inner sequence must complete while outer is still alive (IEEE 1800
    §16.9.10). Product construction: cross-product state IDs;
    transitions AND-composed; accept = inner_accept × outer_alive.
    """
    inner_nfa = _try_lift_operand(node.inner, clock, label, original_text)
    outer_nfa = _try_lift_operand(node.outer, clock, label, original_text)
    assert inner_nfa and outer_nfa, "pre-checked by _is_nfa_liftable"
    n_inner, t_inner, acc_inner, sigs_inner = inner_nfa
    n_outer, t_outer, acc_outer, sigs_outer = outer_nfa
    states, trans, accept = _nfa_product_within(
        n_inner,
        t_inner,
        acc_inner,
        n_outer,
        t_outer,
        acc_outer,
    )
    all_sigs = tuple(sorted(set(sigs_inner) | set(sigs_outer)))
    return _emit_nfa_checker(
        "within",
        states,
        trans,
        accept,
        all_sigs,
        "sequence",
        clock,
        label,
        original_text,
        node.source_loc,
        cse_origin,
    )


# ── throughout (v1.5.1 slice 2) ─────────────────────────────────────────


def _nfa_product_throughout(
    cond_text: str,
    n_body: int,
    t_body: tuple[tuple[int, str, int], ...],
    acc_body: frozenset[int],
    cond_signals: tuple[str, ...],
) -> tuple[int, tuple[tuple[int, str, int], ...], frozenset[int]]:
    """Product NFA for ``throughout`` — IEEE 1800 §16.9.11.

    Semantics: ``cond throughout body`` matches iff ``body`` matches AND
    ``cond`` holds on EVERY cycle body is active.

    Encoding: guard every body transition by ``AND (cond)``. If cond
    fails while body is active, no outgoing transition fires → body
    thread drops (dead-end = vacuous no-match for sequence NFAs; a
    property-level guard would fire fail here — deferred to the
    property NFA path used by implication).

    Result: same K as body (no state explosion), same accept set.
    """
    cond_guard = f"({cond_text})"
    trans = tuple((from_s, f"({g}) & {cond_guard}", to_s) for from_s, g, to_s in t_body)
    return n_body, trans, acc_body


def _compose_throughout_nfa(
    node: SeqThroughout,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose ``throughout`` via NFA (v1.5.1 slice 2).

    Requires the condition to be a ``BoolExpr`` (per IEEE 1800 §16.9.11
    and current pipeline; multi-cycle cond is not a valid SVA form).
    Body may be any NFA-liftable shape.
    """
    if not isinstance(node.condition, BoolExpr):
        # Non-boolean condition is not a valid throughout per IEEE 1800.
        # Fall back to the existing rejection (also caught by G2a).
        raise UnsupportedConstruct(
            message=(
                "'throughout' condition must be a boolean expression per "
                f"IEEE 1800 §16.9.11; got {type(node.condition).__name__}."
            ),
            construct_name="throughout with non-boolean condition",
            source_loc=node.source_loc,
        )
    cond_text = node.condition.text
    cond_signals = tuple(sorted({s for s, _ in extract_signals(cond_text)}))

    body_nfa = _try_lift_operand(node.body, clock, label, original_text)
    assert body_nfa, "pre-checked by _is_nfa_liftable"
    n_body, t_body, acc_body, sigs_body = body_nfa
    states, trans, accept = _nfa_product_throughout(
        cond_text,
        n_body,
        t_body,
        acc_body,
        cond_signals,
    )
    all_sigs = tuple(sorted(set(cond_signals) | set(sigs_body)))
    return _emit_nfa_checker(
        "throughout",
        states,
        trans,
        accept,
        all_sigs,
        "sequence",
        clock,
        label,
        original_text,
        node.source_loc,
        cse_origin,
    )


def _compose_within(
    node: SeqWithin,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose within: inner sequence completes within outer's window.

    Routing (v1.5.1 slice 2):
    - Both operands are BoolExpr atoms → direct ``prop_within`` path
      (v1.5.0 behaviour, RISK-02 fixed).
    - Both operands are NFA-liftable → ``_compose_within_nfa``.
    - Other shapes → G2a rejection (unchanged).
    """
    if _is_boolean_leaf(node.inner) and _is_boolean_leaf(node.outer):
        return _compose_within_bool(
            node,
            clock,
            label,
            original_text,
            cse_origin=cse_origin,
        )
    if _is_nfa_liftable(node.inner) and _is_nfa_liftable(node.outer):
        return _compose_within_nfa(
            node,
            clock,
            label,
            original_text,
            cse_origin=cse_origin,
        )
    _reject_non_boolean_composition(
        "within",
        (("inner", node.inner), ("outer", node.outer)),
        node.source_loc,
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _compose_within_bool(
    node: SeqWithin,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Direct path for bool ``within`` bool — unchanged v1.5.0 behaviour."""
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    inner = compose(node.inner, clock, f"{base}_inner", original_text)
    outer = compose(node.outer, clock, f"{base}_outer", original_text)
    all_signals = _collect_signals([inner, outer])
    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="prop_within",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(inner, outer),
        cse_origin=cse_origin,
    )


def _compose_throughout(
    node: SeqThroughout,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose throughout: condition must hold continuously through body sequence.

    Routing (v1.5.1 slice 2):
    - Both condition and body are BoolExpr → direct ``prop_throughout``
      path (v1.5.0 behaviour, IEEE-1800 correct — 4 tests already green).
    - condition is BoolExpr and body is NFA-liftable multi-cycle →
      ``_compose_throughout_nfa`` (guard-every-transition-by-cond).
    - Anything else → G2a rejection.
    """
    if _is_boolean_leaf(node.condition) and _is_boolean_leaf(node.body):
        return _compose_throughout_bool(
            node,
            clock,
            label,
            original_text,
            cse_origin=cse_origin,
        )
    if _is_boolean_leaf(node.condition) and _is_nfa_liftable(node.body):
        return _compose_throughout_nfa(
            node,
            clock,
            label,
            original_text,
            cse_origin=cse_origin,
        )
    _reject_non_boolean_composition(
        "throughout",
        (("condition", node.condition), ("body", node.body)),
        node.source_loc,
    )
    raise AssertionError("unreachable")  # pragma: no cover


def _compose_throughout_bool(
    node: SeqThroughout,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Direct path for bool ``throughout`` bool — unchanged v1.5.0 behaviour."""
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    cond_checker = compose(node.condition, clock, f"{base}_cond", original_text)
    body_checker = compose(node.body, clock, f"{base}_body", original_text)
    all_signals = _collect_signals([cond_checker, body_checker])
    if isinstance(node.condition, BoolExpr):
        cond_text = node.condition.text
    else:
        cond_text = "<cond>"
    params: dict[str, str] = {
        "module_name": module_name,
        "cond_expr": cond_text,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="prop_throughout",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=(cond_checker, body_checker),
        cse_origin=cse_origin,
    )


# ── Phase 4: Property operator composers (v1.3) ────────────────────────────


def _compose_prop_not(
    node: PropNot,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose property NOT: invert pass/fail of the body checker."""
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    body_checker = compose(node.body, clock, f"{base}_body", original_text)
    params: dict[str, str] = {
        "module_name": module_name,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="prop_not",
        module_name=module_name,
        params=params,
        observed_signals=body_checker.observed_signals,
        source_loc=node.source_loc,
        children=(body_checker,),
        cse_origin=cse_origin,
    )


def _compose_prop_if_else(
    node: PropIfElse,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose property if-else: multiplex between true/false branches."""
    module_name = module_name_from_label(label, original_text)
    base = module_name[4:] if module_name.startswith("sva_") else module_name
    true_checker = compose(node.true_branch, clock, f"{base}_true", original_text)
    children = [true_checker]
    has_else = node.false_branch is not None
    if has_else:
        assert node.false_branch is not None
        false_checker = compose(node.false_branch, clock, f"{base}_false", original_text)
        children.append(false_checker)
    all_signals = _collect_signals(children)
    if isinstance(node.condition, BoolExpr):
        cond_text = node.condition.text
        # Add condition signals to observed_signals (used in comb. MUX)
        cond_sigs = extract_signals(cond_text)
        cond_seen = {p for p, _ in all_signals}
        cond_extra = tuple((p, s) for p, s in cond_sigs if p not in cond_seen)
        all_signals = all_signals + cond_extra
    else:
        cond_text = "<cond>"
    params: dict[str, str] = {
        "module_name": module_name,
        "cond_expr": cond_text,
        "has_else": "1" if has_else else "0",
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="prop_if_else",
        module_name=module_name,
        params=params,
        observed_signals=all_signals,
        source_loc=node.source_loc,
        children=tuple(children),
        cse_origin=cse_origin,
    )


def _compose_bounded_eventually(
    node: PropBoundedEventually,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose bounded eventually ``s_eventually [lo:hi] p`` as a leaf monitor.

    The operand is a boolean expression embedded directly (v1.4 Part A); the
    counter sizes to hold offsets 0..hi-1 (``cnt_q == k-1`` at offset k), mirroring
    the ``concat_delay`` width derivation.
    """
    if not isinstance(node.body, BoolExpr):
        raise UnsupportedConstruct(
            message=(
                "bounded eventually currently supports only a boolean-expression "
                "operand; sequence/property operands are deferred to v1.5."
            ),
            construct_name="s_eventually with non-boolean operand",
            source_loc=node.source_loc,
        )
    module_name = module_name_from_label(label, original_text)
    observed = extract_signals(node.body.text)
    cnt_width = max(1, math.ceil(math.log2(node.hi + 1))) if node.hi > 0 else 1
    params: dict[str, str] = {
        "module_name": module_name,
        "bool_expr": node.body.text,
        "lo": str(node.lo),
        "hi": str(node.hi),
        "cnt_width": str(cnt_width),
        "strong": "1" if node.strong else "0",
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="s_eventually",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )


def _compose_bounded_always(
    node: PropBoundedAlways,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose bounded always ``always [lo:hi] p`` as a leaf monitor.

    The universal dual of :func:`_compose_bounded_eventually`: the operand must
    hold at EVERY in-window offset.  Counter sizing mirrors the existential form
    (``cnt_q == k-1`` at offset k).
    """
    if not isinstance(node.body, BoolExpr):
        raise UnsupportedConstruct(
            message=(
                "bounded always currently supports only a boolean-expression "
                "operand; sequence/property operands are deferred to v1.5."
            ),
            construct_name="s_always with non-boolean operand",
            source_loc=node.source_loc,
        )
    module_name = module_name_from_label(label, original_text)
    observed = extract_signals(node.body.text)
    cnt_width = max(1, math.ceil(math.log2(node.hi + 1))) if node.hi > 0 else 1
    params: dict[str, str] = {
        "module_name": module_name,
        "bool_expr": node.body.text,
        "lo": str(node.lo),
        "hi": str(node.hi),
        "cnt_width": str(cnt_width),
        "strong": "1" if node.strong else "0",
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="s_always",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )


def _compose_until(
    node: PropUntil,
    clock: ClockSpec,
    label: str | None,
    original_text: str,
    cse_origin: str | None = None,
) -> CheckerNode:
    """Compose weak ``a until b`` / ``a until_with b`` as a leaf safety monitor.

    Both operands are boolean expressions embedded directly (v1.4 Part A). The
    monitor decides each cycle from ``start`` onward: PASS when the obligation is
    discharged, FAIL when ``a`` drops before ``b`` (see :class:`PropUntil`). No
    counter is needed — the property is a pure safety FSM.
    """
    if not isinstance(node.left, BoolExpr) or not isinstance(node.right, BoolExpr):
        raise UnsupportedConstruct(
            message=(
                "until currently supports only boolean-expression operands; "
                "sequence/property operands are deferred to v1.5."
            ),
            construct_name="until with non-boolean operand",
            source_loc=node.source_loc,
        )
    module_name = module_name_from_label(label, original_text)
    left_obs = extract_signals(node.left.text)
    right_obs = extract_signals(node.right.text)
    # Ordered union (left first), preserving first-appearance order.
    seen: set[str] = set()
    observed: list[tuple[str, str]] = []
    for port, sig in (*left_obs, *right_obs):
        if port not in seen:
            seen.add(port)
            observed.append((port, sig))
    params: dict[str, str] = {
        "module_name": module_name,
        "left_expr": node.left.text,
        "right_expr": node.right.text,
        "left_signals": ",".join(p for p, _ in left_obs),
        "right_signals": ",".join(p for p, _ in right_obs),
        "with_": "1" if node.with_ else "0",
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="until",
        module_name=module_name,
        params=params,
        observed_signals=tuple(observed),
        source_loc=node.source_loc,
        children=(),
        cse_origin=cse_origin,
    )
