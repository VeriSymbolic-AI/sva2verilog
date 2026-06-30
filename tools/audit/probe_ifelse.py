"""Probe if/else monitor with independently-varying sel/a/b to derive fail expr."""
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

ast = json.loads(Path("tests/fixtures/v13_if_else_prop.json").read_text())
node, clock, label, text = import_assertion(ast)
node = normalize(node)
ck = optimize(compose(node, clock, label, text))
mods = emit_all(ck)
top = ck.module_name
print("sigs order:", [p for p, _ in ck.observed_signals])

work = Path(tempfile.mkdtemp())
files = []
for nm, sv in mods.items():
    (work / f"{nm}.sv").write_text(sv)
    files.append(f"{nm}.sv")

tb = f"""
module tb;
  logic clk=0, rst_n=0, start=1, disable_i=0, a=0, b=0, sel=0;
  logic active, pass, fail, attempt_fired, disabled_o;
  integer _t=0;
  {top} dut(.clk(clk), .rst_n(rst_n), .start(start), .a(a), .b(b), .sel(sel),
    .disable_i(disable_i), .active(active), .pass(pass), .fail(fail),
    .attempt_fired(attempt_fired), .disabled_o(disabled_o));
  always #5 clk=~clk;
  always @(posedge clk) begin
    _t<=_t+1; rst_n<=(_t!=0);
    sel<=(_t%2==0); a<=(_t%3!=0); b<=((_t/2)%2==0);
    if(_t>=1) $display("t=%0d sel=%b a=%b b=%b | pass=%b fail=%b", _t, sel, a, b, pass, fail);
    if(_t>=13) $finish;
  end
endmodule
"""
(work / "tb.sv").write_text(tb)
files.append("tb.sv")
cr = subprocess.run(["iverilog", "-g2012", "-o", "s.out", *files],
                    cwd=str(work), capture_output=True, text=True)
if cr.returncode:
    print("COMPILE ERR", cr.stdout, cr.stderr)
else:
    print(subprocess.run(["vvp", "s.out"], cwd=str(work), capture_output=True, text=True).stdout)
