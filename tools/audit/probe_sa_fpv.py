"""Probe: non-circular FPV miter for always[lo:hi] (v1.4 A3).

Builds the generated monitor and an INDEPENDENT reference monitor (offset-counter,
derived from IEEE forall-k-in-[lo,hi]:a(t0+k)), then runs sby BMC comparing pass
and fail. The reference is the UNIVERSAL dual of the s_eventually reference.
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
    PropBoundedAlways,
    SourceLoc,
)
from sva2rtl.optimizer import optimize  # noqa: E402


def build_checker(lo: int, hi: int) -> CheckerNode:
    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropBoundedAlways(
        body=BoolExpr(text="a", source_loc=loc), lo=lo, hi=hi, strong=False, source_loc=loc
    )
    return optimize(compose(node, clock, "sa", f"always [{lo}:{hi}] a"))


def ref_module(name: str, lo: int, hi: int) -> str:
    return f"""
module {name} (
    input  logic clk, rst_n, start, a,
    output logic pass, fail
);
    // Independent reference for always [{lo}:{hi}] a (single attempt).
    // o counts cycles since start (o==0 at the start cycle). The operand must
    // hold at EVERY offset in [{lo},{hi}]. Authored from IEEE-1800 semantics —
    // the universal dual of the s_eventually reference.
    logic [7:0] o;
    logic       armed, viol, pass_q, fail_q;
    wire in_win   = armed && (o >= 8'd{lo}) && (o <= 8'd{hi});
    wire miss     = in_win && !a && !viol;
    wire deadline = armed && (o == 8'd{hi});
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            o <= 8'd0; armed <= 1'b0; viol <= 1'b0; pass_q <= 1'b0; fail_q <= 1'b0;
        end else begin
            pass_q <= 1'b0;
            fail_q <= 1'b0;
            if (start) begin
                o <= 8'd1; armed <= 1'b1; viol <= 1'b0;
                if (({lo} == 0) && !a) begin fail_q <= 1'b1; viol <= 1'b1; end
                if ({hi} == 0) begin
                    if (!(({lo} == 0) && !a)) pass_q <= 1'b1;
                    armed <= 1'b0;
                end
            end else if (armed) begin
                if (miss)                   fail_q <= 1'b1;
                else if (deadline && !viol) pass_q <= 1'b1;
                if (miss) viol <= 1'b1;
                if (o == 8'd{hi}) armed <= 1'b0;
                o <= o + 8'd1;
            end
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
    for lo, hi in [(1, 1), (1, 3), (2, 2), (2, 5), (0, 2)]:
        checker = build_checker(lo, hi)
        name = f"ref_sa_{lo}_{hi}"
        ref = ref_module(name, lo, hi)
        for cmp in ("pass", "fail"):
            ok, out = run_sva_miter_check(checker, ref, name, compare=cmp, depth=20)
            tail = "" if ok else "\n" + out[-1500:]
            print(f"[{ 'PASS' if ok else 'FAIL' }] always[{lo}:{hi}] cmp={cmp}{tail}")


if __name__ == "__main__":
    main()
