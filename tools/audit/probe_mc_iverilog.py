"""Probe: iverilog compile + sim for multi-clock mode 1 (v1.4.1 B2)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.ast_importer import import_assertion  # noqa: E402
from sva2rtl.composer import compose  # noqa: E402
from sva2rtl.emitter import emit_all  # noqa: E402
from sva2rtl.frontend import invoke_slang  # noqa: E402
from sva2rtl.normalizer import normalize  # noqa: E402


def main() -> None:
    sv_src = Path("/tmp/_mc_b2_tb.sv")
    sv_src.write_text(
        "module m(input logic clk1, clk2, a, b);\n"
        "  ap: assert property (@(posedge clk1) a ##1 @(posedge clk2) b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    ast = invoke_slang(sv_src, "slang")
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    ck = compose(node, clock, label, text)
    mods = emit_all(ck)

    with tempfile.TemporaryDirectory(prefix="sva2rtl_mc_") as tmpdir:
        d = Path(tmpdir)
        for name, src in mods.items():
            (d / f"{name}.sv").write_text(src, encoding="utf-8")

        tb = """\
module tb;
    reg clk1 = 0, clk2 = 0, rst_n = 0, a = 0, b = 0;
    wire active, pass, fail;
    always #5 clk1 = ~clk1;
    always #3 clk2 = ~clk2;
    sva_ap dut (.clk1(clk1), .clk2(clk2), .rst_n(rst_n), .a(a), .b(b),
                .active(active), .pass(pass), .fail(fail));
    initial begin
        $dumpfile("mc_b2.vcd"); $dumpvars;
        #1 rst_n = 0; #10 rst_n = 1;
        a = 1;
        #10;
        #40;
        $display("t=%0t pass=%b fail=%b active=%b", $time, pass, fail, active);
        #30 $finish;
    end
endmodule
"""
        (d / "tb.sv").write_text(tb)
        files = [str(d / f) for f in sorted(os.listdir(d)) if f.endswith(".sv")]
        cmds = ["iverilog", "-g2012", "-o", str(d / "tb.out")] + files
        r = subprocess.run(cmds, capture_output=True, text=True, cwd=str(d))
        if r.returncode != 0:
            print("IVERILOG COMPILE FAILED:", r.stderr[-600:])
            return
        print("IVERILOG COMPILE: OK")
        r2 = subprocess.run(
            ["vvp", str(d / "tb.out")],
            capture_output=True, text=True, cwd=str(d), timeout=15,
        )
        print(r2.stdout.strip())


if __name__ == "__main__":
    main()
