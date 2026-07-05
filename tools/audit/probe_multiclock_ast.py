"""Spike: dump slang AST shape for multi-clock SVA forms (v1.4.1 Part B)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.frontend import invoke_slang  # noqa: E402

_SNIPPETS: dict[str, str] = {
    "seq_two_clock": "@(posedge clk1) a ##1 @(posedge clk2) b",
    "impl_two_clock": "@(posedge clk1) a |=> @(posedge clk2) b",
    "seq_three_clock": "@(posedge clk1) a ##1 @(posedge clk2) b ##1 @(posedge clk3) c",
    "bad_delay2_cross": "@(posedge clk1) a ##2 @(posedge clk2) b",
}


def _kinds(node: object, out: list[str], depth: int = 0) -> None:
    if isinstance(node, dict):
        k = node.get("kind")
        if isinstance(k, str):
            extra = ""
            for key in ("op", "signal", "symbol", "edge"):
                if key in node:
                    extra += f" {key}={node[key]!r}"
            out.append("  " * depth + f"{k}{extra}")
        for key, v in node.items():
            if key in ("kind", "op", "signal", "symbol", "edge"):
                continue
            _kinds(v, out, depth + 1)
    elif isinstance(node, list):
        for v in node:
            _kinds(v, out, depth)


def _find_prop(node: object) -> object:
    found: list[object] = []

    def walk(n: object) -> None:
        if isinstance(n, dict):
            if n.get("kind") in ("AssertionExpr", "Concurrent") and "propertySpec" in n:
                found.append(n.get("propertySpec"))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return found[0] if found else node


def main() -> None:
    for name, prop in _SNIPPETS.items():
        sv = (
            "module m(input logic clk1, clk2, clk3, a, b, c);\n"
            f"  ap: assert property ({prop});\n"
            "endmodule\n"
        )
        tmp = Path(f"/tmp/_mc_{name}.sv")
        tmp.write_text(sv, encoding="utf-8")
        print(f"\n===== {name}:  {prop}")
        try:
            ast = invoke_slang(tmp, "slang")
        except Exception as exc:  # noqa: BLE001
            print(f"  slang error: {str(exc)[:200]}")
            continue
        out: list[str] = []
        _kinds(_find_prop(ast), out)
        print("\n".join(out[:40]))


if __name__ == "__main__":
    main()
