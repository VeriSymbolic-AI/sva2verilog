"""Generated RTL Verilator lint gate tests."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.generated_rtl_cases import (
    EmittedMonitorCase,
    GeneratedMonitorCase,
    all_generated_monitor_cases,
    emit_generated_case,
    lint_generated_monitor_cases,
    write_generated_modules,
)


@dataclass(frozen=True)
class ToolRunResult:
    """Captured external tool result."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def verilator_is_available() -> bool:
    """Return True when Verilator is available on PATH."""
    return shutil.which("verilator") is not None


def build_verilator_lint_command(
    verilator: str,
    emitted: EmittedMonitorCase,
    sv_files: list[Path],
) -> list[str]:
    """Build the Verilator lint-only command for one generated case.

    Uses ``-Wno-fatal`` to prevent Verilator from upgrading warnings to
    errors.  ``-Wall`` is intentionally omitted because Verilator minor-
    version upgrades frequently add new warning categories that cannot be
    anticipated, and the smoke gate should only fail on genuine
    structural or syntax errors (which always produce a non-zero exit
    code with or without ``-Wall``).
    """
    return [
        verilator,
        "--lint-only",
        "-Wno-fatal",
        "--top-module",
        emitted.top_module,
        *[str(path) for path in sv_files],
    ]


def run_verilator_lint(
    emitted: EmittedMonitorCase,
    sv_files: list[Path],
    *,
    timeout: int = 30,
) -> ToolRunResult:
    """Run Verilator lint-only with a bounded timeout."""
    verilator = shutil.which("verilator")
    if verilator is None:
        pytest.skip("verilator not found on PATH - install Verilator to run generated lint")

    cmd = build_verilator_lint_command(verilator, emitted, sv_files)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return ToolRunResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return ToolRunResult(-1, stdout, stderr, timed_out=True)


@pytest.mark.parametrize(
    "case",
    all_generated_monitor_cases(),
    ids=lambda case: case.case_id,
)
def test_generated_lint_case_catalog_emits_modules(case: object) -> None:
    """The lint gate consumes the same representative generated RTL catalog."""
    assert isinstance(case, GeneratedMonitorCase)
    emitted = emit_generated_case(case)
    assert emitted.modules, f"{emitted.case.case_id}: no modules emitted"
    assert emitted.top_module in emitted.modules, (
        f"{emitted.case.case_id}: top {emitted.top_module} missing from "
        f"{sorted(emitted.modules)}"
    )
    assert emitted.case.families, f"{emitted.case.case_id}: missing family tags"


def test_verilator_lint_command_names_top_module(tmp_path: Path) -> None:
    """The lint helper routes the generated top explicitly."""
    case = lint_generated_monitor_cases()[0]
    emitted, sv_files = write_generated_modules(tmp_path, case)
    cmd = build_verilator_lint_command("verilator", emitted, sv_files)
    assert "verilator" in cmd
    assert "--lint-only" in cmd
    assert "-Wno-fatal" in cmd
    assert "--top-module" in cmd
    assert emitted.top_module in cmd
    for path in sv_files:
        assert str(path) in cmd


@pytest.mark.generated_lint
@pytest.mark.parametrize(
    "case",
    lint_generated_monitor_cases(),
    ids=lambda case: case.case_id,
)
def test_verilator_lint_generated_modules(case: object, tmp_path: Path) -> None:
    """Verilator lint-only accepts each representative generated monitor."""
    assert isinstance(case, GeneratedMonitorCase)
    emitted, sv_files = write_generated_modules(tmp_path, case)
    result = run_verilator_lint(emitted, sv_files)

    assert not result.timed_out, (
        f"Verilator lint timed out for {case.case_id} top {emitted.top_module}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert result.returncode == 0, (
        f"Verilator lint failed for {case.case_id} top {emitted.top_module}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
