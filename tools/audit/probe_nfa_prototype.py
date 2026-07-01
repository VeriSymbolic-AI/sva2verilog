"""G0.2 + G0.3 + G0.4: Python-only NFA prototype + state-count analysis (v1.5).

Purpose: prove the NFA model works on paper before touching RTL.

Runs entirely in Python (no slang, no iverilog). Builds NFAs for RISK-02
targets and NFA-07 nested patterns; simulates against hand-derived
pass/fail vectors; measures state counts and reports headroom vs K ≤ 32
budget (D3).

Exit code 0 = all hand-derived vectors matched AND K ≤ 32 for every case.
Non-zero exit = spike GATE failed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

# ══════════════════════════════════════════════════════════════════════════
# Minimal NFA data model — mirrors NFA-01 IR fields (states, transitions,
# accept, nfa_kind, observed_signals) minus source_loc.
# ══════════════════════════════════════════════════════════════════════════

Guard = str  # boolean expression over signals (e.g. "a", "a & b", "~a", "1")


@dataclass(frozen=True)
class Nfa:
    """One-hot NFA: state i active ⇔ bit i in active_set."""

    states: int
    """Number of NFA states K (one-hot bits)."""

    transitions: tuple[tuple[int, Guard, int], ...]
    """(from_state, guard_expr, to_state) tuples."""

    accept: frozenset[int]
    """Set of accepting state IDs."""

    kind: str  # "sequence" or "property"
    """Fail semantic selector — see NFA-01."""

    signals: tuple[str, ...] = field(default_factory=tuple)
    """Alphabet — free variable names appearing in guards."""


# ── Guard evaluator (independent of any RTL — RISK-01) ─────────────────────

def _eval_guard(expr: Guard, sig: dict[str, bool]) -> bool:
    """Evaluate a boolean guard against a signal snapshot.

    Grammar: signal | '1' | '0' | '~' expr | expr '&' expr | expr '|' expr |
             '(' expr ')'. Precedence: ~ > & > |. Pure recursive descent,
             no external parser.
    """
    tokens = _tokenize(expr)
    pos = [0]

    def parse_or() -> bool:
        v = parse_and()
        while pos[0] < len(tokens) and tokens[pos[0]] == "|":
            pos[0] += 1
            v = v | parse_and()
        return v

    def parse_and() -> bool:
        v = parse_not()
        while pos[0] < len(tokens) and tokens[pos[0]] == "&":
            pos[0] += 1
            v = v & parse_not()
        return v

    def parse_not() -> bool:
        if pos[0] < len(tokens) and tokens[pos[0]] == "~":
            pos[0] += 1
            return not parse_not()
        return parse_atom()

    def parse_atom() -> bool:
        t = tokens[pos[0]]
        pos[0] += 1
        if t == "(":
            v = parse_or()
            assert tokens[pos[0]] == ")", f"expected ), got {tokens[pos[0]]}"
            pos[0] += 1
            return v
        if t == "1":
            return True
        if t == "0":
            return False
        return bool(sig.get(t, False))

    return parse_or()


def _tokenize(expr: Guard) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(expr):
        c = expr[i]
        if c.isspace():
            i += 1
        elif c in "()~&|":
            out.append(c)
            i += 1
        elif c.isalnum() or c == "_":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            out.append(expr[i:j])
            i = j
        else:
            raise ValueError(f"bad char {c!r} in guard {expr!r}")
    return out


# ── NFA simulator (rule-based, matches NFA-05 oracle contract) ─────────────

@dataclass
class SimResult:
    passes: list[bool]
    fails: list[bool]
    active_trace: list[frozenset[int]]


def simulate(nfa: Nfa, stim: list[dict[str, bool]]) -> SimResult:
    """Rule-based simulator for one NFA.

    Convention: each cycle receives 'start' in the stim dict; on start, {0}
    is added to active set (fresh attempt). Output for cycle t is computed
    from the next_active derived at t (matches G1.2 spec: pass on
    next_active ∩ accept ≠ ∅).
    """
    active: set[int] = set()
    passes: list[bool] = []
    fails: list[bool] = []
    trace: list[frozenset[int]] = []
    attempt_fired = False

    for step in stim:
        if step.get("start", False):
            active.add(0)
            attempt_fired = True

        # Compute next_active from current active + transitions
        next_active: set[int] = set()
        for s, guard, t in nfa.transitions:
            if s in active and _eval_guard(guard, step):
                next_active.add(t)

        passed = bool(next_active & nfa.accept)
        if nfa.kind == "property":
            failed = attempt_fired and (not next_active) and (not passed)
        else:  # sequence
            failed = False

        passes.append(passed)
        fails.append(failed)
        trace.append(frozenset(next_active))
        active = next_active
    return SimResult(passes=passes, fails=fails, active_trace=trace)


# ══════════════════════════════════════════════════════════════════════════
# NFA constructors — hand-authored from IEEE-1800 semantics (G0.4 algorithm
# reference). These are prototypes; production versions live in
# src/sva2rtl/composer.py after G2.
# ══════════════════════════════════════════════════════════════════════════

def nfa_boolean(sig: str) -> Nfa:
    """Boolean atom `x` — single-cycle sequence.

    States: 0=idle-armed, 1=matched. Accept={1}.
    """
    return Nfa(
        states=2,
        transitions=((0, sig, 1),),
        accept=frozenset({1}),
        kind="sequence",
        signals=(sig,),
    )


def nfa_delay(a: str, delay: int, b: str) -> Nfa:
    """`a ##N b` — sequence with fixed delay.

    States: 0=start, 1..N=in-flight, N+1=b-check → N+2=accept if b holds.
    Actually simpler: 0=want-a, 1..N=waiting, N=want-b, N+1=accept.
    Total states = delay + 2.
    """
    # 0 --a--> 1 (a matched); i --true--> i+1 for i in 1..delay-1 (wait);
    # delay --b--> delay+1 (b matches, accept).
    trans: list[tuple[int, Guard, int]] = []
    trans.append((0, a, 1))              # cycle 0: check a
    for i in range(1, delay):
        trans.append((i, "1", i + 1))    # cycles 1..delay-1: wait
    trans.append((delay, b, delay + 1))  # cycle delay: check b, accept
    return Nfa(
        states=delay + 2,
        transitions=tuple(trans),
        accept=frozenset({delay + 1}),
        kind="sequence",
        signals=(a, b),
    )


def nfa_repeat(sig: str, n: int) -> Nfa:
    """`sig[*N]` — N consecutive holds.

    States: 0..N; state i means "i holds observed"; accept={N}.
    """
    trans = tuple((i, sig, i + 1) for i in range(n))
    return Nfa(
        states=n + 1,
        transitions=trans,
        accept=frozenset({n}),
        kind="sequence",
        signals=(sig,),
    )


def nfa_product(left: Nfa, right: Nfa, mode: str) -> Nfa:
    """Cross-product NFA construction (G0.4 algorithm).

    Args:
      left, right: sub-NFAs
      mode: 'intersect' — accept when both accept on the same cycle
            'within'    — accept when left accepts AND right is active
            'concat_and'— just used internally; not exposed

    State mapping: state (i, j) → i*right.states + j.
    Transitions: (i,j) --gL & gR--> (i',j') iff (i --gL--> i') in left
                 AND (j --gR--> j') in right.
    """
    n_left, n_right = left.states, right.states
    k = n_left * n_right

    def sid(i: int, j: int) -> int:
        return i * n_right + j

    trans: list[tuple[int, Guard, int]] = []
    for (li, g_left, lt) in left.transitions:
        for (rj, g_right, rt) in right.transitions:
            g = f"({g_left}) & ({g_right})"
            trans.append((sid(li, rj), g, sid(lt, rt)))

    if mode == "intersect":
        accept = frozenset(sid(i, j) for i in left.accept for j in right.accept)
    elif mode == "within":
        # inner (left) accept while outer (right) is still active
        # An outer state j is "active" if it's reachable — approximate as any
        # non-accept state (still in-flight) OR accept itself (accepted this
        # cycle). Simpler formulation: accept when inner accepts AND outer
        # has at least ONE outbound transition being taken this cycle (i.e.
        # outer is not yet dead). For this prototype: accept = product
        # states where inner ∈ inner.accept AND outer any state (as long as
        # outer transitions exist from j).
        outer_alive = {j for (j, _, _) in right.transitions} | right.accept
        accept = frozenset(sid(i, j) for i in left.accept for j in outer_alive)
    else:
        raise ValueError(f"bad mode {mode!r}")

    signals = tuple(sorted(set(left.signals) | set(right.signals)))
    return Nfa(states=k, transitions=tuple(trans), accept=accept,
               kind="sequence", signals=signals)


# ══════════════════════════════════════════════════════════════════════════
# Test cases — G0.2 prototype cases + G0.3 state-count analysis
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Case:
    name: str
    build: object  # callable returning Nfa
    stim: list[dict[str, bool]]
    expected_pass: list[bool]
    note: str = ""


def _stim(cycles: int, **sig_streams: list[bool]) -> list[dict[str, bool]]:
    """Build per-cycle dict list from parallel signal streams."""
    out = []
    for c in range(cycles):
        d = {"start": True}  # pulse start every cycle
        for k, v in sig_streams.items():
            d[k] = v[c] if c < len(v) else False
        out.append(d)
    return out


def _cases() -> list[Case]:
    # Short aliases for stimulus vectors (lowercase to satisfy ruff N806).
    tt, ff = True, False

    def build_intersect() -> Nfa:
        return nfa_product(nfa_boolean("a"), nfa_boolean("b"), "intersect")

    def build_within() -> Nfa:
        return nfa_product(nfa_boolean("a"), nfa_boolean("b"), "within")

    def build_delay() -> Nfa:
        return nfa_delay("a", 2, "b")

    def build_nested_intersect_within() -> Nfa:
        # (a intersect b) within c
        inner = nfa_product(nfa_boolean("a"), nfa_boolean("b"), "intersect")
        return nfa_product(inner, nfa_boolean("c"), "within")

    def build_delay_intersect_rep() -> Nfa:
        # (a ##2 b) intersect (c[*3])
        return nfa_product(nfa_delay("a", 2, "b"), nfa_repeat("c", 3),
                           "intersect")

    def build_intersect_chain() -> Nfa:
        # (a intersect b) intersect c
        inner = nfa_product(nfa_boolean("a"), nfa_boolean("b"), "intersect")
        return nfa_product(inner, nfa_boolean("c"), "intersect")

    return [
        # ─ G0.2: primitive prototypes ────────────────────────────────────
        Case(
            name="a intersect b (TT/TF/FT/TT)",
            build=build_intersect,
            stim=_stim(4, a=[tt, tt, ff, tt], b=[tt, ff, tt, tt]),
            expected_pass=[tt, ff, ff, tt],
            note="a && b on start cycle only",
        ),
        Case(
            name="a within b (in/out)",
            build=build_within,
            stim=_stim(2, a=[tt, tt], b=[tt, ff]),
            expected_pass=[tt, ff],
            note="inner match while outer alive",
        ),
        Case(
            name="a ##2 b (delay=2)",
            build=build_delay,
            # a at cyc 0, b at cyc 2 → pass at cyc 2 (next reaches accept)
            stim=[
                {"start": True,  "a": tt, "b": ff},   # arm at 0, a taken
                {"start": False, "a": ff, "b": ff},   # in-flight
                {"start": False, "a": ff, "b": tt},   # b matches → PASS
                {"start": False, "a": ff, "b": ff},
            ],
            expected_pass=[ff, ff, tt, ff],
            note="DEMONSTRATION ONLY — production uses token-passing (D1)",
        ),
        # ─ G0.2: nested prototype ────────────────────────────────────────
        Case(
            name="(a intersect b) within c",
            build=build_nested_intersect_within,
            stim=_stim(3, a=[tt, tt, ff], b=[tt, ff, tt], c=[tt, tt, tt]),
            # Cyc 0: (a=T,b=T) inner accepts, outer c=T alive → PASS
            # Cyc 1: inner NOT (a=T,b=F) → no accept → no pass
            # Cyc 2: inner NOT (a=F,b=T) → no accept → no pass
            expected_pass=[tt, ff, ff],
            note="nested via product-of-products",
        ),
        # ─ G0.3: state-count analysis (no expected vector — check K only) ─
        Case(
            name="(a ##2 b) intersect (c[*3])",
            build=build_delay_intersect_rep,
            stim=[],
            expected_pass=[],
            note="state count check only",
        ),
        Case(
            name="(a intersect b) intersect c",
            build=build_intersect_chain,
            stim=[],
            expected_pass=[],
            note="state count check only",
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    print("=" * 72)
    print("v1.5 G0 spike — NFA Python prototype + state-count analysis")
    print("=" * 72)

    failed: list[str] = []
    max_k = 0

    for case in _cases():
        nfa: Nfa = case.build()
        max_k = max(max_k, nfa.states)
        status = f"K={nfa.states:3d}  transitions={len(nfa.transitions):3d}"

        if case.stim:
            result = simulate(nfa, case.stim)
            ok = result.passes == case.expected_pass
            marker = "OK  " if ok else "FAIL"
            if not ok:
                failed.append(case.name)
                print(f"  [{marker}] {case.name}")
                print(f"        {status}")
                print(f"        expected pass: {case.expected_pass}")
                print(f"        actual   pass: {result.passes}")
                print(f"        active trace : {result.active_trace}")
            else:
                print(f"  [{marker}] {case.name} — {status}")
        else:
            print(f"  [K   ] {case.name} — {status}")

        if nfa.states > 32:
            failed.append(f"{case.name}: K={nfa.states} > 32 budget")

    print("-" * 72)
    print(f"state-count budget: K ≤ 32  |  max observed K = {max_k}")
    print(f"status: {len(failed)} failure(s)")
    for fail_msg in failed:
        print(f"  - {fail_msg}")
    print("=" * 72)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
