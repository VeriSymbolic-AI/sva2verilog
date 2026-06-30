"""Probe pass/fail timing of property-level monitors to author fail-expr refs."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_FIX = Path(__file__).resolve().parents[2] / "tests/fixtures"


def build(name: str) -> tuple[CheckerNode, str]:
    ast = json.loads((_FIX / f"{name}.json").read_text())
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    return optimize(compose(node, clock, label, text)), text


def run(name: str, n: int = 12) -> None:
    checker, text = build(name)
    mods = emit_all(checker)
    top = checker.module_name
    sigs = [p for p, _ in checker.observed_signals]
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        files = []
        for nm, sv in mods.items():
            (work / f"{nm}.sv").write_text(sv)
            files.append(f"{nm}.sv")
        has_ovf = "overflow_flag" in mods[top]
        decl = " ".join(f"logic {s}=0;" for s in sigs)
        conn = " ".join(f".{s}({s})," for s in sigs)
        ovf_port = ".overflow_flag(overflow_flag), " if has_ovf else ""
        # drive each signal with a distinct, genuinely-varying pattern
        _pat = {0: "(_t % 2 == 0)", 1: "(_t % 3 == 0)", 2: "((_t/2) % 2 == 0)"}
        drive = "\n".join(
            f"    {s} <= {_pat.get(i, '(_t % 2 == 1)')};" for i, s in enumerate(sigs)
        )
        disp_sigs = " ".join(f"{s}=%b" for s in sigs)
        disp_args = ", ".join(sigs)
        tb = f"""
module tb;
  logic clk=0, rst_n=0, start=1, disable_i=0;
  {decl}
  logic active, pass, fail, attempt_fired, overflow_flag, disabled_o;
  integer _t=0;
  {top} dut(.clk(clk), .rst_n(rst_n), .start(start), {conn}
      .disable_i(disable_i), .active(active), .pass(pass), .fail(fail),
      .attempt_fired(attempt_fired), {ovf_port}.disabled_o(disabled_o));
  always #5 clk=~clk;
  always @(posedge clk) begin
    _t<=_t+1; rst_n<=(_t!=0);
{drive}
    if (_t>=1)
      $display("t=%0d {disp_sigs} | pass=%b fail=%b", _t, {disp_args}, pass, fail);
    if (_t>={n}) $finish;
  end
endmodule
"""
        (work / "tb.sv").write_text(tb)
        files.append("tb.sv")
        cr = subprocess.run(["iverilog", "-g2012", "-o", "s.out", *files],
                            cwd=str(work), capture_output=True, text=True)
        if cr.returncode:
            print(f"\n### {name}: COMPILE ERR\n", cr.stdout, cr.stderr)
            return
        out = subprocess.run(["vvp", "s.out"], cwd=str(work), capture_output=True, text=True)
        print(f"\n### {name}: '{text}'  sigs={sigs}")
        print(out.stdout)


for nm in ("v13_prop_not", "v13_and_seq", "v13_or_seq", "v13_if_else_prop", "disable_iff"):
    run(nm)
