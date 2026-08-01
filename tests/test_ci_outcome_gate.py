"""Tests for CI outcome-budget enforcement."""

from __future__ import annotations

from pathlib import Path

from tools.ci.check_junit import CaseOutcome, JUnitOutcomes, parse_junit, validate_outcomes


def test_parse_junit_counts_all_outcomes(tmp_path: Path) -> None:
    report = tmp_path / "results.xml"
    report.write_text(
        """
<testsuites>
  <testsuite name="suite">
    <testcase name="pass"/>
    <testcase name="skip"><skipped message="tool missing"/></testcase>
    <testcase name="fail"><failure message="bad"/></testcase>
    <testcase name="error"><error message="boom"/></testcase>
  </testsuite>
</testsuites>
""".strip(),
        encoding="utf-8",
    )

    assert parse_junit(report) == JUnitOutcomes(
        total=4,
        passed=1,
        skipped=1,
        failures=1,
        errors=1,
    )


def test_validate_outcomes_rejects_low_execution_and_excess_skips() -> None:
    violations = validate_outcomes(
        JUnitOutcomes(total=12, passed=7, skipped=5, failures=0, errors=0),
        min_passed=10,
        max_skipped=2,
    )

    assert violations == (
        "only 7 tests passed; required at least 10",
        "5 tests skipped; allowed at most 2",
    )


def test_validate_outcomes_accepts_budget_boundary() -> None:
    assert (
        validate_outcomes(
            JUnitOutcomes(total=12, passed=10, skipped=2, failures=0, errors=0),
            min_passed=10,
            max_skipped=2,
        )
        == ()
    )


def test_validate_outcomes_rejects_unapproved_skip_reason() -> None:
    outcomes = JUnitOutcomes(
        total=2,
        passed=1,
        skipped=1,
        failures=0,
        errors=0,
        skipped_cases=(CaseOutcome("suite::case", "unexpected quarantine"),),
    )

    assert validate_outcomes(
        outcomes,
        min_passed=1,
        max_skipped=1,
        allowed_skip_prefixes=("sby", "yosys", "verilator"),
    ) == ("1 skipped tests have an unapproved skip reason",)


def test_validate_outcomes_accepts_approved_skip_reason_prefix() -> None:
    outcomes = JUnitOutcomes(
        total=2,
        passed=1,
        skipped=1,
        failures=0,
        errors=0,
        skipped_cases=(CaseOutcome("suite::case", "sby not found on PATH"),),
    )

    assert (
        validate_outcomes(
            outcomes,
            min_passed=1,
            max_skipped=1,
            allowed_skip_prefixes=("sby",),
        )
        == ()
    )
