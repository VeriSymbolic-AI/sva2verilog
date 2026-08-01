"""Decisive non-circular probe: for `a ##N b`, which a->b gap makes pass fire?

Continuous monitoring (start=1 every cycle after reset). Drive a single 1-cycle
`a` pulse at a fixed cycle, then a single 1-cycle `b` pulse swept across many
offsets. Record, for each offset k = (b_cycle - a_cycle), whether pass EVER
fires. The set of k for which pass fires reveals the operator gap the monitor
actually recognizes, independent of report latency.

IEEE-1800: `a ##N b` (continuous) should match iff b is exactly N cycles after a
(k == N). Any other accepted k is a genuine spacing defect.
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


def build_and_emit(fixture: str) -> tuple[str, dict[str, str], list[str]]:
    ast = json.loads((Path("tests/fixtures") / f"{fixture}.json").read_text())
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    ck = optimize(compose(node, clock, label, text))
    mods = emit_all(ck)
    sigs = [p for p, _ in ck.observed_signals]
    return ck.module_name, mods, sigs


def run_gap(fixture: str, a_cycle: int, b_cycle: int, n_cycles: int = 30) -> bool:
    """Return True iff pass fires at any cycle for a@a_cycle, b@b_cycle."""
    top, mods, sigs = build_and_emit(fixture)
    work = Path(tempfile.mkdtemp())
    files = []
    for nm, sv in mods.items():
        (work / f"{nm}.sv").write_text(sv)
        files.append(f"{nm}.sv")
    has_ovf = "overflow_flag" in mods[top]
    ovf_port = ".overflow_flag(ovf), " if has_ovf else ""
    ovf_decl = "logic ovf;" if has_ovf else ""
    # continuous start; single a pulse, single b pulse
    tb = f"""
module tb;
  logic clk=0, rst_n=0, start=0, disable_i=0, a=0, b=0;
  logic active, pass, fail, attempt_fired, disabled_o; {ovf_decl}
  integer _t=0; integer fired=0;
  {top} dut(.clk(clk), .rst_n(rst_n), .start(start), .a(a), .b(b),
    .disable_i(disable_i), .active(active), .pass(pass), .fail(fail),
    .attempt_fired(attempt_fired), {ovf_port}.disabled_o(disabled_o));
  always #5 clk = ~clk;
  always @(posedge clk) begin
    _t <= _t + 1;
    rst_n <= (_t != 0);
    start <= (_t >= 1);           // continuous start after reset
    a <= (_t == {a_cycle});
    b <= (_t == {b_cycle});
    if (_t >= 1 && pass) fired <= 1;
    if (_t == {n_cycles}) begin
      $display("FIRED=%0d", fired);
      $finish;
    end
  end
endmodule
"""
    (work / "tb.sv").write_text(tb)
    files.append("tb.sv")
    cr = subprocess.run(["iverilog", "-g2012", "-o", "s.out", *files],
                        cwd=str(work), capture_output=True, text=True)
    if cr.returncode != 0:
        print("COMPILE ERROR", fixture, cr.stderr[:400])
        return False
    rr = subprocess.run(["vvp", "s.out"], cwd=str(work), capture_output=True, text=True)
    return "FIRED=1" in rr.stdout


def sweep(fixture: str, expected_gaps: list[int], a_cycle: int = 3,
          max_gap: int = 9) -> None:
    print(f"\n=== {fixture}  (IEEE-correct accepted gaps: {expected_gaps}) ===")
    accepted = []
    for k in range(0, max_gap + 1):
        b_cycle = a_cycle + k
        fired = run_gap(fixture, a_cycle, b_cycle)
        mark = ""
        if fired and k not in expected_gaps:
            mark = "  <-- ACCEPTED but IEEE says NO"
        if (not fired) and k in expected_gaps:
            mark = "  <-- REJECTED but IEEE says YES"
        if fired:
            accepted.append(k)
        print(f"  a@{a_cycle}  b@{b_cycle}  (gap={k})  pass_fires={fired}{mark}")
    print(f"  --> monitor accepts gaps {accepted}; IEEE expects {expected_gaps}")


if __name__ == "__main__":
    # a ##3 b: IEEE accepts only gap==3
    sweep("delay_fixed", expected_gaps=[3])
    # a ##[2:5] b: IEEE accepts gaps 2,3,4,5
    sweep("delay_range", expected_gaps=[2, 3, 4, 5])
