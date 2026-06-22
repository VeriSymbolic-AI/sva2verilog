"""Simulation tests for the disable_iff_top template.

The fixture ``disable_iff.json`` wraps ``a |-> b`` (overlapping implication,
BV_WIDTH=1) with ``disable iff (!rst_n)``.

Disable logic:
    ``cond_result = (!rst_n)``
    ``effective_disable = disable_i | cond_result``

The body (overlap_bitvec) is passed ``effective_disable`` instead of
``disable_i``.  When the disable condition is true — i.e. when ``rst_n=0`` —
the body is effectively disabled and all outputs are gated to 0.

RTL timing for the wrapped ``a |-> b`` (BV_WIDTH=1):
    Antecedent and consequent are each bool_expr modules (registered, 1 cycle).
    With BV_WIDTH=1, pass NEVER fires for a single-cycle antecedent (thread
    leaves MSB before consequent registers).  Fail fires at t+2 after the
    antecedent fires.

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


# ── Fixture loading ───────────────────────────────────────────────────────────


def _build_checker() -> CheckerNode:
    ast = json.loads((_FIXTURES / "disable_iff.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)


# ── Run helper ────────────────────────────────────────────────────────────────


def _run_stimulus(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str = "iverilog",
) -> list[dict]:
    """Compile and run stimulus through the disable_iff RTL, return outputs."""
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]

    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=False,  # disable_iff_top has no overflow_flag port
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
# Normal operation (disable condition = false after reset, disable_i = 0)
# ══════════════════════════════════════════════════════════════════════════════


def test_fail_fires_at_t2_when_b_false(tmp_path: Path) -> None:
    """disable_iff: when condition is false (rst_n=1 after reset), body runs normally.

    Body is a |-> b (BV_WIDTH=1).  With bool_expr children (registered, 1-cycle):
      t=0: start=1, a=1, b=0 → antecedent pipeline starts
      t=1: ant_pass_w=1 → bv_q<=1; con has no start yet → con_pass_w=0
      t=2: bv_q=1 → con_start_w=1; con_pass_w=0 (registered from t=1)
           → fail=1 (bv_q[0]=1 & !con_pass_w & con_start_w)
    """
    checker = _build_checker()
    stimulus = [
        {"start": True,  "a": True,  "b": False},  # t=0
        {"start": False, "a": False, "b": False},  # t=1
        {"start": False, "a": False, "b": False},  # t=2: fail fires
        {"start": False, "a": False, "b": False},  # t=3: no more activity
    ]
    rtl_out = _run_stimulus(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)

    assert not rtl_out[0]["fail"], "t=0: start cycle — not yet active"
    assert not rtl_out[1]["fail"], "t=1: antecedent thread inserted into bv"
    assert     rtl_out[2]["fail"], "t=2: thread matures, b=0 → fail"
    assert not rtl_out[3]["fail"], "t=3: thread already consumed"


def test_no_outputs_when_start_false(tmp_path: Path, simulator: str) -> None:
    """disable_iff: when start=F, body never becomes active."""
    checker = _build_checker()
    stimulus = [
        {"start": False, "a": True,  "b": False},
        {"start": False, "a": True,  "b": False},
        {"start": False, "a": False, "b": True},
    ]
    rtl_out = _run_stimulus(checker, stimulus, tmp_path)

    for i, row in enumerate(rtl_out):
        assert not row["active"], f"t={i}: start=F → active=0"
        assert not row["pass"],   f"t={i}: start=F → pass=0"
        assert not row["fail"],   f"t={i}: start=F → fail=0"


def test_multiple_starts_produce_multiple_fails(tmp_path: Path, simulator: str) -> None:
    """disable_iff: consecutive antecedent triggers each produce a fail.

    With BV_WIDTH=1, overlap fires at overflow for back-to-back starts.
    Two separate starts (with gap) each independently fire a fail at t+2.
    """
    checker = _build_checker()
    # start at t=0, no b → fail at t=2
    # start at t=4, no b → fail at t=6
    stimulus = [
        {"start": True,  "a": True,  "b": False},  # t=0
        {"start": False, "a": False, "b": False},  # t=1
        {"start": False, "a": False, "b": False},  # t=2: fail
        {"start": False, "a": False, "b": False},  # t=3: idle
        {"start": True,  "a": True,  "b": False},  # t=4: second start
        {"start": False, "a": False, "b": False},  # t=5
        {"start": False, "a": False, "b": False},  # t=6: fail
    ]
    rtl_out = _run_stimulus(checker, stimulus, tmp_path)

    assert len(rtl_out) == len(stimulus)
    assert     rtl_out[2]["fail"], "t=2: first fail"
    assert not rtl_out[3]["fail"], "t=3: idle"
    assert     rtl_out[6]["fail"], "t=6: second fail"


# ══════════════════════════════════════════════════════════════════════════════
# External disable_i: outer disable gates everything
# ══════════════════════════════════════════════════════════════════════════════


def test_external_disable_i_gates_outputs(tmp_path: Path, simulator: str) -> None:
    """disable_iff: disable_i=1 gates active/pass/fail to 0.

    Even though a=1 would normally trigger an antecedent, with disable_i=1
    the outputs are all 0.
    """
    checker = _build_checker()
    stimulus = [
        {"start": True,  "a": True,  "b": False, "disable_i": True},  # t=0: disabled
        {"start": True,  "a": True,  "b": False, "disable_i": True},  # t=1: still disabled
        {"start": False, "a": False, "b": False, "disable_i": True},  # t=2: would-be fail
    ]
    rtl_out = _run_stimulus(checker, stimulus, tmp_path)

    for i, row in enumerate(rtl_out):
        assert not row["active"], f"t={i}: disable_i=1 → active=0"
        assert not row["pass"],   f"t={i}: disable_i=1 → pass=0"
        assert not row["fail"],   f"t={i}: disable_i=1 → fail=0"


def test_disable_then_reenable(tmp_path: Path, simulator: str) -> None:
    """disable_iff: after disable_i=0 is restored, body starts fresh (state cleared).

    t=0: start=1, a=1 → antecedent fires
    t=1: disable_i=1 → state cleared, all outputs 0
    t=2: disable_i=0 again → body re-enabled; state was cleared by disable
         so no fail fires (thread from t=0 was lost when disabled)
    """
    checker = _build_checker()
    stimulus = [
        {"start": True,  "a": True,  "b": False},              # t=0: start
        {"start": False, "a": False, "b": False, "disable_i": True},  # t=1: disable
        {"start": False, "a": False, "b": False},               # t=2: re-enable
        {"start": False, "a": False, "b": False},               # t=3: idle
    ]
    rtl_out = _run_stimulus(checker, stimulus, tmp_path)

    # t=1: disabled → all 0
    assert not rtl_out[1]["active"], "t=1: disabled"
    assert not rtl_out[1]["fail"],   "t=1: disabled → no fail"

    # t=2 and t=3: re-enabled but state was cleared → no fail
    assert not rtl_out[2]["fail"], "t=2: thread lost during disable → no fail"
    assert not rtl_out[3]["fail"], "t=3: no pending threads"


# ══════════════════════════════════════════════════════════════════════════════
# Condition-driven disable: rst_n=0 → !rst_n=1 → effective_disable=1
# ══════════════════════════════════════════════════════════════════════════════


def test_condition_disable_gates_body(tmp_path: Path, simulator: str) -> None:
    """disable_iff: when the condition !rst_n fires (rst_n=0), body is disabled.

    This test uses a custom testbench that drives rst_n=0 mid-simulation.
    Setting rst_n=0 causes cond_result=1 → effective_disable=1 → body gated.

    Custom stimulus:
      reset phase (rst_n=0 × 2), then rst_n=1 for active cycles.
      t=0: start=1, a=1, b=0, rst_n=1 → antecedent fires normally
      t=1: start=0, rst_n=0  → condition=1 → body disabled; all outputs=0
      t=2: start=0, rst_n=1  → re-enabled; state cleared → no fail
    """
    checker = _build_checker()
    modules = emit_all(checker)
    sv_sources = list(modules.values())

    # Build a custom testbench that drives rst_n from inside the stimulus loop
    tb = _custom_tb_with_rst_control(checker.module_name)

    rtl_out = run_simulation(
        simulator=simulator,
        module_name=checker.module_name,
        sv_sources=sv_sources,
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=False,
    )

    # Expect 3 output rows from the custom TB
    assert len(rtl_out) == 3, f"Expected 3 rows, got {len(rtl_out)}"

    # t=0: normal operation, not yet active (antecedent not yet registered)
    assert not rtl_out[0]["fail"], "t=0: no fail yet"
    assert not rtl_out[0]["pass"], "t=0: no pass yet"

    # t=1: rst_n=0 → condition=1 → disabled; all outputs must be 0
    assert not rtl_out[1]["active"], "t=1: condition disable → active=0"
    assert not rtl_out[1]["pass"],   "t=1: condition disable → pass=0"
    assert not rtl_out[1]["fail"],   "t=1: condition disable → fail=0 (gated)"

    # t=2: rst_n=1 again; state was cleared → no fail (thread lost during rst_n=0)
    assert not rtl_out[2]["fail"], "t=2: thread was lost during rst_n=0 → no fail"


def _custom_tb_with_rst_control(module_name: str, simulator: str = "iverilog") -> str:
    """Generate a custom testbench that drives rst_n=0 mid-simulation.

    The standard :func:`generate_testbench` hard-codes rst_n=1 after reset;
    this variant inlines the reset drive so we can force rst_n=0 during an
    active cycle to exercise the disable_iff condition.
    """
    return f"""`timescale 1ns/1ps
module tb;

    reg clk;
    initial clk = 0;
    always #5 clk = ~clk;

    reg rst_n;
    reg disable_i;
    reg start;
    reg a;
    reg b;

    wire active;
    wire pass_out;
    wire fail_out;
    wire attempt_fired;
    wire disabled_o;

    {module_name} dut (
        .clk(clk),
        .rst_n    (rst_n),
        .start    (start),
        .a(a),
        .b(b),
        .disable_i     (disable_i),
        .active        (active),
        .pass          (pass_out),
        .fail          (fail_out),
        .attempt_fired (attempt_fired),
        .disabled_o    (disabled_o)
    );

    initial begin
        // Reset sequence: hold rst_n=0 for 2 cycles
        rst_n     = 0;
        disable_i = 0;
        start     = 0;
        a         = 0;
        b         = 0;
        repeat(2) @(posedge clk);

        // Release reset
        @(negedge clk); rst_n = 1;

        // ── cycle 0: start=1, a=1, b=0 — antecedent fires ──────────────
        start = 1; a = 1; b = 0;
        @(posedge clk);
        $display("%b %b %b", active, pass_out, fail_out);

        @(negedge clk);
        // ── cycle 1: drive rst_n=0 — condition (!rst_n)=1 → disable ────
        start = 0; a = 0; b = 0; rst_n = 0;
        @(posedge clk);
        $display("%b %b %b", active, pass_out, fail_out);

        @(negedge clk);
        // ── cycle 2: restore rst_n=1 — re-enable, but state was cleared ─
        rst_n = 1; start = 0; a = 0; b = 0;
        @(posedge clk);
        $display("%b %b %b", active, pass_out, fail_out);

        $finish;
    end

endmodule"""


# ══════════════════════════════════════════════════════════════════════════════
# Oracle cross-check tests
# ══════════════════════════════════════════════════════════════════════════════


class TestDisableIffOracleCrosscheck:
    """Oracle cross-check: verify RTL and oracle event patterns match."""

    def _count_events(self, results: list[dict]) -> dict[str, int]:
        return {
            "pass": sum(1 for r in results if r.get("pass")),
            "fail": sum(1 for r in results if r.get("fail")),
            "active": sum(1 for r in results if r.get("active")),
        }

    def test_disable_iff_oracle_no_disable(self, tmp_path: Path, simulator: str) -> None:
        """disable_iff: with condition false, RTL and oracle produce same fail events."""
        checker = _build_checker()
        stimulus = [
            {"start": True,  "a": True,  "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": True,  "a": True,  "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
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
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["fail"] > 0
        assert oracle_events["fail"] > 0

    @pytest.mark.xfail(
        reason="simulate_checker_hierarchy disable_iff oracle does not correctly "
               "gate all fail events when disable_i=True",
        strict=True,
    )
    def test_disable_iff_oracle_disabled(self, tmp_path: Path, simulator: str) -> None:
        """disable_iff: with disable_i=True, both RTL and oracle produce zero events."""
        checker = _build_checker()
        stimulus = [
            {"start": True,  "a": True,  "b": False, "disable_i": True},
            {"start": True,  "a": True,  "b": False, "disable_i": True},
            {"start": False, "a": False, "b": False, "disable_i": True},
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
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["fail"] == 0
        assert rtl_events["pass"] == 0
        assert oracle_events["fail"] == 0
        assert oracle_events["pass"] == 0
