"""Simulation tests for named sequence inline expansion.

Fixture exercised:
  - ``named_seq.json`` — named sequence `req_ack = a ##1 b`, assertion uses `req_ack`

RTL pipeline timing
-------------------
The named sequence ``req_ack`` expands to ``a ##1 b``, producing the same
three-stage token-passing chain as a fixed delay:

    bool_expr(a) → concat_delay(##1) → bool_expr(b)

Corrected latency for ``a ##N b`` (BUG-DELAY-01 fix): b must be 1 at gap N from
a, and pass fires one cycle later.

For N=1: b must be 1 at t=1; pass fires at t=2.

Breakdown:
    t=0: start=1, a=1 → registered in bool_expr(a)
    t=1: bool_expr(a) pass fires → concat_delay(##1) asserts pass → bool_expr(b)
         checks b here (gap 1 from a)
    t=2: bool_expr(b) pass/fail fires → top-level output

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
        stimulus=stimulus,
        extra_inputs=extra_inputs,
        clock_signal=clock_signal,
    )


# ══════════════════════════════════════════════════════════════════════════════
# named_seq: sequence req_ack = a ##1 b; assert property (@(posedge clk) req_ack)
# Equivalent to: a ##1 b  (3-stage pipeline)
# ══════════════════════════════════════════════════════════════════════════════


class TestNamedSeqPass:
    """Tests for named sequence pass behavior — validates inline expansion correctness."""

    def test_pass_fires_on_correct_cycle(self, tmp_path: Path, simulator: str) -> None:
        """Named seq ``a ##1 b``: pass fires at t=2 when a=1 at t=0, b=1 at t=1 (gap=1).

        Corrected timing (BUG-DELAY-01):
          t=0: start=1, a=1 → bool_expr(a) registered
          t=1: concat_delay(##1) asserts pass → bool_expr(b) checks b; b=1
          t=2: bool_expr(b) pass fires → top-level pass=1
        """
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0: trigger
            {"start": 0, "a": 0, "b": 1},  # t=1: b ready (gap1)
            {"start": 0, "a": 0, "b": 0},  # t=2: pass should fire
            {"start": 0, "a": 0, "b": 0},  # t=3
        ]
        results = _run_stimulus(checker, stimulus, tmp_path)

        assert results[2]["pass"] is True, (
            f"Expected pass at t=2, got pass={results[2]['pass']}. Full results: {results[:4]}"
        )
        for t in [0, 1]:
            assert results[t]["pass"] is False, f"Unexpected pass at t={t}"

    def test_fail_when_b_not_asserted(self, tmp_path: Path, simulator: str) -> None:
        """Named seq ``a ##1 b``: fail fires when b=0 at the check cycle (t=1).

        a=1 at t=0 triggers the sequence; b=0 at t=1 means the final bool_expr(b)
        check fails, so fail fires at t=2.
        """
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0: trigger with a=1
            {"start": 0, "a": 0, "b": 0},  # t=1: b=0 when checked → fail
            {"start": 0, "a": 0, "b": 0},  # t=2: fail fires
        ]
        results = _run_stimulus(checker, stimulus, tmp_path)

        assert results[2]["fail"] is True, (
            f"Expected fail at t=2, got fail={results[2]['fail']}. Full results: {results[:4]}"
        )
        assert results[2]["pass"] is False

    def test_multiple_triggers_independent(self, tmp_path: Path, simulator: str) -> None:
        """Two independent triggers produce two independent pass events.

        Trigger 1: start=1, a=1 at t=0; b=1 at t=1 → pass at t=2
        Trigger 2: start=1, a=1 at t=4; b=1 at t=5 → pass at t=6
        """
        checker = _build_checker()
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0: trigger 1
            {"start": 0, "a": 0, "b": 1},  # t=1: b for trigger 1
            {"start": 0, "a": 0, "b": 0},  # t=2: pass 1
            {"start": 0, "a": 0, "b": 0},  # t=3
            {"start": 1, "a": 1, "b": 0},  # t=4: trigger 2
            {"start": 0, "a": 0, "b": 1},  # t=5: b for trigger 2
            {"start": 0, "a": 0, "b": 0},  # t=6: pass 2
            {"start": 0, "a": 0, "b": 0},  # t=7
        ]
        results = _run_stimulus(checker, stimulus, tmp_path)

        assert results[2]["pass"] is True, f"Expected pass at t=2: {results[2]}"
        assert results[6]["pass"] is True, f"Expected pass at t=6: {results[6]}"

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
        # Corrected window: b at gap1 (t=1); hold b over t=1..2 to cover it.
        stimulus: list[dict[str, Any]] = [
            {"start": 1, "a": 1, "b": 0},  # t=0
            {"start": 0, "a": 0, "b": 1},  # t=1: b (gap1)
            {"start": 0, "a": 0, "b": 1},  # t=2
            {"start": 0, "a": 0, "b": 0},  # t=3
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
