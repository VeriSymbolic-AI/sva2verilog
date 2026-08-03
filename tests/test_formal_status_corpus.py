"""Checked-in real-source corpus for every externally visible result boundary."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sva2rtl.formal_flow import (
    CoverStatus,
    FormalRunConfig,
    FormalStatus,
    build_formal_bundle,
    run_formal_bundle,
)

CORPUS = Path(__file__).parent / "formal_user_dut"


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


def test_status_corpus_is_complete_and_uses_real_source_files() -> None:
    payload = json.loads((CORPUS / "status_corpus.json").read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert {case["expected"] for case in cases} == {
        "PROVEN",
        "FAILED",
        "UNKNOWN",
        "UNSUPPORTED",
        "TIMEOUT",
    }
    assert {case["id"] for case in cases} >= {
        "vacuous-cover",
        "missing-live-engine",
        "multiclock-boundary",
        "xz-boundary",
    }
    for case in cases:
        dut = CORPUS / case["dut"]
        prop = CORPUS / case["property"]
        assert dut.is_file() and prop.is_file()
        assert "assert property" not in dut.read_text(encoding="utf-8")
        assert "assert property" in prop.read_text(encoding="utf-8")


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize(
    ("dut", "expected", "cover"),
    [
        ("reachable_progress_dut.sv", FormalStatus.PROVEN, CoverStatus.REACHED),
        ("vacuous_dut.sv", FormalStatus.UNKNOWN, CoverStatus.UNREACHED),
    ],
)
def test_checked_progress_fixtures_expose_vacuity(
    tmp_path: Path,
    dut: str,
    expected: FormalStatus,
    cover: CoverStatus,
) -> None:
    config = FormalRunConfig(
        dut_sources=(CORPUS / dut,),
        property_file=CORPUS / "nexttime_property.sv",
        property_name="req_has_delayed_ack",
        top="user_progress_dut",
        output_dir=tmp_path / "evidence",
        depth=12,
        timeout_seconds=60,
    )
    result = run_formal_bundle(build_formal_bundle(config))
    assert result.status is expected
    assert result.cover_status is cover


@pytest.mark.formal
@requires_formal_stack
def test_checked_live_fixture_without_engine_is_unknown_with_cover(
    tmp_path: Path,
) -> None:
    config = FormalRunConfig(
        dut_sources=(CORPUS / "live_good_dut.sv",),
        property_file=CORPUS / "live_property.sv",
        property_name="req_eventually_ack",
        top="user_live_dut",
        output_dir=tmp_path / "evidence",
        suprove_path="sva2rtl-intentionally-missing-suprove",
        depth=12,
        timeout_seconds=60,
    )
    result = run_formal_bundle(build_formal_bundle(config))
    assert result.status is FormalStatus.UNKNOWN
    assert result.cover_status is CoverStatus.REACHED
    assert "suprove" in result.message.lower()
