"""Simulation tests for the $stable signal function template (stable.sv.j2).

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
    ast = json.loads((_FIXTURES / "stable.json").read_text(encoding="utf-8"))
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

    sim = SVABehavioralSim("stable", {})
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


def test_rtl_stable_vs_oracle_basic(tmp_path: Path) -> None:
    """$stable(sig): RTL matches oracle.

    sig_prev starts at 0 after reset.
    tick 0: start=T, sig=0 → stable (0==0) → pass=T
    tick 1: start=T, sig=1 → not stable (1!=0) → fail, no pass
    tick 2: start=T, sig=1 → stable (1==1) → pass=T
    tick 3: start=T, sig=0 → not stable (0!=1) → fail, no pass
    """
    checker = _build_checker()
    stimulus = [
        {"start": True, "sig": False},  # tick 0 → stable (0==0) → pass
        {"start": True, "sig": True},   # tick 1 → unstable (1!=0) → fail
        {"start": True, "sig": True},   # tick 2 → stable (1==1) → pass
        {"start": True, "sig": False},  # tick 3 → unstable (0!=1) → fail
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"


def test_rtl_stable_pass_when_unchanged(tmp_path: Path) -> None:
    """$stable(sig): pass when sig doesn't change; fail when it changes."""
    checker = _build_checker()
    stimulus = [
        {"start": True, "sig": False},  # tick 0: prev=0, sig=0 → stable → pass
        {"start": True, "sig": False},  # tick 1: prev=0, sig=0 → stable → pass
        {"start": True, "sig": True},   # tick 2: prev=0, sig=1 → change → fail
        {"start": True, "sig": True},   # tick 3: prev=1, sig=1 → stable → pass
    ]
    _, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert     rtl_out[0]["pass"], "tick 0: stable at 0 → pass"
    assert     rtl_out[1]["pass"], "tick 1: stable at 0 → pass"
    assert not rtl_out[2]["pass"], "tick 2: 0→1 change → not pass"
    assert     rtl_out[2]["fail"], "tick 2: 0→1 change → fail"
    assert     rtl_out[3]["pass"], "tick 3: stable at 1 → pass"


def test_rtl_stable_no_start_no_output(tmp_path: Path) -> None:
    """$stable: start=F suppresses all outputs even when sig is stable."""
    checker = _build_checker()
    stimulus = [
        {"start": False, "sig": False},
        {"start": False, "sig": False},
        {"start": False, "sig": True},
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    for i, rtl in enumerate(rtl_out):
        assert not rtl["pass"],   f"tick {i}: no pass without start"
        assert not rtl["fail"],   f"tick {i}: no fail without start"
        assert not rtl["active"], f"tick {i}: not active without start"


def test_rtl_stable_full_oracle_compare(tmp_path: Path) -> None:
    """$stable: long mixed trace fully matches oracle."""
    checker = _build_checker()
    stimulus = [
        {"start": True,  "sig": False},  # 0 → stable (0==0)
        {"start": True,  "sig": True},   # 1 → change (1!=0)
        {"start": False, "sig": True},   # 2
        {"start": True,  "sig": True},   # 3 → stable
        {"start": True,  "sig": False},  # 4 → change
        {"start": True,  "sig": False},  # 5 → stable
        {"start": True,  "sig": False},  # 6 → stable
        {"start": False, "sig": True},   # 7
    ]
    oracle_out, rtl_out = _run_both(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    for i, (oracle, rtl) in enumerate(zip(oracle_out, rtl_out)):
        assert rtl["pass"]   == oracle["pass"],   f"tick {i}: pass mismatch"
        assert rtl["fail"]   == oracle["fail"],   f"tick {i}: fail mismatch"
        assert rtl["active"] == oracle["active"], f"tick {i}: active mismatch"
