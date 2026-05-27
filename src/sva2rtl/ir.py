"""SVA intermediate representation — frozen dataclasses for the compiler pipeline.

All IR nodes are immutable (frozen=True) and hashable, enabling structural CSE
(common subexpression elimination) across compilation passes.

SourceLoc is a required field on every SVANode subclass — this prevents pitfall
P5.1 (source location not threaded) and is enforced from Phase 1.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceLoc:
    """Source location from slang AST, threaded through the entire pipeline.

    Prevents pitfall P5.1: if source location is not carried on every node,
    error messages can only point to generated RTL line numbers, not the
    original SVA source.
    """

    file: str
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"


# ── SVA IR Node hierarchy ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SVANode:
    """Base class for all SVA IR nodes.

    Every concrete node must carry a source_loc so that errors at any stage
    of the pipeline can be reported with the original SVA file/line/column.
    """

    source_loc: SourceLoc


@dataclass(frozen=True)
class BoolExpr(SVANode):
    """Leaf node: a purely boolean SVA property (no temporal operators).

    ``text`` is the verbatim reconstructed SV expression for embedding in RTL.
    The AST importer reconstructs this text by recursive descent over the
    slang JSON AST.

    Example::

        BoolExpr(text="(a && b)", source_loc=SourceLoc("foo.sv", 3, 5))
    """

    text: str  # reconstructed SV boolean expression, ready for RTL embedding


@dataclass(frozen=True)
class SeqConcat(SVANode):
    """Sequence concatenation: ``s1 ##N s2`` (Phase 2+).

    In Phase 1 the importer raises ``UnsupportedConstruct`` when it encounters
    this node kind.  The class is defined here so that Phase 2 can reference it
    without changing the IR module interface.

    ``delays[i]`` is the ``(min, max)`` cycle delay between ``elements[i]`` and
    ``elements[i+1]``.  For a fixed delay ``##N`` both values are ``N``.
    """

    elements: tuple[SVANode, ...]
    delays: tuple[tuple[int, int], ...]  # (min, max) delay between elements


@dataclass(frozen=True)
class SeqRepetition(SVANode):
    """Consecutive repetition: ``expr[*N]`` or ``expr[*M:N]`` (Phase 3+).

    ``rep_min`` and ``rep_max`` are the lower and upper bounds of the
    repetition count.  For a fixed repetition ``[*N]`` both equal N.
    Unbounded ``[*0:$]`` is rejected at import time with SVA-E002.

    Example::

        SeqRepetition(expr=BoolExpr(text="a", ...), rep_min=3, rep_max=3, ...)
    """

    expr: SVANode
    rep_min: int
    rep_max: int


@dataclass(frozen=True)
class SignalFunc(SVANode):
    """Signal function leaf: ``$rose``, ``$fell``, ``$stable``, or ``$past`` (Phase 3+).

    These are edge/stability detection functions that operate on a single signal
    and produce a 1-bit result.  Each maps to a small RTL template with either
    one flip-flop (rose/fell/stable) or an N-stage shift register (past).

    Attributes:
        func_name:  One of ``"rose"``, ``"fell"``, ``"stable"``, ``"past"``.
        signal:     The signal name, e.g. ``"req"``.
        depth:      Pipeline depth for ``$past(sig, N)``; default ``1``.
                    Ignored for rose/fell/stable.

    Example::

        SignalFunc(func_name="rose", signal="req", depth=1, source_loc=...)
        SignalFunc(func_name="past", signal="data", depth=3, source_loc=...)
    """

    func_name: str   # "rose" | "fell" | "stable" | "past"
    signal: str      # signal name referenced by the function
    depth: int = 1   # pipeline depth for $past; 1 for all others


@dataclass(frozen=True)
class PropImplication(SVANode):
    """Overlapping (``|->``) or non-overlapping (``|=>``) implication (Phase 2+).

    In Phase 1 the importer raises ``UnsupportedConstruct`` for this construct.
    """

    antecedent: SVANode
    consequent: SVANode
    overlapping: bool = True  # False means |=>


# ── Clocking ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClockSpec:
    """Extracted clock event from ``@(posedge clk)`` or ``@(negedge clk)``.

    Extracted once per property and threaded into every emitted template.
    Kept separate from SVANode because the clock is a cross-cutting concern,
    not part of the property tree itself.
    """

    edge: str  # "posedge" or "negedge"
    signal: str  # clock signal name, e.g. "clk"
    source_loc: SourceLoc


# ── CheckerNode: IR-to-RTL bridge ─────────────────────────────────────────


@dataclass(frozen=True)
class CheckerNode:
    """Represents one instantiated template in the RTL module hierarchy.

    Carries all information the emitter needs to render the Jinja2 template
    and the instantiation wiring.

    Standard port contract (every generated checker module exposes all ports):

    * ``clk``           — clock input
    * ``rst_n``         — active-low synchronous reset
    * ``start``         — pulse to begin evaluation this cycle
    * ``active``        — evaluation is currently in progress (registered)
    * ``pass``          — check passed this cycle (registered)
    * ``fail``          — check failed this cycle (registered)
    * ``attempt_fired`` — sticky: set on first ``start`` pulse, never cleared
                          except by reset.  Prevents vacuous-satisfaction
                          (pitfall P1.1): a monitor with ``start`` never pulsed
                          has ``pass=0, fail=0`` which looks like "no failures"
                          but actually means "nothing was checked."

    Attributes:
        template_name:      Jinja2 template file stem, e.g. ``"bool_expr"``.
        module_name:        Emitted SV module name, e.g. ``"sva_my_check"``.
        params:             Template parameter dict (strings for Jinja2 compatibility).
        observed_signals:   ``(port_name, dut_signal_name)`` pairs used by
                            the bind-statement generator.
        source_loc:         Source location of the originating SVA assertion.
        children:           Sub-checker modules wired into this one (for
                            hierarchical composition in Phase 2+).
    """

    template_name: str
    module_name: str
    params: dict[str, str]  # Jinja2 template params; dict for template ergonomics
    observed_signals: tuple[tuple[str, str], ...]  # (port_name, signal_name)
    source_loc: SourceLoc
    children: tuple[CheckerNode, ...] = ()

    # params is a mutable dict, which prevents the auto-generated __hash__ and
    # __eq__ from working correctly on a frozen dataclass.  We override them
    # explicitly using an immutable representation of params.

    def __hash__(self) -> int:
        return hash(
            (
                self.template_name,
                self.module_name,
                frozenset(self.params.items()),
                self.observed_signals,
                self.source_loc,
                self.children,
            )
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CheckerNode):
            return NotImplemented
        return (
            self.template_name == other.template_name
            and self.module_name == other.module_name
            and frozenset(self.params.items()) == frozenset(other.params.items())
            and self.observed_signals == other.observed_signals
            and self.source_loc == other.source_loc
            and self.children == other.children
        )
