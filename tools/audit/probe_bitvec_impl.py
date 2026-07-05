"""Probe the BV_WIDTH>1 sequence-consequent implication monitor timing.

Generates RTL for `a |-> a ##[2:5] b` (fixtures/implication_bitvec.json), drives a
SINGLE antecedent pulse plus various single-b positions, and prints the per-cycle
pass/fail trace via iverilog. Purpose: determine the monitor's report latency and
whether pass/fail fire correctly, BEFORE building an independent BMC reference.

Throwaway audit tool (tools/audit/), not part of the package.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_FIX = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "implication_bitvec.json"


def build_modules() -> tuple[str, dict[str, str], tuple[tuple[str, str], ...]]:
    ast = json.loads(_FIX.read_text())
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    checker = optimize(compose(node, clock, label, text))
    mods = emit_all(checker)
    return checker.module_name, mods, checker.observed_signals


def run_trace(b_cycle: int, n: int = 16) -> None:
    top, mods, sigs = build_modules()
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        files = []
        for name, sv in mods.items():
            (work / f"{name}.sv").write_text(sv)
            files.append(f"{name}.sv")
        # Testbench: reset 1 cycle, single a pulse at cycle 2, single b at b_cycle.
        drive_a = "        if (_t==2) a<=1; else a<=0;\n"
        drive_b = f"        if (_t=={b_cycle}) b<=1; else b<=0;\n"
        tb = f"""
module tb;
  logic clk=0, rst_n=0, start=1, a=0, b=0, disable_i=0;
  logic active, pass, fail, attempt_fired, overflow_flag, disabled_o;
  integer _t=0;
  {top} dut(.clk(clk), .rst_n(rst_n), .start(start), .a(a), .b(b),
      .disable_i(disable_i), .active(active), .pass(pass), .fail(fail),
      .attempt_fired(attempt_fired), .overflow_flag(overflow_flag), .disabled_o(disabled_o));
  always #5 clk=~clk;
  always @(posedge clk) begin
    _t<=_t+1;
    if (_t==0) rst_n<=0; else rst_n<=1;
{drive_a}{drive_b}
    if (_t>=1)
      $display("t=%0d a=%b b=%b | active=%b pass=%b fail=%b ovf=%b",
               _t, a, b, active, pass, fail, overflow_flag);
    if (_t>={n}) $finish;
  end
endmodule
"""
        (work / "tb.sv").write_text(tb)
        files.append("tb.sv")
        cr = subprocess.run(["iverilog", "-g2012", "-o", "sim.out", *files],
                             cwd=str(work), capture_output=True, text=True)
        if cr.returncode != 0:
            print("IVERILOG COMPILE ERROR:\n", cr.stdout, cr.stderr)
            print("--- top module ---\n", mods[top])
            return
        out = subprocess.run(["vvp", "sim.out"], cwd=str(work),
                             capture_output=True, text=True)
        print(f"\n=== a pulse @ t=2, b pulse @ t={b_cycle}  (a |-> a ##[2:5] b) ===")
        print(out.stdout)


if __name__ == "__main__":
    top, mods, sigs = build_modules()
    print("observed signals:", sigs)
    print("modules:", list(mods.keys()))
    # b within window [2+2, 2+5] = [4,7] => should PASS; b at 8 or never => should FAIL.
    for bc in (4, 5, 6, 7, 8, 99):
        run_trace(bc)
