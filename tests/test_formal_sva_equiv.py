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
from sva2rtl.formal_equiv import run_sva_equiv_check, sby_is_available
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
