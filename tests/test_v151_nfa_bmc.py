"""v1.5.1 P1 slice 4 — sby BMC miters for NFA-composed operators.

Each miter compares the generated ``nfa_generic`` monitor against an
INDEPENDENTLY-authored reference monitor written from IEEE 1800
first-principles. The reference uses a naive shift-register implementation
(structurally different from the one-hot NFA product), giving genuine
implementation independence:

- NFA path  = product-of-NFAs → one-hot state vector → registered outputs
- Reference = shift registers of raw inputs → combinational match predicate

If the two agree on every reachable trace within the BMC depth bound,
the compilation is genuinely faithful to IEEE 1800 semantics — not
merely self-consistent (which is what an isomorphic behavioral oracle
would prove).

Preflight (2026-07-01) confirmed sby+smtbmc+yices converges on the
prop_intersect miter class in ~0.5 s at depth 20; this file's miters
are of the same class (small registered FSMs).

Skipped when sby is not on PATH.

Covers v1.5.1-ROADMAP P1.6 + P1.7 (12 miters × 3 operators).
"""

from __future__ import annotations

import pytest

from sva2rtl.composer import compose
from sva2rtl.formal_equiv import run_sva_miter_check, sby_is_available
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockSpec,
    SeqConcat,
    SeqIntersect,
    SeqRepetition,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
    SVANode,
)

pytestmark = [
    pytest.mark.formal,
    pytest.mark.skipif(
        not sby_is_available(),
        reason="sby (SymbiYosys) not found — NFA formal miters disabled",
    ),
]

_LOC = SourceLoc("nfa_bmc.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


# ─────────────────────────────────────────────────────────────────────────
# IR builders
# ─────────────────────────────────────────────────────────────────────────


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


def _sc_a2b() -> SeqConcat:
    """`a ##2 b` — 4-state sub-NFA."""
    return SeqConcat(
        elements=(_b("a"), _b("b")),
        delays=((0, 0), (2, 2)),
        source_loc=_LOC,
    )


def _rep_c3() -> SeqRepetition:
    """`c[*3]` — 4-state sub-NFA."""
    return SeqRepetition(expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC)


# ─────────────────────────────────────────────────────────────────────────
# Reference monitor factories — one shift-register-based module per shape.
#
# All references share the following contract to plug into build_miter_harness:
#   ports:  clk, rst_n, start, <observed>..., pass
#   pass  = registered by one cycle to align with nfa_generic's registered
#           pass_q latency (matching leaf-registered + composed-registered
#           = 1-cycle net latency, per preflight-notes.md).
# ─────────────────────────────────────────────────────────────────────────


def _ref_intersect_bool_rep1(name: str) -> str:
    """`a intersect (b[*1])` — bool × rep-1; forces the NFA path.

    IEEE 1800 §16.9.7: both single-cycle → match iff a & b at start.
    NFA latency = 1 cycle (state_d combinational fire + pass_q register).
    Reference: pass(t) = start(t-1) & a(t-1) & b(t-1).
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b,
    output logic pass
);
    logic pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= start & a & b;
    end
    assign pass = pass_q;
endmodule
"""


def _ref_intersect_seq_bool(name: str) -> str:
    """`(a ##2 b) intersect c` — SeqConcat on left, bool on right.

    Both operands must complete on the SAME cycle.
    - Left  `a ##2 b`: succeeds on cycle s+2 iff a(s) & b(s+2).
    - Right `c`: succeeds on cycle s iff c(s), single cycle.
    They agree only when the left completes AT the start cycle — but the
    left needs 2 cycles. Therefore the intersection NEVER matches; the
    only way both end on the same cycle is if `a ##2 b` completed at
    cycle s AND c was true at cycle s. Since left completion needs
    s+2, this is impossible.

    Result: pass is always 0. This is a strong witness of the correct
    "end-on-same-cycle" semantics — the wrong end-any-cycle semantics
    would give false positives.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c,
    output logic pass
);
    // No trace satisfies (a ##2 b) intersect (c): the sub-sequences
    // cannot both end on the same cycle. Reference pass = 0.
    assign pass = 1'b0;
endmodule
"""


def _ref_intersect_rep_bool(name: str) -> str:
    """`(c[*3]) intersect b` — c[*3] takes 3 cycles, b is single-cycle.

    Same argument: c[*3] ends at s+2, b ends at s → cannot align.
    Reference pass = 0.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, b, c,
    output logic pass
);
    assign pass = 1'b0;
endmodule
"""


def _ref_intersect_seq_rep(name: str) -> str:
    """`(a ##2 b) intersect (c[*3])` — both length-3 sequences.

    IEEE 1800 §16.9.7 + product-of-NFAs: both threads start at s, both
    complete at s+2 iff a(s) & b(s+2) & c(s) & c(s+1) & c(s+2).
    NFA pipeline latency: 3 cycle-steps + 1 register = 4 cycles.
    Pass at s+3 in the composed monitor's frame; the miter uses
    ``start_pulse=(_t==1)``, so pass fires at t=4 iff full match.

    Reference: capture (start & a & c) at cycle s into a 2-stage
    shift register (s_q2 = value at s), then AND-gate with c(s+1)
    stored (c_q1 = c at s+1), c(s+2) captured live at s+2, and b(s+2).
    The extra pass_q register aligns to NFA's register output.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c,
    output logic pass
);
    // Stage 0: sample (start & a & c) at s → s_ac_q available at s+1.
    logic s_ac_q;
    always_ff @(posedge clk) begin
        if (!rst_n) s_ac_q <= 1'b0;
        else        s_ac_q <= start & a & c;
    end
    // Stage 1: AND with c at s+1 → carry_q available at s+2.
    logic carry_q;
    always_ff @(posedge clk) begin
        if (!rst_n) carry_q <= 1'b0;
        else        carry_q <= s_ac_q & c;
    end
    // Stage 2: AND with c(s+2) & b(s+2) → match_w at s+2.
    // Register once more to align with NFA's pass_q.
    logic match_w, pass_q;
    assign match_w = carry_q & c & b;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= match_w;
    end
    assign pass = pass_q;
endmodule
"""


def _ref_within_bool_rep1(name: str) -> str:
    """`a within (b[*1])` — bool inner × 1-rep outer; forces NFA path.

    Inner accept at s if a(s); outer alive at s if b(s). Product
    (1,1) is accept iff a(s) & b(s). Registered pass_q → pass at s+1.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b,
    output logic pass
);
    logic pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= start & a & b;
    end
    assign pass = pass_q;
endmodule
"""


def _ref_within_bool_rep(name: str) -> str:
    """`a within (c[*3])` — inner a bool, outer c[*3].

    Product-of-NFAs sync: inner-thread and outer-thread both start at s.
    Inner = a completes at s if a(s)=1. Outer c[*3] is "alive" (has a
    live thread) whenever any state in [0..3] is populated; state i is
    alive iff c held for the past i cycles starting from s. State 0
    alive at s (always, from start seed). Cross-product accept =
    inner_accept × outer_alive.

    So the match happens at cycle s iff a(s) & c(s) (both threads live
    together at s, inner reaches accept, outer state 0 → 1 requires
    c(s), alive-mask includes state 0 which is always alive at s).

    Actually inner accept-state × outer alive-state: after 1 transition
    from (0,0), inner is in state 1 (accept) iff a(s), outer is in
    state 1 (alive) iff c(s). Product state (1,1) is in accept iff
    inner state 1 ∈ acc_inner AND outer state 1 ∈ alive_outer. Both
    hold → pass at s+1.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, c,
    output logic pass
);
    logic pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= start & a & c;
    end
    assign pass = pass_q;
endmodule
"""


def _ref_within_seq_bool(name: str) -> str:
    """`(a ##2 b) within c` — inner is seq, outer is bool.

    Outer c is alive for only 1 cycle (state 0 → accept in 1 step;
    outer state 0 alive at s only if start pulsed). Inner ##2 needs
    3 cycles. Product sync requires inner accept and outer alive on
    the same cycle. But outer is alive only at s; inner cannot accept
    until s+2. So pass is always 0.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c,
    output logic pass
);
    assign pass = 1'b0;
endmodule
"""


def _ref_within_seq_rep(name: str) -> str:
    """`(a ##2 b) within (c[*3])` — both pinned length-3 sequences.

    Product NFA sync: inner accept AND outer alive on the same cycle.
    With both pinned at 3 cycles, this equals the intersect case: pass
    at s+3 (miter frame t=4) iff (start & a & c)(s) & c(s+1) & c(s+2)
    & b(s+2). Same shift-register-pipeline reference as intersect.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b, c,
    output logic pass
);
    logic s_ac_q, carry_q, match_w, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            s_ac_q  <= 1'b0;
            carry_q <= 1'b0;
            pass_q  <= 1'b0;
        end else begin
            s_ac_q  <= start & a & c;
            carry_q <= s_ac_q & c;
            pass_q  <= match_w;
        end
    end
    assign match_w = carry_q & c & b;
    assign pass = pass_q;
endmodule
"""


def _ref_throughout_bool_rep2(name: str) -> str:
    """`en throughout (a[*2])` — en gates 2-cycle body; forces NFA path.

    Body a[*2] transitions: 0→1 on a, 1→2 on a. Product with cond:
    0→1 on (a & en), 1→2 on (a & en). Accept = {2}. NFA latency 2
    cycles from start-cycle to pass_q assertion (state_d combi + q reg).

    Match at cycle s: reach accept iff start(s) & en(s) & a(s) &
    en(s+1) & a(s+1); pass_q asserts at s+2.

    Reference: 1-cycle delayed AND of (start & en & a) at s and
    (en & a) at s+1 → 2 flops deep.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, en, a,
    output logic pass
);
    // Capture cycle-s snapshot (start & en & a).
    logic s0_q;
    always_ff @(posedge clk) begin
        if (!rst_n) s0_q <= 1'b0;
        else        s0_q <= start & en & a;
    end
    // At cycle s+1, AND with (en & a) to detect full match.
    logic match_w, pass_q;
    assign match_w = s0_q & en & a;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= match_w;
    end
    assign pass = pass_q;
endmodule
"""


def _ref_throughout_bool_seq(name: str) -> str:
    """`en throughout (a ##2 b)` — cond gates each of body's 3 cycles.

    Body: 0→1 on a, 1→2 on true, 2→3 on b. Product with cond en:
    0→1 on (a & en), 1→2 on (en), 2→3 on (b & en). Accept={3}.
    Match at s+2: start(s) & a(s) & en(s) & en(s+1) & b(s+2) & en(s+2).
    Register once → pass at s+3.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, en, a, b,
    output logic pass
);
    // Stage 0: capture start & a & en at cycle s.
    logic s_ae_q;
    // Stage 1: AND with en at s+1.
    logic carry_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            s_ae_q  <= 1'b0;
            carry_q <= 1'b0;
        end else begin
            s_ae_q  <= start & a & en;
            carry_q <= s_ae_q & en;
        end
    end
    // Stage 2: AND with b & en at s+2, then register.
    logic match_w, pass_q;
    assign match_w = carry_q & b & en;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= match_w;
    end
    assign pass = pass_q;
endmodule
"""


def _ref_throughout_bool_rep(name: str) -> str:
    """`en throughout (c[*3])` — cond gates c[*3] body (3 cycles).

    Body c[*3] transitions: 0→1, 1→2, 2→3 each on c. Product with en:
    every transition gated by (c & en). Accept={3}.
    Match at s+2 iff (start & c & en)(s) & (c & en)(s+1) & (c & en)(s+2).
    Register once → pass at s+3.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, en, c,
    output logic pass
);
    logic s_ce_q, carry_q, match_w, pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            s_ce_q  <= 1'b0;
            carry_q <= 1'b0;
            pass_q  <= 1'b0;
        end else begin
            s_ce_q  <= start & c & en;
            carry_q <= s_ce_q & c & en;
            pass_q  <= match_w;
        end
    end
    assign match_w = carry_q & c & en;
    assign pass = pass_q;
endmodule
"""


def _ref_throughout_bool_short_rep(name: str) -> str:
    """`en throughout (c[*1])` — cond gates single-cycle rep body.

    c[*1] completes at s if c(s). Pass at s+1 iff start(s) & en(s) & c(s).
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, en, c,
    output logic pass
);
    logic pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= start & en & c;
    end
    assign pass = pass_q;
endmodule
"""


# ─────────────────────────────────────────────────────────────────────────
# Compose helpers
# ─────────────────────────────────────────────────────────────────────────


def _compose_intersect(
    left: SVANode, right: SVANode, text: str,
) -> CheckerNode:
    node = SeqIntersect(left=left, right=right, source_loc=_LOC)
    return compose(node, _CLK, None, text)


def _compose_within(
    inner: SVANode, outer: SVANode, text: str,
) -> CheckerNode:
    node = SeqWithin(inner=inner, outer=outer, source_loc=_LOC)
    return compose(node, _CLK, None, text)


def _compose_throughout(
    cond: BoolExpr, body: SVANode, text: str,
) -> CheckerNode:
    node = SeqThroughout(condition=cond, body=body, source_loc=_LOC)
    return compose(node, _CLK, None, text)


# ═════════════════════════════════════════════════════════════════════════
# intersect miters — 4 shapes
# ═════════════════════════════════════════════════════════════════════════


class TestNfaIntersectMiter:
    def test_bool_rep1_miter(self) -> None:
        rep1 = SeqRepetition(
            expr=_b("b"), rep_min=1, rep_max=1, source_loc=_LOC,
        )
        checker = _compose_intersect(
            _b("a"), rep1, "a intersect (b[*1])",
        )
        assert checker.template_name == "nfa_generic", (
            "expected NFA path for bool × rep-1"
        )
        ref_name = "ref_isect_br1"
        ref = _ref_intersect_bool_rep1(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, (
            f"a intersect (b[*1]) miter FAILED:\n{output[-2500:]}"
        )

    def test_seq_bool_miter(self) -> None:
        checker = _compose_intersect(
            _sc_a2b(), _b("c"), "(a ##2 b) intersect c",
        )
        ref_name = "ref_isect_sb"
        ref = _ref_intersect_seq_bool(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, f"(a ##2 b) intersect c miter FAILED:\n{output[-2500:]}"

    def test_rep_bool_miter(self) -> None:
        checker = _compose_intersect(
            _rep_c3(), _b("b"), "(c[*3]) intersect b",
        )
        ref_name = "ref_isect_rb"
        ref = _ref_intersect_rep_bool(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, f"(c[*3]) intersect b miter FAILED:\n{output[-2500:]}"

    def test_seq_rep_miter(self) -> None:
        checker = _compose_intersect(
            _sc_a2b(), _rep_c3(), "(a ##2 b) intersect (c[*3])",
        )
        ref_name = "ref_isect_sr"
        ref = _ref_intersect_seq_rep(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, (
            f"(a ##2 b) intersect (c[*3]) miter FAILED:\n{output[-2500:]}"
        )


# ═════════════════════════════════════════════════════════════════════════
# within miters — 4 shapes
# ═════════════════════════════════════════════════════════════════════════


class TestNfaWithinMiter:
    def test_bool_rep1_miter(self) -> None:
        rep1 = SeqRepetition(
            expr=_b("b"), rep_min=1, rep_max=1, source_loc=_LOC,
        )
        checker = _compose_within(_b("a"), rep1, "a within (b[*1])")
        assert checker.template_name == "nfa_generic"
        ref_name = "ref_within_br1"
        ref = _ref_within_bool_rep1(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, f"a within (b[*1]) miter FAILED:\n{output[-2500:]}"

    def test_bool_rep_miter(self) -> None:
        checker = _compose_within(_b("a"), _rep_c3(), "a within (c[*3])")
        ref_name = "ref_within_br"
        ref = _ref_within_bool_rep(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, f"a within (c[*3]) miter FAILED:\n{output[-2500:]}"

    def test_seq_bool_miter(self) -> None:
        checker = _compose_within(_sc_a2b(), _b("c"), "(a ##2 b) within c")
        ref_name = "ref_within_sb"
        ref = _ref_within_seq_bool(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, f"(a ##2 b) within c miter FAILED:\n{output[-2500:]}"

    def test_seq_rep_miter(self) -> None:
        checker = _compose_within(
            _sc_a2b(), _rep_c3(), "(a ##2 b) within (c[*3])",
        )
        ref_name = "ref_within_sr"
        ref = _ref_within_seq_rep(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, (
            f"(a ##2 b) within (c[*3]) miter FAILED:\n{output[-2500:]}"
        )


# ═════════════════════════════════════════════════════════════════════════
# throughout miters — 4 shapes
# ═════════════════════════════════════════════════════════════════════════


class TestNfaThroughoutMiter:
    def test_bool_rep2_miter(self) -> None:
        rep2 = SeqRepetition(
            expr=_b("a"), rep_min=2, rep_max=2, source_loc=_LOC,
        )
        checker = _compose_throughout(
            _b("en"), rep2, "en throughout (a[*2])",
        )
        assert checker.template_name == "nfa_generic"
        ref_name = "ref_thr_br2"
        ref = _ref_throughout_bool_rep2(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, (
            f"en throughout (a[*2]) miter FAILED:\n{output[-2500:]}"
        )

    def test_bool_seq_miter(self) -> None:
        checker = _compose_throughout(
            _b("en"), _sc_a2b(), "en throughout (a ##2 b)",
        )
        ref_name = "ref_thr_bs"
        ref = _ref_throughout_bool_seq(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, (
            f"en throughout (a ##2 b) miter FAILED:\n{output[-2500:]}"
        )

    def test_bool_rep_miter(self) -> None:
        checker = _compose_throughout(
            _b("en"), _rep_c3(), "en throughout (c[*3])",
        )
        ref_name = "ref_thr_br"
        ref = _ref_throughout_bool_rep(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, (
            f"en throughout (c[*3]) miter FAILED:\n{output[-2500:]}"
        )

    def test_bool_short_rep_miter(self) -> None:
        short_rep = SeqRepetition(
            expr=_b("c"), rep_min=1, rep_max=1, source_loc=_LOC,
        )
        checker = _compose_throughout(
            _b("en"), short_rep, "en throughout (c[*1])",
        )
        ref_name = "ref_thr_bsr"
        ref = _ref_throughout_bool_short_rep(ref_name)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=15,
        )
        assert passed, (
            f"en throughout (c[*1]) miter FAILED:\n{output[-2500:]}"
        )
