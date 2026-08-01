"""v1.5.1 P2 slice 2 — dual-oracle iverilog simulation for NFA implication.

Each test builds an implication with multi-cycle consequent, runs BOTH
iverilog RTL and behavioral oracle on the same stimulus, and asserts
pass-bit vectors match cycle-for-cycle.

Covers: |-> and |=> with SeqConcat / SeqRepetition consequents.
Requires iverilog on PATH; skipped otherwise.
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
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SourceLoc,
)
from tests.simulation.tb_generator import (
    TEMPLATES_WITH_OVERFLOW,
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_LOC = SourceLoc("sim_p2.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


def _pad(stim: list[dict[str, Any]], n: int = 4) -> list[dict[str, Any]]:
    keys: set[str] = set()
    for s in stim:
        keys.update(s.keys())
    idle = {k: False for k in keys}
    return stim + [idle.copy() for _ in range(n)]


def _run_stimulus(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str = "iverilog",
) -> list[dict[str, Any]]:
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    has_overflow = checker.template_name in TEMPLATES_WITH_OVERFLOW
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=checker.params["clock_signal"],
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=has_overflow,
    )
    return run_simulation(
        simulator=simulator,
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=has_overflow,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
    )


def _bits(results: list[dict[str, Any]], key: str) -> list[bool]:
    return [bool(r.get(key, False)) for r in results]


def _dual_check(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str,
    key: str = "pass",
) -> tuple[list[bool], list[bool]]:
    rtl = _run_stimulus(checker, stimulus, tmp_path, simulator)
    oracle = simulate_checker_hierarchy(checker, stimulus)
    n = min(len(rtl), len(oracle))
    rtl_vec = _bits(rtl[:n], key)
    oracle_vec = _bits(oracle[:n], key)
    assert rtl_vec == oracle_vec, f"{key} mismatch: rtl={rtl_vec} oracle={oracle_vec}"
    return rtl_vec, oracle_vec


# ═════════════════════════════════════════════════════════════════════════
# |-> overlapping — b ##2 c
# ═════════════════════════════════════════════════════════════════════════


class TestOverlapImplNfaSim:
    def _checker(self) -> CheckerNode:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),),
                source_loc=_LOC,
            ),
            overlapping=True,
            source_loc=_LOC,
        )
        return compose(node, _CLK, None, "a |-> b ##2 c")

    def test_pass_path(self, tmp_path: Path, simulator: str) -> None:
        stim = _pad(
            [
                {"start": True, "a": True, "b": True, "c": False},
                {"start": False, "a": False, "b": False, "c": False},
                {"start": False, "a": False, "b": False, "c": True},
                {"start": False, "a": False, "b": False, "c": False},
            ]
        )
        rtl_pass, _ = _dual_check(self._checker(), stim, tmp_path, simulator)
        assert any(rtl_pass)
        rtl_fail, _ = _dual_check(self._checker(), stim, tmp_path, simulator, "fail")
        assert not any(rtl_fail)

    def test_consequent_incomplete_no_pass(
        self,
        tmp_path: Path,
        simulator: str,
    ) -> None:
        stim = _pad(
            [
                {"start": True, "a": True, "b": True, "c": False},
                {"start": False, "a": False, "b": False, "c": False},
                {"start": False, "a": False, "b": False, "c": False},
            ]
        )
        rtl_pass, _ = _dual_check(self._checker(), stim, tmp_path, simulator)
        assert not any(rtl_pass)

    def test_dead_attempt_fails_once(self, tmp_path: Path, simulator: str) -> None:
        stim = _pad(
            [
                {"start": True, "a": True, "b": False, "c": False},
                {"start": False, "a": False, "b": False, "c": False},
            ]
        )
        rtl_fail, _ = _dual_check(self._checker(), stim, tmp_path, simulator, "fail")
        assert sum(rtl_fail) == 1

    def test_slot_exhaustion_is_fail_closed(
        self,
        tmp_path: Path,
        simulator: str,
    ) -> None:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((5, 5),),
                source_loc=_LOC,
            ),
            overlapping=True,
            source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |-> b ##5 c")
        stim = _pad([{"start": True, "a": True, "b": True, "c": False} for _ in range(5)])
        rtl_overflow, _ = _dual_check(checker, stim, tmp_path, simulator, "overflow")
        rtl_fail, _ = _dual_check(checker, stim, tmp_path, simulator, "fail")
        assert any(rtl_overflow)
        assert any(rtl_fail)


# ═════════════════════════════════════════════════════════════════════════
# |-> overlapping — b[*3]
# ═════════════════════════════════════════════════════════════════════════


class TestOverlapImplNfaRepSim:
    def _checker(self) -> CheckerNode:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqRepetition(
                expr=_b("b"),
                rep_min=3,
                rep_max=3,
                source_loc=_LOC,
            ),
            overlapping=True,
            source_loc=_LOC,
        )
        return compose(node, _CLK, None, "a |-> b[*3]")

    def test_pass_path(self, tmp_path: Path, simulator: str) -> None:
        stim = _pad(
            [
                {"start": True, "a": True, "b": True},
                {"start": False, "a": False, "b": True},
                {"start": False, "a": False, "b": True},
                {"start": False, "a": False, "b": False},
            ]
        )
        rtl_pass, _ = _dual_check(self._checker(), stim, tmp_path, simulator)
        assert any(rtl_pass)

    def test_incomplete_no_pass(
        self,
        tmp_path: Path,
        simulator: str,
    ) -> None:
        stim = _pad(
            [
                {"start": True, "a": True, "b": True},
                {"start": False, "a": False, "b": True},
                {"start": False, "a": False, "b": False},
            ]
        )
        rtl_pass, _ = _dual_check(self._checker(), stim, tmp_path, simulator)
        assert not any(rtl_pass)


# ═════════════════════════════════════════════════════════════════════════
# |=> non-overlapping — b ##2 c
# ═════════════════════════════════════════════════════════════════════════


class TestNonoverlapImplNfaSim:
    def _checker(self) -> CheckerNode:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),),
                source_loc=_LOC,
            ),
            overlapping=False,
            source_loc=_LOC,
        )
        return compose(node, _CLK, None, "a |=> b ##2 c")

    def test_pass_path(self, tmp_path: Path, simulator: str) -> None:
        stim = _pad(
            [
                {"start": True, "a": True, "b": False, "c": False},
                {"start": False, "a": False, "b": True, "c": False},
                {"start": False, "a": False, "b": False, "c": False},
                {"start": False, "a": False, "b": False, "c": True},
                {"start": False, "a": False, "b": False, "c": False},
            ]
        )
        rtl_pass, _ = _dual_check(self._checker(), stim, tmp_path, simulator)
        assert any(rtl_pass)

    def test_consequent_incomplete_no_pass(
        self,
        tmp_path: Path,
        simulator: str,
    ) -> None:
        stim = _pad(
            [
                {"start": True, "a": True, "b": True, "c": False},
                {"start": False, "a": False, "b": False, "c": False},
            ]
        )
        rtl_pass, _ = _dual_check(self._checker(), stim, tmp_path, simulator)
        assert not any(rtl_pass)
