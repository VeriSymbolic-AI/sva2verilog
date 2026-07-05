"""Probe: compile always[1:3] a, emit RTL, and trace the oracle (v1.4 A3)."""

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
    tmp = Path("/tmp/_sa_probe.sv")
    tmp.write_text(sv, encoding="utf-8")
    ast = invoke_slang(tmp, "slang")
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    return compose(node, clock, label, text)


def main() -> None:
    checker = build("always [1:3] a")
    mods = emit_all(checker)
    top = checker.module_name
    print("=== TOP:", top, "===")
    print(mods[top])
    # All-hold stimulus: a high at every in-window offset 1..3. Expect pass@t4.
    stim = [
        {"start": True, "a": True},    # t0 offset0 (out of window for lo=1)
        {"start": False, "a": True},   # t1 offset1
        {"start": False, "a": True},   # t2 offset2
        {"start": False, "a": True},   # t3 offset3 (deadline)
        {"start": False, "a": False},  # t4 -> pass expected here
        {"start": False, "a": False},
    ]
    out = simulate_checker_hierarchy(checker, stim)
    print("\n=== ORACLE trace (start@0, a holds 1..3) -> expect pass@t4 ===")
    for t, o in enumerate(out):
        print(f"t{t}: pass={int(o['pass'])} fail={int(o['fail'])} active={int(o['active'])}")
    # Violation stimulus: a low at offset 2. Expect fail@ t0+2+1 = t3.
    stim2 = [
        {"start": True, "a": True},
        {"start": False, "a": True},
        {"start": False, "a": False},  # offset2 violation
        {"start": False, "a": True},
        {"start": False, "a": True},
        {"start": False, "a": False},
    ]
    out2 = simulate_checker_hierarchy(checker, stim2)
    print("\n=== ORACLE trace (start@0, a false@offset2) -> expect fail@t3 ===")
    for t, o in enumerate(out2):
        print(f"t{t}: pass={int(o['pass'])} fail={int(o['fail'])} active={int(o['active'])}")


if __name__ == "__main__":
    main()
