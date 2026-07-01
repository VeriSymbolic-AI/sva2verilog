"""v1.5 G1 — extra independent baseline gate for RISK-02 closure.

Extends ``test_v13_independent_baseline.py`` with the exhaustive TT/TF/FT/FF
truth table for boolean-atom ``intersect`` and ``within``, plus 4 additional
``within`` shape variations.  All expected outputs are hand-derived from
IEEE 1800 semantics (RISK-01 independent authoring), NOT read off the RTL
implementation.

These 8 tests must all PASS after G1 (RISK-02 xfails flipped).  A future
regression in the operand-truth path (e.g. G2 refactor accidentally re-
introducing the "always pass" leaf) would show up here immediately, so the
tests double as a permanent guard rail for the fix.
"""

from __future__ import annotations

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    SeqIntersect,
    SeqWithin,
    SourceLoc,
)

_LOC = SourceLoc("v15_risk02.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(text: str) -> BoolExpr:
    return BoolExpr(text=text, source_loc=_LOC)


def _passes(results: list[dict[str, bool]]) -> list[bool]:
    return [bool(r.get("pass", False)) for r in results]


def _intersect_checker() -> object:
    return compose(
        SeqIntersect(left=_b("a"), right=_b("b"), source_loc=_LOC),
        _CLK, "risk02_intersect", "a intersect b",
    )


def _within_checker() -> object:
    return compose(
        SeqWithin(inner=_b("a"), outer=_b("b"), source_loc=_LOC),
        _CLK, "risk02_within", "a within b",
    )


# ══════════════════════════════════════════════════════════════════════════════
# intersect — full truth table (TT/TF/FT/FF).  Each row is one attempt (start
# pulsed every cycle for independence).  For single-cycle boolean sequences,
# `a intersect b` matches iff a && b hold on the same cycle.
# ══════════════════════════════════════════════════════════════════════════════


def test_intersect_tt_passes() -> None:
    """a=1 b=1 -> both complete same cycle -> PASS."""
    stim = [{"start": True, "a": True, "b": True}]
    assert _passes(simulate_checker_hierarchy(_intersect_checker(), stim)) == [True]


def test_intersect_tf_no_pass() -> None:
    """a=1 b=0 -> b does not complete -> no pass (vacuous drop, NOT fail)."""
    stim = [{"start": True, "a": True, "b": False}]
    assert _passes(simulate_checker_hierarchy(_intersect_checker(), stim)) == [False]


def test_intersect_ft_no_pass() -> None:
    """a=0 b=1 -> a does not complete -> no pass."""
    stim = [{"start": True, "a": False, "b": True}]
    assert _passes(simulate_checker_hierarchy(_intersect_checker(), stim)) == [False]


def test_intersect_ff_no_pass() -> None:
    """a=0 b=0 -> neither completes -> no pass."""
    stim = [{"start": True, "a": False, "b": False}]
    assert _passes(simulate_checker_hierarchy(_intersect_checker(), stim)) == [False]


# ══════════════════════════════════════════════════════════════════════════════
# within — 4 shapes covering: inner-inside-outer (pass), inner-outside-outer
# (no pass), only-outer (no pass, inner never matches), only-inner (no pass,
# outer never active).
# ══════════════════════════════════════════════════════════════════════════════


def test_within_inner_and_outer_true_passes() -> None:
    """a=1 b=1 -> inner matches while outer active -> PASS."""
    stim = [{"start": True, "a": True, "b": True}]
    assert _passes(simulate_checker_hierarchy(_within_checker(), stim)) == [True]


def test_within_inner_true_outer_false_no_pass() -> None:
    """a=1 b=0 -> outer not active in match cycle -> no pass."""
    stim = [{"start": True, "a": True, "b": False}]
    assert _passes(simulate_checker_hierarchy(_within_checker(), stim)) == [False]


def test_within_inner_false_outer_true_no_pass() -> None:
    """a=0 b=1 -> inner never matches -> no pass."""
    stim = [{"start": True, "a": False, "b": True}]
    assert _passes(simulate_checker_hierarchy(_within_checker(), stim)) == [False]


def test_within_inner_false_outer_false_no_pass() -> None:
    """a=0 b=0 -> neither matches nor outer active -> no pass."""
    stim = [{"start": True, "a": False, "b": False}]
    assert _passes(simulate_checker_hierarchy(_within_checker(), stim)) == [False]
