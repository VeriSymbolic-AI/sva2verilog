"""Spike: dump slang AST shape for bounded-liveness SVA forms (v1.4 Part A, A0).

Runs slang --ast-json on each liveness property and prints the property-expression
subtree (kind/op + min/max/left/right), so we can mirror the shape in
ast_importer.py. Read-only probe; writes only to /tmp.

Findings (slang 11.0.0):
- s_eventually/eventually/always/s_always [m:n] p -> kind="Unary",
  op in {SEventually,Eventually,Always,SAlways}, with "min"/"max"; operand under
  expr={kind:"Simple", expr:<bool>}.
- Unbounded forms: same op, NO "min"/"max" -> reject (bounded vs unbounded =
  presence of min/max).
- a until/s_until/until_with b -> kind="Binary", op in {Until,SUntil,UntilWith},
  with left/right.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.frontend import invoke_slang  # noqa: E402

_SNIPPETS: dict[str, str] = {
    "s_eventually_bounded": "s_eventually [1:3] a",
    "eventually_bounded": "eventually [1:3] a",
    "always_bounded": "always [1:3] a",
    "s_always_bounded": "s_always [1:3] a",
    "until_weak": "a until b",
    "s_until_strong": "a s_until b",
    "until_with": "a until_with b",
    "s_eventually_unbounded": "s_eventually a",
    "always_unbounded": "always a",
}


def _find_prop_expr(node: object) -> object:
    """Return the propertySpec.expr subtree (the actual property expression)."""
    found: list[object] = []

    def walk(n: object) -> None:
        if isinstance(n, dict):
            if n.get("kind") == "Clocking" and "expr" in n:
                found.append(n["expr"])
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return found[0] if found else None


def main() -> None:
    for name, prop in _SNIPPETS.items():
        sv = (
            "module m(input logic clk, a, b);\n"
            f"  ap: assert property (@(posedge clk) {prop});\n"
            "endmodule\n"
        )
        tmp = Path(f"/tmp/_liveness_{name}.sv")
        tmp.write_text(sv, encoding="utf-8")
        print(f"\n===== {name}:  {prop}  =====")
        try:
            ast = invoke_slang(tmp, "slang")
        except Exception as exc:  # noqa: BLE001
            print(f"  slang error: {exc}")
            continue
        print(json.dumps(_find_prop_expr(ast), indent=2)[:1400])


if __name__ == "__main__":
    main()
