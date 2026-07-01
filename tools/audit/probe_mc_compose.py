"""Probe: multi-clock compose tree structure (v1.4.1 B2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.ast_importer import import_assertion  # noqa: E402
from sva2rtl.composer import compose  # noqa: E402
from sva2rtl.emitter import emit_all  # noqa: E402
from sva2rtl.frontend import invoke_slang  # noqa: E402
from sva2rtl.ir import CheckerNode  # noqa: E402
from sva2rtl.normalizer import normalize  # noqa: E402


def build(prop: str) -> CheckerNode:
    sv = (
        "module m(input logic clk1, clk2, clk3, a, b, c);\n"
        f"  ap: assert property ({prop});\n"
        "endmodule\n"
    )
    tmp = Path("/tmp/_mc_b2.sv")
    tmp.write_text(sv, encoding="utf-8")
    ast = invoke_slang(tmp, "slang")
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    return compose(node, clock, label, text)


def dump_tree(ck: CheckerNode, indent: int = 0) -> None:
    prefix = "  " * indent
    obs = ",".join(p for p, _ in ck.observed_signals)
    print(
        f"{prefix}{ck.module_name}: {ck.template_name}"
        f"  params={sorted(ck.params.keys())}  obs=[{obs}]"
    )
    for child in ck.children:
        dump_tree(child, indent + 1)


def main() -> None:
    for prop in [
        "@(posedge clk1) a ##1 @(posedge clk2) b",  # mode 1
        "@(posedge clk1) a ##1 @(posedge clk2) b ##1 @(posedge clk1) c",  # 3 elem, 2 switches
    ]:
        print(f"\n=== {prop}")
        ck = build(prop)
        dump_tree(ck)
        try:
            mods = emit_all(ck)
            print(f"  EMITTED: {list(mods.keys())}")
        except Exception as e:
            print(f"  EMIT ERROR: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
