"""Probe: non-circular FPV miter for weak until / until_with (v1.4 A4).

Builds the generated monitor and an INDEPENDENT reference monitor (a two-register
started/decided formulation, distinct from the monitor's single running_q FSM),
then runs sby BMC comparing pass and fail. The reference is authored directly from
IEEE-1800 weak-until safety semantics.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.composer import compose  # noqa: E402
from sva2rtl.formal_equiv import run_sva_miter_check, sby_is_available  # noqa: E402
from sva2rtl.ir import (  # noqa: E402
    BoolExpr,
    CheckerNode,
    ClockSpec,
    PropUntil,
    SourceLoc,
)
from sva2rtl.optimizer import optimize  # noqa: E402


def build_checker(with_: bool) -> CheckerNode:
    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    kw = "until_with" if with_ else "until"
    node = PropUntil(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        with_=with_,
        source_loc=loc,
    )
    return optimize(compose(node, clock, "u", f"a {kw} b"))


def ref_module(name: str, with_: bool) -> str:
    if with_:
        sat = "live &  a &  b"
        vio = "live & ~a"
    else:
        sat = "live &  b"
        vio = "live & ~b & ~a"
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b,
    output logic pass, fail
);
    // Independent reference for weak {"until_with" if with_ else "until"} (single
    // attempt). Two sticky registers (started/decided) gate a live window — a
    // distinct structure from the monitor's single running_q FSM. Authored from
    // IEEE-1800 weak-until safety semantics.
    logic started, decided, pass_q, fail_q;
    wire live = (start | started) & ~decided;
    wire sat  = {sat};
    wire vio  = {vio};
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            started <= 1'b0; decided <= 1'b0; pass_q <= 1'b0; fail_q <= 1'b0;
        end else begin
            if (start) started <= 1'b1;
            pass_q <= sat;
            fail_q <= vio;
            if (sat | vio) decided <= 1'b1;
        end
    end
    assign pass = pass_q;
    assign fail = fail_q;
endmodule
"""


def main() -> None:
    if not sby_is_available():
        print("sby not available")
        return
    for with_ in (False, True):
        checker = build_checker(with_)
        name = f"ref_u_{'w' if with_ else 'u'}"
        ref = ref_module(name, with_)
        kw = "until_with" if with_ else "until"
        for cmp in ("pass", "fail"):
            ok, out = run_sva_miter_check(checker, ref, name, compare=cmp, depth=20)
            tail = "" if ok else "\n" + out[-1500:]
            print(f"[{ 'PASS' if ok else 'FAIL' }] {kw} cmp={cmp}{tail}")


if __name__ == "__main__":
    main()
