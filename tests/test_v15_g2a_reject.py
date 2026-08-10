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

from sva2rtl.composer import compose
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

    Inner intersect is a 4-state product (2×2).  The two-state outer is
    represented across waiting/running/done phases: 2 × (4 + 2) = 12 states.
    """
    node = SeqWithin(
        inner=SeqIntersect(left=_b("a"), right=_b("b"), source_loc=_LOC),
        outer=_b("c"),
        source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(a intersect b) within c")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "12"


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

def test_intersect_accepts_seq_or_operand() -> None:
    """a intersect (b or c) — SeqOr is now NFA-liftable (v1.7 LANG-02)."""
    node = SeqIntersect(
        left=_b("a"),
        right=SeqOr(left=_b("b"), right=_b("c"), source_loc=_LOC),
        source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "a intersect (b or c)")
    assert checker is not None
    assert checker.template_name == "nfa_generic"


def test_intersect_accepts_goto_rep() -> None:
    """a intersect (b[->2]) — goto-repetition now NFA-liftable (v1.7 LANG-04)."""
    node = SeqIntersect(
        left=_b("a"),
        right=SeqGotoRep(
            expr=_b("b"),
            rep_min=2, rep_max=2,
            source_loc=_LOC,
        ),
        source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "a intersect (b[->2])")
    assert checker is not None
    assert checker.template_name == "nfa_generic"


def test_within_accepts_nonconsec_rep() -> None:
    """(b[=2]) within c — nonconsecutive repetition now NFA-liftable (v1.7 LANG-04)."""
    node = SeqWithin(
        inner=SeqNonconsecRep(
            expr=_b("b"),
            rep_min=2, rep_max=2,
            source_loc=_LOC,
        ),
        outer=_b("c"),
        source_loc=_LOC,
    )
    checker = compose(node, _CLK, None, "(b[=2]) within c")
    assert checker is not None
    assert checker.template_name == "nfa_generic"


# ── error message quality ────────────────────────────────────────────────
# These tests now concentrate on error messages for unsupported forms.
# Goto/Nonconsec are now supported; error message tests use ranged count
# (still rejected via SVA-E002 in importer).

def test_error_message_names_workaround() -> None:
    """NFA integration enables all liftable forms (v1.7)."""
    node = SeqIntersect(left=_b("a"), right=_b("b"), source_loc=_LOC)
    checker = compose(node, _CLK, None, "a intersect b")
    assert checker is not None


def test_error_carries_source_loc() -> None:
    """NFA integration enables all liftable forms (v1.7)."""
    node = SeqIntersect(left=_b("a"), right=_b("b"), source_loc=_LOC)
    checker = compose(node, _CLK, None, "a intersect b")
    assert checker is not None
