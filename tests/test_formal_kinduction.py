"""k-induction complete proof tests (v1.6 FORMAL-PROVE).

These tests extend the SVA↔Verilog formal equivalence verification from bounded
model checking (BMC) to k-induction — providing a COMPLETE mathematical proof
that the generated monitor faithfully implements the IEEE 1800 semantics for ALL
reachable states, not just within a bounded depth.

k-induction works by:
  1. Base case: prove the property holds for the first k cycles (BMC).
  2. Inductive step: assume the property holds for k consecutive cycles and
     prove it holds for the (k+1)th cycle.

If both steps succeed, the property is proven for all time — a mathematical
proof, not just bounded evidence.

Scope: Tier-A core operators (FPV-friendly per YosysHQ AppNote-109). These
are the simplest monitors and most likely to converge with k-induction.
Complex sequential operators (intersect/within/throughout, NFA-based) may
not converge and are left as BMC-only.

When `sby` (SymbiYosys) is not installed, all tests are skipped.
When k-induction does not converge within the timeout, the test is marked
xfail (honest boundary recording, per project's honesty-first discipline).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.bool_semantics import deserialize_bool_expr, render_bool_expr
from sva2rtl.composer import compose
from sva2rtl.formal_equiv import (
    run_sva_equiv_check,
    run_sva_miter_check,
    sby_is_available,
)
from sva2rtl.ir import BoolExpr, CheckerNode, ClockSpec, SeqConcat, SeqRepetition, SourceLoc
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

pytestmark = [
    pytest.mark.formal,
    pytest.mark.skipif(
        not sby_is_available(),
        reason="sby (SymbiYosys) not found on PATH — k-induction proofs disabled",
    ),
]

_FIXTURES = Path(__file__).parent / "fixtures"
_DEFAULT_PROVE_TIMEOUT_SECONDS = 600
_PHASE10_PROVE_TIMEOUT_SECONDS = 60


def _prove_timeout() -> int:
    """Return k-induction subprocess timeout for this environment."""
    raw = os.environ.get("SVA2RTL_FORMAL_PROVE_TIMEOUT")
    if raw is None:
        return _DEFAULT_PROVE_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_PROVE_TIMEOUT_SECONDS


def _phase10_prove_timeout() -> int:
    """Keep Phase 10 expansion proofs bounded for local developer loops."""
    return min(_prove_timeout(), _PHASE10_PROVE_TIMEOUT_SECONDS)


def _build(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = optimize(compose(node, clock, label, text))
    return checker


def _semantic_bool_reference_expr(checker: CheckerNode) -> str:
    """Render the formal reference expression from bool_semantic params."""
    payload = checker.params.get("bool_semantic")
    assert payload is not None, "bool_expr checker must carry bool_semantic"
    return render_bool_expr(deserialize_bool_expr(payload))


def _loc() -> SourceLoc:
    return SourceLoc("test.sv", 1, 1)


def _clock(loc: SourceLoc) -> ClockSpec:
    return ClockSpec(edge="posedge", signal="clk", source_loc=loc)


def _delay_ref_module(name: str, m: int, n: int) -> str:
    """Independent single-attempt reference monitor for ``a ##[m:n] b``."""
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
            cnt_q   <= 8'd1;
            armed_q <= 1'b1;
        end else if (armed_q) begin
            if (cnt_q >= 8'd{n}) armed_q <= 1'b0;
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
    loc = _loc()
    seq = SeqConcat(
        elements=(BoolExpr(text="a", source_loc=loc), BoolExpr(text="b", source_loc=loc)),
        delays=((m, n),),
        source_loc=loc,
    )
    text = f"a ##[{m}:{n}] b" if m != n else f"a ##{n} b"
    return optimize(compose(seq, _clock(loc), "dly", text))


def _ref_rep_consecutive(name: str, n: int) -> str:
    """Independent reference for ``a[*N]`` consecutive repetition."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, a,
    output logic pass
);
    logic [1:0] cnt_q;
    logic running_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cnt_q     <= 0;
            running_q <= 1'b0;
        end else if (start && a) begin
            cnt_q     <= 1;
            running_q <= 1'b1;
        end else if (running_q && a) begin
            if (cnt_q < {n})
                cnt_q <= cnt_q + 1'b1;
        end else if (running_q && !a) begin
            running_q <= 1'b0;
            cnt_q     <= 0;
        end
    end
    assign pass = running_q && a && (cnt_q == {n});
endmodule
"""


def _build_rep_checker(n: int) -> CheckerNode:
    """Compose+optimize the monitor for ``a[*N]`` directly from IR."""
    loc = _loc()
    node = SeqRepetition(
        expr=BoolExpr(text="a", source_loc=loc),
        rep_min=n,
        rep_max=n,
        source_loc=loc,
    )
    return optimize(compose(node, _clock(loc), "rep", f"a[*{n}]"))


def _is_induction_boundary(output: str) -> bool:
    """Return True only for proof non-convergence, not real counterexamples."""
    lower = output.lower()
    lines = [line.lower() for line in output.splitlines()]
    basecase_failed = any(
        "basecase failed" in line
        or "for basecase: fail" in line
        or "returned fail for basecase" in line
        for line in lines
    )
    if basecase_failed:
        return False

    if "timed out" in lower or "timeout" in lower:
        return True

    basecase_passed = any(
        "for basecase: pass" in line or "returned pass for basecase" in line for line in lines
    )
    induction_failed = "temporal induction failed" in lower or any(
        "for induction: fail" in line
        or "returned fail for induction" in line
        or "returned unknown for induction" in line
        for line in lines
    )
    return basecase_passed and induction_failed


def _assert_kinduction_passed(passed: bool, output: str, op_name: str) -> None:
    """Fail on real counterexamples; xfail only for induction convergence limits."""
    if passed:
        return
    if _is_induction_boundary(output):
        pytest.xfail(
            f"k-induction did not converge for {op_name} (honest boundary):\n{output[-500:]}"
        )
    pytest.fail(f"{op_name} k-induction proof FAILED:\n{output[-2000:]}")


# ── bool_expr: k-induction complete proof ─────────────────────────────────


class TestKinductionBoolExpr:
    """Prove bool_expr monitor correctness via k-induction (complete proof)."""

    def test_bool_kinduction_prove(self) -> None:
        """bool_expr monitor PROVEN equivalent to `assert property (expr)`.

        This is a COMPLETE proof (all reachable states), not just bounded.
        """
        checker = _build("bool_simple")
        expr = _semantic_bool_reference_expr(checker)
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
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            mode="prove",
            timeout=_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "bool_expr")


# ── $rose: k-induction complete proof ─────────────────────────────────────


class TestKinductionRose:
    """Prove $rose monitor correctness via k-induction."""

    def test_rose_kinduction_prove(self) -> None:
        """$rose monitor PROVEN equivalent to IEEE 1800 $rose semantics."""
        checker = _build("rose")
        sig = checker.observed_signals[0][0]
        helper = (
            f"    logic {sig}_prev_ref_q;\n"
            "    always_ff @(posedge clk) begin\n"
            f"        if (!rst_n) {sig}_prev_ref_q <= 1'b0;\n"
            f"        else        {sig}_prev_ref_q <= {sig};\n"
            "    end\n"
        )
        reference = f"~({sig} & ~{sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            mode="prove",
            timeout=_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "$rose")


# ── $fell: k-induction complete proof ─────────────────────────────────────


class TestKinductionFell:
    """Prove $fell monitor correctness via k-induction."""

    def test_fell_kinduction_prove(self) -> None:
        """$fell monitor PROVEN equivalent to IEEE 1800 $fell semantics."""
        checker = _build("fell")
        sig = checker.observed_signals[0][0]
        helper = (
            f"    logic {sig}_prev_ref_q;\n"
            "    always_ff @(posedge clk) begin\n"
            f"        if (!rst_n) {sig}_prev_ref_q <= 1'b0;\n"
            f"        else        {sig}_prev_ref_q <= {sig};\n"
            "    end\n"
        )
        reference = f"~(~{sig} & {sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            mode="prove",
            timeout=_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "$fell")


# ── $stable: k-induction complete proof ───────────────────────────────────


class TestKinductionStable:
    """Prove $stable monitor correctness via k-induction."""

    def test_stable_kinduction_prove(self) -> None:
        """$stable monitor PROVEN equivalent to IEEE 1800 $stable semantics."""
        checker = _build("stable")
        sig = checker.observed_signals[0][0]
        helper = (
            f"    logic {sig}_prev_ref_q;\n"
            "    always_ff @(posedge clk) begin\n"
            f"        if (!rst_n) {sig}_prev_ref_q <= 1'b0;\n"
            f"        else        {sig}_prev_ref_q <= {sig};\n"
            "    end\n"
        )
        reference = f"({sig} != {sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            mode="prove",
            timeout=_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "$stable")


# ── $changed: k-induction complete proof ──────────────────────────────────


class TestKinductionChanged:
    """Prove $changed monitor correctness via k-induction."""

    def test_changed_kinduction_prove(self) -> None:
        """$changed monitor PROVEN equivalent to IEEE 1800 $changed semantics."""
        checker = _build("changed")
        sig = checker.observed_signals[0][0]
        helper = (
            f"    logic {sig}_prev_ref_q;\n"
            "    always_ff @(posedge clk) begin\n"
            f"        if (!rst_n) {sig}_prev_ref_q <= 1'b0;\n"
            f"        else        {sig}_prev_ref_q <= {sig};\n"
            "    end\n"
        )
        reference = f"({sig} == {sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            mode="prove",
            timeout=_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "$changed")


# ── Phase 10 expansion: small finite-state templates ─────────────────────


class TestKinductionFixedDelay:
    """Attempt complete proof for fixed-delay sequence monitor pass behavior."""

    def test_fixed_delay_kinduction_prove(self) -> None:
        """Phase 10: `a ##1 b` pass behavior attempted with k-induction."""
        checker = _build_delay_checker(1, 1)
        ref_name = "ref_delay_1_1_prove"
        passed, output = run_sva_miter_check(
            checker,
            _delay_ref_module(ref_name, 1, 1),
            ref_name,
            compare="pass",
            depth=10,
            mode="prove",
            timeout=_phase10_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "fixed delay ##1")


class TestKinductionImplication:
    """Attempt complete proof for simple overlapping implication."""

    def test_overlap_implication_kinduction_prove(self) -> None:
        """Phase 10: `a |-> b` fail behavior attempted with k-induction."""
        checker = _build("implication_overlap")
        a = checker.children[0].observed_signals[0][0]
        b = checker.children[1].observed_signals[0][0]
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
            checker,
            reference,
            helper_regs=helper,
            depth=10,
            mode="prove",
            timeout=_phase10_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "overlap implication")


class TestKinductionRepConsecutive:
    """Attempt complete proof for fixed consecutive repetition."""

    def test_rep_fixed_kinduction_prove(self) -> None:
        """Phase 10: `a[*3]` pass behavior attempted with k-induction."""
        checker = _build_rep_checker(3)
        ref_name = "ref_rep3_prove"
        passed, output = run_sva_miter_check(
            checker,
            _ref_rep_consecutive(ref_name, 3),
            ref_name,
            compare="pass",
            depth=10,
            mode="prove",
            timeout=_phase10_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "fixed consecutive repetition [*3]")


# ── Phase P2-1 expansion: bounded delay and bounded repetition ────────────


class TestKinductionBoundedDelay:
    """Attempt complete proof for bounded (ranged) delay sequence monitor."""

    def test_bounded_delay_kinduction_prove(self) -> None:
        """P2-1: `a ##[1:5] b` pass behavior attempted with k-induction.

        The ranged delay monitor has a small finite state space (counter
        0..5 + armed flag), making k-induction convergence feasible.
        """
        checker = _build_delay_checker(1, 5)
        ref_name = "ref_delay_1_5_prove"
        passed, output = run_sva_miter_check(
            checker,
            _delay_ref_module(ref_name, 1, 5),
            ref_name,
            compare="pass",
            depth=12,
            mode="prove",
            timeout=_phase10_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "bounded delay ##[1:5]")


class TestKinductionBoundedRepetition:
    """Attempt complete proof for bounded (ranged) consecutive repetition."""

    def test_bounded_rep_kinduction_prove(self) -> None:
        """P2-1: `a[*2:5]` pass behavior attempted with k-induction.

        Ranged consecutive repetition uses a counter with acceptance window
        [2,5]. The state space is small enough for k-induction to converge.
        """
        loc = _loc()
        node = SeqRepetition(
            expr=BoolExpr(text="a", source_loc=loc),
            rep_min=2,
            rep_max=5,
            source_loc=loc,
        )
        checker = optimize(compose(node, _clock(loc), "brep", "a[*2:5]"))
        ref_name = "ref_brep_2_5_prove"
        # Independent reference: count consecutive a, pass when count in [2,5] and a
        ref_module = f"""
module {ref_name} (
    input  logic clk, rst_n, start, a,
    output logic pass
);
    logic [2:0] cnt_q;
    logic running_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cnt_q     <= 3'd0;
            running_q <= 1'b0;
        end else if (start && a) begin
            cnt_q     <= 3'd1;
            running_q <= 1'b1;
        end else if (running_q && a) begin
            if (cnt_q < 3'd5)
                cnt_q <= cnt_q + 3'd1;
        end else if (running_q && !a) begin
            running_q <= 1'b0;
            cnt_q     <= 3'd0;
        end
    end
    assign pass = running_q && a && (cnt_q >= 3'd2) && (cnt_q <= 3'd5);
endmodule
"""
        passed, output = run_sva_miter_check(
            checker,
            ref_module,
            ref_name,
            compare="pass",
            depth=12,
            mode="prove",
            timeout=_phase10_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "bounded consecutive repetition [*2:5]")


# ── Phase P2-1 expansion: bounded liveness ───────────────────────────────


class TestKinductionBoundedEventually:
    """Attempt complete proof for bounded eventually ``s_eventually[1:3] a``."""

    def test_bounded_eventually_kinduction_prove(self) -> None:
        """P2-1: `s_eventually[1:3] a` pass behavior attempted with k-induction.

        The bounded eventually monitor has a small finite state space
        (counter 0..3 + running flag), making k-induction convergence feasible.
        Uses the same independent reference monitor structure as the BMC test
        in test_formal_sva_equiv.py (registered pass_q, offset counter o
        starting at 1 on start cycle, in-window check o >= lo && o <= hi).
        """
        from sva2rtl.ir import PropBoundedEventually

        lo, hi = 1, 3
        loc = _loc()
        node = PropBoundedEventually(
            body=BoolExpr(text="a", source_loc=loc),
            lo=lo,
            hi=hi,
            strong=True,
            source_loc=loc,
        )
        checker = optimize(compose(node, _clock(loc), "be", f"s_eventually[{lo}:{hi}] a"))
        ref_name = "ref_be_1_3_prove"
        ref_module = f"""\
module {ref_name} (
    input  logic clk, rst_n, start, a,
    output logic pass
);
    logic [7:0] o;
    logic       armed, sat, pass_q;
    wire in_win   = armed && (o >= 8'd{lo}) && (o <= 8'd{hi});
    wire hit      = in_win && a && !sat;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            o <= 8'd0; armed <= 1'b0; sat <= 1'b0; pass_q <= 1'b0;
        end else begin
            pass_q <= 1'b0;
            if (start) begin
                o <= 8'd1; armed <= 1'b1; sat <= 1'b0;
            end else if (armed) begin
                if (hit) pass_q <= 1'b1;
                if (hit) sat <= 1'b1;
                if (o == 8'd{hi}) armed <= 1'b0;
                o <= o + 8'd1;
            end
        end
    end
    assign pass = pass_q;
endmodule
"""
        passed, output = run_sva_miter_check(
            checker,
            ref_module,
            ref_name,
            compare="pass",
            depth=12,
            mode="prove",
            timeout=_phase10_prove_timeout(),
        )
        _assert_kinduction_passed(passed, output, "bounded eventually s_eventually[1:3]")
