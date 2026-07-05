"""v1.5.1 P1 slice 1 — NFA-based multi-cycle intersect (positive tests).

Migrated from ``test_v15_g2a_reject.py``: the three intersect cases that
were rejected in v1.5.0 (SeqConcat operand, SeqRepetition operand, both)
now compile successfully via ``_compose_intersect_nfa`` → ``nfa_generic``.

Each test exercises the full pipeline: IR → composer (NFA product) →
oracle simulation with hand-derived pass vectors independently derived
from IEEE 1800 §16.9.7.

The RTL side (nfa_generic template) is cross-checked separately by
``tests/simulation/test_sim_nfa_intersect.py`` (iverilog) and — per
v1.5.1-ROADMAP P1.7 — by 4 sby BMC miters against a hand-authored IEEE
reference. Those layers arrive in the next commits of this slice.
"""

from __future__ import annotations

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    SeqConcat,
    SeqIntersect,
    SeqRepetition,
    SourceLoc,
)

_LOC = SourceLoc("nfa_intersect.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


def _passes(results: list[dict[str, bool]]) -> list[bool]:
    return [bool(r.get("pass", False)) for r in results]


def _seq_a_dd2_b() -> SeqConcat:
    """`a ##2 b` — 4-state NFA (0 --a--> 1 --1--> 2 --b--> 3)."""
    return SeqConcat(
        elements=(_b("a"), _b("b")),
        delays=((0, 0), (2, 2)),
        source_loc=_LOC,
    )


def _rep_c_star_3() -> SeqRepetition:
    """`c[*3]` — 4-state NFA (0 --c--> 1 --c--> 2 --c--> 3)."""
    return SeqRepetition(expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC)


# ══════════════════════════════════════════════════════════════════════════
# Compile-time checks — the NFA path replaces the v1.5.0 hard-reject.
# ══════════════════════════════════════════════════════════════════════════


def test_intersect_seq_concat_left_compiles() -> None:
    """(a ##2 b) intersect c — was G2a-rejected, now compiles via NFA.

    K = |left NFA| * |right NFA| = 4 * 2 = 8.
    """
    node = SeqIntersect(left=_seq_a_dd2_b(), right=_b("c"), source_loc=_LOC)
    checker = compose(node, _CLK, None, "(a ##2 b) intersect c")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "8"
    assert checker.params["nfa_kind"] == "sequence"


def test_intersect_repetition_right_compiles() -> None:
    """a intersect (c[*3]) — was G2a-rejected, now compiles via NFA.

    K = 2 * 4 = 8.
    """
    node = SeqIntersect(left=_b("a"), right=_rep_c_star_3(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "a intersect (c[*3])")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "8"


def test_intersect_both_multi_cycle_compiles() -> None:
    """(a ##2 b) intersect (c[*3]) — was G2a-rejected, now compiles via NFA.

    K = 4 * 4 = 16. Verified in the G0 Python NFA prototype
    (``tools/audit/probe_nfa_prototype.py``) as the max-K NFA-07 case.
    """
    node = SeqIntersect(
        left=_seq_a_dd2_b(), right=_rep_c_star_3(), source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(a ##2 b) intersect (c[*3])")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "16"


# ══════════════════════════════════════════════════════════════════════════
# Oracle-level correctness — hand-derived pass vectors per IEEE 1800.
# 1-cycle registered latency: pass fires on cycle t iff accept was reached
# on cycle t-1's next-state computation.
# ══════════════════════════════════════════════════════════════════════════


def test_intersect_seq_concat_and_rep_matches_when_aligned() -> None:
    """(a ##2 b) intersect (c[*3]) — pass when both complete at same cycle.

    Stimulus:
      t=0: start=1, a=1, c=1 (left arms with a, right consumes c #1)
      t=1: start=0, a=0, c=1 (left waits, right consumes c #2)
      t=2: start=0, a=0, b=1, c=1 (left checks b match, right c #3 → both accept)
      t=3: expect PASS (registered 1 cycle after accept).
    """
    node = SeqIntersect(
        left=_seq_a_dd2_b(), right=_rep_c_star_3(), source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(a ##2 b) intersect (c[*3])")
    stim = [
        {"start": True,  "a": True,  "b": False, "c": True},   # t=0
        {"start": False, "a": False, "b": False, "c": True},   # t=1
        {"start": False, "a": False, "b": True,  "c": True},   # t=2 (accept)
        {"start": False, "a": False, "b": False, "c": False},  # t=3 (pass)
        {"start": False, "a": False, "b": False, "c": False},  # t=4
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert _passes(result) == [False, False, False, True, False]


def test_intersect_seq_concat_no_match_when_b_missing() -> None:
    """(a ##2 b) intersect (c[*3]) — no match if left never completes (b=0).

    Vacuous drop (sequence NFA never fires fail), so pass must stay 0.
    """
    node = SeqIntersect(
        left=_seq_a_dd2_b(), right=_rep_c_star_3(), source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(a ##2 b) intersect (c[*3])")
    stim = [
        {"start": True,  "a": True,  "b": False, "c": True},
        {"start": False, "a": False, "b": False, "c": True},
        {"start": False, "a": False, "b": False, "c": True},   # b=0 → no left match
        {"start": False, "a": False, "b": False, "c": False},
        {"start": False, "a": False, "b": False, "c": False},
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert all(not p for p in _passes(result))


def test_intersect_seq_concat_no_match_when_c_drops() -> None:
    """(a ##2 b) intersect (c[*3]) — no match if right's c drops mid-window."""
    node = SeqIntersect(
        left=_seq_a_dd2_b(), right=_rep_c_star_3(), source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(a ##2 b) intersect (c[*3])")
    stim = [
        {"start": True,  "a": True,  "b": False, "c": True},
        {"start": False, "a": False, "b": False, "c": False},  # c=0 → break rep
        {"start": False, "a": False, "b": True,  "c": True},
        {"start": False, "a": False, "b": False, "c": False},
        {"start": False, "a": False, "b": False, "c": False},
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert all(not p for p in _passes(result))


def test_intersect_left_multi_right_bool_asymmetric() -> None:
    """(a ##2 b) intersect c — length mismatch: left takes 3 cycles, right 1.

    IEEE 1800 §16.9.7: both must complete on the SAME cycle. Since left
    always takes 3 cycles and right (single boolean) always completes on
    its start cycle, the intersect is UNSATISFIABLE — never passes.
    """
    node = SeqIntersect(left=_seq_a_dd2_b(), right=_b("c"), source_loc=_LOC)
    checker = compose(node, _CLK, None, "(a ##2 b) intersect c")
    stim = [
        {"start": True,  "a": True,  "b": False, "c": True},
        {"start": False, "a": False, "b": False, "c": True},
        {"start": False, "a": False, "b": True,  "c": True},
        {"start": False, "a": False, "b": False, "c": False},
        {"start": False, "a": False, "b": False, "c": False},
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert all(not p for p in _passes(result))


def test_intersect_bool_left_rep_right_asymmetric() -> None:
    """a intersect (c[*3]) — same asymmetry: left is 1 cycle, right is 3.

    Never passes.
    """
    node = SeqIntersect(left=_b("a"), right=_rep_c_star_3(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "a intersect (c[*3])")
    stim = [
        {"start": True,  "a": True,  "c": True},
        {"start": False, "a": True,  "c": True},
        {"start": False, "a": True,  "c": True},
        {"start": False, "a": False, "c": False},
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert all(not p for p in _passes(result))
