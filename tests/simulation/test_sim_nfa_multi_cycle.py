"""v1.5.1 P1 slice 3 — dual-oracle iverilog simulation for NFA-composed
multi-cycle intersect / within / throughout.

Each test:
  1. Builds the operator IR (with SeqConcat or SeqRepetition operands that
     were G2a-rejected in v1.5.0 and unlocked in v1.5.1 P1 slices 1+2).
  2. Compiles it end-to-end (composer → emit_all → nfa_generic template).
  3. Runs iverilog on a stimulus vector.
  4. Runs the independent rule-based oracle
     (``simulate_checker_hierarchy`` → ``_tick_nfa_generic``) on the SAME
     stimulus.
  5. Asserts the pass/fail bit-patterns match cycle-for-cycle — a strict
     RISK-01-safe cross-check because oracle and RTL are derived from
     INDEPENDENT sources (rule-based thread simulator vs. one-hot FSM).

If either side implements a wrong semantic, the mismatch surfaces here.

Requires iverilog on PATH; skipped otherwise (see conftest.py).

Covers v1.5.1-ROADMAP P1.8 (12 stimuli across 3 operators × 4 shapes).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockSpec,
    SeqConcat,
    SeqIntersect,
    SeqRepetition,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
)
from tests.simulation.tb_generator import (
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_LOC = SourceLoc("sim_nfa.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


def _sc_a2b() -> SeqConcat:
    """`a ##2 b` — 4-state sub-NFA."""
    return SeqConcat(
        elements=(_b("a"), _b("b")),
        delays=((0, 0), (2, 2)),
        source_loc=_LOC,
    )


def _rep_c3() -> SeqRepetition:
    """`c[*3]` — 4-state sub-NFA."""
    return SeqRepetition(expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC)


def _pad(stim: list[dict[str, Any]], n: int = 4) -> list[dict[str, Any]]:
    keys: set[str] = set()
    for s in stim:
        keys.update(s.keys())
    idle: dict[str, Any] = {k: False for k in keys}
    return stim + [idle.copy() for _ in range(n)]


def _run_stimulus(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str = "iverilog",
) -> list[dict[str, Any]]:
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=False,
    )
    return run_simulation(
        simulator=simulator,
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=False,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
    )


def _bits(results: list[dict[str, Any]], key: str) -> list[bool]:
    return [bool(r.get(key, False)) for r in results]


def _dual_oracle_check(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str,
) -> tuple[list[bool], list[bool]]:
    """Run RTL and oracle on the same stimulus; return their pass-bit vectors.

    Both vectors must match cycle-for-cycle. The pair is returned so tests
    can additionally assert a semantic expectation (at least one pass, or
    exactly one pass at cycle t, etc.).
    """
    rtl = _run_stimulus(checker, stimulus, tmp_path, simulator)
    oracle = simulate_checker_hierarchy(checker, stimulus)

    # Truncate to shorter length: iverilog may report an extra final settle
    # cycle beyond len(stimulus); oracle stops exactly at len(stimulus).
    n = min(len(rtl), len(oracle))
    rtl_pass = _bits(rtl[:n], "pass")
    oracle_pass = _bits(oracle[:n], "pass")

    assert rtl_pass == oracle_pass, (
        f"pass mismatch: rtl={rtl_pass} oracle={oracle_pass}"
    )
    return rtl_pass, oracle_pass


# ═════════════════════════════════════════════════════════════════════════
# intersect — 4 stimuli
# ═════════════════════════════════════════════════════════════════════════


class TestNfaIntersectSim:
    """`(a ##2 b) intersect (c[*3])` — both operands are 4-state; K=16.

    IEEE 1800 §16.9.7: intersect matches iff both operands succeed and end
    on the SAME cycle. `a ##2 b` and `c[*3]` are both length-3, so a
    simultaneous start with a=1, then any middle, then b=1 & c=1 on the
    third cycle should match.
    """

    def _checker(self) -> CheckerNode:
        node = SeqIntersect(left=_sc_a2b(), right=_rep_c3(), source_loc=_LOC)
        return compose(node, _CLK, None, "(a ##2 b) intersect (c[*3])")

    def test_both_end_together_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """t=0 start & a; t=1 c only; t=2 b & c → both complete t=2."""
        stim = _pad([
            {"start": True,  "a": True,  "b": False, "c": True},   # t=0
            {"start": False, "a": False, "b": False, "c": True},   # t=1
            {"start": False, "a": False, "b": True,  "c": True},   # t=2
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert any(rtl_pass), "expected at least one pass"

    def test_left_incomplete_no_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """b never asserts → left never completes → no pass."""
        stim = _pad([
            {"start": True,  "a": True,  "b": False, "c": True},
            {"start": False, "a": False, "b": False, "c": True},
            {"start": False, "a": False, "b": False, "c": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)

    def test_right_incomplete_no_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """c drops mid-run → c[*3] never completes → no pass."""
        stim = _pad([
            {"start": True,  "a": True,  "b": False, "c": True},
            {"start": False, "a": False, "b": False, "c": False},
            {"start": False, "a": False, "b": True,  "c": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)

    def test_no_start_no_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """Never pulse start → NFA idle → no pass."""
        stim = _pad([
            {"start": False, "a": True,  "b": True,  "c": True},
            {"start": False, "a": True,  "b": True,  "c": True},
            {"start": False, "a": True,  "b": True,  "c": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)


# ═════════════════════════════════════════════════════════════════════════
# within — 4 stimuli
# ═════════════════════════════════════════════════════════════════════════


class TestNfaWithinSim:
    """`a within (c[*3])` — inner is 2-state (a), outer is 4-state; K=8.

    IEEE 1800 §16.9.10: `inner within outer` = outer starts before or with
    inner-start AND ends at-or-after inner-end. With inner = bool a,
    completion is single-cycle, so any cycle a=1 while outer is alive
    yields a match.
    """

    def _checker(self) -> CheckerNode:
        node = SeqWithin(
            inner=_b("a"), outer=_rep_c3(), source_loc=_LOC,
        )
        return compose(node, _CLK, None, "a within (c[*3])")

    def test_a_and_c_aligned_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """t=0 start & a & c → inner completes while outer alive."""
        stim = _pad([
            {"start": True,  "a": True,  "c": True},
            {"start": False, "a": False, "c": True},
            {"start": False, "a": False, "c": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert any(rtl_pass)

    def test_outer_dead_before_inner(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """c=0 at t=0 → outer c[*3] dies immediately → no pass."""
        stim = _pad([
            {"start": True,  "a": True,  "c": False},
            {"start": False, "a": True,  "c": True},
            {"start": False, "a": True,  "c": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)

    def test_inner_may_start_after_outer_start(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """The inner sequence can begin on any cycle inside the outer window."""
        stim = _pad([
            {"start": True,  "a": False, "c": True},
            {"start": False, "a": True,  "c": True},
            {"start": False, "a": False, "c": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert sum(rtl_pass) == 1

    def test_inner_never_true_no_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """a always 0 → inner never completes → no match."""
        stim = _pad([
            {"start": True,  "a": False, "c": True},
            {"start": False, "a": False, "c": True},
            {"start": False, "a": False, "c": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)


# ═════════════════════════════════════════════════════════════════════════
# throughout — 4 stimuli
# ═════════════════════════════════════════════════════════════════════════


class TestNfaThroughoutSim:
    """`en throughout (a ##2 b)` — cond gates each body transition; K=4.

    IEEE 1800 §16.9.11: cond must hold on every cycle the body sequence is
    alive. This is the classic "hold enable" pattern.
    """

    def _checker(self) -> CheckerNode:
        node = SeqThroughout(
            condition=_b("en"), body=_sc_a2b(), source_loc=_LOC,
        )
        return compose(node, _CLK, None, "en throughout (a ##2 b)")

    def test_en_holds_all_cycles_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """en=1 t=0..2, a=1 t=0, b=1 t=2 → body completes with cond held."""
        stim = _pad([
            {"start": True,  "en": True,  "a": True,  "b": False},
            {"start": False, "en": True,  "a": False, "b": False},
            {"start": False, "en": True,  "a": False, "b": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert any(rtl_pass)

    def test_en_lost_mid_body_no_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """en=0 at t=1 while body alive → cond violated → no pass."""
        stim = _pad([
            {"start": True,  "en": True,  "a": True,  "b": False},
            {"start": False, "en": False, "a": False, "b": False},
            {"start": False, "en": True,  "a": False, "b": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)

    def test_body_dies_no_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """b never asserts → body ##2 b never completes → no pass."""
        stim = _pad([
            {"start": True,  "en": True,  "a": True,  "b": False},
            {"start": False, "en": True,  "a": False, "b": False},
            {"start": False, "en": True,  "a": False, "b": False},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)

    def test_en_zero_at_start_no_pass(
        self, tmp_path: Path, simulator: str,
    ) -> None:
        """en=0 at start cycle → body first transition blocked → no pass."""
        stim = _pad([
            {"start": True,  "en": False, "a": True,  "b": False},
            {"start": False, "en": True,  "a": False, "b": False},
            {"start": False, "en": True,  "a": False, "b": True},
        ])
        rtl_pass, _ = _dual_oracle_check(
            self._checker(), stim, tmp_path, simulator,
        )
        assert not any(rtl_pass)
