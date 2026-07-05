"""Debug: iverilog compile test for sync_2dff with META_ENABLE=1."""

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

sv = Path("/tmp/_mc_e.sv")
sv.write_text(
    "module m(input logic clk1, clk2, a, b);\n"
    "  ap: assert property (@(posedge clk1) a ##1 @(posedge clk2) b);\n"
    "endmodule\n",
    encoding="utf-8",
)
ast = invoke_slang(sv, "slang")
node, clock, text, label = import_assertion(ast)
ck = compose(normalize(node), clock, label, text)
mods = emit_all(ck)

with tempfile.TemporaryDirectory() as d:
    dp = Path(d)
    for name, src in mods.items():
        (dp / f"{name}.sv").write_text(src)
    for fp in sorted(dp.glob("*sync*")):
        if "sync" in fp.name and "top" not in fp.name:
            t = fp.read_text()
            t = t.replace("parameter META_ENABLE = 0,", "parameter META_ENABLE = 1,")
            fp.write_text(t)
    files = [str(dp / f) for f in sorted(dp.glob("*.sv"))]
    r = subprocess.run(
        ["iverilog", "-g2012", "-o", str(dp / "tb.out")] + files,
        capture_output=True, text=True, cwd=str(d),
    )
    if r.returncode != 0:
        print("FAIL:", r.stderr[-400:])
    else:
        print("OK — META_ENABLE=1 compiles")
