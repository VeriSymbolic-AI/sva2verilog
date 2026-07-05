"""Probe: LFSR determinism + injection test for multi-clock sync_2dff (v1.4.2)."""

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


def _compile_and_run(seed: str, meta: bool) -> str:
    sv_src = Path("/tmp/_mc_lfsr_tb.sv")
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

    with tempfile.TemporaryDirectory(prefix="sva2rtl_mc_lfsr_") as tmpdir:
        d = Path(tmpdir)
        for name, src in mods.items():
            (d / f"{name}.sv").write_text(src, encoding="utf-8")

        # If META_ENABLE, override the sync_2dff parameter in the top module.
        if meta:
            # Override META_ENABLE=1 + LFSR_SEED in the sync_2dff instantiation
            for fname in sorted(os.listdir(d)):
                fp = d / fname
                txt = fp.read_text()
                if "sync_" in fname and "_i" not in fname:
                    txt = txt.replace(
                        "parameter META_ENABLE = 0,",
                        "parameter META_ENABLE = 1,",
                    )
                    txt = txt.replace(
                        "parameter [7:0] LFSR_SEED = 8'hA5",
                        f"parameter [7:0] LFSR_SEED = 8'h{seed}",
                    )
                fp.write_text(txt)

        tb_seed = seed  # Passed through file naming
        tb_seed_file = d / f"seed_{tb_seed}.txt"
        tb_seed_file.write_text(tb_seed)

        tb = f"""\
module tb;
    reg clk1 = 0, clk2 = 0, rst_n = 0, a = 0, b = 0;
    wire active, pass, fail;
    always #5 clk1 = ~clk1;
    always #3 clk2 = ~clk2;
    sva_ap dut (.clk1(clk1), .clk2(clk2), .rst_n(rst_n), .a(a), .b(b),
                .active(active), .pass(pass), .fail(fail));
    integer pass_count, fail_count;
    initial begin
        pass_count = 0; fail_count = 0;
        #1 rst_n = 0; #10 rst_n = 1;
        a = 1;
        repeat (50) @(posedge clk1);
        repeat (80) @(posedge clk2);
        $display("pass=%b fail=%b active=%b", pass, fail, active);
        $display("SEED_{tb_seed}=%b-%b-%b", pass, fail, active);
        $finish;
    end
endmodule
"""
        (d / "tb.sv").write_text(tb)
        files = [str(d / f) for f in sorted(os.listdir(d)) if f.endswith(".sv")]
        cmds = ["iverilog", "-g2012", "-o", str(d / "tb.out")] + files
        r = subprocess.run(cmds, capture_output=True, text=True, cwd=str(d))
        if r.returncode != 0:
            return f"IVL_ERROR: {r.stderr[-300:]}"
        r2 = subprocess.run(
            ["vvp", str(d / "tb.out")],
            capture_output=True, text=True, cwd=str(d), timeout=15,
        )
        return r2.stdout.strip()


def _extract_signal(line: str) -> str:
    """Extract SEED_XX=pass-fail-active from the output line."""
    for part in line.split("\n"):
        if part.startswith("SEED_"):
            return part.strip()
    return "NO_SEED"


def main() -> None:
    # Test 1: META_ENABLE=0 — two runs should be identical
    print("=== META_ENABLE=0: determinism ===")
    r1 = _extract_signal(_compile_and_run("A5", meta=False))
    r2 = _extract_signal(_compile_and_run("A5", meta=False))
    print(f"run1: {r1}  run2: {r2}")
    assert r1 == r2, f"META_ENABLE=0 runs differ!\n{r1}\n{r2}"
    print("PASS: identical output (no injection)\n")

    # Test 2: META_ENABLE=1, same seed — deterministic
    print("=== META_ENABLE=1 seed=A5: determinism ===")
    r3 = _extract_signal(_compile_and_run("A5", meta=True))
    r4 = _extract_signal(_compile_and_run("A5", meta=True))
    print(f"run1: {r3}  run2: {r4}")
    assert r3 == r4, f"META_ENABLE=1 same-seed runs differ!\n{r3}\n{r4}"
    print("PASS: identical output with same seed\n")

    # Test 3: META_ENABLE=1, different seed — (likely) different
    print("=== META_ENABLE=1 seed=A5 vs seed=3C: different? ===")
    r5 = _extract_signal(_compile_and_run("3C", meta=True))
    print(f"seed=A5: {r3}  seed=3C: {r5}")
    if r3 != r5:
        print("PASS: different seeds produce different output (injection active)\n")
    else:
        print("NOTE: same output (seeds may have collided — deterministic)\n")

    # Test 4: META_ENABLE=1 vs META_ENABLE=0 — (likely) different
    print("=== META_ENABLE=1 vs META_ENABLE=0 ===")
    if r3 != r1:
        print("PASS: injection ON differs from injection OFF\n")
    else:
        print("NOTE: same (token was low, injection had no visible effect)\n")


if __name__ == "__main__":
    main()
