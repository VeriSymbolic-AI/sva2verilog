"""Enforce aggregate and critical-module branch coverage floors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

CRITICAL_MODULE_FLOORS: dict[str, float] = {
    "src/sva2rtl/bool_semantics.py": 85.0,
    "src/sva2rtl/behavioral_oracle.py": 78.0,
    "src/sva2rtl/composer.py": 84.0,
    "src/sva2rtl/ast_importer.py": 79.5,
    "src/sva2rtl/cli.py": 66.0,
}
AGGREGATE_FLOOR = 82.0


def _percent(payload: dict[str, object]) -> float:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("coverage entry is missing its summary")
    value = summary.get("percent_covered")
    if not isinstance(value, int | float):
        raise ValueError("coverage summary is missing percent_covered")
    return float(value)


def check_coverage(report: dict[str, object]) -> list[str]:
    """Return human-readable failures for floors not met by a coverage JSON report."""

    failures: list[str] = []
    totals = report.get("totals")
    if not isinstance(totals, dict):
        return ["coverage report is missing totals"]
    aggregate = _percent({"summary": totals})
    if aggregate < AGGREGATE_FLOOR:
        failures.append(f"aggregate: {aggregate:.2f}% < {AGGREGATE_FLOOR:.2f}%")

    files = report.get("files")
    if not isinstance(files, dict):
        return [*failures, "coverage report is missing files"]
    for module, floor in CRITICAL_MODULE_FLOORS.items():
        entry = files.get(module)
        if not isinstance(entry, dict):
            failures.append(f"{module}: missing from coverage report")
            continue
        actual = _percent(entry)
        if actual < floor:
            failures.append(f"{module}: {actual:.2f}% < {floor:.2f}%")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: check_coverage.py COVERAGE_JSON", file=sys.stderr)
        return 2
    report = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    failures = check_coverage(report)
    if failures:
        print("coverage gate failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("coverage gate passed: aggregate and all critical-module floors met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
