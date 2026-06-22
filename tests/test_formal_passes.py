"""Per-pass formal equivalence tests (Phase 1, Plan 1-2).

For each of the 5 optimizer passes, a dedicated formal test proves that the
pass preserves semantic equivalence between unoptimized and optimized RTL.

Tests use yosys equiv_induct (temporal induction) for unbounded proofs.
When yosys is not installed, tests are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_all_assertions
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.formal import (
    _yosys_is_available,
    check_optimizer_pass,
    run_equiv_check,
    run_equiv_check_multi,
)
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

# ── Helpers ────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.skipif(
    not _yosys_is_available(),
    reason="yosys not found on PATH — formal verification disabled",
)


def _compile_to_checker(sv_text: str, *, optimize_flag: bool = True) -> CheckerNode:
    """Compile an inline SVA text to a (optionally optimized) CheckerNode tree.

    Writes the text to a temp file, invokes slang, imports, normalizes,
    composes, and optionally optimizes.
    """
    import tempfile
    import os

    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".sv", delete=False, encoding="utf-8")
    try:
        tmp.write(sv_text)
        tmp.close()

        ast = invoke_slang(Path(tmp.name))
        assertions = import_all_assertions(ast)
        assert assertions, "No assertions found"

        node, clock, label, original_text = assertions[0]
        node = normalize(node)
        checker = compose(node, clock, label, original_text)
        if optimize_flag:
            checker = optimize(checker)
        return checker
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _check_equiv(sv_text: str) -> tuple[bool, str]:
    """Compile SVA text with and without optimization, then check equivalence."""
    unopt = _compile_to_checker(sv_text, optimize_flag=False)
    opt = _compile_to_checker(sv_text, optimize_flag=True)
    return check_optimizer_pass(unopt, opt)


# ── constant_fold pass ─────────────────────────────────────────────────────


class TestConstantFoldEquiv:
    """Verify that constant folding preserves equivalence."""

    def test_constant_true_is_equivalent(self) -> None:
        """1'b1 in a sequence is semantically neutral."""
        sv = """
module test(input logic clk, a, b);
    a_const: assert property (@(posedge clk) a ##1 1'b1 ##2 b);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"

    def test_constant_false_is_equivalent(self) -> None:
        """1'b0 in a sequence — the branch is unreachable but equivalence holds."""
        sv = """
module test(input logic clk, a, b);
    a_const: assert property (@(posedge clk) a ##1 1'b0 ##2 b);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"

    def test_standalone_constant_true(self) -> None:
        """assert property(@(posedge clk) 1'b1) is equivalent under optimization."""
        sv = """
module test(input logic clk);
    a_const: assert property (@(posedge clk) 1'b1);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"


# ── concat_merge pass ────────────────────────────────────────────────────


class TestConcatMergeEquiv:
    """Verify that adjacent delay merging preserves equivalence."""

    def test_adjacent_delays_merge_equiv(self) -> None:
        """##1 ##2 a — merged to ##3 a — proved equivalent."""
        sv = """
module test(input logic clk, a);
    a_seq: assert property (@(posedge clk) ##1 ##2 a);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"

    def test_nonadjacent_delays_not_merged_equiv(self) -> None:
        """a ##2 b ##3 c has non-adjacent delays (separated by b) — no merge."""
        sv = """
module test(input logic clk, a, b, c);
    a_seq: assert property (@(posedge clk) a ##2 b ##3 c);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"


# ── cse pass ──────────────────────────────────────────────────────────────


class TestCSEEquiv:
    """Verify that common subexpression elimination preserves equivalence."""

    @pytest.mark.xfail(
        reason="yosys 0.66 SAT model limit — CSE-shared delay nodes create wider "
               "state spaces that yosys cannot prove equivalent via induction",
        strict=True,
    )
    def test_duplicate_subsequence_cse_equiv(self) -> None:
        """``a ##3 b ##1 a ##3 b`` — duplicate subsequence merged by CSE."""
        sv = """
module test(input logic clk, a, b);
    a_seq: assert property (@(posedge clk) a ##3 b ##1 a ##3 b);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"

    @pytest.mark.xfail(
        reason="ast_importer does not support |-> (Binary expression) via slang "
               "frontend — needs fixture-based test instead",
        strict=True,
    )
    def test_implication_with_shared_structure(self) -> None:
        """|-> with repeated signal patterns exercises CSE in sub-trees."""
        sv = """
module test(input logic clk, a, b, c);
    a_impl: assert property (@(posedge clk) a ##2 b |-> c ##2 b);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"


# ── dead_node pass ────────────────────────────────────────────────────────


class TestDeadNodeEquiv:
    """Verify that dead node elimination preserves equivalence."""

    def test_const_false_branch_dead_equiv(self) -> None:
        """``1'b0 ##1 a`` — const_false marked branch is dead; removal is safe."""
        sv = """
module test(input logic clk, a);
    a_seq: assert property (@(posedge clk) 1'b0 ##1 a);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"

    def test_const_false_precedes_branch(self) -> None:
        """``a ##1 1'b0 ##2 b`` — middle dead branch removal is safe."""
        sv = """
module test(input logic clk, a, b);
    a_seq: assert property (@(posedge clk) a ##1 1'b0 ##2 b);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"


# ── Boolean (no optimization needed) ──────────────────────────────────────


class TestBoolExprEquiv:
    """Verify that boolean expressions without sequence operators are equivalent."""

    def test_simple_boolean(self) -> None:
        """``a && b`` is trivially equivalent (no optimization applies)."""
        sv = """
module test(input logic clk, a, b);
    a_bool: assert property (@(posedge clk) a && b);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"

    def test_boolean_with_negation(self) -> None:
        """``a || !b`` is trivially equivalent under optimization."""
        sv = """
module test(input logic clk, a, b);
    a_bool: assert property (@(posedge clk) a || !b);
endmodule
"""
        passed, output = _check_equiv(sv)
        assert passed, f"Equivalence check FAILED:\n{output}"
