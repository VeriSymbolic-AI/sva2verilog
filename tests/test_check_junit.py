"""Tests for the CI execution-budget gate diagnostics.

Aggregate-count behaviour is covered by ``test_ci_outcome_gate.py``.  This module
covers the per-case diagnostics that name which tests skipped or failed and why,
which is what makes an under-executed matrix axis actionable from CI output
alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.ci.check_junit import main, parse_junit, render_diagnostics

_REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="pytest" tests="4">
    <testcase classname="tests.test_sim" name="test_pass_one"/>
    <testcase classname="tests.test_sim" name="test_pass_two"/>
    <testcase classname="tests.test_sim" name="test_skipped">
      <skipped message="verilator not found on PATH">skip detail</skipped>
    </testcase>
    <testcase classname="tests.test_sim" name="test_failed">
      <failure message="assert 0 == 1">trace</failure>
    </testcase>
  </testsuite>
</testsuites>
"""


def _write(tmp_path: Path, body: str) -> Path:
    report = tmp_path / "results.xml"
    report.write_text(body, encoding="utf-8")
    return report


def test_parse_junit_identifies_offending_cases(tmp_path: Path) -> None:
    outcomes = parse_junit(_write(tmp_path, _REPORT))

    assert [case.name for case in outcomes.skipped_cases] == ["tests.test_sim::test_skipped"]
    assert outcomes.skipped_cases[0].reason == "verilator not found on PATH"
    assert [case.name for case in outcomes.failed_cases] == ["tests.test_sim::test_failed"]
    assert outcomes.failed_cases[0].reason == "assert 0 == 1"


def test_diagnostic_detail_does_not_affect_outcome_equality(tmp_path: Path) -> None:
    """Counts define the budget result; case detail must not change identity."""

    outcomes = parse_junit(_write(tmp_path, _REPORT))
    counts_only = parse_junit(_write(tmp_path, _REPORT)).__class__(
        total=outcomes.total,
        passed=outcomes.passed,
        skipped=outcomes.skipped,
        failures=outcomes.failures,
        errors=outcomes.errors,
    )

    assert outcomes == counts_only
    assert outcomes.skipped_cases != counts_only.skipped_cases


def test_render_diagnostics_names_cases_and_reasons(tmp_path: Path) -> None:
    rendered = "\n".join(render_diagnostics(parse_junit(_write(tmp_path, _REPORT))))

    assert "tests.test_sim::test_skipped: verilator not found on PATH" in rendered
    assert "tests.test_sim::test_failed: assert 0 == 1" in rendered


def test_render_diagnostics_falls_back_to_element_text(tmp_path: Path) -> None:
    body = (
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="c" name="t"><skipped>reason in body text</skipped>'
        "</testcase></testsuite></testsuites>"
    )

    rendered = "\n".join(render_diagnostics(parse_junit(_write(tmp_path, body))))

    assert "reason in body text" in rendered


def test_render_diagnostics_truncates_long_case_lists(tmp_path: Path) -> None:
    cases = "".join(
        f'<testcase classname="c" name="t{index}"><skipped message="reason {index}"/></testcase>'
        for index in range(40)
    )
    body = f'<testsuites><testsuite name="pytest">{cases}</testsuite></testsuites>'

    rendered = render_diagnostics(parse_junit(_write(tmp_path, body)))

    assert any("more skipped case(s) omitted" in line for line in rendered)


def test_main_prints_diagnostics_when_budget_is_violated(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main([str(_write(tmp_path, _REPORT)), "--min-passed", "10", "--max-skipped", "0"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "JUnit outcomes: total=4 passed=2" in captured.out
    assert "verilator not found on PATH" in captured.err


def test_main_stays_quiet_when_budget_is_met(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = (
        '<testsuites><testsuite name="pytest">'
        '<testcase classname="c" name="t0"/><testcase classname="c" name="t1"/>'
        "</testsuite></testsuites>"
    )

    exit_code = main([str(_write(tmp_path, body)), "--min-passed", "2", "--max-skipped", "0"])

    assert exit_code == 0
    assert capsys.readouterr().err == ""


def test_main_allows_only_declared_skip_reason_prefixes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    body = _REPORT.replace("<failure", "<skipped").replace(
        "</failure>", "</skipped>"
    )
    report = _write(tmp_path, body)

    exit_code = main(
        [
            str(report),
            "--min-passed",
            "2",
            "--max-skipped",
            "2",
            "--allow-skip-prefix",
            "verilator",
        ]
    )

    assert exit_code == 1
    assert "unapproved skip reason" in capsys.readouterr().err
