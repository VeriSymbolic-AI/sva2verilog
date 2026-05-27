"""Simulation tests for the $fell signal function template (fell.sv.j2).

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

from tests.simulation.tb_generator import (
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_FIXTURES = Path(__file__).parent.parent / "fixtures"


def _build_checker():  # type: ignore[no-untyped-def]
    ast = json.loads((_FIXTURES / "fell.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)


def _run_both(
    checker,  # type: ignore[no-untyped-def]
    stimulus: list[dict],
    tmp_path: Path,
) -> tuple[list[dict], list[dict]]:
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]

    sim = SVABehavioralSim("fell", {})
    oracle_out = [sim.tick(s) for s in stimulus]

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


def test_rtl_fell_vs_oracle_transition(tmp_path: Path) -> None:
    """$fell(sig): RTL matches oracle across a 1→0 transition.

    tick 0: start=T, sig=1 → fell_detect=0 (sig_prev=0) → pass=F
    tick 1: start=T, sig=0 → fell_detect=1 (1→0) → pass=T
    tick 2: start=T, sig=0 → fell_detect=0 (0→0) → pass=F
    tick 3: start=T, sig=1 → fell_detect=0 (0→1 is rose) → pass=F
    """
    checker = _build_checker()
    stimulus = [
        {"start": True, "sig": True},   # tick 0
        {"start": True, "sig": False},  # tick 1 → pass
        {"start": True, "sig": False},  # tick 2 → no pass
        {"start": True, "sig": True},   # tick 3 → no pass (rose)
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"


def test_rtl_fell_pass_fires_at_correct_tick(tmp_path: Path) -> None:
    """$fell(sig): pass fires exactly on the 1→0 edge."""
    checker = _build_checker()
    stimulus = [
        {"start": True, "sig": True},   # tick 0: old_prev=0, sig=1 → fell=0 → pass=F
        {"start": True, "sig": False},  # tick 1: old_prev=1, sig=0 → fell=1 → pass=T
        {"start": True, "sig": False},  # tick 2: old_prev=0, sig=0 → fell=0 → pass=F
    ]
    _, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert not rtl_out[0]["pass"], "tick 0: 0→1 edge, no fell"
    assert     rtl_out[1]["pass"], "tick 1: 1→0 edge → fell → pass"
    assert not rtl_out[2]["pass"], "tick 2: 0→0, no fell"


def test_rtl_fell_no_start_no_output(tmp_path: Path) -> None:
    """$fell(sig): start=F suppresses all outputs."""
    checker = _build_checker()
    stimulus = [
        {"start": False, "sig": True},   # tick 0
        {"start": False, "sig": False},  # tick 1: fell event but start=F
        {"start": False, "sig": True},   # tick 2
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    for i, rtl in enumerate(rtl_out):
        assert not rtl["pass"],   f"tick {i}: no start → no pass"
        assert not rtl["fail"],   f"tick {i}: no start → no fail"
        assert not rtl["active"], f"tick {i}: no start → not active"


def test_rtl_fell_full_oracle_compare(tmp_path: Path) -> None:
    """$fell(sig): long trace — every cycle matches oracle."""
    checker = _build_checker()
    stimulus = [
        {"start": True,  "sig": True},   # 0
        {"start": True,  "sig": False},  # 1 → fell
        {"start": False, "sig": False},  # 2
        {"start": True,  "sig": True},   # 3 → rose (not fell)
        {"start": True,  "sig": True},   # 4
        {"start": True,  "sig": False},  # 5 → fell
        {"start": True,  "sig": False},  # 6
        {"start": False, "sig": True},   # 7
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"
