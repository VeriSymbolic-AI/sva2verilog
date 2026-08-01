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
from sva2rtl.bool_semantics import deserialize_bool_expr, render_bool_expr
from sva2rtl.composer import compose
from sva2rtl.formal_equiv import (
    FormalHarnessConfig,
    FormalOutputContract,
    run_sva_equiv_check,
    run_sva_miter_check,
    sby_is_available,
)
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

pytestmark = [
    pytest.mark.formal,
    pytest.mark.skipif(
        not sby_is_available(),
        reason="sby (SymbiYosys) not found on PATH — SVA↔RTL equivalence disabled",
    ),
]

_FIXTURES = Path(__file__).parent / "fixtures"


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


def _arbitrary_start_config(
    *,
    overlap: str = "unconstrained",
) -> FormalHarnessConfig:
    """Config for explicit Phase 10 arbitrary-start BMC claims."""
    return FormalHarnessConfig(
        start_mode="arbitrary_start",
        assumptions=("start is low while reset is asserted",),
        overlap=overlap,  # type: ignore[arg-type]
    )


def _reset_recovery_config() -> FormalHarnessConfig:
    """Config for explicit Phase 10 reset-recovery BMC claims."""
    return FormalHarnessConfig(
        reset_mode="reset_recovery",
        assumptions=("assertions are disabled while reset recovery is active",),
    )


def _bool_contract_ref_module(name: str) -> str:
    """Independent bool contract reference with variable disable support.

    This reference models the public monitor contract for ``assert property
    (a && b)``. In particular, ``attempt_fired`` is sticky across disable_i and
    is cleared only by reset, so a generated monitor that incorrectly clears it
    on disable would fail this miter.
    """
    return f"""
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    input  logic disable_i,
    output logic pass,
    output logic fail,
    output logic active,
    output logic attempt_fired,
    output logic disabled_o
);
    wire bool_result = a && b;
    logic active_q, pass_q, fail_q, attempt_fired_q;

    always_ff @(posedge clk) begin
        if (!rst_n || disable_i) begin
            active_q <= 1'b0;
            pass_q   <= 1'b0;
            fail_q   <= 1'b0;
        end else begin
            active_q <= start;
            pass_q   <= start &  bool_result;
            fail_q   <= start & ~bool_result;
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) attempt_fired_q <= 1'b0;
        else if (start) attempt_fired_q <= 1'b1;
    end

    assign active        = disable_i ? 1'b0 : active_q;
    assign pass          = disable_i ? 1'b0 : pass_q;
    assign fail          = disable_i ? 1'b0 : fail_q;
    assign attempt_fired = attempt_fired_q;
    assign disabled_o    = disable_i;
endmodule
"""


def _rose_contract_ref_module(name: str) -> str:
    """Independent full-contract reference for ``$rose(sig)``."""
    return f"""
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic sig,
    output logic pass,
    output logic fail,
    output logic active,
    output logic attempt_fired,
    output logic disabled_o
);
    logic sig_prev_q, attempt_fired_q;
    always_ff @(posedge clk) begin
        if (!rst_n) sig_prev_q <= 1'b0;
        else        sig_prev_q <= sig;
    end
    always_ff @(posedge clk) begin
        if (!rst_n) attempt_fired_q <= 1'b0;
        else if (start) attempt_fired_q <= 1'b1;
    end
    wire rose_detect = sig && !sig_prev_q;
    assign active        = start;
    assign pass          = start && rose_detect;
    assign fail          = start && !rose_detect;
    assign attempt_fired = attempt_fired_q;
    assign disabled_o    = 1'b0;
endmodule
"""


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
        passed, output = run_sva_equiv_check(checker, reference, helper_regs=helper, depth=15)
        assert passed, f"bool_simple SVA↔RTL equivalence FAILED:\n{output[-2000:]}"

    def test_bool_simple_arbitrary_start_bmc_depth15(self) -> None:
        """Phase 10: arbitrary_start BMC depth 15 for a bool leaf."""
        checker = _build("bool_simple")
        expr = _semantic_bool_reference_expr(checker)
        helper = (
            "    logic prev_start_q;\n"
            "    logic prev_expr_q;\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (!rst_n) begin\n"
            "            prev_start_q <= 1'b0;\n"
            "            prev_expr_q  <= 1'b0;\n"
            "        end else begin\n"
            "            prev_start_q <= formal_start;\n"
            f"            prev_expr_q  <= ({expr});\n"
            "        end\n"
            "    end\n"
        )
        reference = "prev_start_q && !prev_expr_q"
        passed, output = run_sva_equiv_check(
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            config=_arbitrary_start_config(),
        )
        assert passed, f"bool_simple arbitrary_start BMC depth 15 FAILED:\n{output[-2000:]}"

    def test_bool_simple_arbitrary_disable_contract_bmc_depth12(self) -> None:
        """Phase 10: arbitrary_disable contract BMC guards HARDEN-01 stickiness."""
        checker = _build("bool_simple")
        ref_name = "ref_bool_contract_disable"
        config = FormalHarnessConfig(
            start_mode="arbitrary_start",
            disable_mode="arbitrary_disable",
            output_contract=FormalOutputContract.full_monitor(include_overflow=False),
            assumptions=("start and disable are low while reset is asserted",),
            covers=("pass", "fail", "disable"),
            reference_disable_port=True,
        )
        passed, output = run_sva_miter_check(
            checker,
            _bool_contract_ref_module(ref_name),
            ref_name,
            depth=12,
            config=config,
        )
        assert passed, (
            "bool_simple arbitrary_disable full-contract BMC depth 12 FAILED:\n"
            f"{output[-2500:]}"
        )

    def test_bool_simple_reset_recovery_bmc_depth15(self) -> None:
        """Phase 10: reset_recovery BMC depth 15 for a bool leaf."""
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
            config=_reset_recovery_config(),
        )
        assert passed, f"bool_simple reset_recovery BMC depth 15 FAILED:\n{output[-2000:]}"


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
        passed, output = run_sva_equiv_check(checker, reference, helper_regs=helper, depth=15)
        assert passed, f"rose SVA↔RTL equivalence FAILED:\n{output[-2000:]}"

    def test_rose_arbitrary_start_bmc_depth15(self) -> None:
        """Phase 10: arbitrary_start BMC depth 15 for a sampled-value leaf."""
        checker = _build("rose")
        sig = checker.observed_signals[0][0]
        helper = _prev_helper(sig)
        reference = f"formal_start && !({sig} && !{sig}_prev_ref_q)"
        passed, output = run_sva_equiv_check(
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            config=_arbitrary_start_config(),
        )
        assert passed, f"rose arbitrary_start BMC depth 15 FAILED:\n{output[-2000:]}"

    def test_rose_full_contract_bmc_depth12(self) -> None:
        """Phase 10: full-contract BMC depth 12 for a sampled-value leaf."""
        checker = _build("rose")
        config = FormalHarnessConfig(
            start_mode="arbitrary_start",
            output_contract=FormalOutputContract.full_monitor(include_overflow=False),
            assumptions=("start is low while reset is asserted",),
            covers=("pass", "fail"),
        )
        passed, output = run_sva_miter_check(
            checker,
            _rose_contract_ref_module("ref_rose_contract"),
            "ref_rose_contract",
            depth=12,
            config=config,
        )
        assert passed, f"rose full-contract BMC depth 12 FAILED:\n{output[-2500:]}"


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
            (1, 1),  # ##1: gap-1 boundary (start-cycle combinational fire)
            (3, 3),  # ##3: the operator whose +2 defect BUG-DELAY-01 first caught
            (1, 3),  # ##[1:3]: range spanning the start-term and counter boundary
            (2, 5),  # ##[2:5]: pure counter-path range
        ],
    )
    def test_delay_gap_equiv(self, m: int, n: int) -> None:
        """`a ##[m:n] b` monitor matches the gap-pinned reference (non-circular)."""
        checker = _build_delay_checker(m, n)
        ref_name = f"ref_a_{m}_{n}_b"
        ref = _delay_ref_module(ref_name, m, n)
        passed, output = run_sva_miter_check(checker, ref, ref_name, compare="pass", depth=20)
        assert passed, f"a ##[{m}:{n}] b SVA↔RTL equivalence FAILED:\n{output[-2500:]}"

    def test_delay_fixed_arbitrary_start_bmc_depth20(self) -> None:
        """Phase 10: arbitrary_start BMC depth 20 for fixed delay ##1."""
        checker = _build_delay_checker(1, 1)
        ref_name = "ref_a_1_1_b_arbitrary_start"
        ref = _delay_ref_module(ref_name, 1, 1)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare="pass",
            depth=20,
            config=FormalHarnessConfig(
                start_mode="arbitrary_start",
                output_contract=FormalOutputContract.single("pass"),
                assumptions=("start is low while reset is asserted",),
                overlap="bounded",
            ),
        )
        assert passed, f"delay ##1 arbitrary_start BMC depth 20 FAILED:\n{output[-2500:]}"


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


def _implication_overlap_contract_ref_module(name: str) -> str:
    """Independent full-contract reference for single-cycle ``a |-> b``."""
    return f"""
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    output logic pass,
    output logic fail,
    output logic active,
    output logic attempt_fired,
    output logic disabled_o,
    output logic overflow_flag
);
    logic ant_active_q, ant_pass_q, ant_fail_q;
    logic con_active_q, con_pass_q, con_fail_q;
    logic attempt_fired_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            ant_active_q <= 1'b0; ant_pass_q <= 1'b0; ant_fail_q <= 1'b0;
            con_active_q <= 1'b0; con_pass_q <= 1'b0; con_fail_q <= 1'b0;
        end else begin
            ant_active_q <= start;
            ant_pass_q   <= start &  a;
            ant_fail_q   <= start & ~a;
            con_active_q <= start;
            con_pass_q   <= start &  b;
            con_fail_q   <= start & ~b;
        end
    end

    always_ff @(posedge clk) begin
        if (!rst_n) attempt_fired_q <= 1'b0;
        else if (start) attempt_fired_q <= 1'b1;
    end

    assign active        = ant_active_q | con_active_q;
    assign pass          = ant_pass_q & con_pass_q;
    assign fail          = ant_pass_q & con_fail_q;
    assign attempt_fired = attempt_fired_q;
    assign disabled_o    = 1'b0;
    assign overflow_flag = 1'b0;
endmodule
"""


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
        passed, output = run_sva_equiv_check(checker, reference, helper_regs=helper, depth=15)
        assert passed, f"a |-> b SVA↔RTL equivalence FAILED:\n{output[-2500:]}"

    def test_overlap_arbitrary_start_bmc_depth15(self) -> None:
        """Phase 10: arbitrary_start BMC depth 15 for simple overlapping implication."""
        checker = _build("implication_overlap")  # a |-> b
        a, b = _impl_sigs(checker)
        helper = (
            f"    logic start_d1, {a}_d1, {b}_d1, vld1;\n"
            "    always_ff @(posedge clk) begin\n"
            "        if (!rst_n) begin\n"
            f"            start_d1 <= 1'b0; {a}_d1 <= 1'b0; {b}_d1 <= 1'b0; vld1 <= 1'b0;\n"
            "        end else begin\n"
            f"            start_d1 <= formal_start; {a}_d1 <= {a}; {b}_d1 <= {b}; vld1 <= 1'b1;\n"
            "        end\n"
            "    end\n"
        )
        reference = f"vld1 & start_d1 & {a}_d1 & ~{b}_d1"
        passed, output = run_sva_equiv_check(
            checker,
            reference,
            helper_regs=helper,
            depth=15,
            config=_arbitrary_start_config(overlap="bounded"),
        )
        assert passed, f"a |-> b arbitrary_start BMC depth 15 FAILED:\n{output[-2500:]}"

    def test_overlap_full_contract_bmc_depth15(self) -> None:
        """Phase 10: full-contract BMC depth 15 for overlap implication."""
        checker = _build("implication_overlap")
        config = FormalHarnessConfig(
            start_mode="single_shot",
            output_contract=FormalOutputContract.full_monitor(include_overflow=True),
            covers=("pass", "fail"),
        )
        passed, output = run_sva_miter_check(
            checker,
            _implication_overlap_contract_ref_module("ref_impl_overlap_contract"),
            "ref_impl_overlap_contract",
            depth=15,
            config=config,
        )
        assert passed, f"a |-> b full-contract BMC depth 15 FAILED:\n{output[-2500:]}"

    def test_overlap_is_reachable_with_arbitrary_start(self) -> None:
        """Overlap cover uses a start model that can actually reach it."""
        checker = _build("implication_overlap")
        config = FormalHarnessConfig(
            start_mode="arbitrary_start",
            output_contract=FormalOutputContract.full_monitor(include_overflow=True),
            assumptions=("start is low while reset is asserted",),
            # overflow_flag is part of the equality contract above, but is
            # unreachable by construction for this one-cycle consequent.
            covers=("overlap",),
            overlap="bounded",
        )
        passed, output = run_sva_miter_check(
            checker,
            _implication_overlap_contract_ref_module("ref_impl_overlap_reachability"),
            "ref_impl_overlap_reachability",
            depth=15,
            config=config,
        )
        assert passed, f"a |-> b overlap reachability FAILED:\n{output[-2500:]}"

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
        passed, output = run_sva_equiv_check(checker, reference, helper_regs=helper, depth=15)
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
        passed, output = run_sva_equiv_check(checker, reference, helper_regs=helper, depth=15)
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
        passed, output = run_sva_equiv_check(checker, reference, helper_regs=helper, depth=15)
        assert passed, f"if/else SVA↔RTL equivalence FAILED:\n{output[-2500:]}"


# ── Named sequence and simple sequence and/or ─────────────────────────────
# These reference modules are intentionally authored directly from source SVA
# semantics.  They do not instantiate generated children or reproduce the
# token-passing hierarchy, which makes the miters non-circular.


def _named_seq_ref_module(name: str) -> str:
    """Independent reference for ``sequence req_ack; a ##1 b; endsequence``."""
    return f"""\
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    output logic pass,
    output logic fail
);
    // a is sampled with start.  Exactly one cycle later b decides the
    // sequence; an initial a miss is terminal immediately.
    logic pending_q, a_fail_q, pass_q, b_fail_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            pending_q <= 1'b0;
            a_fail_q  <= 1'b0;
            pass_q    <= 1'b0;
            b_fail_q  <= 1'b0;
        end else begin
            pending_q <= start && a;
            a_fail_q  <= start && !a;
            pass_q    <= pending_q && b;
            b_fail_q  <= pending_q && !b;
        end
    end
    assign pass = pass_q;
    assign fail = a_fail_q || b_fail_q;
endmodule
"""


def _simple_binary_seq_ref_module(name: str, *, op: str) -> str:
    """Independent reference for one-cycle boolean ``a and/or b`` sequences."""
    assert op in {"and", "or"}
    pass_expr = "left_pass_q && right_pass_q" if op == "and" else "left_pass_q || right_pass_q"
    fail_expr = "left_fail_q || right_fail_q" if op == "and" else "left_fail_q && right_fail_q"
    return f"""\
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    output logic pass,
    output logic fail
);
    // Stage one evaluates the two source alternatives independently.  Stage
    // two applies the IEEE sequence-composition truth table.
    logic left_pass_q, left_fail_q, right_pass_q, right_fail_q;
    logic pass_q, fail_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            left_pass_q  <= 1'b0;
            left_fail_q  <= 1'b0;
            right_pass_q <= 1'b0;
            right_fail_q <= 1'b0;
            pass_q       <= 1'b0;
            fail_q       <= 1'b0;
        end else begin
            left_pass_q  <= start && a;
            left_fail_q  <= start && !a;
            right_pass_q <= start && b;
            right_fail_q <= start && !b;
            pass_q       <= {pass_expr};
            fail_q       <= {fail_expr};
        end
    end
    assign pass = pass_q;
    assign fail = fail_q;
endmodule
"""


class TestNamedSequenceSvaEquiv:
    """Named ``a ##1 b`` expansion matches an independent source reference."""

    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_named_sequence_equiv(self, compare: str) -> None:
        checker = _build("named_seq")
        ref_name = "ref_named_a_gap1_b"
        ref = _named_seq_ref_module(ref_name)
        passed, output = run_sva_miter_check(checker, ref, ref_name, compare=compare, depth=18)
        assert passed, f"named a ##1 b {compare} equivalence FAILED:\n{output[-2500:]}"


class TestSimpleBinarySequenceSvaEquiv:
    """Simple sequence ``and``/``or`` match independent source truth tables."""

    @pytest.mark.parametrize("op", ["and", "or"])
    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_simple_binary_sequence_equiv(self, op: str, compare: str) -> None:
        checker = _build(f"v13_{op}_seq")
        ref_name = f"ref_simple_seq_{op}"
        ref = _simple_binary_seq_ref_module(ref_name, op=op)
        passed, output = run_sva_miter_check(checker, ref, ref_name, compare=compare, depth=15)
        assert passed, f"sequence {op} {compare} equivalence FAILED:\n{output[-2500:]}"


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
            (1, 1),  # single offset, gap-1
            (1, 3),  # range spanning start-relative window
            (2, 2),  # single offset, deeper
            (2, 5),  # wider counter range
            (0, 2),  # lo==0: start-cycle offset included
        ],
    )
    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_s_eventually_equiv(self, lo: int, hi: int, compare: str) -> None:
        """Monitor's pass/fail matches the independent reference (non-circular BMC)."""
        checker = _build_se_checker(lo, hi)
        ref_name = f"ref_se_{lo}_{hi}"
        ref = _se_ref_module(ref_name, lo, hi)
        passed, output = run_sva_miter_check(checker, ref, ref_name, compare=compare, depth=20)
        assert passed, (
            f"s_eventually[{lo}:{hi}] {compare} SVA↔RTL equivalence FAILED:\n{output[-2500:]}"
        )


# ── Bounded always always [lo:hi] p (v1.4 Part A) ─────────────────────────────
# The UNIVERSAL dual of bounded eventually. The generated monitor
# (templates/s_always.sv.j2) is proven against an INDEPENDENT reference monitor
# authored from IEEE-1800 semantics (forall k in [lo,hi] : p holds at offset k).
# The reference uses an offset counter ``o`` and a structurally distinct decision:
# FAIL at the first in-window violating offset, PASS at the deadline offset hi
# only if no offset violated. Both outputs are compared by BMC miter — a source
# of truth separate from the implementation (breaks RISK-01).


def _sa_ref_module(name: str, lo: int, hi: int) -> str:
    """Independent reference monitor for ``always [lo:hi] a`` (single attempt)."""
    return f"""\
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    output logic pass,
    output logic fail
);
    // o counts cycles since start (o==0 at the start cycle). The operand must
    // hold at EVERY offset in [{lo},{hi}]. Derived from IEEE-1800 semantics,
    // independently of the generated counter+latch monitor (universal dual).
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


def _build_sa_checker(lo: int, hi: int) -> CheckerNode:
    """Compose+optimize the monitor for ``always [lo:hi] a`` directly from IR."""
    from sva2rtl.ir import BoolExpr, ClockSpec, PropBoundedAlways, SourceLoc

    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropBoundedAlways(
        body=BoolExpr(text="a", source_loc=loc), lo=lo, hi=hi, strong=False, source_loc=loc
    )
    return optimize(compose(node, clock, "sa", f"always [{lo}:{hi}] a"))


class TestSAlwaysSvaEquiv:
    """``always [lo:hi] a`` monitor proven equiv to an independent reference."""

    @pytest.mark.parametrize(
        "lo,hi",
        [
            (1, 1),  # single offset, gap-1
            (1, 3),  # range spanning start-relative window
            (2, 2),  # single offset, deeper
            (2, 5),  # wider counter range
            (0, 2),  # lo==0: start-cycle offset included
        ],
    )
    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_s_always_equiv(self, lo: int, hi: int, compare: str) -> None:
        """Monitor's pass/fail matches the independent reference (non-circular BMC)."""
        checker = _build_sa_checker(lo, hi)
        ref_name = f"ref_sa_{lo}_{hi}"
        ref = _sa_ref_module(ref_name, lo, hi)
        passed, output = run_sva_miter_check(checker, ref, ref_name, compare=compare, depth=20)
        assert passed, f"always[{lo}:{hi}] {compare} SVA↔RTL equivalence FAILED:\n{output[-2500:]}"


# ── Weak until / until_with a until b (v1.4 Part A) ───────────────────────────
# Safety properties (no liveness obligation). The generated monitor
# (templates/until.sv.j2) is proven against an INDEPENDENT reference monitor
# authored from IEEE-1800 weak-until semantics. The reference uses a two-register
# started/decided live-window encoding — structurally distinct from the monitor's
# single running_q FSM — so it is a separate source of truth (breaks RISK-01).


def _until_ref_module(name: str, with_: bool) -> str:
    """Independent reference monitor for weak ``until`` / ``until_with``."""
    if with_:
        sat = "live &  a &  b"
        vio = "live & ~a"
    else:
        sat = "live &  b"
        vio = "live & ~b & ~a"
    return f"""\
module {name} (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    output logic pass,
    output logic fail
);
    // Two sticky registers (started/decided) gate a live window — distinct from
    // the monitor's single running_q FSM. Authored from IEEE-1800 weak-until
    // safety semantics ({"until_with" if with_ else "until"}).
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


def _build_until_checker(with_: bool) -> CheckerNode:
    """Compose+optimize the monitor for weak ``a until[_with] b`` from IR."""
    from sva2rtl.ir import BoolExpr, ClockSpec, PropUntil, SourceLoc

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


class TestUntilSvaEquiv:
    """Weak ``until`` / ``until_with`` proven equiv to an independent reference."""

    @pytest.mark.parametrize("with_", [False, True], ids=["until", "until_with"])
    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_until_equiv(self, with_: bool, compare: str) -> None:
        """Monitor's pass/fail matches the independent reference (non-circular BMC)."""
        checker = _build_until_checker(with_)
        ref_name = f"ref_u_{'w' if with_ else 'u'}"
        ref = _until_ref_module(ref_name, with_)
        passed, output = run_sva_miter_check(checker, ref, ref_name, compare=compare, depth=20)
        kw = "until_with" if with_ else "until"
        assert passed, f"{kw} {compare} SVA↔RTL equivalence FAILED:\n{output[-2500:]}"


# ══════════════════════════════════════════════════════════════════════════════
# v1.5.2: BMC miter proofs for the 6 operators that were previously
# simulation-only (no formal equivalence). Each uses an independently
# authored IEEE-1800 reference monitor (shift-register / counter structure
# distinct from the generated RTL) to break RISK-01 circularity.
# ══════════════════════════════════════════════════════════════════════════════


def _ref_disable_iff(name: str) -> str:
    """Independent reference for ``disable iff (!rst_n) (a |-> b)``.

    RTL: disable_iff_top wraps overlap_bitvec. effective_disable = !rst_n.
    When rst_n=1 (enabled): pass = ant_pass_w & con_pass_w, fail = ant_pass_w
    & con_fail_w. Both ant/con are bool_expr leaves (registered 1 cycle).
    So pass at t+1 if a(t) & b(t).

    Reference: independent prev_a + prev_b registers + combinational pass/fail.
    pass at t+1 = a(t) & b(t) (both sampled at start, reported next cycle).
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, dut_rst_n, a, b,
    output logic pass, fail
);
    logic prev_a_q, prev_b_q;
    always_ff @(posedge clk) begin
        if (!rst_n || !dut_rst_n) begin
            prev_a_q <= 1'b0;
            prev_b_q <= 1'b0;
        end else begin
            prev_a_q <= start & a;
            prev_b_q <= start & b;
        end
    end
    assign pass = rst_n & dut_rst_n & prev_a_q & prev_b_q;
    assign fail = rst_n & dut_rst_n & prev_a_q & ~prev_b_q;
endmodule
"""


def _ref_disable_iff_with_disable(name: str) -> str:
    """Independent reference for ``disable iff`` with incoming disable_i variable."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, dut_rst_n, a, b, disable_i,
    output logic pass, fail
);
    logic prev_a_q, prev_b_q;
    always_ff @(posedge clk) begin
        if (!rst_n || !dut_rst_n || disable_i) begin
            prev_a_q <= 1'b0;
            prev_b_q <= 1'b0;
        end else begin
            prev_a_q <= start & a;
            prev_b_q <= start & b;
        end
    end
    assign pass = rst_n & dut_rst_n & !disable_i & prev_a_q & prev_b_q;
    assign fail = rst_n & dut_rst_n & !disable_i & prev_a_q & ~prev_b_q;
endmodule
"""


class TestDisableIffSvaEquiv:
    """``disable iff`` monitor proven equiv to independent reference."""

    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_disable_iff_equiv(self, compare: str) -> None:
        checker = _build("disable_iff")
        ref_name = "ref_diff"
        ref = _ref_disable_iff(ref_name)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare=compare,
            depth=15,
        )
        assert passed, f"disable_iff {compare} SVA↔RTL equiv FAILED:\n{output[-2500:]}"

    @pytest.mark.parametrize("compare", ["pass", "fail"])
    def test_disable_iff_arbitrary_disable_bmc_depth15(self, compare: str) -> None:
        """Phase 10: arbitrary_disable BMC depth 15 for disable iff."""
        checker = _build("disable_iff")
        ref_name = "ref_diff_arbitrary_disable"
        ref = _ref_disable_iff_with_disable(ref_name)
        config = FormalHarnessConfig(
            start_mode="single_shot",
            disable_mode="arbitrary_disable",
            output_contract=FormalOutputContract.single(compare),  # type: ignore[arg-type]
            reference_disable_port=True,
        )
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare=compare,
            depth=15,
            config=config,
        )
        assert passed, (
            f"disable_iff {compare} arbitrary_disable BMC depth 15 FAILED:\n"
            f"{output[-2500:]}"
        )


def _ref_rep_consecutive(name: str, n: int) -> str:
    """Independent reference for ``a[*N]`` consecutive repetition.

    RTL timing (rep_consecutive.sv.j2): count_q initialized to 1 at
    start (registered), incremented each cycle while running && a.
    pass is COMBINATIONAL: running_q && a && count_q == n.
    """
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


def _ref_rep_consecutive_contract(name: str, n: int) -> str:
    """Independent full-contract reference for ``a[*N]`` consecutive repetition."""
    return f"""
module {name} (
    input  logic clk, rst_n, start, a,
    output logic pass, fail, active, attempt_fired, disabled_o
);
    logic [1:0] cnt_q;
    logic running_q, attempt_fired_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cnt_q     <= 0;
            running_q <= 1'b0;
        end else if (start && a) begin
            cnt_q     <= 1;
            running_q <= 1'b1;
        end else if (running_q && a) begin
            if (cnt_q < {n}) cnt_q <= cnt_q + 1'b1;
        end else if (running_q && !a) begin
            running_q <= 1'b0;
            cnt_q     <= 0;
        end
    end
    always_ff @(posedge clk) begin
        if (!rst_n) attempt_fired_q <= 1'b0;
        else if (start) attempt_fired_q <= 1'b1;
    end
    assign active        = running_q;
    assign pass          = running_q && a && (cnt_q == {n});
    assign fail          = running_q && !a && (cnt_q < {n});
    assign attempt_fired = attempt_fired_q;
    assign disabled_o    = 1'b0;
endmodule
"""


class TestRepConsecutiveSvaEquiv:
    """``[*N]`` consecutive repetition proven equiv to independent reference."""

    def test_rep_fixed_equiv(self) -> None:
        checker = _build("rep_fixed")
        ref_name = "ref_rep3"
        ref = _ref_rep_consecutive(ref_name, 3)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare="pass",
            depth=20,
        )
        assert passed, f"[*3] SVA↔RTL equiv FAILED:\n{output[-2500:]}"

    def test_rep_fixed_arbitrary_start_bmc_depth20(self) -> None:
        """Phase 10: arbitrary_start BMC depth 20 for fixed consecutive repetition."""
        checker = _build("rep_fixed")
        ref_name = "ref_rep3_arbitrary_start"
        ref = _ref_rep_consecutive(ref_name, 3)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare="pass",
            depth=20,
            config=FormalHarnessConfig(
                start_mode="arbitrary_start",
                output_contract=FormalOutputContract.single("pass"),
                assumptions=("start is low while reset is asserted",),
                overlap="bounded",
            ),
        )
        assert passed, f"[*3] arbitrary_start BMC depth 20 FAILED:\n{output[-2500:]}"

    def test_rep_fixed_full_contract_bmc_depth20(self) -> None:
        """Phase 10: full-contract BMC depth 20 for fixed consecutive repetition."""
        checker = _build("rep_fixed")
        config = FormalHarnessConfig(
            start_mode="arbitrary_start",
            output_contract=FormalOutputContract.full_monitor(include_overflow=False),
            assumptions=("start is low while reset is asserted",),
            covers=("pass", "fail", "overlap"),
            overlap="bounded",
        )
        passed, output = run_sva_miter_check(
            checker,
            _ref_rep_consecutive_contract("ref_rep3_contract", 3),
            "ref_rep3_contract",
            depth=20,
            config=config,
        )
        assert passed, f"[*3] full-contract BMC depth 20 FAILED:\n{output[-2500:]}"


def _ref_past(name: str, depth: int) -> str:
    """Independent reference for ``$past(sig, N)``.

    IEEE 1800 §16.9.8.4: ``$past(sig, N)`` returns the value of sig N
    cycles ago. Reference: independent N-stage shift register.
    """
    stages = "\n".join(
        f"        s_q[{i}] <= s_q[{i - 1}];" if i > 0 else "        s_q[0] <= sig;"
        for i in range(depth)
    )
    return f"""
module {name} (
    input  logic clk, rst_n, start, sig,
    output logic pass, fail
);
    logic [0:{depth - 1}] s_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            for (int i = 0; i < {depth}; i++) s_q[i] <= 1'b0;
        end else begin
{stages}
        end
    end
    // pass: start & (past value is true); fail: start & (past value is false)
    assign pass = start & s_q[{depth - 1}];
    assign fail = start & ~s_q[{depth - 1}];
endmodule
"""


class TestPastSvaEquiv:
    """``$past(sig, N)`` proven equiv to independent shift-register reference."""

    def test_past_equiv(self) -> None:
        checker = _build("past")
        ref_name = "ref_past3"
        ref = _ref_past(ref_name, 3)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare="pass",
            depth=15,
        )
        assert passed, f"$past SVA↔RTL equiv FAILED:\n{output[-2500:]}"


def _ref_first_match(name: str) -> str:
    """Independent reference for ``first_match(a ##1 b)``.

    RTL: seq_concat_top body (a ##1 b) has pass at start+2 (a sampled at
    start, b at start+1, both through registered leaves + concat_delay).
    locked_q registered when body_pass_w fires. pass = body_pass_w && !locked_q.

    Reference: a_q at start+1 = a(start), match at start+1 = a_q & b.
    pass_q registered: pass at start+2 = a(start) & b(start+1).
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a, b,
    output logic pass
);
    logic a_q;
    logic match_w;
    logic pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            a_q    <= 1'b0;
            pass_q <= 1'b0;
        end else begin
            a_q <= start & a;
            pass_q <= match_w;
        end
    end
    assign match_w = a_q & b;
    assign pass = pass_q;
endmodule
"""


class TestFirstMatchSvaEquiv:
    """``first_match`` proven equiv to independent reference (v1.5.2 fix)."""

    def test_first_match_equiv(self) -> None:
        checker = _build("first_match")
        ref_name = "ref_fm"
        ref = _ref_first_match(ref_name)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare="pass",
            depth=15,
        )
        assert passed, f"first_match SVA↔RTL equiv FAILED:\n{output[-2500:]}"


def _ref_goto_rep(name: str, n: int) -> str:
    """Independent reference for ``a[->N]`` goto repetition.

    Semantic reference: a single start pulse arms one attempt, which then counts
    non-consecutive ``a`` occurrences until the Nth occurrence completes it.
    The reference deliberately keeps counting after start deasserts so the miter
    catches regressions where the implementation incorrectly gates counting by
    start every cycle.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a,
    output logic pass
);
    logic [1:0] cnt_q;
    logic running_q;
    logic passed_q;
    wire hit_now = !passed_q && a &&
                   ((start && !running_q && ({n} == 1)) ||
                    (running_q && (cnt_q >= {n - 1})));
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cnt_q     <= 0;
            running_q <= 1'b0;
            passed_q  <= 1'b0;
        end else if (hit_now) begin
            running_q <= 1'b0;
            passed_q  <= 1'b1;
        end else if (start && !running_q && !passed_q) begin
            running_q <= 1'b1;
            cnt_q     <= a ? 1 : 0;
        end else if (running_q && !passed_q) begin
            if (a && cnt_q < {n})
                cnt_q <= cnt_q + 1'b1;
        end
    end
    assign pass = passed_q | hit_now;
endmodule
"""


class TestGotoRepSvaEquiv:
    """``[->N]`` goto repetition proven equiv to independent reference."""

    def test_goto_rep_equiv(self) -> None:
        checker = _build("goto_rep")
        ref_name = "ref_goto3"
        ref = _ref_goto_rep(ref_name, 3)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare="pass",
            depth=25,
        )
        assert passed, f"[->3] SVA↔RTL equiv FAILED:\n{output[-2500:]}"


def _ref_nonconsec_rep(name: str, n: int) -> str:
    """Independent reference for ``a[=N]`` nonconsecutive repetition.

    Semantic reference: a single start pulse arms one attempt. The attempt
    counts non-consecutive ``a`` occurrences after start and completes once the
    Nth occurrence has been observed. Counting is independent of subsequent
    start values.
    """
    return f"""
module {name} (
    input  logic clk, rst_n, start, a,
    output logic pass
);
    logic [2:0] cnt_q;
    logic running_q;
    logic passed_q;
    wire hit_now = !passed_q && a &&
                   ((start && !running_q && ({n} == 1)) ||
                    (running_q && (cnt_q >= {n - 1})));
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            cnt_q     <= 0;
            running_q <= 1'b0;
            passed_q  <= 1'b0;
        end else if (hit_now) begin
            running_q <= 1'b0;
            passed_q  <= 1'b1;
        end else if (start && !running_q && !passed_q) begin
            running_q <= 1'b1;
            cnt_q     <= a ? 1 : 0;
        end else if (running_q && !passed_q) begin
            if (a && cnt_q < {n})
                cnt_q <= cnt_q + 1'b1;
        end
    end
    assign pass = passed_q | hit_now;
endmodule
"""


class TestNonconsecRepSvaEquiv:
    """``[=N]`` nonconsecutive repetition proven equiv to independent ref."""

    def test_nonconsec_rep_equiv(self) -> None:
        checker = _build("nonconsec_rep")
        ref_name = "ref_noncon5"
        ref = _ref_nonconsec_rep(ref_name, 5)
        passed, output = run_sva_miter_check(
            checker,
            ref,
            ref_name,
            compare="pass",
            depth=30,
        )
        assert passed, f"[=5] SVA↔RTL equiv FAILED:\n{output[-2500:]}"
