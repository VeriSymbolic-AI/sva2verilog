"""Simulation tests for the seq_concat_top + concat_delay template pipeline.

Fixtures exercised:
  - ``delay_zero.json``          — ``a ##0 b``
  - ``delay_fixed.json``         — ``a ##3 b``
  - ``delay_range.json``         — ``a ##[2:5] b``
  - ``delay_three_element.json`` — ``a ##1 b ##2 c``

RTL pipeline timing
-------------------
Each ``a ##N b`` property is implemented as a three-stage token-passing chain:

    bool_expr(a) → concat_delay(N) → bool_expr(b)

Both ``bool_expr`` stages have REGISTERED outputs (1-cycle latency each).
``concat_delay`` with N>0 also registers: its counter starts at 0 on the cycle
after its start fires.

Total observed latency for ``a ##N b`` (a=1 at t=0, b=1 at t_b):

    N = 0 (combinational delay): b must be 1 at t=1;  pass fires at t=2
    N > 0 (counter delay):       b must be 1 at t=N+2; pass fires at t=N+3

For a fail to fire from bool_expr_a: a=0 when start fires → fail at t=1.
For a fail to fire from bool_expr_b: b=0 when delay pass fires → fail at t=N+3.
(concat_delay itself has ``fail = 1'b0``; it never fails.)

Three-element ``a ##1 b ##2 c`` timing:
    a=1 at t=0, b=1 at t=3 (=1+2), c=1 at t=7 (=3+4) → pass at t=8.

Oracle is NOT used for direct comparison here because the behavioral oracle
models delay relative to ``start`` without the 2-cycle bool_expr overhead.
All expected values are hardcoded from the timing analysis above.

Requirements covered: TEST-03, TEST-04
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


def _build_checker(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
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
# delay_zero: a ##0 b
# ══════════════════════════════════════════════════════════════════════════════


class TestDelayZero:
    """Tests for ``a ##0 b`` — zero delay (combinational concat_delay stage)."""

    def test_pass_fires_at_t2(self, tmp_path: Path) -> None:
        """a ##0 b: pass fires at t=2 when a=1 at t=0, b=1 at t=1.

        Pipeline: bool_expr(a)[1cy] → concat_delay(##0)[combi] → bool_expr(b)[1cy]
          t=0: start=1, a=1 → a_pass registered, fires at END t=0
          t=1: a_pass=1; ##0 passes immediately; b gets start=1; b=1 → b_pass←b(t=1)
          t=2: b_pass=b(t=1)=1 → top-level pass=1
        """
        checker = _build_checker("delay_zero")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0: start a
            {"start": False, "a": False, "b": True},   # t=1: ##0 fires → b needed here
            {"start": False, "a": False, "b": False},  # t=2: pass fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert len(rtl_out) == len(stimulus)
        assert not rtl_out[0]["pass"], "t=0: pipeline not complete"
        assert not rtl_out[1]["pass"], "t=1: bool_expr_b not yet registered"
        assert     rtl_out[2]["pass"], "t=2: pass fires"
        assert not rtl_out[2]["fail"], "t=2: no fail"

    def test_fail_when_a_false_at_start(self, tmp_path: Path, simulator: str) -> None:
        """a ##0 b: bool_expr(a) fails when start fires but a=0."""
        checker = _build_checker("delay_zero")
        stimulus = [
            {"start": True,  "a": False, "b": False},  # t=0: start=1 but a=0
            {"start": False, "a": False, "b": False},  # t=1: a_fail fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert not rtl_out[0]["fail"], "t=0: fail not yet registered"
        assert     rtl_out[1]["fail"], "t=1: a=0 at start → bool_expr_a fail"

    def test_fail_when_b_false_at_fire(self, tmp_path: Path, simulator: str) -> None:
        """a ##0 b: bool_expr(b) fails when ##0 fires but b=0."""
        checker = _build_checker("delay_zero")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1: ##0 fires, b=0
            {"start": False, "a": False, "b": False},  # t=2: b_fail fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert not rtl_out[0]["fail"], "t=0: no fail yet"
        assert not rtl_out[1]["fail"], "t=1: bool_expr_b not yet registered"
        assert     rtl_out[2]["fail"], "t=2: b=0 when ##0 fires → bool_expr_b fail"
        assert not rtl_out[2]["pass"], "t=2: not pass"

    def test_disable_gates_outputs(self, tmp_path: Path, simulator: str) -> None:
        """a ##0 b: disable_i=1 gates all outputs to 0."""
        checker = _build_checker("delay_zero")
        stimulus = [
            {"start": True,  "a": True,  "b": False, "disable_i": True},
            {"start": False, "a": False, "b": True,  "disable_i": True},
            {"start": False, "a": False, "b": False, "disable_i": True},
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        for i, row in enumerate(rtl_out):
            assert not row["active"], f"t={i}: disabled → active=0"
            assert not row["pass"],   f"t={i}: disabled → pass=0"
            assert not row["fail"],   f"t={i}: disabled → fail=0"


# ══════════════════════════════════════════════════════════════════════════════
# delay_fixed: a ##3 b
# ══════════════════════════════════════════════════════════════════════════════


class TestDelayFixed:
    """Tests for ``a ##3 b`` — fixed 3-cycle delay."""

    def test_pass_fires_at_t4(self, tmp_path: Path) -> None:
        """a ##3 b: pass fires at t=4 when a=1 at t=0, b=1 at t=3 (gap=3).

        Corrected timing (BUG-DELAY-01 fix): a sampled at t=0, b sampled exactly
        N=3 cycles later (t=3), pass registered one cycle after the b-sample (t=4).
          t=0: start=1, a=1 → bool_expr_a registered
          t=1: a_pass=1 → delay starts
          t=3: delay asserts pass (start+(N-1)) → bool_expr_b sees b=1
          t=4: b_pass=1 → top-level pass=1
        """
        checker = _build_checker("delay_fixed")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1
            {"start": False, "a": False, "b": False},  # t=2
            {"start": False, "a": False, "b": True},   # t=3: b needed here (gap=3)
            {"start": False, "a": False, "b": False},  # t=4: pass fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert len(rtl_out) == len(stimulus)
        for i in range(4):
            assert not rtl_out[i]["pass"], f"t={i}: pass too early"
        assert rtl_out[4]["pass"], "t=4: pass fires (a=1 at t=0, b=1 at t=3)"
        assert not rtl_out[4]["fail"], "t=4: not fail"

    def test_no_pass_when_b_misses_window(self, tmp_path: Path, simulator: str) -> None:
        """a ##3 b: pass does NOT fire when b=0 at t=3 (the only firing window)."""
        checker = _build_checker("delay_fixed")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1
            {"start": False, "a": False, "b": False},  # t=2
            {"start": False, "a": False, "b": False},  # t=3: b=0 when delay fires
            {"start": False, "a": False, "b": False},  # t=4: fail fires (b=0 at t=3)
            {"start": False, "a": False, "b": True},   # t=5: too late
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert not rtl_out[4]["pass"], "t=4: b=0 at t=3 → no pass"
        assert     rtl_out[4]["fail"], "t=4: b=0 when delay fires → fail"
        assert not rtl_out[5]["pass"], "t=5: b=1 but window already closed"

    def test_fail_when_a_false_at_start(self, tmp_path: Path, simulator: str) -> None:
        """a ##3 b: bool_expr_a fails immediately when start=1 but a=0."""
        checker = _build_checker("delay_fixed")
        stimulus = [
            {"start": True,  "a": False, "b": False},  # t=0: a=0
            {"start": False, "a": False, "b": False},  # t=1: fail fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert not rtl_out[0]["fail"], "t=0: not yet registered"
        assert     rtl_out[1]["fail"], "t=1: a=0 at start → immediate fail"

    def test_active_during_delay_window(self, tmp_path: Path, simulator: str) -> None:
        """a ##3 b: active=1 during the delay counting period."""
        checker = _build_checker("delay_fixed")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1: a_pass fires
            {"start": False, "a": False, "b": False},  # t=2: counting (active)
            {"start": False, "a": False, "b": False},  # t=3: counting (active)
            {"start": False, "a": False, "b": False},  # t=4: counting (active)
            {"start": False, "a": False, "b": True},   # t=5: delay fires (active)
            {"start": False, "a": False, "b": False},  # t=6: pass fires, done
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        # active should be True during the counting window
        assert rtl_out[2]["active"], "t=2: counting → active"
        assert rtl_out[3]["active"], "t=3: counting → active"
        assert rtl_out[4]["active"], "t=4: counting → active"
        assert rtl_out[5]["active"], "t=5: delay fires, b_expr pending → active"

    def test_disable_mid_delay_clears_state(self, tmp_path: Path, simulator: str) -> None:
        """a ##3 b: disable during counting clears the delay counter."""
        checker = _build_checker("delay_fixed")
        stimulus = [
            {"start": True,  "a": True,  "b": False},             # t=0: start
            {"start": False, "a": False, "b": False},              # t=1: counting
            {"start": False, "a": False, "b": False, "disable_i": True},  # t=2: disable
            {"start": False, "a": False, "b": True},               # t=3: re-enable
            {"start": False, "a": False, "b": False},              # t=4: idle
            {"start": False, "a": False, "b": True},               # t=5: past orig window
            {"start": False, "a": False, "b": False},              # t=6: no pass
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        # t=2: disabled → no active
        assert not rtl_out[2]["active"], "t=2: disabled → active=0"
        # t=6: no pass because state was cleared at t=2
        assert not rtl_out[6]["pass"], "t=6: state was cleared → no pass"


# ══════════════════════════════════════════════════════════════════════════════
# delay_range: a ##[2:5] b
# ══════════════════════════════════════════════════════════════════════════════


class TestDelayRange:
    """Tests for ``a ##[2:5] b`` — range delay (window of b positions)."""

    def test_pass_at_min_delay(self, tmp_path: Path, simulator: str) -> None:
        """a ##[2:5] b: pass fires when b=1 at t=4 (min_delay=2 → t=2+2=4).

        Range window: delay_pass fires when count in [2,5].
          count=2 fires at t_delay_start + 3 = 1 + 3 = t=4.
          bool_expr_b registers b(t=4) → pass at t=5.
        """
        checker = _build_checker("delay_range")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1: delay starts
            {"start": False, "a": False, "b": False},  # t=2: count=0
            {"start": False, "a": False, "b": False},  # t=3: count=1
            {"start": False, "a": False, "b": True},   # t=4: count=2 → delay fires; b=1
            {"start": False, "a": False, "b": False},  # t=5: pass fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert len(rtl_out) == len(stimulus)
        for i in range(5):
            assert not rtl_out[i]["pass"], f"t={i}: pass too early"
        assert rtl_out[5]["pass"], "t=5: pass fires at min delay (b=1 at t=4)"

    def test_pass_at_max_delay(self, tmp_path: Path, simulator: str) -> None:
        """a ##[2:5] b: pass fires when b=1 at t=5 (max gap=5 → pass at t=6).

        Corrected timing (BUG-DELAY-01): the b window is t=2..5 (gaps 2..5 from
        a@0); the latest is b@5 → pass at t=6.
        """
        checker = _build_checker("delay_range")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1
            {"start": False, "a": False, "b": False},  # t=2: window opens (gap2), b=0
            {"start": False, "a": False, "b": False},  # t=3
            {"start": False, "a": False, "b": False},  # t=4
            {"start": False, "a": False, "b": True},   # t=5: b at max gap=5
            {"start": False, "a": False, "b": False},  # t=6: pass fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert rtl_out[6]["pass"], "t=6: pass fires at max delay (b=1 at t=5)"
        for i in range(6):
            assert not rtl_out[i]["pass"], f"t={i}: no pass before t=6"

    def test_pass_across_multiple_delay_cycles(self, tmp_path: Path, simulator: str) -> None:
        """a ##[2:5] b: pass fires on each cycle within the window where b=1.

        Corrected window is b at t=2..5 → pass at t=3..6 (BUG-DELAY-01).
        """
        checker = _build_checker("delay_range")
        # b=1 on all cycles t=2..5 → pass on t=3..6
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1
            {"start": False, "a": False, "b": True},   # t=2: first window cycle (gap2)
            {"start": False, "a": False, "b": True},   # t=3
            {"start": False, "a": False, "b": True},   # t=4
            {"start": False, "a": False, "b": True},   # t=5: last window cycle (gap5)
            {"start": False, "a": False, "b": False},  # t=6: last pass
            {"start": False, "a": False, "b": False},  # t=7: idle
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        for i in range(3):
            assert not rtl_out[i]["pass"], f"t={i}: no pass yet"
        for i in range(3, 7):
            assert rtl_out[i]["pass"], f"t={i}: pass fires (b=1 at t={i-1})"
        assert not rtl_out[7]["pass"], "t=7: window closed (delay stopped)"

    def test_no_pass_when_b_missed_window(self, tmp_path: Path, simulator: str) -> None:
        """a ##[2:5] b: no pass when b is always 0 in the window (t=4..7)."""
        checker = _build_checker("delay_range")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1
            {"start": False, "a": False, "b": False},  # t=2
            {"start": False, "a": False, "b": False},  # t=3
            {"start": False, "a": False, "b": False},  # t=4: window, b=0 → fail at t=5
            {"start": False, "a": False, "b": False},  # t=5: fail fires for t=4
            {"start": False, "a": False, "b": False},  # t=6: (window continues)
            {"start": False, "a": False, "b": False},  # t=7
            {"start": False, "a": False, "b": False},  # t=8: window closes
            {"start": False, "a": False, "b": True},   # t=9: too late
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        for i in range(len(stimulus)):
            assert not rtl_out[i]["pass"], f"t={i}: b never in window → no pass"

    def test_fail_when_a_false_at_start(self, tmp_path: Path, simulator: str) -> None:
        """a ##[2:5] b: bool_expr_a fails when start=1 but a=0."""
        checker = _build_checker("delay_range")
        stimulus = [
            {"start": True,  "a": False, "b": False},  # t=0: a=0
            {"start": False, "a": False, "b": False},  # t=1: fail
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert not rtl_out[0]["fail"], "t=0: not yet registered"
        assert     rtl_out[1]["fail"], "t=1: a=0 at start → fail"


# ══════════════════════════════════════════════════════════════════════════════
# delay_three_element: a ##1 b ##2 c
# ══════════════════════════════════════════════════════════════════════════════


class TestDelayThreeElement:
    """Tests for ``a ##1 b ##2 c`` — two-delay three-element sequence.

    Corrected timing (BUG-DELAY-01 fix), a=1 at t=0:
      t=0: start=1, a=1 → a_pass registered
      t=1: delay_1 (##1) asserts pass → b sampled here (gap 1 from a)
      t=2: b_pass → delay_2 (##2) starts
      t=3: delay_2 asserts pass → c sampled here (gap 2 from b)
      t=4: c_pass → top-level pass fires
    """

    def test_pass_fires_at_t4(self, tmp_path: Path) -> None:
        """a ##1 b ##2 c: pass fires at t=4 (a@0, b@1, c@3 — corrected gaps 1, 2)."""
        checker = _build_checker("delay_three_element")
        stimulus = [
            {"start": True,  "a": True,  "b": False, "c": False},  # t=0: a
            {"start": False, "a": False, "b": True,  "c": False},  # t=1: b (gap1 from a)
            {"start": False, "a": False, "b": False, "c": False},  # t=2
            {"start": False, "a": False, "b": False, "c": True},   # t=3: c (gap2 from b)
            {"start": False, "a": False, "b": False, "c": False},  # t=4: pass fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert len(rtl_out) == len(stimulus)
        for i in range(4):
            assert not rtl_out[i]["pass"], f"t={i}: pass too early"
        assert rtl_out[4]["pass"], "t=4: full chain completes → pass"
        assert not rtl_out[4]["fail"], "t=4: not fail"

    def test_fail_at_middle_when_b_false(self, tmp_path: Path, simulator: str) -> None:
        """a ##1 b ##2 c: chain fails at the bool_expr_b stage when b=0 at t=1."""
        checker = _build_checker("delay_three_element")
        stimulus = [
            {"start": True,  "a": True,  "b": False, "c": False},  # t=0
            {"start": False, "a": False, "b": False, "c": False},  # t=1: b=0 → fail
            {"start": False, "a": False, "b": False, "c": False},  # t=2: fail fires
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert     rtl_out[2]["fail"], "t=2: b=0 at t=1 → bool_expr_b fail"
        assert not rtl_out[2]["pass"], "t=2: no pass"

    def test_fail_from_a(self, tmp_path: Path, simulator: str) -> None:
        """a ##1 b ##2 c: fails at bool_expr_a when start fires with a=0."""
        checker = _build_checker("delay_three_element")
        stimulus = [
            {"start": True,  "a": False, "b": False, "c": False},  # t=0: a=0
            {"start": False, "a": False, "b": False, "c": False},  # t=1: fail
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        assert rtl_out[1]["fail"], "t=1: a=0 at start → fail"

    def test_active_across_full_chain(self, tmp_path: Path, simulator: str) -> None:
        """a ##1 b ##2 c: active=1 while the (corrected) chain is in progress."""
        checker = _build_checker("delay_three_element")
        stimulus = [
            {"start": True,  "a": True,  "b": False, "c": False},  # t=0: a
            {"start": False, "a": False, "b": True,  "c": False},  # t=1: b (gap1)
            {"start": False, "a": False, "b": False, "c": False},  # t=2
            {"start": False, "a": False, "b": False, "c": True},   # t=3: c (gap2)
            {"start": False, "a": False, "b": False, "c": False},  # t=4: pass
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        # The chain is active while delay_2 is counting (t=2..3).
        assert rtl_out[2]["active"], "t=2: delay_2 counting → active"
        assert rtl_out[3]["active"], "t=3: delay_2 completes → active"
        # t=4: pass fires.
        assert rtl_out[4]["pass"], "t=4: pass fires"

    def test_disable_mid_chain(self, tmp_path: Path, simulator: str) -> None:
        """a ##1 b ##2 c: disable_i=1 mid-chain clears state, no pass at end."""
        checker = _build_checker("delay_three_element")
        stimulus = [
            {"start": True,  "a": True,  "b": False, "c": False},  # t=0
            {"start": False, "a": False, "b": False, "c": False},  # t=1
            {"start": False, "a": False, "b": False, "c": False, "disable_i": True},  # t=2
            {"start": False, "a": False, "b": True,  "c": False},  # t=3
            {"start": False, "a": False, "b": False, "c": False},  # t=4
            {"start": False, "a": False, "b": False, "c": False},  # t=5
            {"start": False, "a": False, "b": False, "c": False},  # t=6
            {"start": False, "a": False, "b": False, "c": True},   # t=7
            {"start": False, "a": False, "b": False, "c": False},  # t=8
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path)

        # t=2: disabled → all 0
        assert not rtl_out[2]["active"], "t=2: disabled → active=0"
        # t=8: would be pass if not for the mid-chain disable
        assert not rtl_out[8]["pass"], "t=8: chain was broken by disable → no pass"


# ══════════════════════════════════════════════════════════════════════════════
# Oracle cross-check tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDelayOracleCrosscheck:
    """Oracle cross-check: verify RTL and oracle event patterns match.

    Note: the behavioral oracle models delay relative to ``start`` without the
    2-cycle bool_expr overhead.  Cycle-by-cycle comparison is therefore not
    possible; instead we verify that both produce the same set of pass/fail events.
    """

    def _count_events(self, results: list[dict]) -> dict[str, int]:
        return {
            "pass": sum(1 for r in results if r.get("pass")),
            "fail": sum(1 for r in results if r.get("fail")),
            "active": sum(1 for r in results if r.get("active")),
        }

    def test_fixed_delay_oracle_event_pattern(self, tmp_path: Path, simulator: str) -> None:
        """a ##3 b: both RTL and oracle produce pass events when timing is correct."""
        checker = _build_checker("delay_fixed")
        # Corrected window is b at gap 3 (t=3); hold b over t=2..4 to cover it.
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1
            {"start": False, "a": False, "b": True},   # t=2
            {"start": False, "a": False, "b": True},   # t=3: gap=3 window
            {"start": False, "a": False, "b": True},   # t=4
            {"start": False, "a": False, "b": False},  # t=5
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        # Both should have a pass event
        assert rtl_events["pass"] > 0
        assert oracle_events["pass"] > 0

    def test_range_delay_oracle_event_pattern(self, tmp_path: Path, simulator: str) -> None:
        """a ##[2:5] b: both RTL and oracle produce pass events within window."""
        checker = _build_checker("delay_range")
        # b=1 held over a wide window to cover both timing domains
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},  # t=1
            {"start": False, "a": False, "b": False},  # t=2
            {"start": False, "a": False, "b": True},   # t=3
            {"start": False, "a": False, "b": True},   # t=4
            {"start": False, "a": False, "b": True},   # t=5
            {"start": False, "a": False, "b": True},   # t=6
            {"start": False, "a": False, "b": True},   # t=7
            {"start": False, "a": False, "b": False},  # t=8
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["pass"] > 0
        assert oracle_events["pass"] > 0

    def test_zero_delay_oracle_event_pattern(self, tmp_path: Path, simulator: str) -> None:
        """a ##0 b: both RTL and oracle produce pass events."""
        checker = _build_checker("delay_zero")
        # b=1 at t=1 (after bool_expr_a registers), held for pipeline
        stimulus = [
            {"start": True,  "a": True,  "b": True},   # t=0
            {"start": False, "a": False, "b": True},   # t=1: b needed for ##0
            {"start": False, "a": False, "b": False},  # t=2: pass fires
            {"start": False, "a": False, "b": False},  # t=3
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["pass"] > 0
        assert oracle_events["pass"] > 0

    def test_three_element_oracle_event_pattern(self, tmp_path: Path, simulator: str) -> None:
        """a ##1 b ##2 c: both RTL and oracle produce pass events."""
        checker = _build_checker("delay_three_element")
        # Corrected timing: b at gap1 (t=1), c at gap2 from b (t=3).
        stimulus = [
            {"start": True,  "a": True,  "b": False, "c": False},  # t=0
            {"start": False, "a": False, "b": True,  "c": False},  # t=1: b
            {"start": False, "a": False, "b": False, "c": False},  # t=2
            {"start": False, "a": False, "b": False, "c": True},   # t=3: c
            {"start": False, "a": False, "b": False, "c": True},   # t=4
            {"start": False, "a": False, "b": False, "c": False},  # t=5
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["pass"] > 0
        assert oracle_events["pass"] > 0
