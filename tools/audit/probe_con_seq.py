"""Probe the standalone consequent sequence checker `a ##[2:5] b`.

Drives a single start pulse and a single b at varying positions to learn the
checker's pass/fail/active latency, to decide how to wire the implication top
correctly (without the buggy bv_q gating).
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

_FIX = Path(__file__).resolve().parents[2] / "tests/fixtures/implication_bitvec.json"


def build():
    ast = json.loads(_FIX.read_text())
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    checker = optimize(compose(node, clock, label, text))
    return emit_all(checker)


def run(con_top: str, start_cycle: int, b_cycle: int, n: int = 14) -> None:
    mods = build()
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        files = []
        for name, sv in mods.items():
            (work / f"{name}.sv").write_text(sv)
            files.append(f"{name}.sv")
        tb = f"""
module tb;
  logic clk=0, rst_n=0, start=0, a=0, b=0, disable_i=0;
  logic active, pass, fail, attempt_fired, disabled_o;
  integer _t=0;
  {con_top} dut(.clk(clk), .rst_n(rst_n), .start(start), .a(a), .b(b),
      .disable_i(disable_i), .active(active), .pass(pass), .fail(fail),
      .attempt_fired(attempt_fired), .disabled_o(disabled_o));
  always #5 clk=~clk;
  always @(posedge clk) begin
    _t<=_t+1;
    rst_n<=(_t!=0);
    start<=(_t=={start_cycle});
    a<=(_t=={start_cycle});       // a high at the start cycle (consequent's first elem)
    b<=(_t=={b_cycle});
    if (_t>=1)
      $display("t=%0d start=%b a=%b b=%b | active=%b pass=%b fail=%b",
               _t, start, a, b, active, pass, fail);
    if (_t>={n}) $finish;
  end
endmodule
"""
        (work / "tb.sv").write_text(tb)
        files.append("tb.sv")
        cr = subprocess.run(["iverilog", "-g2012", "-o", "s.out", *files],
                            cwd=str(work), capture_output=True, text=True)
        if cr.returncode:
            print("COMPILE ERR", cr.stdout, cr.stderr); return
        out = subprocess.run(["vvp", "s.out"], cwd=str(work), capture_output=True, text=True)
        print(f"\n=== con `a ##[2:5] b`: start@{start_cycle}, b@{b_cycle} ===")
        print(out.stdout)


if __name__ == "__main__":
    mods = build()
    con = [k for k in mods if k.endswith("_con")][0]
    print("consequent module:", con)
    # window for start@3 is b in [3+2,3+5]=[5,8]
    for bc in (5, 7, 8, 9, 99):
        run(con, 3, bc)
