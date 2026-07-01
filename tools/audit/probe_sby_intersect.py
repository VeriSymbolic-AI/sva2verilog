"""v1.5.1 preflight — sby AppNote-109 convergence spike for intersect/within.

YosysHQ AppNote-109 flags ``intersect`` / ``within`` / ``throughout`` as
"not FPV-friendly" and warns that formal engines may fail to converge on
them. Before v1.5.1 commits to 12 sby BMC miters as its release gate we
must know empirically whether sby can prove even the SIMPLEST intersect
monitor against a hand-authored IEEE-1800 reference.

Strategy — use the pre-v1.5.1 `prop_intersect` template (which is
structurally identical in complexity to what nfa_generic will be for a
2-state one-hot NFA — a small registered FSM with pass/fail outputs).
If sby converges here, it will converge on nfa_generic. If not, v1.5.1
must adopt an iverilog-only + documented-xfail policy.

The reference for ``a intersect b`` with boolean atoms is derived
independently from IEEE 1800 §16.9.7: both sub-sequences complete on
their start cycle iff ``a && b``. Because the monitor registers its
outputs (`pass_q <= _body_pass`), the reference violation indicator on
cycle t is:

    ref_violation(t) = m_fail(t) != (registered ~(a & b))

For `pass` equivalence (the more informative direction), we compare
against `~(a & b)_prev` — the registered form of "operands did NOT both
hold last cycle". This mirrors the monitor's 1-cycle output latency.

Exit codes:
    0 = sby PASS (convergence confirmed; v1.5.1 can commit to BMC gate)
    1 = sby FAIL/TIMEOUT (convergence risk; v1.5.1 must plan iverilog
        fallback + xfail for formal miters)
    2 = infrastructure error (sby missing, harness build fail, etc.)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from sva2rtl.composer import compose  # noqa: E402
from sva2rtl.formal_equiv import (  # noqa: E402
    run_sva_equiv_check,
    sby_is_available,
)
from sva2rtl.ir import (  # noqa: E402
    BoolExpr,
    ClockSpec,
    SeqIntersect,
    SourceLoc,
)


def main() -> int:
    print("=" * 72)
    print("v1.5.1 preflight — sby AppNote-109 convergence spike (intersect)")
    print("=" * 72)

    if not sby_is_available():
        print("[FAIL] sby not on PATH — cannot run spike.")
        return 2

    loc = SourceLoc("spike.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqIntersect(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, "spike_intersect", "a intersect b")
    print(f"monitor top: {checker.module_name}")
    print(f"observed_signals: {checker.observed_signals}")

    # ── Reference: fail equivalence ──────────────────────────────────
    # Two-cycle registered output pipeline of prop_intersect:
    #   bool_expr leaves register once:  left_pass(t) = start(t-1) & a(t-1)
    #                                    right_pass(t) = start(t-1) & b(t-1)
    #   prop_intersect registers again:  m_pass(t) = _body_pass(t-1)
    #                                             = start(t-2) & a(t-2) & b(t-2)
    #   Symmetrically for fail:          m_fail(t) = start(t-2) & ~(a(t-2) & b(t-2))
    #
    # With start held at 1'b1 in the equiv harness, the "start(t-2)" factor
    # is always 1 once the pipeline has filled (t >= 2 cycles after reset).
    # Reference: two-cycle delayed ~(a & b), gated by pipeline-settled flag.
    helper = """
    logic ab_q1, ab_q2;
    always @(posedge clk) begin
        if (!rst_n) begin
            ab_q1 <= 1'b0;
            ab_q2 <= 1'b0;
        end else begin
            ab_q1 <= (a & b);
            ab_q2 <= ab_q1;
        end
    end
    // Pipeline-settled flag: after reset, need >=2 cycles for both stages
    // to fill before m_fail semantics is meaningful.
    integer _spike_t = 0;
    always @(posedge clk) begin
        if (!rst_n) _spike_t <= 0;
        else        _spike_t <= _spike_t + 1;
    end
    wire _spike_settled = (_spike_t >= 2);
"""
    ref_expr = "(_spike_settled ? ~ab_q2 : 1'b0)"

    print(f"\nreference violation expr: {ref_expr}")
    print("Running sby BMC depth=20, timeout=120s ...")
    t0 = time.time()
    passed, output = run_sva_equiv_check(
        checker,
        ref_expr,
        helper_regs=helper,
        clock="clk",
        depth=20,
        timeout=120,
    )
    elapsed = time.time() - t0

    print(f"\nElapsed: {elapsed:.1f}s")
    print(f"Result:  {'PASS' if passed else 'FAIL / non-convergent'}")

    # Print last 30 lines of sby output for diagnostic
    tail = "\n".join(output.strip().splitlines()[-30:])
    print("\n--- sby tail ---")
    print(tail)
    print("--- end ---")

    if passed:
        print("\n[CONCLUSION] sby CONVERGES on prop_intersect equivalence.")
        print("  → v1.5.1 can commit to 12-BMC gate for nfa_generic.")
        return 0
    else:
        print("\n[CONCLUSION] sby DID NOT converge / passed at 20 cycles.")
        print("  → v1.5.1 must plan iverilog-only fallback + xfail on the")
        print("    formal miters. Consider deeper BMC with induction, or a")
        print("    smaller/simpler reference. Log full output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
