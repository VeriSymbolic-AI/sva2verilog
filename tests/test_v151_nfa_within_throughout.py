"""v1.5.1 P1 slice 2 — NFA-based multi-cycle within + throughout.

Migrated from ``test_v15_g2a_reject.py``: within(seq_concat, ...),
within(..., seq_rep), throughout(cond, seq_concat) now compile via
``_compose_within_nfa`` / ``_compose_throughout_nfa`` → ``nfa_generic``.

Semantic vectors hand-derived from IEEE 1800:
- within (§16.9.10): inner match cycle falls in outer's alive window
- throughout (§16.9.11): cond holds every cycle body is active
"""

from __future__ import annotations

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    SeqConcat,
    SeqRepetition,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
)

_LOC = SourceLoc("nfa_wt.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


def _passes(rs: list[dict[str, bool]]) -> list[bool]:
    return [bool(r.get("pass", False)) for r in rs]


def _sc_a2b() -> SeqConcat:
    return SeqConcat(
        elements=(_b("a"), _b("b")),
        delays=((0, 0), (2, 2)),
        source_loc=_LOC,
    )


def _rep_c3() -> SeqRepetition:
    return SeqRepetition(expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC)


# ══════════════════════════════════════════════════════════════════════
# within — compile + oracle
# ══════════════════════════════════════════════════════════════════════


def test_within_seq_concat_inner_compiles() -> None:
    """(a ##2 b) within c — was G2a-rejected, now compiles.

    K = |inner NFA| * |outer NFA| = 4 * 2 = 8.
    """
    node = SeqWithin(inner=_sc_a2b(), outer=_b("c"), source_loc=_LOC)
    checker = compose(node, _CLK, None, "(a ##2 b) within c")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "8"


def test_within_repetition_outer_compiles() -> None:
    """a within (c[*3]) — was G2a-rejected, now compiles. K = 2*4 = 8."""
    node = SeqWithin(inner=_b("a"), outer=_rep_c3(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "a within (c[*3])")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "8"


def test_within_bool_inner_rep_outer_matches() -> None:
    """a within (c[*3]) — inner a=1 while outer c[*3] is running.

    Outer c[*3] is alive across states 0..3; inner a completes on any
    cycle a=1 while outer is alive. Registered pass = 1 cycle later.

    Stim:
      t=0: start=1 a=1 c=1  → inner accepts + outer alive → pass at t=1
    """
    node = SeqWithin(inner=_b("a"), outer=_rep_c3(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "a within (c[*3])")
    stim = [
        {"start": True,  "a": True,  "c": True},   # t=0
        {"start": False, "a": False, "c": True},   # t=1 (expect pass)
        {"start": False, "a": False, "c": False},  # t=2
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert _passes(result) == [False, True, False]


def test_within_inner_completes_but_outer_dead() -> None:
    """a within c — inner a=1 but outer c=0 → no match (outer not alive)."""
    node = SeqWithin(inner=_b("a"), outer=_b("c"), source_loc=_LOC)
    checker = compose(node, _CLK, None, "a within c")
    # This is the bool-bool path, unchanged from v1.5.0.
    stim = [{"start": True, "a": True, "c": False}]
    result = simulate_checker_hierarchy(checker, stim)
    assert not _passes(result)[0]


# ══════════════════════════════════════════════════════════════════════
# throughout — compile + oracle
# ══════════════════════════════════════════════════════════════════════


def test_throughout_multi_cycle_body_compiles() -> None:
    """en throughout (a ##2 b) — was G2a-rejected, now compiles.

    K = |body NFA| = 4 (same as body — cond gates transitions).
    """
    node = SeqThroughout(condition=_b("en"), body=_sc_a2b(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "en throughout (a ##2 b)")
    assert checker.template_name == "nfa_generic"
    assert checker.params["nfa_states"] == "4"


def test_throughout_cond_holds_matches() -> None:
    """en throughout (a ##2 b) — en=1 every cycle body active → pass.

    Stim:
      t=0: start=1 en=1 a=1 b=0  → arm, take a→state 1
      t=1: en=1 a=0 b=0          → wait (transition state 1 --1&en--> 2)
      t=2: en=1 a=0 b=1          → match b, accept
      t=3: expect pass
    """
    node = SeqThroughout(condition=_b("en"), body=_sc_a2b(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "en throughout (a ##2 b)")
    stim = [
        {"start": True,  "en": True, "a": True,  "b": False},   # t=0
        {"start": False, "en": True, "a": False, "b": False},   # t=1
        {"start": False, "en": True, "a": False, "b": True},    # t=2
        {"start": False, "en": True, "a": False, "b": False},   # t=3 pass
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert _passes(result) == [False, False, False, True]


def test_throughout_cond_drops_kills_match() -> None:
    """en throughout (a ##2 b) — en=0 mid-window kills transition → no match.

    Stim:
      t=0: start=1 en=1 a=1 → take a→1
      t=1: en=0 (cond drops!) → no transition fires → thread dies
      t=2: en=1 a=0 b=1 → too late, thread is dead
    """
    node = SeqThroughout(condition=_b("en"), body=_sc_a2b(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "en throughout (a ##2 b)")
    stim = [
        {"start": True,  "en": True,  "a": True,  "b": False},
        {"start": False, "en": False, "a": False, "b": False},
        {"start": False, "en": True,  "a": False, "b": True},
        {"start": False, "en": True,  "a": False, "b": False},
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert all(not p for p in _passes(result))


def test_throughout_cond_drops_at_body_completion() -> None:
    """en throughout (a ##2 b) — en=0 on final b-cycle → no match."""
    node = SeqThroughout(condition=_b("en"), body=_sc_a2b(), source_loc=_LOC)
    checker = compose(node, _CLK, None, "en throughout (a ##2 b)")
    stim = [
        {"start": True,  "en": True,  "a": True,  "b": False},
        {"start": False, "en": True,  "a": False, "b": False},
        {"start": False, "en": False, "a": False, "b": True},   # en=0 at match
        {"start": False, "en": True,  "a": False, "b": False},
    ]
    result = simulate_checker_hierarchy(checker, stim)
    assert all(not p for p in _passes(result))
