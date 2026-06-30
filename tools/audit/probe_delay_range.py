"""Probe `a ##[2:5] b` (delay_range) monitor pass timing under a single start."""
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

ast = json.loads(Path("tests/fixtures/delay_range.json").read_text())
node, clock, label, text = import_assertion(ast)
node = normalize(node)
ck = optimize(compose(node, clock, label, text))
mods = emit_all(ck)
top = ck.module_name
print("sigs:", [p for p, _ in ck.observed_signals], "top:", top)


def run(b_cycle: int, n: int = 16) -> None:
    work = Path(tempfile.mkdtemp())
    files = []
    for nm, sv in mods.items():
        (work / f"{nm}.sv").write_text(sv)
        files.append(f"{nm}.sv")
    has_ovf = "overflow_flag" in mods[top]
    ovf = ".overflow_flag(ovf), " if has_ovf else ""
    tb = f"""
module tb;
  logic clk=0, rst_n=0, start=0, a=0, b=0, disable_i=0;
  logic active, pass, fail, attempt_fired, ovf, disabled_o;
  integer _t=0;
  {top} dut(.clk(clk), .rst_n(rst_n), .start(start), .a(a), .b(b),
    .disable_i(disable_i), .active(active), .pass(pass), .fail(fail),
    .attempt_fired(attempt_fired), {ovf}.disabled_o(disabled_o));
  always #5 clk=~clk;
  always @(posedge clk) begin
    _t<=_t+1; rst_n<=(_t!=0);
    start<=(_t==2); a<=(_t==2); b<=(_t=={b_cycle});
    if(_t>=1) $display("t=%0d a=%b b=%b | active=%b pass=%b", _t, a, b, active, pass);
    if(_t>={n}) $finish;
  end
endmodule
"""
    (work / "tb.sv").write_text(tb)
    files.append("tb.sv")
    cr = subprocess.run(["iverilog", "-g2012", "-o", "s.out", *files],
                        cwd=str(work), capture_output=True, text=True)
    if cr.returncode:
        print("ERR", cr.stdout, cr.stderr); return
    print(f"\n=== start/a @ t=3 (driven _t==2), b @ t={b_cycle} ===")
    print(subprocess.run(["vvp", "s.out"], cwd=str(work), capture_output=True, text=True).stdout)


# a matches at t=3 (displayed). window b in [3+2,3+5]=[5,8]. probe each.
for bc in (4, 5, 6, 7, 8):
    run(bc)
