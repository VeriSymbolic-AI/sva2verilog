"""Probe: compile s_eventually[1:3] a, emit RTL, and trace the oracle (v1.4 A2)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.ast_importer import import_assertion  # noqa: E402
from sva2rtl.behavioral_oracle import simulate_checker_hierarchy  # noqa: E402
from sva2rtl.composer import compose  # noqa: E402
from sva2rtl.emitter import emit_all  # noqa: E402
from sva2rtl.frontend import invoke_slang  # noqa: E402
from sva2rtl.ir import CheckerNode  # noqa: E402
from sva2rtl.normalizer import normalize  # noqa: E402


def build(prop: str) -> CheckerNode:
    sv = (
        "module m(input logic clk, a, b);\n"
        f"  ap: assert property (@(posedge clk) {prop});\n"
        "endmodule\n"
    )
    tmp = Path("/tmp/_se_probe.sv")
    tmp.write_text(sv, encoding="utf-8")
    ast = invoke_slang(tmp, "slang")
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    return compose(node, clock, label, text)


def main() -> None:
    checker = build("s_eventually [1:3] a")
    mods = emit_all(checker)
    top = checker.module_name
    print("=== TOP:", top, "===")
    print(mods[top])
    # Directed stimulus: start@0; a high at offset 2 (cycle 2). Expect pass@3.
    stim = [
        {"start": True, "a": False},   # t0 offset0
        {"start": False, "a": False},  # t1 offset1
        {"start": False, "a": True},   # t2 offset2  -> hit
        {"start": False, "a": False},  # t3 -> pass expected here
        {"start": False, "a": False},
        {"start": False, "a": False},
    ]
    out = simulate_checker_hierarchy(checker, stim)
    print("\n=== ORACLE trace (start@0, a@offset2) ===")
    for t, o in enumerate(out):
        print(f"t{t}: pass={int(o['pass'])} fail={int(o['fail'])} active={int(o['active'])}")
    # No-hit stimulus: a always low. Expect fail@ t0+hi+1 = t4.
    stim2 = [{"start": t == 0, "a": False} for t in range(6)]
    out2 = simulate_checker_hierarchy(checker, stim2)
    print("\n=== ORACLE trace (start@0, a never) -> expect fail@t4 ===")
    for t, o in enumerate(out2):
        print(f"t{t}: pass={int(o['pass'])} fail={int(o['fail'])} active={int(o['active'])}")


if __name__ == "__main__":
    main()
