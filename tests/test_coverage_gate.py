"""Regression tests for the release coverage gate."""

from __future__ import annotations

from tools.ci.check_coverage import (
    AGGREGATE_FLOOR,
    CRITICAL_MODULE_FLOORS,
    check_coverage,
)


def _report(*, delta: float = 0.0) -> dict[str, object]:
    return {
        "totals": {"percent_covered": AGGREGATE_FLOOR + delta},
        "files": {
            name: {"summary": {"percent_covered": floor + delta}}
            for name, floor in CRITICAL_MODULE_FLOORS.items()
        },
    }


def test_coverage_gate_accepts_all_floors() -> None:
    assert check_coverage(_report()) == []


def test_coverage_gate_reports_aggregate_and_module_regressions() -> None:
    failures = check_coverage(_report(delta=-0.5))

    assert len(failures) == len(CRITICAL_MODULE_FLOORS) + 1
    assert failures[0].startswith("aggregate:")
