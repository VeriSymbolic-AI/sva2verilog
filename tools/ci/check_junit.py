#!/usr/bin/env python3
"""Fail CI when a pytest job ran too little of its intended validation surface."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JUnitOutcomes:
    """Aggregated outcomes from one pytest JUnit XML report."""

    total: int
    passed: int
    skipped: int
    failures: int
    errors: int


def parse_junit(path: Path) -> JUnitOutcomes:
    """Parse testcase elements instead of trusting producer-specific root totals."""

    root = ET.parse(path).getroot()
    testcases = list(root.iter("testcase"))
    skipped = sum(case.find("skipped") is not None for case in testcases)
    failures = sum(case.find("failure") is not None for case in testcases)
    errors = sum(case.find("error") is not None for case in testcases)
    passed = len(testcases) - skipped - failures - errors
    return JUnitOutcomes(
        total=len(testcases),
        passed=passed,
        skipped=skipped,
        failures=failures,
        errors=errors,
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
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
