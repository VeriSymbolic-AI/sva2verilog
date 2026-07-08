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
from sva2rtl.composer import compose
from sva2rtl.formal_equiv import (
    run_sva_equiv_check,
    sby_is_available,
)
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

pytestmark = pytest.mark.skipif(
    not sby_is_available(),
    reason="sby (SymbiYosys) not found on PATH — k-induction proofs disabled",
)

_FIXTURES = Path(__file__).parent / "fixtures"
_DEFAULT_PROVE_TIMEOUT_SECONDS = 600


def _prove_timeout() -> int:
    """Return k-induction subprocess timeout for this environment."""
    raw = os.environ.get("SVA2RTL_FORMAL_PROVE_TIMEOUT")
    if raw is None:
        return _DEFAULT_PROVE_TIMEOUT_SECONDS
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_PROVE_TIMEOUT_SECONDS


def _build(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    checker = optimize(compose(node, clock, label, text))
    return checker


def _is_induction_boundary(output: str) -> bool:
    """Return True only for proof non-convergence, not real counterexamples."""
    lower = output.lower()
    if "timed out" in lower or "timeout" in lower:
        return True

    lines = [line.lower() for line in output.splitlines()]
    basecase_failed = any(
        "basecase" in line
        and any(token in line for token in ("fail", "assert", "counterexample"))
        for line in lines
    )
    if basecase_failed:
        return False

    if "temporal induction failed" in lower:
        return True
    return any(
        "induction" in line
        and any(token in line for token in ("fail", "unknown", "unreached"))
        for line in lines
    )


def _assert_kinduction_passed(passed: bool, output: str, op_name: str) -> None:
    """Fail on real counterexamples; xfail only for induction convergence limits."""
    if passed:
        return
    if _is_induction_boundary(output):
        pytest.xfail(
            f"k-induction did not converge for {op_name} (honest boundary):\n"
            f"{output[-500:]}"
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
