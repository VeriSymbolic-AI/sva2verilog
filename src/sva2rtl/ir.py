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
    """Signal function leaf: ``$rose``, ``$fell``, ``$stable``, ``$past``, or ``$changed``.

    These are edge/stability/delta detection functions that operate on a single
    signal and produce a 1-bit result.  Each maps to a small RTL template with either
    one flip-flop (rose/fell/stable/changed) or an N-stage shift register (past).

    Attributes:
        func_name:  One of ``"rose"``, ``"fell"``, ``"stable"``, ``"past"``, ``"changed"``.
        signal:     The signal name, e.g. ``"req"``.
        depth:      Pipeline depth for ``$past(sig, N)``; default ``1``.
                    Ignored for rose/fell/stable/changed.

    Example::

        SignalFunc(func_name="rose", signal="req", depth=1, source_loc=...)
        SignalFunc(func_name="past", signal="data", depth=3, source_loc=...)
        SignalFunc(func_name="changed", signal="sig", depth=1, source_loc=...)
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


@dataclass(frozen=True)
class DisableIff(SVANode):
    """``disable iff (expr) property`` — conditional disable wrapper (Phase 3+).

    When the ``condition`` is true the property evaluation is suppressed for
    that cycle: outputs gate to 0 and the internal state is synchronously
    cleared (same semantics as asserting disable_i on the underlying checker).

    Attributes:
        condition:  Boolean expression that disables the check when true.
        body:       The wrapped property or sequence.

    Example::

        // disable iff (reset_n == 0) a |-> b
        DisableIff(condition=BoolExpr(text="!reset_n", ...), body=PropImplication(...), ...)
    """

    condition: SVANode  # boolean expression for the disable condition
    body: SVANode       # the wrapped property/sequence


@dataclass(frozen=True)
class SeqFirstMatch(SVANode):
    """``first_match(seq)`` — earliest completion wins (Phase 3+ / v1.3).

    Wraps a sequence so that only the earliest possible completion is
    reported.  Once the inner sequence matches, all subsequent matches
    are suppressed.

    Attributes:
        body:  The wrapped sequence or property.

    Example::

        // first_match(a ##[1:3] b) — match at earliest b, suppress later matches
        SeqFirstMatch(body=SeqConcat(...), source_loc=...)
    """

    body: SVANode


@dataclass(frozen=True)
class SeqGotoRep(SVANode):
    """``expr[->N]`` — goto repetition (Phase 3+ / v1.3).

    N non-consecutive occurrences of *expr*.  The sequence matches
    immediately at the Nth occurrence.  Unlike ``[*N]``, the occurrences
    need not be consecutive.

    Attributes:
        expr:     Boolean expression to monitor (must be BoolExpr).
        rep_min:  Minimum occurrence count (typically == rep_max for [->N]).
        rep_max:  Maximum occurrence count.

    Example::

        // a[->3] — a must be true exactly 3 times (not consecutively)
        SeqGotoRep(expr=BoolExpr(text="a"), rep_min=3, rep_max=3, source_loc=...)
    """

    expr: SVANode
    rep_min: int
    rep_max: int


@dataclass(frozen=True)
class SeqNonconsecRep(SVANode):
    """``expr[=N]`` — non-consecutive repetition (Phase 3+ / v1.3).

    N non-consecutive occurrences of *expr*.  Similar to ``[->N]`` but
    after the Nth occurrence the sequence may end at any later cycle
    (no requirement for *expr* to become false after N matches).

    Attributes:
        expr:     Boolean expression to monitor (must be BoolExpr).
        rep_min:  Minimum occurrence count.
        rep_max:  Maximum occurrence count.

    Example::

        // a[=2] — a must be true at least 2 times (not consecutively)
        SeqNonconsecRep(expr=BoolExpr(text="a"), rep_min=2, rep_max=2, source_loc=...)
    """

    expr: SVANode
    rep_min: int
    rep_max: int


# ── Phase 3: Complex sequence operators (v1.3) ────────────────────────────


@dataclass(frozen=True)
class SeqOr(SVANode):
    """Sequence OR: ``s1 or s2`` — either sequence matches (share same start point).

    Both sequences are evaluated simultaneously from the same start.  The
    composed sequence matches when either sub-sequence matches.

    Attributes:
        left:   Left operand sequence.
        right:  Right operand sequence.
    """

    left: SVANode
    right: SVANode


@dataclass(frozen=True)
class SeqAnd(SVANode):
    """Sequence AND: ``s1 and s2`` — both sequences match (share same start point).

    Both sequences are evaluated simultaneously from the same start.  The
    composed sequence matches when both sub-sequences have matched.
    Length may differ; match at the later completion time.

    Attributes:
        left:   Left operand sequence.
        right:  Right operand sequence.
    """

    left: SVANode
    right: SVANode


@dataclass(frozen=True)
class SeqIntersect(SVANode):
    """Sequence intersect: ``s1 intersect s2`` — both complete simultaneously.

    Both sequences must start at the same time AND complete at the same
    cycle for the composed sequence to match.

    Attributes:
        left:   Left operand sequence.
        right:  Right operand sequence.
    """

    left: SVANode
    right: SVANode


@dataclass(frozen=True)
class SeqWithin(SVANode):
    """Sequence within: ``s1 within s2`` — s1 completes within s2's window.

    s1 must match entirely within the evaluation window of s2.
    s2 defines the temporal envelope.

    Attributes:
        inner:  The sequence that must complete within the outer envelope.
        outer:  The enclosing sequence defining the temporal window.
    """

    inner: SVANode
    outer: SVANode


@dataclass(frozen=True)
class SeqThroughout(SVANode):
    """Sequence throughout: ``expr throughout seq`` — expr holds throughout seq.

    The boolean expression *condition* must hold continuously for the
    entire duration of the sub-sequence *body*.

    Attributes:
        condition:  Boolean expression that must hold true.
        body:       The sequence being conditioned.
    """

    condition: SVANode  # BoolExpr
    body: SVANode


# ── Phase 4: Property operators (v1.3) ────────────────────────────────────


@dataclass(frozen=True)
class PropNot(SVANode):
    """Property not: ``not (property)`` — invert pass/fail of the wrapped property.

    Swaps the pass and fail outputs of the underlying property checker.
    Attributes:
        body:  The property to negate.
    """

    body: SVANode


@dataclass(frozen=True)
class PropIfElse(SVANode):
    """Property if-else: ``if (cond) prop1 else prop2`` — conditional property.

    Evaluates *cond* and selects which property to check: prop1 when
    cond is true, prop2 (if present) when cond is false.

    Attributes:
        condition:  Boolean selector expression.
        true_branch:  Property checked when condition is true.
        false_branch:  Property checked when condition is false (None if no else).
    """

    condition: SVANode  # BoolExpr
    true_branch: SVANode
    false_branch: SVANode | None = None


# ── v1.4 Part A: Bounded liveness ─────────────────────────────────────────


@dataclass(frozen=True)
class PropBoundedEventually(SVANode):
    """Bounded eventually: ``s_eventually [lo:hi] p`` / ``eventually [lo:hi] p``.

    A deadline-bounded EXISTENTIAL obligation: starting at the evaluation
    (``start``) cycle, the boolean property *body* must hold at SOME cycle offset
    k with ``lo <= k <= hi``.  PASS fires at the first in-window cycle where body
    holds; FAIL fires when the window closes (offset ``hi``) with no holding
    cycle.  This is distinct from a ``##[M:N]`` sequence match.

    Weak (``eventually``) and strong (``s_eventually``) bounded forms collapse to
    the same synthesizable monitor over a finite window; ``strong`` is retained
    only for faithful text reconstruction.  The operand *body* must reduce to a
    boolean expression (``BoolExpr``) in v1.4 Part A; sequence/property operands
    are rejected (deferred to the v1.5 NFA engine).  Unbounded forms (no range)
    are rejected at import time — not synthesizable on finite state.

    Attributes:
        body:    Boolean expression to satisfy within the window (BoolExpr).
        lo:      Lower window bound (cycles from start), >= 0.
        hi:      Upper window bound (cycles from start), >= lo.
        strong:  True for ``s_eventually``, False for ``eventually``.
    """

    body: SVANode
    lo: int
    hi: int
    strong: bool = True


@dataclass(frozen=True)
class PropBoundedAlways(SVANode):
    """Bounded always: ``always [lo:hi] p`` / ``s_always [lo:hi] p``.

    A deadline-bounded UNIVERSAL obligation (the dual of
    :class:`PropBoundedEventually`): starting at the evaluation (``start``) cycle,
    the boolean property *body* must hold at EVERY cycle offset k with
    ``lo <= k <= hi``.  FAIL fires at the first in-window cycle where body is
    false; PASS fires when the window closes (offset ``hi``) with no violating
    cycle.

    Over a finite window the weak (``always``) and strong (``s_always``) forms
    collapse to the same synthesizable monitor (the window always completes under
    continuous clocking); ``strong`` is retained only for faithful text
    reconstruction.  The operand *body* must reduce to a boolean expression
    (``BoolExpr``) in v1.4 Part A; sequence/property operands are rejected
    (deferred to the v1.5 NFA engine).  Unbounded forms (no range) are rejected at
    import time — not synthesizable on finite state.

    Attributes:
        body:    Boolean expression that must hold throughout the window (BoolExpr).
        lo:      Lower window bound (cycles from start), >= 0.
        hi:      Upper window bound (cycles from start), >= lo.
        strong:  True for ``s_always``, False for ``always``.
    """

    body: SVANode
    lo: int
    hi: int
    strong: bool = False


@dataclass(frozen=True)
class PropUntil(SVANode):
    """Until: ``a until b`` / ``a until_with b`` (weak forms only, v1.4 Part A).

    A SAFETY property: the left boolean operand must hold at every cycle from the
    evaluation (``start``) cycle until the right operand holds.  Two flavours:

    * ``until`` (``with_=False``): ``a`` must hold at every cycle strictly before
      the first cycle where ``b`` holds.  PASS when ``b`` first holds (``a`` having
      held throughout); FAIL at the first cycle where ``b`` is false and ``a`` is
      also false (``a`` dropped before ``b``).
    * ``until_with`` (``with_=True``): ``a`` must additionally hold at the cycle
      where ``b`` first holds.  PASS when ``a & b`` first holds; FAIL at the first
      cycle where ``a`` is false (whether or not ``b`` holds that cycle).

    Only the WEAK forms are accepted: they carry no liveness obligation (``b`` is
    not required to ever hold), so they are synthesizable as finite-state safety
    monitors.  The STRONG forms (``s_until`` / ``s_until_with``) additionally
    require ``b`` to eventually hold — an unbounded eventual obligation that is not
    synthesizable on finite state — and are rejected at import time.

    Both operands must reduce to boolean expressions (``BoolExpr``) in v1.4 Part A;
    sequence/property operands are rejected (deferred to the v1.5 NFA engine).

    Attributes:
        left:   Boolean expression that must hold until ``right`` (BoolExpr).
        right:  Boolean expression whose first occurrence discharges the obligation.
        with_:  True for ``until_with`` (``left`` required at the ``right`` cycle).
    """

    left: SVANode
    right: SVANode
    with_: bool = False


# ── v1.4.1 Part B: Multi-clock ─────────────────────────────────────────────


@dataclass(frozen=True)
class ClockedSeq(SVANode):
    """A sub-property explicitly re-clocked by a (possibly different) clock.

    Emitted by the frontend ONLY at a nested ``@(clk) ...`` boundary inside a
    MULTI-clock property (e.g. the ``@(clk2) b`` part of
    ``@(clk1) a ##1 @(clk2) b``).  Single-clock properties NEVER contain this
    node — for them the single :class:`ClockSpec` is threaded separately exactly
    as before, keeping the single-clock pipeline byte-identical.

    Marks a clock-domain switch: ``body`` is evaluated in the ``clock`` domain.
    The composer splits at this node, compiles ``body`` as a single-clock
    sub-checker on ``clock``, and inserts a 2-DFF synchronizer on the token
    crossing into this domain (IEEE-1800 allows only ``##1``/``##0`` across the
    boundary; slang enforces this).

    Attributes:
        clock:  The clock domain that ``body`` is evaluated in.
        body:   The sub-property/sequence evaluated in ``clock``'s domain.
    """

    clock: ClockSpec
    body: SVANode


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
    cse_origin: str | None = None  # named-sequence label for CSE tag (task 3.3.5)

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
                self.cse_origin,
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
            and self.cse_origin == other.cse_origin
        )
