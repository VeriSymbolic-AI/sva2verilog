"""Simulation tests for v1.3 operators: iverilog RTL + behavioral oracle cross-check.

Fixtures exercised: all 6 composed templates.  Requires iverilog on PATH.

The behavioral oracle models temporal operator composition but does NOT evaluate
boolean expressions (bool_expr is modelled as always-passing ##0).  Therefore
oracle cross-checks only test temporal composition correctness (and latency,
throughout cond re-evaluation).  Boolean expression values are covered by the
dedicated behavioral oracle tests in test_v13_operators.py.

Requirements covered: SEQ-SIM-01 (Tier 2 dual-oracle simulation)
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
from tests.simulation.tb_generator import (
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _build_checker(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / f"v13_{name}.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)


def _run_stimulus(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str = "iverilog",
) -> list[dict]:
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]
    has_overflow = checker.template_name in ("overlap_bitvec", "nonoverlap")
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=clock_signal,
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


def _pad(stim: list[dict], n: int = 3) -> list[dict]:
    keys = set()
    for s in stim:
        keys.update(s.keys())
    idle = {k: False for k in keys if k != "start"}
    idle["start"] = False
    return stim + [idle.copy() for _ in range(n)]


def _count_events(results: list[dict[str, bool]]) -> dict[str, int]:
    d: dict[str, int] = {"pass": 0, "fail": 0, "active": 0}
    for r in results:
        for k in d:
            if r.get(k, False):
                d[k] += 1
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# prop_or — RTL simulation + oracle event pattern cross-check
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeqOrRTL:
    def test_both_pass_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("or_seq")
        stimulus = _pad([{"start": True, "a": True, "b": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0

    def test_left_pass_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("or_seq")
        stimulus = _pad([{"start": True, "a": True, "b": False}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0
        assert _count_events(rtl_out)["fail"] == 0

    def test_both_fail_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("or_seq")
        stimulus = _pad([{"start": True, "a": False, "b": False}], 8)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["fail"] > 0

    def test_event_pattern_match(self, tmp_path: Path, simulator: str) -> None:
        """Oracle must produce at least as many pass events as RTL (conservative check)."""
        checker = _build_checker("or_seq")
        stimulus = _pad([{"start": True, "a": True, "b": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)
        assert _count_events(oracle_out)["pass"] >= _count_events(rtl_out)["pass"]


# ═══════════════════════════════════════════════════════════════════════════════
# prop_and — latency-aware matching (RTL verification)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeqAndRTL:
    def test_both_pass_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("and_seq")
        stimulus = _pad([{"start": True, "a": True, "b": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0

    def test_one_fails_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("and_seq")
        stimulus = _pad([{"start": True, "a": True, "b": False}], 8)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["fail"] > 0

    def test_event_pattern_match(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("and_seq")
        stimulus = _pad([{"start": True, "a": True, "b": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)
        assert _count_events(oracle_out)["pass"] >= _count_events(rtl_out)["pass"]


# ═══════════════════════════════════════════════════════════════════════════════
# prop_intersect
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeqIntersectRTL:
    def test_both_pass_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("intersect_seq")
        stimulus = _pad([{"start": True, "a": True, "b": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0

    def test_one_passing_no_pass(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("intersect_seq")
        stimulus = _pad([{"start": True, "a": True, "b": False}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# prop_not
# ═══════════════════════════════════════════════════════════════════════════════

class TestPropNotRTL:
    def test_not_inverts_pass(self, tmp_path: Path, simulator: str) -> None:
        """not(a): a=true → body passes → not fails"""
        checker = _build_checker("prop_not")
        stimulus = _pad([{"start": True, "a": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["fail"] > 0

    def test_not_inverts_fail(self, tmp_path: Path, simulator: str) -> None:
        """not(a): a=false → body fails → not passes"""
        checker = _build_checker("prop_not")
        stimulus = _pad([{"start": True, "a": False}], 8)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# prop_if_else
# ═══════════════════════════════════════════════════════════════════════════════

class TestPropIfElseRTL:
    def test_true_branch_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("if_else_prop")
        # Hold start + sel + a = 1 for 2 cycles to flush NBA pipeline
        stimulus = _pad([
            {"start": True,  "sel": True,  "a": True,  "b": False},
            {"start": True,  "sel": True,  "a": True,  "b": False},
        ], 12)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0

    def test_false_branch_rtl(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("if_else_prop")
        stimulus = _pad([{"start": True, "sel": False, "a": False, "b": True}], 8)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# prop_throughout — cond re-evaluation during body (key temporal composition test)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSeqThroughoutRTL:
    def test_en_holds_pass(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("throughout_seq")
        stimulus = _pad([{"start": True, "en": True, "a": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["pass"] > 0

    def test_en_lost_fails(self, tmp_path: Path, simulator: str) -> None:
        checker = _build_checker("throughout_seq")
        stimulus = _pad([{"start": True, "en": False, "a": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        assert _count_events(rtl_out)["fail"] > 0

    def test_oracle_temporal_pattern(self, tmp_path: Path, simulator: str) -> None:
        """Temporal composition: oracle must detect en=0 as fail when body active."""
        checker = _build_checker("throughout_seq")
        stimulus = _pad([{"start": True, "en": False, "a": True}], 6)
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)
        assert _count_events(oracle_out)["fail"] > 0
        assert _count_events(rtl_out)["fail"] > 0
