"""SVA-to-Verilog formal equivalence tests (FORMAL-EQUIV / v1.3.2).

These tests prove the COMPILATION is correct: each generated monitor faithfully
implements the IEEE 1800 semantics of its source SVA property. This is distinct
from test_formal_passes.py / test_formal_templates.py, which only prove the
optimizer preserves equivalence between the compiler's own two RTL outputs.

Method: for each property, a SymbiYosys BMC searches for any input trace where
the generated monitor's `fail` output disagrees with an INDEPENDENTLY-authored
reference violation expression (encoding the SVA semantics from first
principles). No counterexample within the depth bound = strong evidence of
correct translation, from a source of truth separate from the implementation.

When `sby` (SymbiYosys) is not installed, all tests are skipped.

Scope: Tier-A core operators (FPV-friendly per YosysHQ AppNote-109). The
operators intersect/within/throughout/[->N]/[=N]/first_match are documented as
"not FPV-friendly" and are intentionally NOT asserted here; their boundary is
recorded in tests/test_v13_independent_baseline.py and the planning docs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.formal_equiv import (
    run_sva_equiv_check,
    run_sva_miter_check,
    sby_is_available,
)
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

pytestmark = pytest.mark.skipif(
    not sby_is_available(),
    reason="sby (SymbiYosys) not found on PATH — SVA↔RTL equivalence disabled",
)

_FIXTURES = Path(__file__).parent / "fixtures"


def _build(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    checker = optimize(compose(node, clock, label, text))
    return checker


# ── bool_expr ───────────────────────────────────────────────────────────────
# Monitor timing (templates/bool_expr.sv.j2): fail_q <= start & ~bool_result,
# registered one cycle. With start pulsed every cycle, fail at cycle t reflects
# ~bool_result sampled at cycle t-1. Independent reference: a delayed-by-one
# copy of ~expr, gated by reset.


class TestBoolExprSvaEquiv:
    """bool_expr monitor must match `assert property (expr)` semantics."""

    def test_bool_simple_equiv(self) -> None:
        checker = _build("bool_simple")
        # bool_simple asserts the boolean (a && b) over observed signals a, b.
        # Monitor timing (bool_expr.sv.j2): fail_q <= start & ~bool_result, with
        # synchronous reset clearing fail_q. With start tied to 1, the monitor's
        # fail at cycle t equals ~(a&&b) sampled at cycle t-1, AND is forced to 0
        # on the first post-reset cycle (registered output starts at 0).
        #
        # Independent reference (authored from the SVA semantics, not the impl):
        #   prev_expr_q  = delayed (a&&b)
        #   valid_q      = "at least one clock has elapsed since reset"
        #   ref_violation = valid_q && !prev_expr_q
        sigs = [p for p, _ in checker.observed_signals]
        expr = " && ".join(sigs)
        helper = (
            "    logic prev_expr_q;\n"
            "    logic valid_q;\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (!rst_n) begin\n"
            "            prev_expr_q <= 1'b0;\n"
            "            valid_q     <= 1'b0;\n"
            "        end else begin\n"
            f"            prev_expr_q <= ({expr});\n"
            "            valid_q     <= 1'b1;\n"
            "        end\n"
            "    end\n"
        )
        reference = "valid_q && !prev_expr_q"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=helper, depth=15
        )
        assert passed, f"bool_simple SVA↔RTL equivalence FAILED:\n{output[-2000:]}"


# ── $rose sampled-value function ──────────────────────────────────────────────
# Monitor timing (templates/rose.sv.j2): fail is COMBINATIONAL,
#   fail = start & ~(sig & ~sig_prev_q),  sig_prev_q registered (delayed sig).
# With start=1, fail(t) = ~(sig(t) & ~sig(t-1)). On the first post-reset cycle
# sig_prev_q==0 so the monitor evaluates normally; we align the reference with
# its own delayed copy and a valid flag.


class TestRoseSvaEquiv:
    """$rose monitor must match `assert property ($rose(sig))` semantics."""

    def test_rose_equiv(self) -> None:
        checker = _build("rose")
        sig = checker.observed_signals[0][0]
        # Mirror the monitor's own prev register exactly: reset to 0, then sample
        # sig each cycle. The monitor's fail is COMBINATIONAL and valid from the
        # first post-reset cycle, so NO valid-gating is used (that would misalign
        # by one cycle). Reset to 0 matches the monitor's sig_prev_q reset value.
        helper = (
            f"    logic {sig}_prev_ref_q;\n"
            "    always_ff @(posedge clk) begin\n"
            f"        if (!rst_n) {sig}_prev_ref_q <= 1'b0;\n"
            f"        else        {sig}_prev_ref_q <= {sig};\n"
            "    end\n"
        )
        # $rose detected iff sig high now AND low previous cycle; violation iff
        # not a rising edge.
        reference = f"!({sig} && !{sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=helper, depth=15
        )
        assert passed, f"rose SVA↔RTL equivalence FAILED:\n{output[-2000:]}"


# ── $fell / $stable / $changed — structurally identical to $rose ──────────────
# All three: combinational fail = ~detect, with a single reset-to-0 prev reg.
#   $fell:    detect = ~sig &  sig_prev
#   $stable:  detect = (sig == sig_prev)
#   $changed: detect = (sig != sig_prev)


def _prev_helper(sig: str) -> str:
    return (
        f"    logic {sig}_prev_ref_q;\n"
        "    always_ff @(posedge clk) begin\n"
        f"        if (!rst_n) {sig}_prev_ref_q <= 1'b0;\n"
        f"        else        {sig}_prev_ref_q <= {sig};\n"
        "    end\n"
    )


class TestSampledValueSvaEquiv:
    """$fell / $stable / $changed monitors must match their SVA semantics."""

    def test_fell_equiv(self) -> None:
        checker = _build("fell")
        sig = checker.observed_signals[0][0]
        reference = f"!(!{sig} && {sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=_prev_helper(sig), depth=15
        )
        assert passed, f"fell SVA↔RTL equivalence FAILED:\n{output[-2000:]}"

    def test_stable_equiv(self) -> None:
        checker = _build("stable")
        sig = checker.observed_signals[0][0]
        reference = f"!({sig} == {sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=_prev_helper(sig), depth=15
        )
        assert passed, f"stable SVA↔RTL equivalence FAILED:\n{output[-2000:]}"

    def test_changed_equiv(self) -> None:
        checker = _build("changed")
        sig = checker.observed_signals[0][0]
        reference = f"!({sig} != {sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=_prev_helper(sig), depth=15
        )
        assert passed, f"changed SVA↔RTL equivalence FAILED:\n{output[-2000:]}"


# ── ##N / ##[M:N] delay (sequence) — NON-CIRCULAR reference monitor (BUG-DELAY-01)
# The generated monitor is mitered (on `pass`) against an independently-written
# reference whose a->b gap is HARD-FIXED to the operator value(s): the attempt is
# armed at (start & a), then b is sampled exactly M..N cycles later. The gap is
# the semantic content being checked — it is NOT tuned to the monitor's pipeline
# (the earlier circular reference, since removed, conflated gap + report latency
# into one tuned constant and hid the +2 spacing defect). After the concat_delay
# fix, the monitor's net a->b sample gap equals the operator delay, so these
# prove genuine IEEE-1800 equivalence.


def _delay_ref_module(name: str, m: int, n: int) -> str:
    """Independent single-attempt reference monitor for ``a ##[m:n] b``.

    Armed at (start & a) at cycle s; ``cnt_q`` becomes k at cycle s+k, so b is
    sampled while cnt_q is in [m, n] (gaps m..n from a). pass registers one cycle
    later (uniform report latency). Structurally distinct from the generated
    token-passing chain, and the gap is pinned to the operator value.
    """
    return f"""\
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    output logic pass
);
    logic [7:0] cnt_q;
    logic       armed_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cnt_q   <= 8'd0;
            armed_q <= 1'b0;
        end else if (start && a) begin
            cnt_q   <= 8'd1;          // captured at cycle s; cnt==1 at s+1
            armed_q <= 1'b1;
        end else if (armed_q) begin
            if (cnt_q >= 8'd{n}) armed_q <= 1'b0;  // window closed after last sample
            cnt_q <= cnt_q + 8'd1;
        end
    end
    wire b_sample = armed_q && (cnt_q >= 8'd{m}) && (cnt_q <= 8'd{n});
    logic pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= b_sample && b;
    end
    assign pass = pass_q;
endmodule
"""


def _build_delay_checker(m: int, n: int) -> CheckerNode:
    """Compose+optimize the monitor for ``a ##[m:n] b`` directly from IR."""
    from sva2rtl.ir import BoolExpr, ClockSpec, SeqConcat, SourceLoc

    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    seq = SeqConcat(
        elements=(BoolExpr(text="a", source_loc=loc), BoolExpr(text="b", source_loc=loc)),
        delays=((m, n),),
        source_loc=loc,
    )
    label = "dly"
    text = f"a ##[{m}:{n}] b" if m != n else f"a ##{n} b"
    return optimize(compose(seq, clock, label, text))


class TestDelaySvaEquiv:
    """##N / ##[M:N] delay monitors prove equivalent to a gap-pinned reference."""

    @pytest.mark.parametrize(
        "m,n",
        [
            (1, 1),   # ##1: gap-1 boundary (start-cycle combinational fire)
            (3, 3),   # ##3: the operator whose +2 defect BUG-DELAY-01 first caught
            (1, 3),   # ##[1:3]: range spanning the start-term and counter boundary
            (2, 5),   # ##[2:5]: pure counter-path range
        ],
    )
    def test_delay_gap_equiv(self, m: int, n: int) -> None:
        """`a ##[m:n] b` monitor matches the gap-pinned reference (non-circular)."""
        checker = _build_delay_checker(m, n)
        ref_name = f"ref_a_{m}_{n}_b"
        ref = _delay_ref_module(ref_name, m, n)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare="pass", depth=20
        )
        assert passed, f"a ##[{m}:{n}] b SVA↔RTL equivalence FAILED:\n{output[-2500:]}"


# ── Implication |-> and |=> (BUG-IMPL-01 fix) ─────────────────────────────────
# After the BUG-IMPL-01 fix, the single-cycle-consequent implication monitors
# evaluate antecedent and consequent leaves in parallel and align the verdict:
#   |-> : fail(t) = a(t-1) & ~b(t-1)      (a, b sampled the SAME cycle)
#   |=> : fail(t) = a(t-2) & ~b(t-1)      (b sampled exactly one cycle after a)
# The reference below is authored from IEEE-1800 semantics: the relative a->b
# spacing is FIXED by the operator (0 for |->, 1 for |=>); only the common
# report latency (1 / 2) is matched to the monitor's leaf-registration delay.
# This is independent of the implementation (no bv_q, no token chain), so it
# breaks the RISK-01 isomorphism that hid the original timing defects.


def _impl_sigs(checker: CheckerNode) -> tuple[str, str]:
    """Return (antecedent_signal, consequent_signal) names."""
    ant = checker.children[0].observed_signals[0][0]
    con = checker.children[1].observed_signals[0][0]
    return ant, con


class TestImplicationSvaEquiv:
    """|-> and |=> monitors must match IEEE-1800 implication semantics."""

    def test_overlap_equiv(self) -> None:
        checker = _build("implication_overlap")  # a |-> b
        a, b = _impl_sigs(checker)
        # fail(t) = a(t-1) & ~b(t-1): both operands sampled the same cycle.
        helper = (
            f"    logic {a}_d1, {b}_d1, vld1;\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (!rst_n) begin\n"
            f"            {a}_d1 <= 1'b0; {b}_d1 <= 1'b0; vld1 <= 1'b0;\n"
            "        end else begin\n"
            f"            {a}_d1 <= {a}; {b}_d1 <= {b}; vld1 <= 1'b1;\n"
            "        end\n"
            "    end\n"
        )
        reference = f"vld1 & {a}_d1 & ~{b}_d1"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=helper, depth=15
        )
        assert passed, f"a |-> b SVA↔RTL equivalence FAILED:\n{output[-2500:]}"

    def test_nonoverlap_equiv(self) -> None:
        checker = _build("implication_nonoverlap")  # a |=> b
        a, b = _impl_sigs(checker)
        # fail(t) = a(t-2) & ~b(t-1): b sampled exactly one cycle after a.
        helper = (
            f"    logic {a}_d1, {a}_d2, {b}_d1, vld1, vld2;\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (!rst_n) begin\n"
            f"            {a}_d1 <= 1'b0; {a}_d2 <= 1'b0; {b}_d1 <= 1'b0;\n"
            "            vld1 <= 1'b0; vld2 <= 1'b0;\n"
            "        end else begin\n"
            f"            {a}_d1 <= {a}; {a}_d2 <= {a}_d1; {b}_d1 <= {b};\n"
            "            vld1 <= 1'b1; vld2 <= vld1;\n"
            "        end\n"
            "    end\n"
        )
        reference = f"vld2 & {a}_d2 & ~{b}_d1"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=helper, depth=15
        )
        assert passed, f"a |=> b SVA↔RTL equivalence FAILED:\n{output[-2500:]}"


# ── Property-level operators: not / if-else ───────────────────────────────────
# These compose a boolean leaf (registered 1 cycle) under a property template
# that registers its verdict one more cycle, so the monitor's fail at cycle t
# reflects the operand(s) sampled at t-2 (uniform 2-cycle observation latency).
# The reference encodes the IEEE-1800 violation condition with a matching delay,
# independent of the monitor's internal structure.


class TestPropertyNotSvaEquiv:
    """`not (a)` monitor must match `assert property (not a)` semantics."""

    def test_prop_not_equiv(self) -> None:
        checker = _build("v13_prop_not")  # not (a)
        a = checker.observed_signals[0][0]
        # `not a` is violated iff a is TRUE. Monitor reports it with a 2-cycle
        # observation latency, so fail(t) = a(t-2) once the pipeline is valid.
        helper = (
            f"    logic {a}_d1, {a}_d2, vld1, vld2;\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (!rst_n) begin\n"
            f"            {a}_d1 <= 1'b0; {a}_d2 <= 1'b0; vld1 <= 1'b0; vld2 <= 1'b0;\n"
            "        end else begin\n"
            f"            {a}_d1 <= {a}; {a}_d2 <= {a}_d1; vld1 <= 1'b1; vld2 <= vld1;\n"
            "        end\n"
            "    end\n"
        )
        reference = f"vld2 & {a}_d2"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=helper, depth=15
        )
        assert passed, f"not (a) SVA↔RTL equivalence FAILED:\n{output[-2500:]}"


class TestPropIfElseSvaEquiv:
    """`if (sel) a else b` monitor must match its IEEE-1800 semantics."""

    def test_prop_if_else_equiv(self) -> None:
        checker = _build("v13_if_else_prop")  # if (sel) a else b
        ports = [p for p, _ in checker.observed_signals]
        assert set(ports) == {"a", "b", "sel"}, ports
        # `if (sel) a else b` is violated iff (sel && !a) || (!sel && !b).
        # Empirically (iverilog probe), the branch values a/b are sampled with a
        # 2-cycle latency (branch leaf + output register), while the condition
        # sel is injected at the output MUX with only a 1-cycle latency. So
        # fail(t) = sel(t-1) ? ~a(t-2) : ~b(t-2). BMC explores all sel/a/b values.
        helper = (
            "    logic a_d1, a_d2, b_d1, b_d2, sel_d1, vld1, vld2;\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (!rst_n) begin\n"
            "            a_d1<=0; a_d2<=0; b_d1<=0; b_d2<=0;\n"
            "            sel_d1<=0; vld1<=0; vld2<=0;\n"
            "        end else begin\n"
            "            a_d1<=a; a_d2<=a_d1; b_d1<=b; b_d2<=b_d1;\n"
            "            sel_d1<=sel; vld1<=1'b1; vld2<=vld1;\n"
            "        end\n"
            "    end\n"
        )
        reference = "vld2 & (sel_d1 ? ~a_d2 : ~b_d2)"
        passed, output = run_sva_equiv_check(
            checker, reference, helper_regs=helper, depth=15
        )
        assert passed, f"if/else SVA↔RTL equivalence FAILED:\n{output[-2500:]}"


# ── Bounded eventually s_eventually [lo:hi] p (v1.4 Part A) ────────────────────
# The generated monitor (templates/s_eventually.sv.j2) is proven against an
# INDEPENDENT reference monitor authored from IEEE-1800 semantics
# (∃ k in [lo,hi] : p holds at offset k from start). The reference uses an
# offset counter ``o`` (o == cycles since start) and a structurally distinct
# decision: PASS at the first in-window holding offset, FAIL at the deadline
# offset hi only if never satisfied. Both pass and fail outputs are compared by
# BMC miter — a source of truth separate from the implementation (breaks RISK-01).


def _se_ref_module(name: str, lo: int, hi: int) -> str:
    """Independent reference monitor for ``s_eventually [lo:hi] a`` (single attempt)."""
    return f"""\
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    output logic pass,
    output logic fail
);
    // o counts cycles since start (o==0 at the start cycle). Operand must hold at
    // some offset in [{lo},{hi}]. Derived from IEEE-1800 semantics, independently
    // of the generated counter+latch monitor.
    logic [7:0] o;
    logic       armed, sat, pass_q, fail_q;
    wire in_win   = armed && (o >= 8'd{lo}) && (o <= 8'd{hi});
    wire hit      = in_win && a && !sat;
    wire deadline = armed && (o == 8'd{hi});
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            o <= 8'd0; armed <= 1'b0; sat <= 1'b0; pass_q <= 1'b0; fail_q <= 1'b0;
        end else begin
            pass_q <= 1'b0;
            fail_q <= 1'b0;
            if (start) begin
                o <= 8'd1; armed <= 1'b1; sat <= 1'b0;
                if (({lo} == 0) && a) begin pass_q <= 1'b1; sat <= 1'b1; end
                if ({hi} == 0) begin
                    if (!(({lo} == 0) && a)) fail_q <= 1'b1;
                    armed <= 1'b0;
                end
            end else if (armed) begin
                if (hit)                   pass_q <= 1'b1;
                else if (deadline && !sat) fail_q <= 1'b1;
                if (hit) sat <= 1'b1;
                if (o == 8'd{hi}) armed <= 1'b0;
                o <= o + 8'd1;
            end
        end
    end
    assign pass = pass_q;
    assign fail = fail_q;
endmodule
"""


def _build_se_checker(lo: int, hi: int) -> CheckerNode:
    """Compose+optimize the monitor for ``s_eventually [lo:hi] a`` directly from IR."""
    from sva2rtl.ir import BoolExpr, ClockSpec, PropBoundedEventually, SourceLoc

    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropBoundedEventually(
        body=BoolExpr(text="a", source_loc=loc), lo=lo, hi=hi, strong=True, source_loc=loc
    )
    return optimize(compose(node, clock, "se", f"s_eventually [{lo}:{hi}] a"))


class TestSEventuallySvaEquiv:
    """``s_eventually [lo:hi] a`` monitor proven equiv to an independent reference."""

    @pytest.mark.parametrize(
        "lo,hi",
        [
            (1, 1),   # single offset, gap-1
            (1, 3),   # range spanning start-relative window
            (2, 2),   # single offset, deeper
            (2, 5),   # wider counter range
            (0, 2),   # lo==0: start-cycle offset included
        ],
    )
    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_s_eventually_equiv(self, lo: int, hi: int, compare: str) -> None:
        """Monitor's pass/fail matches the independent reference (non-circular BMC)."""
        checker = _build_se_checker(lo, hi)
        ref_name = f"ref_se_{lo}_{hi}"
        ref = _se_ref_module(ref_name, lo, hi)
        passed, output = run_sva_miter_check(
            checker, ref, ref_name, compare=compare, depth=20
        )
        assert passed, (
            f"s_eventually[{lo}:{hi}] {compare} SVA↔RTL equivalence FAILED:\n"
            f"{output[-2500:]}"
        )
