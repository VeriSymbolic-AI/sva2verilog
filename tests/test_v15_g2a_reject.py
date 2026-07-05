"""v1.5 G2a — honesty-boundary rejection for multi-cycle intersect / within /
throughout operands.

Before G2a the composer silently accepted multi-cycle sequence operands and
generated an RTL monitor whose ``left_pass & right_pass`` (or equivalent
active-window AND) only produced the semantically-correct pass output when
both sub-sequences happened to complete on the same cycle by accident. G2a
closes that silent-wrong path with ``UnsupportedConstruct`` errors that
point the user at the exact offending operand and describe the workaround.

These tests are the permanent guard: any regression that re-opens the
silent-wrong path will surface here as an unexpected non-raise. The full
NFA path lands in G2b and un-shields the same constructs one by one.
"""

from __future__ import annotations

import pytest

from sva2rtl.composer import compose
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    SeqConcat,
    SeqGotoRep,
    SeqIntersect,
    SeqNonconsecRep,
    SeqOr,
    SeqRepetition,
    SeqWithin,
    SourceLoc,
)

_LOC = SourceLoc("g2a_reject.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(text: str) -> BoolExpr:
    return BoolExpr(text=text, source_loc=_LOC)


def _seq_concat_ab() -> SeqConcat:
    """`a ##2 b` — a multi-cycle sequence."""
    return SeqConcat(
        elements=(_b("a"), _b("b")),
        delays=((0, 0), (2, 2)),
        source_loc=_LOC,
    )


def _rep_c_3() -> SeqRepetition:
    """`c[*3]` — a multi-cycle sequence."""
    return SeqRepetition(expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC)


# ── intersect — MIGRATED (v1.5.1 P1 slice 1) ─────────────────────────────
# The 3 originally-rejected intersect cases (SeqConcat-left, SeqRepetition-
# right, both-multi-cycle) now compile successfully via the NFA path
# (`_compose_intersect_nfa` → `nfa_generic` template). Positive tests
# covering these constructs live in `tests/test_v151_nfa_intersect.py`
# (compile + oracle end-to-end). This file now only guards the shapes
# still awaiting NFA lifting in later P1 slices.


# ── within — MIGRATED (v1.5.1 P1 slice 2) ────────────────────────────────
# The 2 originally-rejected within cases (SeqConcat-inner, SeqRepetition-
# outer) now compile via ``_compose_within_nfa``. Positive tests live in
# ``tests/test_v151_nfa_within_throughout.py``.


# ── throughout — MIGRATED (v1.5.1 P1 slice 2) ────────────────────────────
# The 1 originally-rejected throughout case (multi-cycle body) now
# compiles via ``_compose_throughout_nfa`` (guards every body transition
# by the cond expression per IEEE 1800 §16.9.11). Positive tests live
# in ``tests/test_v151_nfa_within_throughout.py``.


# ── nested composition — the RISK-02 root case ───────────────────────────

def test_nested_intersect_within_compiles() -> None:
    """(a intersect b) within c — nested composition via NFA (v1.5.1 P3).

    Inner intersect is a 4-state product (2×2). Outer c is 2-state.
    Total: 4 × 2 = 8 states.
    """
    node = SeqWithin(
        inner=SeqIntersect(left=_b("a"), right=_b("b"), source_loc=_LOC),
        outer=_b("c"),
        source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(a intersect b) within c")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "8"


def test_nested_intersect_chain_compiles() -> None:
    """(a intersect b) intersect c — nested intersect chain (v1.5.1 P3).

    Inner intersect: 4 states. Outer with c: 4 × 2 = 8 states.
    """
    node = SeqIntersect(
        left=SeqIntersect(left=_b("a"), right=_b("b"), source_loc=_LOC),
        right=_b("c"),
        source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(a intersect b) intersect c")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "8"


# ── other multi-cycle shapes ─────────────────────────────────────────────

def test_intersect_rejects_or_operand() -> None:
    """a intersect (b or c) — SeqOr result is not a boolean atom."""
    node = SeqIntersect(
        left=_b("a"),
        right=SeqOr(left=_b("b"), right=_b("c"), source_loc=_LOC),
        source_loc=_LOC,
    )
    with pytest.raises(UnsupportedConstruct) as ei:
        compose(node, _CLK, None, "a intersect (b or c)")
    assert "right=SeqOr" in str(ei.value)


def test_intersect_rejects_goto_rep() -> None:
    """a intersect (b[->2]) — goto-repetition is multi-cycle."""
    node = SeqIntersect(
        left=_b("a"),
        right=SeqGotoRep(
            expr=_b("b"),
            rep_min=2, rep_max=2,
            source_loc=_LOC,
        ),
        source_loc=_LOC,
    )
    with pytest.raises(UnsupportedConstruct) as ei:
        compose(node, _CLK, None, "a intersect (b[->2])")
    assert "right=SeqGotoRep" in str(ei.value)


def test_within_rejects_nonconsec_rep() -> None:
    """(b[=2]) within c — non-consecutive repetition is multi-cycle."""
    node = SeqWithin(
        inner=SeqNonconsecRep(
            expr=_b("b"),
            rep_min=2, rep_max=2,
            source_loc=_LOC,
        ),
        outer=_b("c"),
        source_loc=_LOC,
    )
    with pytest.raises(UnsupportedConstruct) as ei:
        compose(node, _CLK, None, "(b[=2]) within c")
    assert "inner=SeqNonconsecRep" in str(ei.value)


# ── error message quality ────────────────────────────────────────────────
# Using SeqOr as the offending operand (still not NFA-lifted in P1 slice 1).

def _seq_or_bc() -> SeqOr:
    return SeqOr(left=_b("b"), right=_b("c"), source_loc=_LOC)


def test_error_message_names_workaround() -> None:
    """The error must point users at the NFA engine and the split-property workaround."""
    node = SeqIntersect(left=_b("a"), right=_seq_or_bc(), source_loc=_LOC)
    with pytest.raises(UnsupportedConstruct) as ei:
        compose(node, _CLK, None, "a intersect (b or c)")
    msg = str(ei.value)
    assert "NFA" in msg
    assert "Workaround" in msg or "split" in msg.lower()


def test_error_carries_source_loc() -> None:
    """Source loc must be threaded per pitfall P5.1."""
    node = SeqIntersect(left=_b("a"), right=_seq_or_bc(), source_loc=_LOC)
    with pytest.raises(UnsupportedConstruct) as ei:
        compose(node, _CLK, None, "a intersect (b or c)")
    assert "g2a_reject.sv:1:1" in str(ei.value)
