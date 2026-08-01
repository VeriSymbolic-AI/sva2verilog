"""v1.5.1 P2 slice 2 — sby BMC miters for NFA-based implication.

6 miters: 3 shapes × (|-> + |=>). Each miter compares the generated
implication_nfa monitor against an INDEPENDENT reference monitor
written as a shift-register pipeline.

NFA pipeline latency for `b ##2 c` (4 states, 3 transitions):
  state_d combi fire → 3 cycles → pass_q register → 4-cycle total
  from start seed to pass output.

NFA pipeline latency for `b[*3]` (4 states, 3 transitions): same 4-cycle.

When sby is not on PATH, all tests are skipped.
"""

from __future__ import annotations

import pytest

from sva2rtl.composer import compose
from sva2rtl.formal_equiv import run_sva_miter_check, sby_is_available
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SourceLoc,
)

pytestmark = [
    pytest.mark.formal,
    pytest.mark.skipif(
        not sby_is_available(),
        reason="sby not found — NFA impl formal miters disabled",
    ),
]

_LOC = SourceLoc("p2_bmc.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


# ─────────────────────────────────────────────────────────────────────────
# Reference monitors — shift-register pipelines (structurally distinct
# from one-hot NFA product + multi-thread allocator).
#
# NFA for b ##2 c:  0→1 on b, 1→2 on true, 2→3 on c (3 transitions).
# With start seed + registered pass_q → 4-cycle total latency.
#
# NFA for b[*3]:  0→1 on b, 1→2 on b, 2→3 on b (3 transitions).
# Same 4-cycle latency.
#
# Convention: pass = pass_q, registered by 1 extra cycle for alignment.
# ─────────────────────────────────────────────────────────────────────────


def _ref_overlap_b2c(name: str) -> str:
    """a |-> b ##2 c — pass iff start(1) & a(1) & b(1) & c(3)."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c,
    output logic pass
);
    logic s_ab_q, carry_q, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            s_ab_q <= 1'b0; carry_q <= 1'b0; pass_q <= 1'b0;
        end else begin
            s_ab_q  <= start & a & b;   // t=1→2
            carry_q <= s_ab_q;           // t=2→3
            pass_q  <= carry_q & c;      // t=3→4
        end
    end
    assign pass = pass_q;
endmodule
"""


def _ref_overlap_br3(name: str) -> str:
    """a |-> b[*3] — pass iff start(1) & a(1) & b(1) & b(2) & b(3)."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b,
    output logic pass
);
    logic s_ab_q, carry_q, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            s_ab_q <= 1'b0; carry_q <= 1'b0; pass_q <= 1'b0;
        end else begin
            s_ab_q  <= start & a & b;   // t=1→2
            carry_q <= s_ab_q & b;       // t=2→3
            pass_q  <= carry_q & b;      // t=3→4
        end
    end
    assign pass = pass_q;
endmodule
"""


def _ref_overlap_3chain(name: str) -> str:
    """a |-> b ##1 c ##2 d — 5-state NFA (0→b→1→c→2→1→3→d→4), K=5, T=4.

    delay ##1 between b and c = 0 wait cycles (adjacent check).
    delay ##2 between c and d = 1 wait cycle.
    Reference: 5-cycle latency pipeline.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c, d,
    output logic pass
);
    logic s_ab_q, carry1_q, carry2_q, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            s_ab_q <= 1'b0; carry1_q <= 1'b0;
            carry2_q <= 1'b0; pass_q <= 1'b0;
        end else begin
            s_ab_q   <= start & a & b;   // t=1→2   b checked at t=1
            carry1_q <= s_ab_q & c;       // t=2→3   c checked at t=2
            carry2_q <= carry1_q;         // t=3→4   wait 1 cycle
            pass_q   <= carry2_q & d;     // t=4→5   d checked at t=4
        end
    end
    assign pass = pass_q;
endmodule
"""


# |=> references: ant_match delayed by 1 cycle before NFA start.
# NFA starts at t=2 (one cycle later than |->). Extra latency = +1.


def _ref_nonoverlap_b2c(name: str) -> str:
    """a |=> b ##2 c — pass iff start(1) & a(1) & b(2) & c(4)."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c,
    output logic pass
);
    logic sa_q, sb_q, carry_q, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sa_q <= 1'b0; sb_q <= 1'b0;
            carry_q <= 1'b0; pass_q <= 1'b0;
        end else begin
            sa_q    <= start & a;       // t=1→2  ant at t=1
            sb_q    <= sa_q & b;        // t=2→3  b at t=2 (consequent starts)
            carry_q <= sb_q;            // t=3→4  wait 1 cycle (##2 → 0-fill)
            pass_q  <= carry_q & c;     // t=4→5  c at t=4
        end
    end
    assign pass = pass_q;
endmodule
"""


def _ref_nonoverlap_br3(name: str) -> str:
    """a |=> b[*3] — pass iff start(1) & a(1) & b(2) & b(3) & b(4)."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b,
    output logic pass
);
    logic sa_q, sb_q, carry_q, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sa_q <= 1'b0; sb_q <= 1'b0;
            carry_q <= 1'b0; pass_q <= 1'b0;
        end else begin
            sa_q    <= start & a;       // t=1→2  ant at t=1
            sb_q    <= sa_q & b;        // t=2→3  b at t=2
            carry_q <= sb_q & b;        // t=3→4  b at t=3
            pass_q  <= carry_q & b;     // t=4→5  b at t=4
        end
    end
    assign pass = pass_q;
endmodule
"""


def _ref_nonoverlap_3chain(name: str) -> str:
    """a |=> b ##1 c ##2 d — ant t=1, NFA starts t=2, d at t=5."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c, d,
    output logic pass
);
    logic sa_q, sb_q, carry1_q, carry2_q, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            sa_q <= 1'b0; sb_q <= 1'b0;
            carry1_q <= 1'b0; carry2_q <= 1'b0;
            pass_q <= 1'b0;
        end else begin
            sa_q     <= start & a;       // t=1→2
            sb_q     <= sa_q & b;        // t=2→3  b at t=2
            carry1_q <= sb_q & c;        // t=3→4  c at t=3
            carry2_q <= carry1_q;        // t=4→5  wait 1 cycle
            pass_q   <= carry2_q & d;    // t=5→6  d at t=5
        end
    end
    assign pass = pass_q;
endmodule
"""


# ═════════════════════════════════════════════════════════════════════════
# |-> miters — 3 shapes
# ═════════════════════════════════════════════════════════════════════════


class TestOverlapImplNfaMiter:
    def test_b2c_miter(self) -> None:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),), source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |-> b ##2 c")
        ref_name = "ref_ov_b2c"
        passed, output = run_sva_miter_check(
            checker, _ref_overlap_b2c(ref_name), ref_name,
            compare="pass", depth=25,
        )
        assert passed, f"a |-> b ##2 c miter FAILED:\n{output[-2500:]}"

    def test_br3_miter(self) -> None:
        rep3 = SeqRepetition(
            expr=_b("b"), rep_min=3, rep_max=3, source_loc=_LOC,
        )
        node = PropImplication(
            antecedent=_b("a"), consequent=rep3,
            overlapping=True, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |-> b[*3]")
        ref_name = "ref_ov_br3"
        passed, output = run_sva_miter_check(
            checker, _ref_overlap_br3(ref_name), ref_name,
            compare="pass", depth=25,
        )
        assert passed, f"a |-> b[*3] miter FAILED:\n{output[-2500:]}"

    def test_3chain_miter(self) -> None:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c"), _b("d")),
                delays=((1, 1), (2, 2)), source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |-> b ##1 c ##2 d")
        ref_name = "ref_ov_3c"
        passed, output = run_sva_miter_check(
            checker, _ref_overlap_3chain(ref_name), ref_name,
            compare="pass", depth=30,
        )
        assert passed, f"a |-> b ##1 c ##2 d miter FAILED:\n{output[-2500:]}"


# ═════════════════════════════════════════════════════════════════════════
# |=> miters — 3 shapes
# ═════════════════════════════════════════════════════════════════════════


class TestNonoverlapImplNfaMiter:
    def test_b2c_miter(self) -> None:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),), source_loc=_LOC,
            ),
            overlapping=False, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |=> b ##2 c")
        ref_name = "ref_no_b2c"
        passed, output = run_sva_miter_check(
            checker, _ref_nonoverlap_b2c(ref_name), ref_name,
            compare="pass", depth=30,
        )
        assert passed, f"a |=> b ##2 c miter FAILED:\n{output[-2500:]}"

    def test_br3_miter(self) -> None:
        rep3 = SeqRepetition(
            expr=_b("b"), rep_min=3, rep_max=3, source_loc=_LOC,
        )
        node = PropImplication(
            antecedent=_b("a"), consequent=rep3,
            overlapping=False, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |=> b[*3]")
        ref_name = "ref_no_br3"
        passed, output = run_sva_miter_check(
            checker, _ref_nonoverlap_br3(ref_name), ref_name,
            compare="pass", depth=30,
        )
        assert passed, f"a |=> b[*3] miter FAILED:\n{output[-2500:]}"

    def test_3chain_miter(self) -> None:
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c"), _b("d")),
                delays=((1, 1), (2, 2)), source_loc=_LOC,
            ),
            overlapping=False, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |=> b ##1 c ##2 d")
        ref_name = "ref_no_3c"
        passed, output = run_sva_miter_check(
            checker, _ref_nonoverlap_3chain(ref_name), ref_name,
            compare="pass", depth=35,
        )
        assert passed, f"a |=> b ##1 c ##2 d miter FAILED:\n{output[-2500:]}"
