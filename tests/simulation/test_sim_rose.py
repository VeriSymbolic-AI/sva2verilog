"""Simulation tests for the $rose signal function template (rose.sv.j2).

Each test compiles the emitted SystemVerilog with iverilog, drives stimulus,
and compares the captured RTL outputs against the behavioral oracle.

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


def _build_checker(name: str = "rose") -> CheckerNode:
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_both(
    checker: CheckerNode,
    stimulus: list[dict],
    tmp_path: Path,
) -> tuple[list[dict], list[dict]]:
    """Run stimulus through both oracle and RTL, return (oracle_outputs, rtl_outputs)."""
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]

    # Oracle
    sim = SVABehavioralSim("rose", {})
    oracle_out = [sim.tick(s) for s in stimulus]

    # RTL
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=False,
    )
    rtl_out = run_simulation(
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=False,
    )

    return oracle_out, rtl_out


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_rtl_rose_vs_oracle_transition(tmp_path: Path) -> None:
    """$rose(sig): RTL matches oracle across a 0→1 transition.

    tick 0: start=T, sig=0 → rose_detect=0 → pass=F
    tick 1: start=T, sig=1 → rose_detect=1 (0→1) → pass=T
    tick 2: start=T, sig=1 → rose_detect=0 (1→1) → pass=F
    tick 3: start=T, sig=0 → rose_detect=0 (1→0) → pass=F (fell, not rose)
    """
    checker = _build_checker("rose")
    stimulus = [
        {"start": True,  "sig": False},  # tick 0
        {"start": True,  "sig": True},   # tick 1 → pass
        {"start": True,  "sig": True},   # tick 2 → no pass (stable)
        {"start": True,  "sig": False},  # tick 3 → no pass (fell)
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus), (
        f"Expected {len(stimulus)} output rows, got {len(rtl_out)}"
    )

    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass   mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail   mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"


def test_rtl_rose_pass_fires_at_correct_tick(tmp_path: Path) -> None:
    """$rose(sig): pass fires exactly on the 0→1 edge, not before or after."""
    checker = _build_checker("rose")
    stimulus = [
        {"start": True, "sig": False},  # tick 0: old_prev=0, sig=0 → rose=0 → pass=F
        {"start": True, "sig": True},   # tick 1: old_prev=0, sig=1 → rose=1 → pass=T
        {"start": True, "sig": True},   # tick 2: old_prev=1, sig=1 → rose=0 → pass=F
    ]
    _, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert not rtl_out[0]["pass"], "tick 0: sig=0→0, no rose event"
    assert     rtl_out[1]["pass"], "tick 1: sig=0→1, rose event → pass"
    assert not rtl_out[2]["pass"], "tick 2: sig=1→1, no rose event"


def test_rtl_rose_no_start_no_output(tmp_path: Path) -> None:
    """$rose(sig): when start=F, pass/fail/active are all 0 regardless of sig."""
    checker = _build_checker("rose")
    stimulus = [
        {"start": False, "sig": False},  # tick 0
        {"start": False, "sig": True},   # tick 1: 0→1 but start=F
        {"start": False, "sig": False},  # tick 2: 1→0 but start=F
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    for i, rtl in enumerate(rtl_out):
        assert not rtl["pass"],   f"tick {i}: start=F → no pass"
        assert not rtl["fail"],   f"tick {i}: start=F → no fail"
        assert not rtl["active"], f"tick {i}: start=F → not active"


def test_rtl_rose_disable_gates_output(tmp_path: Path) -> None:
    """$rose(sig): disable_i=1 gates all outputs to 0."""
    checker = _build_checker("rose")
    # tick 0: normal pass should fire (0→1)
    # tick 1: disable_i=1 even during a rose event → all outputs = 0
    stimulus = [
        {"start": True, "sig": False, "disable_i": False},  # tick 0 → fail (no rose)
        {"start": True, "sig": True,  "disable_i": True},   # tick 1 → disabled → all 0
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
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=False,
    )

    # tick 1: disable_i=1 → all outputs 0
    assert not rtl_out[1]["pass"],   "disabled: pass must be 0"
    assert not rtl_out[1]["fail"],   "disabled: fail must be 0"
    assert not rtl_out[1]["active"], "disabled: active must be 0"


def test_rtl_rose_full_oracle_compare(tmp_path: Path) -> None:
    """$rose(sig): long trace — every cycle matches oracle."""
    checker = _build_checker("rose")
    # Long mixed trace
    stimulus = [
        {"start": True,  "sig": False},  # 0
        {"start": True,  "sig": True},   # 1 → rose
        {"start": False, "sig": True},   # 2
        {"start": True,  "sig": True},   # 3
        {"start": True,  "sig": False},  # 4 → fell (no rose)
        {"start": True,  "sig": False},  # 5
        {"start": True,  "sig": True},   # 6 → rose
        {"start": True,  "sig": True},   # 7
        {"start": False, "sig": False},  # 8
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"
