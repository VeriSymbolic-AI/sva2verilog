"""Real-tool qualification for the user-DUT open formal workflow."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sva2rtl.formal_flow import (
    FormalMode,
    FormalRunConfig,
    FormalStatus,
    build_formal_bundle,
    run_formal_bundle,
)

FIXTURES = Path(__file__).parent / "formal_user_dut"


def _has_formal_stack() -> bool:
    if any(shutil.which(tool) is None for tool in ("slang", "yosys", "sby", "yices-smt2")):
        return False
    completed = subprocess.run(
        ["yosys", "-m", "slang", "-Q", "-p", "help read_slang"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return completed.returncode == 0 and "read_slang" in completed.stdout


requires_formal_stack = pytest.mark.skipif(
    not _has_formal_stack(),
    reason="requires slang, Yosys read_slang plugin, SBY, and yices-smt2",
)


def _config(tmp_path: Path, dut: str, mode: FormalMode) -> FormalRunConfig:
    return FormalRunConfig(
        dut_sources=(FIXTURES / dut,),
        property_file=FIXTURES / "req_ack_property.sv",
        property_name="req_has_ack",
        top="user_formal_dut",
        output_dir=tmp_path / f"{dut}-{mode.value}",
        mode=mode,
        depth=12,
        timeout_seconds=60,
    )


@pytest.mark.formal
@requires_formal_stack
def test_good_dut_is_proven_and_property_is_not_a_yosys_input(tmp_path: Path) -> None:
    evidence = build_formal_bundle(_config(tmp_path, "good_dut.sv", FormalMode.PROVE))
    result = run_formal_bundle(evidence)
    assert result.status is FormalStatus.PROVEN, (evidence.bundle_dir / "sby.log").read_text()

    sby_text = (evidence.bundle_dir / "formal.sby").read_text(encoding="utf-8")
    manifest = json.loads((evidence.bundle_dir / "manifest.json").read_text())
    assert "req_ack_property" not in sby_text
    assert "evidence/property.sv" not in sby_text
    assert manifest["property"]["path"] not in manifest["yosys_inputs"]


@pytest.mark.formal
@requires_formal_stack
def test_bad_dut_returns_counterexample_and_trace(tmp_path: Path) -> None:
    evidence = build_formal_bundle(_config(tmp_path, "bad_dut.sv", FormalMode.PROVE))
    result = run_formal_bundle(evidence)
    assert result.status is FormalStatus.FAILED, (evidence.bundle_dir / "sby.log").read_text()
    assert result.trace_paths
    assert all((evidence.bundle_dir / path).is_file() for path in result.trace_paths)


@pytest.mark.formal
@requires_formal_stack
def test_successful_bmc_is_unknown_not_proven(tmp_path: Path) -> None:
    evidence = build_formal_bundle(_config(tmp_path, "good_dut.sv", FormalMode.BMC))
    result = run_formal_bundle(evidence)
    assert result.status is FormalStatus.UNKNOWN, (evidence.bundle_dir / "sby.log").read_text()
    assert "bounded" in result.message.lower()
