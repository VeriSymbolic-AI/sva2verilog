"""Template-level formal equivalence tests (Phase 1, Plan 1-3 — FORMAL-03).

For each of the 11 checker templates, a dedicated formal test proves that
the template produces equivalent RTL with and without the optimizer.

Templates tested (via fixture JSON files):
  - bool_expr         — Boolean expression leaf  (bool_simple.json)
  - concat_delay      — Fixed/range delay counter (delay_fixed.json, delay_range.json)
  - overlap_bitvec    — Overlapping implication   (implication_overlap.json)
  - nonoverlap        — Non-overlapping implication (implication_nonoverlap.json)
  - disable_iff_top   — disable iff gating wrapper (disable_iff.json)
  - seq_concat_top    — Sequence concatenation     (named_seq.json, delay_three_element.json)
  - rose              — $rose() sampled value      (rose.json)
  - fell              — $fell() sampled value      (fell.json)
  - stable            — $stable() sampled value    (stable.json)
  - past              — $past() sampled value      (past.json)
  - rep_consecutive   — Consecutive repetition     (rep_fixed.json, rep_range.json)

When yosys is not installed, all tests are skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.formal import _yosys_is_available, check_optimizer_pass
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

pytestmark = [
    pytest.mark.formal,
    pytest.mark.skipif(
        not _yosys_is_available(),
        reason="yosys not found on PATH — formal verification disabled",
    ),
]

_FIXTURES = Path(__file__).parent / "fixtures"


def _build_from_fixture(name: str, *, optimize_flag: bool = True) -> CheckerNode:
    """Load a fixture JSON, compile to CheckerNode with/without optimization."""
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, original_text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, original_text)
    if optimize_flag:
        checker = optimize(checker)
    return checker


def _check_fixture_equiv(name: str) -> tuple[bool, str]:
    """Compile a fixture with and without optimization, then check equivalence."""
    unopt = _build_from_fixture(name, optimize_flag=False)
    opt = _build_from_fixture(name, optimize_flag=True)
    return check_optimizer_pass(unopt, opt)


# ── bool_expr template ─────────────────────────────────────────────────────


class TestBoolExprTemplate:
    """Verify bool_expr template equivalence under optimization."""

    def test_simple_boolean(self) -> None:
        """Simple boolean assertion is equivalent under optimization."""
        passed, output = _check_fixture_equiv("bool_simple")
        assert passed, f"bool_expr FAILED:\n{output}"

    def test_complex_boolean(self) -> None:
        """Complex boolean assertion is equivalent under optimization."""
        passed, output = _check_fixture_equiv("bool_complex")
        assert passed, f"bool_expr complex FAILED:\n{output}"

    def test_labeled_boolean(self) -> None:
        """Labeled boolean assertion is equivalent under optimization."""
        passed, output = _check_fixture_equiv("bool_labeled")
        assert passed, f"bool_expr labeled FAILED:\n{output}"


# ── concat_delay template ─────────────────────────────────────────────────


class TestConcatDelayTemplate:
    """Verify concat_delay template equivalence under optimization."""

    def test_fixed_delay(self) -> None:
        """Fixed delay (##3) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("delay_fixed")
        assert passed, f"concat_delay fixed FAILED:\n{output}"

    def test_range_delay(self) -> None:
        """Range delay (##[2:5]) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("delay_range")
        assert passed, f"concat_delay range FAILED:\n{output}"

    def test_zero_delay(self) -> None:
        """Zero delay (##0) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("delay_zero")
        assert passed, f"concat_delay zero FAILED:\n{output}"


# ── overlap_bitvec template ───────────────────────────────────────────────


class TestOverlapBitvecTemplate:
    """Verify overlap_bitvec template (|->) equivalence under optimization."""

    def test_overlap_implication(self) -> None:
        """Overlapping implication (a |-> b) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("implication_overlap")
        assert passed, f"overlap_bitvec FAILED:\n{output}"

    def test_implication_bitvec_accepted_via_nfa(self) -> None:
        """`a |-> a ##[2:5] b` (BV_WIDTH>1 ranged-delay consequent) compiles via NFA.

        The legacy bv_q path for multi-cycle sequence consequents was a
        confirmed correctness defect (BUG-IMPL-01) and was previously
        rejected. Since v1.7 LANG-03, ranged-delay consequents are
        NFA-liftable, so this now compiles through the NFA composition
        engine instead of raising. The BoolExpr antecedent ``a`` is
        handled combinationally as the NFA start guard.
        """
        checker = _build_from_fixture("implication_bitvec")
        assert checker is not None
        assert checker.template_name == "implication_nfa"


# ── nonoverlap template ───────────────────────────────────────────────────


class TestNonoverlapTemplate:
    """Verify nonoverlap template (|=>) equivalence under optimization."""

    def test_nonoverlap_implication(self) -> None:
        """Non-overlapping implication (a |=> b) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("implication_nonoverlap")
        assert passed, f"nonoverlap FAILED:\n{output}"


# ── disable_iff_top template ──────────────────────────────────────────────


class TestDisableIffTopTemplate:
    """Verify disable_iff_top template equivalence under optimization."""

    def test_disable_iff(self) -> None:
        """disable iff wrapped implication is equivalent under optimization."""
        passed, output = _check_fixture_equiv("disable_iff")
        assert passed, f"disable_iff_top FAILED:\n{output}"


# ── seq_concat_top template ───────────────────────────────────────────────


class TestSeqConcatTopTemplate:
    """Verify seq_concat_top template equivalence under optimization."""

    def test_named_seq(self) -> None:
        """Named sequence (a ##1 b) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("named_seq")
        assert passed, f"seq_concat_top named FAILED:\n{output}"

    def test_three_element_seq(self) -> None:
        """Three-element sequence (a ##1 b ##2 c) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("delay_three_element")
        assert passed, f"seq_concat_top 3-elem FAILED:\n{output}"


# ── rose template ─────────────────────────────────────────────────────────


class TestRoseTemplate:
    """Verify $rose template equivalence under optimization."""

    def test_rose(self) -> None:
        """$rose(sig) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("rose")
        assert passed, f"$rose FAILED:\n{output}"


# ── fell template ─────────────────────────────────────────────────────────


class TestFellTemplate:
    """Verify $fell template equivalence under optimization."""

    def test_fell(self) -> None:
        """$fell(sig) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("fell")
        assert passed, f"$fell FAILED:\n{output}"


# ── stable template ───────────────────────────────────────────────────────


class TestStableTemplate:
    """Verify $stable template equivalence under optimization."""

    def test_stable(self) -> None:
        """$stable(sig) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("stable")
        assert passed, f"$stable FAILED:\n{output}"


# ── past template ─────────────────────────────────────────────────────────


class TestPastTemplate:
    """Verify $past template equivalence under optimization."""

    def test_past(self) -> None:
        """$past(sig, N) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("past")
        assert passed, f"$past FAILED:\n{output}"


# ── rep_consecutive template ──────────────────────────────────────────────


class TestRepConsecutiveTemplate:
    """Verify rep_consecutive template equivalence under optimization."""

    def test_fixed_repetition(self) -> None:
        """Exact repetition [*N] is equivalent under optimization."""
        passed, output = _check_fixture_equiv("rep_fixed")
        assert passed, f"rep_consecutive fixed FAILED:\n{output}"

    def test_range_repetition(self) -> None:
        """Range repetition [*M:N] is equivalent under optimization."""
        passed, output = _check_fixture_equiv("rep_range")
        assert passed, f"rep_consecutive range FAILED:\n{output}"


# ═══════════════════════════════════════════════════════════════════════════════
# v1.3 Tier 2 operator templates (7 new templates)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPropOrTemplate:
    """Verify prop_or template equivalence under optimization."""

    def test_seq_or(self) -> None:
        """a or b is equivalent under optimization."""
        passed, output = _check_fixture_equiv("v13_or_seq")
        assert passed, f"prop_or FAILED:\n{output}"


class TestPropAndTemplate:
    """Verify prop_and template equivalence under optimization."""

    def test_seq_and(self) -> None:
        """a and b is equivalent under optimization."""
        passed, output = _check_fixture_equiv("v13_and_seq")
        assert passed, f"prop_and FAILED:\n{output}"


class TestPropIntersectTemplate:
    """Verify prop_intersect template equivalence under optimization."""

    def test_seq_intersect(self) -> None:
        """a intersect b is equivalent under optimization."""
        passed, output = _check_fixture_equiv("v13_intersect_seq")
        assert passed, f"prop_intersect FAILED:\n{output}"


class TestPropNotTemplate:
    """Verify prop_not template equivalence under optimization."""

    def test_prop_not(self) -> None:
        """not (a) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("v13_prop_not")
        assert passed, f"prop_not FAILED:\n{output}"


class TestPropThroughoutTemplate:
    """Verify prop_throughout template equivalence under optimization."""

    def test_seq_throughout(self) -> None:
        """en throughout (a ##1 a) is equivalent under optimization."""
        passed, output = _check_fixture_equiv("v13_throughout_seq")
        assert passed, f"prop_throughout FAILED:\n{output}"


class TestPropIfElseTemplate:
    """Verify prop_if_else template equivalence under optimization."""

    def test_if_else(self) -> None:
        """if (sel) a else b is equivalent under optimization."""
        passed, output = _check_fixture_equiv("v13_if_else_prop")
        assert passed, f"prop_if_else FAILED:\n{output}"
