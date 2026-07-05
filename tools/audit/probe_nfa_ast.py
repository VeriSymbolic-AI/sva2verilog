"""Spike G0.1: dump slang AST shape for NFA-composition targets (v1.5).

Targets: (1) multi-cycle implication consequent (blocked by composer.py:969),
(2) intersect/within composed with sequences (RISK-02 boundary),
(3) nested intersect/within/throughout patterns (NFA-07).

The goal is to confirm the AST shapes match what nfa_lower will need to
recognise (kind names, child positions, delay wrappers) before writing IR
builders.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.frontend import invoke_slang  # noqa: E402

_SNIPPETS: dict[str, str] = {
    # ── multi-cycle implication consequent (G3 targets) ───────────────────
    "impl_seq_delay":       "@(posedge clk) a |-> b ##2 c",
    "impl_seq_repeat":      "@(posedge clk) a |-> b[*3]",
    "impl_seq_range":       "@(posedge clk) a |-> (b ##[2:5] c)",
    # ── RISK-02 boundary (single-cycle intersect / within) ────────────────
    "intersect_bool":       "@(posedge clk) a intersect b",
    "within_bool":          "@(posedge clk) a within b",
    "throughout_bool":      "@(posedge clk) c throughout b",
    # ── NFA-07 nested composition targets ─────────────────────────────────
    "nested_intersect_within":  "@(posedge clk) (a intersect b) within c",
    "nested_delay_intersect":   "@(posedge clk) (a ##2 b) intersect (c[*3])",
    "nested_intersect_chain":   "@(posedge clk) (a intersect b) intersect c",
    "nested_impl_intersect":    "@(posedge clk) a |-> (b intersect c)",
    "nested_throughout_within": "@(posedge clk) (c throughout b) within d",
}


def _kinds(node: object, out: list[str], depth: int = 0) -> None:
    """Compact recursive dump of dict-kind trees (skip token-level noise)."""
    if isinstance(node, dict):
        k = node.get("kind")
        if isinstance(k, str):
            extra = ""
            for key in ("op", "signal", "symbol", "edge", "min", "max"):
                if key in node:
                    v = node[key]
                    if isinstance(v, (str, int)):
                        extra += f" {key}={v!r}"
            out.append("  " * depth + f"{k}{extra}")
        for key, v in node.items():
            if key in ("kind", "op", "signal", "symbol", "edge", "min", "max"):
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
    max_lines = 50
    for name, prop in _SNIPPETS.items():
        sv = (
            "module m(input logic clk, a, b, c, d);\n"
            f"  ap: assert property ({prop});\n"
            "endmodule\n"
        )
        tmp = Path(f"/tmp/_nfa_ast_{name}.sv")
        tmp.write_text(sv, encoding="utf-8")
        print(f"\n===== {name}:  {prop}")
        try:
            ast = invoke_slang(tmp, "slang")
        except Exception as exc:  # noqa: BLE001
            print(f"  slang error: {str(exc)[:200]}")
            continue
        out: list[str] = []
        _kinds(_find_prop(ast), out)
        for line in out[:max_lines]:
            print(line)
        if len(out) > max_lines:
            print(f"  ... ({len(out) - max_lines} more lines)")


if __name__ == "__main__":
    main()
