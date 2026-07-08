"""Simulation tests for the rep_consecutive template (expr[*M:N] sequences).

Each test compiles the emitted SystemVerilog with iverilog, drives stimulus,
and compares the captured RTL outputs against the behavioral oracle.

Two fixtures are exercised:
  - ``rep_fixed.json``  — ``a[*3]``   (exactly 3 consecutive cycles)
  - ``rep_range.json``  — ``a[*2:5]`` (2 to 5 consecutive cycles)

Oracle adapter note: The behavioral oracle for ``rep_consecutive`` expects the
signal key ``"sig"`` (its internal name), whereas the fixture declares the RTL
port as ``"a"``.  The helper ``_oracle_stim()`` transparently remaps ``a``→``sig``
so each test can use natural stimulus dicts keyed by ``"a"`` for both RTL and
oracle.

Requirements covered: TEST-03, TEST-04
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.behavioral_oracle import SVABehavioralSim
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


# ── Fixture loading ───────────────────────────────────────────────────────────


def _build_checker(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)


# ── Oracle adapter ────────────────────────────────────────────────────────────


def _oracle_stim(stim: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remap signal key ``"a"`` → ``"sig"`` for the behavioral oracle.

    The fixture registers the signal port as ``"a"`` in the RTL but the oracle
    ``_tick_rep_consecutive`` reads ``signals.get("sig", False)``.  This adapter
    produces oracle-compatible stimulus from the shared RTL stimulus list.
    """
    adapted = []
    for s in stim:
        entry = dict(s)
        if "a" in entry and "sig" not in entry:
            entry["sig"] = entry.pop("a")
        adapted.append(entry)
    return adapted


# ── Run helper ────────────────────────────────────────────────────────────────


def _run_both(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    oracle_params: dict[str, Any],
    simulator: str = "iverilog",
    oracle_kind: str = "rep_consecutive",
) -> tuple[list[dict], list[dict]]:
    """Run stimulus through both oracle and RTL; return (oracle_out, rtl_out)."""
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]

    # Oracle — remap "a" → "sig" for the oracle
    sim = SVABehavioralSim(oracle_kind, oracle_params)
    oracle_out = [sim.tick(s) for s in _oracle_stim(stimulus)]

    # RTL
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=False,
    )
    rtl_out = run_simulation(
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

    return oracle_out, rtl_out


# ══════════════════════════════════════════════════════════════════════════════
# rep_fixed: a[*3]  (rep_min=3, rep_max=3)
# ══════════════════════════════════════════════════════════════════════════════


class TestRepFixed:
    """Tests for a[*3] — exactly 3 consecutive high cycles."""

    _PARAMS = {"rep_min": 3, "rep_max": 3}

    def test_pass_fires_at_third_consecutive_cycle(self, tmp_path: Path, simulator: str) -> None:
        """a[*3]: pass first fires on the 3rd cycle where a=1 (after start).

        Timing (RTL outputs are combinational from REGISTERED state):
          t=0: start=1, a=1 → running_q becomes 1, count_q←1. active=0 (old running=0)
          t=1: a=1 → count_q←2. active=1, pass=0 (count=1 old, not ≥3)
          t=2: a=1 → count_q←3. active=1, pass=0 (count=2 old, not ≥3)
          t=3: a=1 → count stays at 3 (= rep_max). active=1, pass=1 (count=3 old)
        """
        checker = _build_checker("rep_fixed")
        stimulus = [
            {"start": True,  "a": True},   # t=0: kick off
            {"start": False, "a": True},   # t=1: 2nd consecutive
            {"start": False, "a": True},   # t=2: 3rd consecutive
            {"start": False, "a": True},   # t=3: pass fires
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        # Explicit: pass only at t=3
        assert not rtl_out[0]["pass"], "t=0: too early"
        assert not rtl_out[1]["pass"], "t=1: still need more cycles"
        assert not rtl_out[2]["pass"], "t=2: need one more cycle"
        assert     rtl_out[3]["pass"], "t=3: exactly 3 cycles → pass"

    def test_fail_when_sequence_broken_before_rep_min(self, tmp_path: Path, simulator: str) -> None:
        """a[*3]: fail fires when a goes low while count < rep_min=3.

        t=0: start=1, a=1 → starts counting
        t=1: a=1 → count=2
        t=2: a=0 → fail fires (count=2 < rep_min=3)
        """
        checker = _build_checker("rep_fixed")
        stimulus = [
            {"start": True,  "a": True},   # t=0: start
            {"start": False, "a": True},   # t=1: count=2
            {"start": False, "a": False},  # t=2: broken — fail
            {"start": False, "a": False},  # t=3: idle (running=0)
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert not rtl_out[0]["fail"], "t=0: start cycle — not yet active"
        assert not rtl_out[1]["fail"], "t=1: still running, a=1"
        assert     rtl_out[2]["fail"], "t=2: a=0 while count < 3 → fail"
        assert not rtl_out[3]["fail"], "t=3: running already cleared"

    def test_start_with_a_false_does_not_start_running(
        self, tmp_path: Path, simulator: str
    ) -> None:
        """a[*3]: start with a=0 fires attempt_fired but does NOT set running_q.

        Because the RTL condition is ``(start && sig_eval)`` to set running_q,
        a start pulse with a=0 never starts the counter — no active/fail emitted.
        """
        checker = _build_checker("rep_fixed")
        stimulus = [
            {"start": True,  "a": False},  # t=0: start=1 but a=0 → no run
            {"start": False, "a": False},  # t=1: still nothing
            {"start": False, "a": True},   # t=2: a=1 but not started
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"

        # None should be active since start fired with a=0
        for i, rtl in enumerate(rtl_out):
            assert not rtl["active"], f"tick {i}: should not be active"

    def test_pass_continues_while_a_stays_high(self, tmp_path: Path, simulator: str) -> None:
        """a[*3]: pass keeps firing while a=1 and count is capped at rep_max=3."""
        checker = _build_checker("rep_fixed")
        stimulus = [
            {"start": True,  "a": True},   # t=0: start
            {"start": False, "a": True},   # t=1
            {"start": False, "a": True},   # t=2
            {"start": False, "a": True},   # t=3: pass
            {"start": False, "a": True},   # t=4: pass again (count capped at 3)
            {"start": False, "a": True},   # t=5: pass again
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert not rtl_out[0]["pass"]
        assert not rtl_out[1]["pass"]
        assert not rtl_out[2]["pass"]
        assert rtl_out[3]["pass"], "t=3: pass"
        assert rtl_out[4]["pass"], "t=4: pass (still high)"
        assert rtl_out[5]["pass"], "t=5: pass (still high)"

    def test_full_oracle_compare_rep_fixed(self, tmp_path: Path, simulator: str) -> None:
        """a[*3]: long mixed trace — every cycle matches oracle."""
        checker = _build_checker("rep_fixed")
        stimulus = [
            {"start": True,  "a": True},   # 0: start, a=1
            {"start": False, "a": True},   # 1
            {"start": False, "a": True},   # 2
            {"start": False, "a": True},   # 3: pass
            {"start": False, "a": False},  # 4: break after pass (count=3, no fail)
            {"start": True,  "a": True},   # 5: restart
            {"start": False, "a": True},   # 6
            {"start": False, "a": False},  # 7: break early (count=2 → fail)
            {"start": False, "a": False},  # 8: idle
            {"start": True,  "a": False},  # 9: start with a=0 (no run)
            {"start": False, "a": True},   # 10
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

    def test_disable_gates_output_rep_fixed(self, tmp_path: Path, simulator: str) -> None:
        """a[*3]: disable_i=1 gates all outputs to 0 and resets state."""
        checker = _build_checker("rep_fixed")
        stimulus = [
            {"start": True,  "a": True},              # t=0: start running
            {"start": False, "a": True, "disable_i": True},  # t=1: disabled
            {"start": False, "a": True},               # t=2: re-enabled, state reset
        ]
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
        rtl_out = run_simulation(
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

        # t=1: disabled → all 0
        assert not rtl_out[1]["active"], "t=1: disabled → active=0"
        assert not rtl_out[1]["pass"],   "t=1: disabled → pass=0"
        assert not rtl_out[1]["fail"],   "t=1: disabled → fail=0"

        # t=2: re-enabled but state was cleared by disable → not active
        assert not rtl_out[2]["active"], "t=2: state cleared by disable → inactive"


# ══════════════════════════════════════════════════════════════════════════════
# rep_range: a[*2:5]  (rep_min=2, rep_max=5)
# ══════════════════════════════════════════════════════════════════════════════


class TestRepRange:
    """Tests for a[*2:5] — 2 to 5 consecutive high cycles."""

    _PARAMS = {"rep_min": 2, "rep_max": 5}

    def test_pass_fires_at_rep_min(self, tmp_path: Path, simulator: str) -> None:
        """a[*2:5]: pass first fires at rep_min=2 consecutive cycles.

        t=0: start=1, a=1 → count=1 (active=0)
        t=1: a=1 → count=2 (active=1, pass=0 — old count=1)
        t=2: a=1 → pass=1 (old count=2 ≥ rep_min=2 ≤ rep_max=5)
        """
        checker = _build_checker("rep_range")
        stimulus = [
            {"start": True,  "a": True},   # t=0
            {"start": False, "a": True},   # t=1
            {"start": False, "a": True},   # t=2: pass fires (old count=2)
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert not rtl_out[0]["pass"], "t=0: start cycle, not yet active"
        assert not rtl_out[1]["pass"], "t=1: count=1, need ≥2"
        assert     rtl_out[2]["pass"], "t=2: count=2, pass fires"

    def test_pass_continues_through_rep_max(self, tmp_path: Path, simulator: str) -> None:
        """a[*2:5]: pass fires for 4 consecutive cycles (count 2..5), then stops."""
        checker = _build_checker("rep_range")
        # 6 cycles with a=1 after start: count reaches 5 (rep_max), then stays there
        stimulus = [
            {"start": True,  "a": True},   # t=0: count=1
            {"start": False, "a": True},   # t=1: count=2
            {"start": False, "a": True},   # t=2: pass (old count=2)
            {"start": False, "a": True},   # t=3: pass (old count=3)
            {"start": False, "a": True},   # t=4: pass (old count=4)
            {"start": False, "a": True},   # t=5: pass (old count=5 = rep_max)
            {"start": False, "a": True},   # t=6: pass (old count=5, capped)
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert not rtl_out[0]["pass"], "t=0: not yet active"
        assert not rtl_out[1]["pass"], "t=1: count=1 old"
        for i in range(2, 7):
            assert rtl_out[i]["pass"], f"t={i}: count in [2,5] → pass"

    def test_fail_when_broken_at_count_1(self, tmp_path: Path) -> None:
        """a[*2:5]: fail fires when a goes low while count < rep_min=2."""
        checker = _build_checker("rep_range")
        stimulus = [
            {"start": True,  "a": True},   # t=0: count=1
            {"start": False, "a": False},  # t=1: a=0, count=1 < rep_min=2 → fail
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert not rtl_out[0]["fail"], "t=0: start cycle"
        assert     rtl_out[1]["fail"], "t=1: broken at count=1 < rep_min=2"

    def test_no_fail_when_broken_at_rep_min(self, tmp_path: Path, simulator: str) -> None:
        """a[*2:5]: breaking at count=rep_min=2 does NOT produce fail (it passed)."""
        checker = _build_checker("rep_range")
        stimulus = [
            {"start": True,  "a": True},   # t=0: count=1
            {"start": False, "a": True},   # t=1: count=2
            {"start": False, "a": True},   # t=2: pass (old count=2)
            {"start": False, "a": False},  # t=3: a=0, count=2 → NOT < rep_min → no fail
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert rtl_out[2]["pass"],  "t=2: pass (count=2 ≥ rep_min)"
        assert not rtl_out[3]["fail"], "t=3: count=2 ≥ rep_min → no fail"

    def test_full_oracle_compare_rep_range(self, tmp_path: Path, simulator: str) -> None:
        """a[*2:5]: long mixed trace — every cycle matches oracle."""
        checker = _build_checker("rep_range")
        stimulus = [
            {"start": True,  "a": True},   # 0
            {"start": False, "a": True},   # 1
            {"start": False, "a": True},   # 2: pass
            {"start": False, "a": True},   # 3: pass
            {"start": False, "a": False},  # 4: break (count=3 ≥ 2 → no fail)
            {"start": False, "a": False},  # 5: idle
            {"start": True,  "a": True},   # 6: restart
            {"start": False, "a": False},  # 7: break at count=1 → fail
            {"start": False, "a": False},  # 8: idle
            {"start": True,  "a": True},   # 9: restart
            {"start": False, "a": True},   # 10: count=2
            {"start": False, "a": True},   # 11: pass (count=2 old)
            {"start": False, "a": True},   # 12: pass (count=3 old)
            {"start": False, "a": True},   # 13: pass (count=4 old)
            {"start": False, "a": True},   # 14: pass (count=5 old = rep_max)
            {"start": False, "a": True},   # 15: pass (capped at 5)
            {"start": False, "a": False},  # 16: break (count=5 ≥ 2 → no fail)
        ]
        oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path, self._PARAMS)

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
            assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

    def test_disable_gates_output_rep_range(self, tmp_path: Path, simulator: str) -> None:
        """a[*2:5]: disable_i=1 gates active/pass/fail to 0."""
        checker = _build_checker("rep_range")
        stimulus = [
            {"start": True,  "a": True},              # t=0: start
            {"start": False, "a": True},               # t=1: count=2
            {"start": False, "a": True, "disable_i": True},   # t=2: disabled
            {"start": False, "a": True},               # t=3: re-enabled, state cleared
        ]
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
        rtl_out = run_simulation(
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

        # t=2: disabled → all 0
        assert not rtl_out[2]["active"], "t=2: disabled → active=0"
        assert not rtl_out[2]["pass"],   "t=2: disabled → pass=0"
        assert not rtl_out[2]["fail"],   "t=2: disabled → fail=0"

        # t=3: re-enabled but disable clears state → not active
        assert not rtl_out[3]["active"], "t=3: state cleared by disable → inactive"


# ══════════════════════════════════════════════════════════════════════════════
# goto_rep: a[->3]  (rep_min=3, rep_max=3)
# ══════════════════════════════════════════════════════════════════════════════


class TestGotoRep:
    """Tests for a[->3] — 3 non-consecutive occurrences after one start pulse."""

    _PARAMS = {"rep_min": 3, "rep_max": 3}

    def test_single_start_keeps_counting_until_third_occurrence(
        self, tmp_path: Path, simulator: str
    ) -> None:
        """a[->3]: a single start pulse arms the attempt until the 3rd occurrence."""
        checker = _build_checker("goto_rep")
        stimulus = [
            {"start": True, "a": True},    # t=0: occurrence 1, arm attempt
            {"start": False, "a": False},  # t=1: gap allowed
            {"start": False, "a": True},   # t=2: occurrence 2
            {"start": False, "a": True},   # t=3: occurrence 3 -> pass
            {"start": False, "a": False},  # t=4: pass remains locked
        ]
        oracle_out, rtl_out = _run_both(
            checker,
            stimulus,
            tmp_path,
            self._PARAMS,
            simulator,
            oracle_kind="goto_rep",
        )

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"] == oracle["pass"], f"tick {i}: pass mismatch"
            assert rtl["fail"] == oracle["fail"], f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert not rtl_out[0]["pass"], "t=0: only first occurrence"
        assert not rtl_out[2]["pass"], "t=2: only second occurrence"
        assert rtl_out[3]["pass"], "t=3: third occurrence completes [->3]"
        assert rtl_out[4]["pass"], "t=4: [->3] pass is locked after completion"


# ══════════════════════════════════════════════════════════════════════════════
# nonconsec_rep: a[=5]  (rep_min=5, rep_max=5)
# ══════════════════════════════════════════════════════════════════════════════


class TestNonconsecRep:
    """Tests for a[=5] — 5 non-consecutive occurrences after one start pulse."""

    _PARAMS = {"rep_min": 5, "rep_max": 5}

    def test_single_start_keeps_counting_until_fifth_occurrence(
        self, tmp_path: Path, simulator: str
    ) -> None:
        """a[=5]: counting continues after the initial start pulse deasserts."""
        checker = _build_checker("nonconsec_rep")
        stimulus = [
            {"start": True, "a": True},    # t=0: occurrence 1, arm attempt
            {"start": False, "a": False},  # t=1: gap allowed
            {"start": False, "a": True},   # t=2: occurrence 2
            {"start": False, "a": False},  # t=3: gap allowed
            {"start": False, "a": True},   # t=4: occurrence 3
            {"start": False, "a": True},   # t=5: occurrence 4
            {"start": False, "a": True},   # t=6: occurrence 5 -> pass
            {"start": False, "a": False},  # t=7: pass remains locked
        ]
        oracle_out, rtl_out = _run_both(
            checker,
            stimulus,
            tmp_path,
            self._PARAMS,
            simulator,
            oracle_kind="nonconsec_rep",
        )

        assert len(rtl_out) == len(stimulus)
        for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
            assert rtl["pass"] == oracle["pass"], f"tick {i}: pass mismatch"
            assert rtl["fail"] == oracle["fail"], f"tick {i}: fail mismatch"
            assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

        assert not rtl_out[5]["pass"], "t=5: only four occurrences"
        assert rtl_out[6]["pass"], "t=6: fifth occurrence completes [=5]"
        assert rtl_out[7]["pass"], "t=7: [=5] pass is locked after completion"
