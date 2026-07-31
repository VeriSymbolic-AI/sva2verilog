#!/usr/bin/env python3
"""Fail CI when a pytest job ran too little of its intended validation surface.

When a budget is violated the gate also names the offending test cases and, for
skips, the reason pytest recorded.  Aggregate counts alone cannot distinguish a
genuine platform gap from a silently missing tool, and CI logs for a failed
matrix axis are not always accessible to every reader.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_MAX_REPORTED_CASES = 25


@dataclass(frozen=True)
class CaseOutcome:
    """One non-passing test case and the reason recorded for it."""

    name: str
    reason: str

    def render(self) -> str:
        return f"{self.name}: {self.reason}" if self.reason else self.name


@dataclass(frozen=True)
class JUnitOutcomes:
    """Aggregated outcomes from one pytest JUnit XML report.

    The per-case tuples are diagnostic detail rather than part of the outcome
    identity, so they are excluded from equality: two reports with the same
    counts describe the same budget result.
    """

    total: int
    passed: int
    skipped: int
    failures: int
    errors: int
    skipped_cases: tuple[CaseOutcome, ...] = field(default=(), compare=False)
    failed_cases: tuple[CaseOutcome, ...] = field(default=(), compare=False)


def _case_name(case: ET.Element) -> str:
    classname = case.get("classname", "")
    name = case.get("name", "<unnamed>")
    return f"{classname}::{name}" if classname else name


def _case_reason(node: ET.Element) -> str:
    message = node.get("message", "").strip()
    if message:
        return message.splitlines()[0]
    text = (node.text or "").strip()
    return text.splitlines()[0] if text else ""


def parse_junit(path: Path) -> JUnitOutcomes:
    """Parse testcase elements instead of trusting producer-specific root totals."""

    root = ET.parse(path).getroot()
    testcases = list(root.iter("testcase"))

    skipped_cases: list[CaseOutcome] = []
    failed_cases: list[CaseOutcome] = []
    skipped = failures = errors = 0

    for case in testcases:
        skip_node = case.find("skipped")
        if skip_node is not None:
            skipped += 1
            skipped_cases.append(CaseOutcome(_case_name(case), _case_reason(skip_node)))
            continue
        for tag in ("failure", "error"):
            node = case.find(tag)
            if node is None:
                continue
            if tag == "failure":
                failures += 1
            else:
                errors += 1
            failed_cases.append(CaseOutcome(_case_name(case), _case_reason(node)))

    passed = len(testcases) - skipped - failures - errors
    return JUnitOutcomes(
        total=len(testcases),
        passed=passed,
        skipped=skipped,
        failures=failures,
        errors=errors,
        skipped_cases=tuple(skipped_cases),
        failed_cases=tuple(failed_cases),
    )


def validate_outcomes(
    outcomes: JUnitOutcomes,
    *,
    min_passed: int,
    max_skipped: int,
) -> tuple[str, ...]:
    """Return deterministic gate violations for the configured job budget."""

    violations: list[str] = []
    if outcomes.failures:
        violations.append(f"{outcomes.failures} test failures recorded")
    if outcomes.errors:
        violations.append(f"{outcomes.errors} test errors recorded")
    if outcomes.passed < min_passed:
        violations.append(
            f"only {outcomes.passed} tests passed; required at least {min_passed}"
        )
    if outcomes.skipped > max_skipped:
        violations.append(
            f"{outcomes.skipped} tests skipped; allowed at most {max_skipped}"
        )
    return tuple(violations)


def render_diagnostics(outcomes: JUnitOutcomes) -> tuple[str, ...]:
    """Return per-case detail lines explaining why a budget was not met."""

    lines: list[str] = []
    for label, cases in (
        ("failed", outcomes.failed_cases),
        ("skipped", outcomes.skipped_cases),
    ):
        if not cases:
            continue
        lines.append(f"{label} test cases ({len(cases)}):")
        for case in cases[:_MAX_REPORTED_CASES]:
            lines.append(f"  - {case.render()}")
        remaining = len(cases) - _MAX_REPORTED_CASES
        if remaining > 0:
            lines.append(f"  ... {remaining} more {label} case(s) omitted")
    return tuple(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--min-passed", type=int, required=True)
    parser.add_argument("--max-skipped", type=int, required=True)
    args = parser.parse_args(argv)

    outcomes = parse_junit(args.report)
    print(
        "JUnit outcomes: "
        f"total={outcomes.total} passed={outcomes.passed} skipped={outcomes.skipped} "
        f"failures={outcomes.failures} errors={outcomes.errors}"
    )
    violations = validate_outcomes(
        outcomes,
        min_passed=args.min_passed,
        max_skipped=args.max_skipped,
    )
    if violations:
        for violation in violations:
            print(f"ERROR: {violation}", file=sys.stderr)
        for line in render_diagnostics(outcomes):
            print(line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
