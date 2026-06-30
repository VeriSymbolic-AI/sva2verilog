"""Probe: compile a until b / a until_with b, emit RTL, trace the oracle (v1.4 A4)."""

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
    tmp = Path("/tmp/_until_probe.sv")
    tmp.write_text(sv, encoding="utf-8")
    ast = invoke_slang(tmp, "slang")
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    return compose(node, clock, label, text)


def _trace(title: str, checker: CheckerNode, stim: list[dict]) -> None:
    out = simulate_checker_hierarchy(checker, stim)
    print(f"\n=== {title} ===")
    for t, o in enumerate(out):
        print(f"t{t}: pass={int(o['pass'])} fail={int(o['fail'])} active={int(o['active'])}")


def main() -> None:
    checker = build("a until b")
    mods = emit_all(checker)
    print("=== TOP:", checker.module_name, "===")
    print(mods[checker.module_name])
    # a holds, b at t2 -> pass at t3.
    _trace("a until b: a holds, b@t2 -> pass@t3", checker, [
        {"start": True, "a": True, "b": False},
        {"start": False, "a": True, "b": False},
        {"start": False, "a": True, "b": True},
        {"start": False, "a": False, "b": False},
        {"start": False, "a": False, "b": False},
    ])
    # a drops at t1 before b -> fail at t2.
    _trace("a until b: a drops@t1 -> fail@t2", checker, [
        {"start": True, "a": True, "b": False},
        {"start": False, "a": False, "b": False},
        {"start": False, "a": True, "b": True},
        {"start": False, "a": False, "b": False},
    ])
    cw = build("a until_with b")
    # until_with: ~a at b-cycle -> fail.
    _trace("a until_with b: b@t2 but ~a@t2 -> fail@t3", cw, [
        {"start": True, "a": True, "b": False},
        {"start": False, "a": True, "b": False},
        {"start": False, "a": False, "b": True},
        {"start": False, "a": False, "b": False},
    ])


if __name__ == "__main__":
    main()
