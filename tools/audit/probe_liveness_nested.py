"""Probe: behavior of liveness operators nested under implication (v1.4 A5.1)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.ast_importer import import_assertion  # noqa: E402
from sva2rtl.composer import compose  # noqa: E402
from sva2rtl.emitter import emit_all  # noqa: E402
from sva2rtl.frontend import invoke_slang  # noqa: E402
from sva2rtl.normalizer import normalize  # noqa: E402

_PROPS = [
    "a |-> s_eventually [1:3] b",
    "a |-> always [1:2] b",
    "a |-> (b until c)",
]


def main() -> None:
    for prop in _PROPS:
        src = Path("/tmp/_nest_probe.sv")
        src.write_text(
            "module m(input logic clk, a, b, c);\n"
            f"  ap: assert property (@(posedge clk) {prop});\n"
            "endmodule\n",
            encoding="utf-8",
        )
        try:
            ast = invoke_slang(src, "slang")
            node, clock, text, label = import_assertion(ast)
            node = normalize(node)
            ck = compose(node, clock, label, text)
            mods = emit_all(ck)
            print(f"{prop!r}: COMPILED top={ck.module_name} mods={list(mods)}")
        except Exception as exc:  # noqa: BLE001
            print(f"{prop!r}: {type(exc).__name__}: {str(exc)[:140]}")


if __name__ == "__main__":
    main()
