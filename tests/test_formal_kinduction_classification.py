"""Regression tests for honest k-induction outcome classification."""

from __future__ import annotations

import pytest

from tests import test_formal_kinduction as kinduction


def test_real_counterexample_is_a_hard_failure() -> None:
    """A base-case counterexample must never be downgraded to xfail."""
    with pytest.raises(pytest.fail.Exception, match="proof FAILED"):
        kinduction._assert_kinduction_passed(
            False,
            "basecase failed: assertion counterexample found",
            "bounded eventually",
        )


def test_tool_error_is_a_hard_failure() -> None:
    """Unexpected tool output must fail instead of consuming the xfail budget."""
    with pytest.raises(pytest.fail.Exception, match="proof FAILED"):
        kinduction._assert_kinduction_passed(
            False,
            "sby terminated: solver process crashed",
            "bounded eventually",
        )


def test_induction_nonconvergence_is_the_only_xfail_boundary() -> None:
    """Only a recognized induction convergence boundary is an expected failure."""
    with pytest.raises(pytest.xfail.Exception, match="did not converge"):
        kinduction._assert_kinduction_passed(
            False,
            "summary: engine returned pass for basecase\n"
            "temporal induction failed\n"
            "summary: engine returned FAIL for induction",
            "bounded eventually",
        )


def test_bounded_eventually_has_no_blanket_xfail_marker() -> None:
    """A blanket marker would hide counterexamples raised inside the proof test."""
    proof_test = kinduction.TestKinductionBoundedEventually.test_bounded_eventually_kinduction_prove
    markers = getattr(proof_test, "pytestmark", ())
    assert all(marker.name != "xfail" for marker in markers)


def test_induction_text_cannot_override_a_basecase_counterexample() -> None:
    """A real base-case failure wins even if the log also names induction."""
    with pytest.raises(pytest.fail.Exception, match="proof FAILED"):
        kinduction._assert_kinduction_passed(
            False,
            "summary: engine returned FAIL for basecase\n"
            "temporal induction failed\n"
            "summary: engine returned FAIL for induction",
            "bounded eventually",
        )
