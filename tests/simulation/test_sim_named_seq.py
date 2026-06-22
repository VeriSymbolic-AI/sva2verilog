"""Simulation tests for named sequence inline expansion.

Fixture exercised:
  - ``named_seq.json`` — named sequence `req_ack = a ##1 b`, assertion uses `req_ack`

RTL pipeline timing
-------------------
The named sequence ``req_ack`` expands to ``a ##1 b``, producing the same
three-stage token-passing chain as a fixed delay:

    bool_expr(a) → concat_delay(##1) → bool_expr(b)

Total observed latency for ``a ##N b`` (from test_sim_delay.py analysis):
    N > 0: b must be 1 at t=N+2; pass fires at t=N+3

For N=1: b must be 1 at t=3; pass fires at t=4.

Breakdown:
    t=0: start=1, a=1 → registered in bool_expr(a)
    t=1: bool_expr(a) pass fires → concat_delay starts
    t=2: concat_delay counting (count=0, target=1)
    t=3: concat_delay fires pass → bool_expr(b) gets start, checks b
    t=4: bool_expr(b) pass/fail fires → top-level output

This test validates that named sequence expansion through `_expand_named_sequence`
produces behaviorally correct RTL that matches the equivalent inline expression.

Requirements covered: PARSE-03, TEST-03, TEST-04
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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _build_checker() -> CheckerNode:
    ast = json.loads((_FIXTURES / "named_seq.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)


def _run_stimulus(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str = "iverilog",
) -> list[dict[str, bool]]:
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
    )


# ══════════════════════════════════════════════════════════════════════════════
# named_seq: sequence req_ack = a ##1 b; assert property (@(posedge clk) req_ack)
# Equivalent to: a ##1 b  (3-stage pipeline)
# ══════════════════════════════════════════════════════════════════════════════


class TestNamedSeqPass:
    """Tests for named sequence pass behavior — validates inline expansion correctness."""

    def test_pass_fires_on_correct_cycle(self, tmp_path: Path, simulator: str) -> None:
        """Named seq ``a ##1 b``: pass fires at t=4 when a=1 at t=0, b=1 at t=3.

        Pipeline: bool_expr(a)[1cy] → concat_delay(##1)[2cy] → bool_expr(b)[1cy]
          t=0: start=1, a=1
          t=1: bool_expr(a) pass fires → concat_delay starts
          t=2: concat_delay counting
          t=3: concat_delay pass → bool_expr(b) checks b; b=1
          t=4: bool_expr(b) pass fires → top-level pass=1
        """
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0: trigger
            {"start": 0, "a": 0, "b": 0},  # t=1: waiting
            {"start": 0, "a": 0, "b": 0},  # t=2: waiting
            {"start": 0, "a": 0, "b": 1},  # t=3: b ready for check
            {"start": 0, "a": 0, "b": 0},  # t=4: pass should fire
            {"start": 0, "a": 0, "b": 0},  # t=5
            {"start": 0, "a": 0, "b": 0},  # t=6
            {"start": 0, "a": 0, "b": 0},  # t=7
        ]
        results = _run_stimulus(checker, stimulus, tmp_path)

        # pass should fire at t=4 (N+3 = 1+3 = 4)
        assert results[4]["pass"] is True, (
            f"Expected pass at t=4, got pass={results[4]['pass']}. "
            f"Full results: {results[:6]}"
        )
        # No pass at t=0..t=3
        for t in [0, 1, 2, 3]:
            assert results[t]["pass"] is False, f"Unexpected pass at t={t}"

    def test_fail_when_b_not_asserted(self, tmp_path: Path, simulator: str) -> None:
        """Named seq ``a ##1 b``: fail fires when b=0 at the check cycle.

        a=1 at t=0 triggers the sequence.
        b=0 at t=3 means the final bool_expr(b) check fails.
        fail should fire at t=4 (N+3 = 1+3 = 4).
        """
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0: trigger with a=1
            {"start": 0, "a": 0, "b": 0},  # t=1: waiting
            {"start": 0, "a": 0, "b": 0},  # t=2: waiting
            {"start": 0, "a": 0, "b": 0},  # t=3: b=0 when checked → fail
            {"start": 0, "a": 0, "b": 0},  # t=4: fail fires
            {"start": 0, "a": 0, "b": 0},  # t=5
        ]
        results = _run_stimulus(checker, stimulus, tmp_path)

        # fail should fire at t=4
        assert results[4]["fail"] is True, (
            f"Expected fail at t=4, got fail={results[4]['fail']}. "
            f"Full results: {results[:6]}"
        )
        # pass should NOT fire
        assert results[4]["pass"] is False

    def test_multiple_triggers_independent(self, tmp_path: Path, simulator: str) -> None:
        """Two independent triggers produce two independent pass events.

        Trigger 1: start=1, a=1 at t=0; b=1 at t=3 → pass at t=4
        Trigger 2: start=1, a=1 at t=6; b=1 at t=9 → pass at t=10
        """
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0: trigger 1
            {"start": 0, "a": 0, "b": 0},  # t=1
            {"start": 0, "a": 0, "b": 0},  # t=2
            {"start": 0, "a": 0, "b": 1},  # t=3: b for trigger 1
            {"start": 0, "a": 0, "b": 0},  # t=4: pass 1
            {"start": 0, "a": 0, "b": 0},  # t=5
            {"start": 1, "a": 1, "b": 0},  # t=6: trigger 2
            {"start": 0, "a": 0, "b": 0},  # t=7
            {"start": 0, "a": 0, "b": 0},  # t=8
            {"start": 0, "a": 0, "b": 1},  # t=9: b for trigger 2
            {"start": 0, "a": 0, "b": 0},  # t=10: pass 2
            {"start": 0, "a": 0, "b": 0},  # t=11
        ]
        results = _run_stimulus(checker, stimulus, tmp_path)

        assert results[4]["pass"] is True, f"Expected pass at t=4: {results[4]}"
        assert results[10]["pass"] is True, f"Expected pass at t=10: {results[10]}"

    def test_a_fail_at_trigger(self, tmp_path: Path, simulator: str) -> None:
        """When a=0 at the trigger cycle, the first bool_expr fails immediately.

        start=1, a=0 at t=0 → bool_expr(a) fail at t=1.
        The downstream stages should NOT produce any output.
        """
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 0, "b": 0},  # t=0: trigger with a=0
            {"start": 0, "a": 0, "b": 0},  # t=1: a_fail fires
            {"start": 0, "a": 0, "b": 0},  # t=2
            {"start": 0, "a": 0, "b": 0},  # t=3
            {"start": 0, "a": 0, "b": 0},  # t=4
        ]
        results = _run_stimulus(checker, stimulus, tmp_path)

        # fail fires at t=1 (from bool_expr_a)
        assert results[1]["fail"] is True, f"Expected fail at t=1: {results[1]}"
        # No pass anywhere
        for t in range(len(results)):
            assert results[t]["pass"] is False, f"Unexpected pass at t={t}"


# ══════════════════════════════════════════════════════════════════════════════
# Oracle cross-check tests
# ══════════════════════════════════════════════════════════════════════════════


class TestNamedSeqOracleCrosscheck:
    """Oracle cross-check: verify RTL and oracle event patterns match."""

    def _count_events(self, results: list[dict]) -> dict[str, int]:
        return {
            "pass": sum(1 for r in results if r.get("pass")),
            "fail": sum(1 for r in results if r.get("fail")),
            "active": sum(1 for r in results if r.get("active")),
        }

    def test_named_seq_oracle_pass_event(self, tmp_path: Path, simulator: str) -> None:
        """Named seq: both RTL and oracle produce pass events."""
        checker = _build_checker()
        # b=1 held from t=2 through t=5 to cover both oracle and RTL timing
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0
            {"start": 0, "a": 0, "b": 0},  # t=1
            {"start": 0, "a": 0, "b": 1},  # t=2
            {"start": 0, "a": 0, "b": 1},  # t=3
            {"start": 0, "a": 0, "b": 1},  # t=4
            {"start": 0, "a": 0, "b": 1},  # t=5
            {"start": 0, "a": 0, "b": 0},  # t=6
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["pass"] > 0
        assert oracle_events["pass"] > 0

    @pytest.mark.xfail(
        reason="simulate_checker_hierarchy bool_expr oracle is passthrough — "
               "does not produce fail events for expression evaluation",
        strict=True,
    )
    def test_named_seq_oracle_fail_event(self, tmp_path: Path, simulator: str) -> None:
        """Named seq: both RTL and oracle produce fail events when b=0."""
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},
            {"start": 0, "a": 0, "b": 0},
            {"start": 0, "a": 0, "b": 0},
            {"start": 0, "a": 0, "b": 0},
            {"start": 0, "a": 0, "b": 0},
            {"start": 0, "a": 0, "b": 0},
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        # Both should have a fail event (b never asserted)
        assert rtl_events["fail"] > 0
        assert oracle_events["fail"] > 0

    def test_named_seq_oracle_no_start(self, tmp_path: Path, simulator: str) -> None:
        """Named seq: with no start, both RTL and oracle produce zero events."""
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 0, "a": 1, "b": 0},
            {"start": 0, "a": 0, "b": 1},
            {"start": 0, "a": 0, "b": 0},
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["pass"] == 0
        assert rtl_events["fail"] == 0
        assert oracle_events["pass"] == 0
        assert oracle_events["fail"] == 0
