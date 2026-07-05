"""Simulation tests for the $past signal function template (past.sv.j2).

The fixture (past.json) encodes $past(sig, 3) — the value of sig 3 clock
cycles ago.  This exercises the multi-FF shift register variant of the
template (DEPTH > 1).

Requirements covered: TEST-03, TEST-04
"""

from __future__ import annotations

import json
from pathlib import Path

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

_PAST_DEPTH = 3  # matches the depth in past.json


def _build_checker() -> CheckerNode:
    ast = json.loads((_FIXTURES / "past.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.params["depth"] == str(_PAST_DEPTH)
    return checker


def _run_both(
    checker: CheckerNode,
    stimulus: list[dict],
    tmp_path: Path,
    simulator: str = "iverilog",
) -> tuple[list[dict], list[dict]]:
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]

    sim = SVABehavioralSim("past", {"depth": _PAST_DEPTH})
    oracle_out = [sim.tick(s) for s in stimulus]

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
    )
    return oracle_out, rtl_out


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_rtl_past_pass_after_depth_cycles(tmp_path: Path, simulator: str) -> None:
    """$past(sig, 3): pass fires at tick 3 when sig was 1 at tick 0.

    Cycle semantics: pass = start & shift_q[DEPTH-1] where shift_q captures
    the value of sig exactly DEPTH cycles ago.

    tick 0: sig=T, start=F → no pass; shift_q samples sig
    tick 1: sig=F, start=F
    tick 2: sig=F, start=F
    tick 3: sig=F, start=T → past_value = sig@tick0 = T → pass=T
    tick 4: sig=F, start=T → past_value = sig@tick1 = F → pass=F
    """
    checker = _build_checker()
    stimulus = [
        {"start": False, "sig": True},   # tick 0: sig=1 enters shift
        {"start": False, "sig": False},  # tick 1: sig=0 enters shift
        {"start": False, "sig": False},  # tick 2: sig=0 enters shift
        {"start": True,  "sig": False},  # tick 3: past_value = sig@0 = T → pass
        {"start": True,  "sig": False},  # tick 4: past_value = sig@1 = F → fail
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    # Ticks 0–2: start=F → no pass, no fail, not active
    for i in range(3):
        assert not rtl_out[i]["pass"],   f"tick {i}: start=F → no pass"
        assert not rtl_out[i]["fail"],   f"tick {i}: start=F → no fail"
        assert not rtl_out[i]["active"], f"tick {i}: start=F → not active"

    assert     rtl_out[3]["pass"], "tick 3: past_value=1 (sig@0=T) → pass"
    assert not rtl_out[3]["fail"], "tick 3: pass, not fail"
    assert not rtl_out[4]["pass"], "tick 4: past_value=0 (sig@1=F) → no pass"
    assert     rtl_out[4]["fail"], "tick 4: past_value=0 → fail"


def test_rtl_past_vs_oracle_full_trace(tmp_path: Path, simulator: str) -> None:
    """$past(sig, 3): RTL output matches oracle for a 10-cycle trace."""
    checker = _build_checker()
    stimulus = [
        {"start": False, "sig": True},   # 0
        {"start": False, "sig": False},  # 1
        {"start": False, "sig": True},   # 2
        {"start": True,  "sig": False},  # 3: past=sig@0=T → pass
        {"start": True,  "sig": False},  # 4: past=sig@1=F → fail
        {"start": True,  "sig": False},  # 5: past=sig@2=T → pass
        {"start": True,  "sig": False},  # 6: past=sig@3=F → fail
        {"start": False, "sig": False},  # 7
        {"start": True,  "sig": True},   # 8: past=sig@5=F → fail
        {"start": True,  "sig": False},  # 9: past=sig@6=F → fail
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"


def test_rtl_past_shift_warmup(tmp_path: Path, simulator: str) -> None:
    """$past(sig, 3): first DEPTH ticks read zero from uninitialized shift register."""
    checker = _build_checker()
    # First 3 ticks with start=T: past_value = 0 (shift not yet filled)
    # so pass=F and fail=T for all
    stimulus = [
        {"start": True, "sig": True},  # tick 0: past_value=0 (shift[2]=0) → fail
        {"start": True, "sig": True},  # tick 1: past_value=0 → fail
        {"start": True, "sig": True},  # tick 2: past_value=0 → fail
        {"start": True, "sig": True},  # tick 3: past_value=sig@0=1 → pass
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"

    assert not rtl_out[0]["pass"], "tick 0: shift empty → no pass"
    assert     rtl_out[0]["fail"], "tick 0: shift empty → fail"
    assert     rtl_out[3]["pass"], "tick 3: shift filled → past=sig@0=T → pass"


def test_rtl_past_disable_clears_shift(tmp_path: Path, simulator: str) -> None:
    """$past: disable_i clears the shift register; subsequent reads see 0."""
    checker = _build_checker()
    # Fill the shift with 1s, then disable, then assert past_value = 0
    stimulus = [
        {"start": False, "sig": True},               # 0 → fill shift
        {"start": False, "sig": True},               # 1
        {"start": False, "sig": True},               # 2
        {"start": True,  "sig": False, "disable_i": True},  # 3 → disable clears shift
        {"start": True,  "sig": False},              # 4 → shift was cleared → past=0 → fail
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
    )

    # tick 3: disable_i=1 → all outputs 0
    assert not rtl_out[3]["pass"],   "disabled: pass must be 0"
    assert not rtl_out[3]["fail"],   "disabled: fail must be 0"
    assert not rtl_out[3]["active"], "disabled: active must be 0"
    # tick 4: shift was cleared by disable; past_value = 0 → fail
    assert not rtl_out[4]["pass"], "after disable: shift was cleared → past=0 → no pass"
    assert     rtl_out[4]["fail"], "after disable: shift was cleared → past=0 → fail"
