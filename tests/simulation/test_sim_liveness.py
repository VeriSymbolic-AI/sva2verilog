"""Simulation tests for bounded-liveness templates (v1.4 Part A).

Cross-checks the generated ``s_eventually`` RTL (iverilog) against the
independent behavioral oracle AND against explicit contract cycles:
``s_eventually [lo:hi] p`` armed at start cycle t0 PASSes at t0+k*+1 (first
in-window holding offset k*) and FAILs at t0+hi+1 if none.

Requirement coverage: LIVE-01 (dual-oracle simulation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from tests.simulation.tb_generator import (
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _build_checker(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    return compose(node, clock, label, text)


def _run(checker: CheckerNode, stimulus: list[dict[str, Any]], tmp_path: Path,
         simulator: str = "iverilog") -> list[dict]:
    modules = emit_all(checker)
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=checker.params["clock_signal"],
        extra_inputs=extra_inputs_from_checker(checker),
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
    )


def _assert_rtl_matches_oracle(checker: CheckerNode, stim: list[dict[str, Any]],
                               rtl: list[dict]) -> None:
    oracle = simulate_checker_hierarchy(checker, stim)
    for t, (r, o) in enumerate(zip(rtl, oracle)):
        assert bool(r["pass"]) == bool(o["pass"]), f"pass mismatch @t{t}: rtl={r} oracle={o}"
        assert bool(r["fail"]) == bool(o["fail"]), f"fail mismatch @t{t}: rtl={r} oracle={o}"


class TestSEventually13:
    """``s_eventually [1:3] a`` — window offsets 1..3."""

    def test_pass_at_offset2(self, tmp_path: Path) -> None:
        """a high at offset 2 (t2) -> pass at t3 (= t0 + k*(2) + 1)."""
        checker = _build_checker("s_eventually_1_3")
        stim = [
            {"start": True, "a": False}, {"start": False, "a": False},
            {"start": False, "a": True}, {"start": False, "a": False},
            {"start": False, "a": False}, {"start": False, "a": False},
        ]
        rtl = _run(checker, stim, tmp_path)
        assert rtl[3]["pass"] and not rtl[3]["fail"], "pass at t3"
        assert not any(rtl[t]["pass"] for t in (0, 1, 2)), "no early pass"
        assert not any(r["fail"] for r in rtl), "no fail on satisfied attempt"
        _assert_rtl_matches_oracle(checker, stim, rtl)

    def test_pass_at_offset1(self, tmp_path: Path) -> None:
        """a high at offset 1 (t1) -> pass at t2."""
        checker = _build_checker("s_eventually_1_3")
        stim = [
            {"start": True, "a": False}, {"start": False, "a": True},
            {"start": False, "a": False}, {"start": False, "a": False},
            {"start": False, "a": False},
        ]
        rtl = _run(checker, stim, tmp_path)
        assert rtl[2]["pass"] and not rtl[2]["fail"], "pass at t2"
        _assert_rtl_matches_oracle(checker, stim, rtl)

    def test_pass_at_last_offset3(self, tmp_path: Path) -> None:
        """a high only at offset 3 (t3) -> pass at t4 (last window cycle wins)."""
        checker = _build_checker("s_eventually_1_3")
        stim = [
            {"start": True, "a": False}, {"start": False, "a": False},
            {"start": False, "a": False}, {"start": False, "a": True},
            {"start": False, "a": False}, {"start": False, "a": False},
        ]
        rtl = _run(checker, stim, tmp_path)
        assert rtl[4]["pass"] and not rtl[4]["fail"], "pass at t4"
        assert not any(r["fail"] for r in rtl), "no fail when satisfied at hi"
        _assert_rtl_matches_oracle(checker, stim, rtl)

    def test_fail_when_never(self, tmp_path: Path) -> None:
        """a never high -> fail at t4 (= t0 + hi(3) + 1)."""
        checker = _build_checker("s_eventually_1_3")
        stim = [{"start": t == 0, "a": False} for t in range(6)]
        rtl = _run(checker, stim, tmp_path)
        assert rtl[4]["fail"] and not rtl[4]["pass"], "fail at t4"
        assert not any(r["pass"] for r in rtl), "no pass when never satisfied"
        _assert_rtl_matches_oracle(checker, stim, rtl)

    def test_disable_gates_outputs(self, tmp_path: Path, simulator: str) -> None:
        """disable_i=1 gates pass/fail/active to 0."""
        checker = _build_checker("s_eventually_1_3")
        stim = [{"start": t == 0, "a": True, "disable_i": True} for t in range(6)]
        rtl = _run(checker, stim, tmp_path, simulator)
        for t, r in enumerate(rtl):
            assert not r["pass"] and not r["fail"] and not r["active"], f"disabled @t{t}"


class TestAlways13:
    """``always [1:3] a`` — universal dual: a must hold at offsets 1..3."""

    def test_pass_when_all_hold(self, tmp_path: Path) -> None:
        """a high at every in-window offset 1..3 -> pass at t4 (= t0 + hi(3) + 1)."""
        checker = _build_checker("always_1_3")
        stim = [
            {"start": True, "a": True}, {"start": False, "a": True},
            {"start": False, "a": True}, {"start": False, "a": True},
            {"start": False, "a": False}, {"start": False, "a": False},
        ]
        rtl = _run(checker, stim, tmp_path)
        assert rtl[4]["pass"] and not rtl[4]["fail"], "pass at t4"
        assert not any(r["fail"] for r in rtl), "no fail when all hold"
        _assert_rtl_matches_oracle(checker, stim, rtl)

    def test_fail_at_first_violation(self, tmp_path: Path) -> None:
        """a false at offset 2 (t2) -> fail at t3 (= t0 + k_viol(2) + 1)."""
        checker = _build_checker("always_1_3")
        stim = [
            {"start": True, "a": True}, {"start": False, "a": True},
            {"start": False, "a": False}, {"start": False, "a": True},
            {"start": False, "a": True}, {"start": False, "a": False},
        ]
        rtl = _run(checker, stim, tmp_path)
        assert rtl[3]["fail"] and not rtl[3]["pass"], "fail at t3"
        assert not any(rtl[t]["fail"] for t in (0, 1, 2)), "no early fail"
        assert not any(r["pass"] for r in rtl), "no pass once violated"
        _assert_rtl_matches_oracle(checker, stim, rtl)

    def test_fail_only_once(self, tmp_path: Path) -> None:
        """Multiple in-window violations -> fail fires once (at the first)."""
        checker = _build_checker("always_1_3")
        stim = [
            {"start": True, "a": False}, {"start": False, "a": False},
            {"start": False, "a": False}, {"start": False, "a": False},
            {"start": False, "a": False}, {"start": False, "a": False},
        ]
        rtl = _run(checker, stim, tmp_path)
        # First in-window offset is 1 (t1) -> fail at t2.
        assert rtl[2]["fail"], "fail at t2 (first violation offset 1)"
        assert sum(1 for r in rtl if r["fail"]) == 1, "fail fires exactly once"
        assert not any(r["pass"] for r in rtl), "no pass on violated attempt"
        _assert_rtl_matches_oracle(checker, stim, rtl)

    def test_disable_gates_outputs(self, tmp_path: Path, simulator: str) -> None:
        """disable_i=1 gates pass/fail/active to 0."""
        checker = _build_checker("always_1_3")
        stim = [{"start": t == 0, "a": False, "disable_i": True} for t in range(6)]
        rtl = _run(checker, stim, tmp_path, simulator)
        for t, r in enumerate(rtl):
            assert not r["pass"] and not r["fail"] and not r["active"], f"disabled @t{t}"
