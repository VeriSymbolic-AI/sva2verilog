"""Synthesis-oriented generated RTL gate tests."""

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
    write_generated_modules,
    yosys_generated_monitor_cases,
)

_REQUIRED_FAMILIES = frozenset(
    {
        "boolean",
        "sampled_value",
        "fixed_delay",
        "bounded_delay",
        "overlap",
        "nonoverlap",
        "rep_consecutive",
        "goto_rep",
        "nonconsec_rep",
        "bounded_liveness",
        "property_composition",
        "nfa_generic",
        "disable_iff",
        "first_match",
        "multi_clock",
    }
)


@dataclass(frozen=True)
class ToolRunResult:
    """Captured external tool result."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def yosys_is_available() -> bool:
    """Return True when Yosys is available on PATH."""
    return shutil.which("yosys") is not None


def _yosys_quote(path: Path) -> str:
    return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_yosys_smoke_script(
    emitted: EmittedMonitorCase,
    sv_files: list[Path],
) -> str:
    """Build the synthesis-oriented Yosys script for one generated case."""
    file_args = " ".join(_yosys_quote(path) for path in sv_files)
    return "\n".join(
        (
            f"read_verilog -sv {file_args}",
            f"hierarchy -check -top {emitted.top_module}",
            "proc",
            "opt",
            "check",
            "synth -run coarse",
            "check",
            "",
        )
    )


def run_yosys_script(
    script: str,
    *,
    work_dir: Path,
    timeout: int = 30,
) -> ToolRunResult:
    """Run a Yosys script with a bounded timeout."""
    yosys = shutil.which("yosys")
    if yosys is None:
        pytest.skip("yosys not found on PATH - install Yosys to run synthesis gates")

    script_path = work_dir / "synthesis_gate.ys"
    script_path.write_text(script, encoding="utf-8")
    try:
        result = subprocess.run(
            [yosys, "-q", "-s", str(script_path)],
            cwd=work_dir,
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


def test_generated_rtl_case_catalog_has_required_families() -> None:
    """The representative catalog covers the Phase 11 major template families."""
    families = frozenset(
        family
        for case in all_generated_monitor_cases()
        for family in case.families
    )
    missing = _REQUIRED_FAMILIES - families
    assert not missing, f"missing generated RTL family coverage: {sorted(missing)}"


@pytest.mark.parametrize(
    "case",
    all_generated_monitor_cases(),
    ids=lambda case: case.case_id,
)
def test_generated_rtl_case_catalog_emits_modules(case: object) -> None:
    """Every catalog case emits modules and includes its declared top module."""
    assert isinstance(case, GeneratedMonitorCase)
    emitted = emit_generated_case(case)
    assert emitted.modules, f"{emitted.case.case_id}: no modules emitted"
    assert emitted.top_module in emitted.modules, (
        f"{emitted.case.case_id}: top {emitted.top_module} missing from "
        f"{sorted(emitted.modules)}"
    )
    for module_name, sv_text in emitted.modules.items():
        assert module_name.startswith("sva_") or module_name == "lfsr_8bit"
        assert sv_text.rstrip().endswith("endmodule"), (
            f"{emitted.case.case_id}/{module_name}: missing final endmodule"
        )
    assert emitted.case.matrix_rows, f"{emitted.case.case_id}: missing matrix rows"


def test_yosys_helper_script_contains_required_passes(tmp_path: Path) -> None:
    """The helper builds the expected synthesis-oriented Yosys pass sequence."""
    case = yosys_generated_monitor_cases()[0]
    emitted, sv_files = write_generated_modules(tmp_path, case)
    script = build_yosys_smoke_script(emitted, sv_files)
    for expected in (
        "read_verilog -sv",
        f"hierarchy -check -top {emitted.top_module}",
        "proc",
        "opt",
        "check",
        "synth -run coarse",
    ):
        assert expected in script


@pytest.mark.synthesis
@pytest.mark.parametrize(
    "case",
    yosys_generated_monitor_cases(),
    ids=lambda case: case.case_id,
)
def test_yosys_synthesis_smoke(case: object, tmp_path: Path) -> None:
    """Yosys accepts each representative generated monitor after coarse synthesis."""
    assert isinstance(case, GeneratedMonitorCase)
    emitted, sv_files = write_generated_modules(tmp_path, case)
    script = build_yosys_smoke_script(emitted, sv_files)
    result = run_yosys_script(script, work_dir=tmp_path)

    assert not result.timed_out, (
        f"Yosys timed out for {case.case_id} top {emitted.top_module}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}\n"
        f"script:\n{script}"
    )
    assert result.returncode == 0, (
        f"Yosys failed for {case.case_id} top {emitted.top_module}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}\n"
        f"script:\n{script}"
    )
