"""Bounded formal qualification against an independently maintained RTL source."""

from __future__ import annotations

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

CORPUS = Path(__file__).parent / "external_corpus" / "opentitan"


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


def _config(tmp_path: Path, dut: Path, name: str) -> FormalRunConfig:
    return FormalRunConfig(
        dut_sources=(dut, CORPUS / "prim_flop_adapter.sv"),
        property_file=CORPUS / "two_cycle_property.sv",
        property_name="p_two_cycle",
        top="prim_flop_2sync",
        clock="clk_i",
        reset="rst_ni",
        output_dir=tmp_path / name,
        mode=FormalMode.PROVE,
        depth=12,
        timeout_seconds=90,
    )


@pytest.mark.formal
@requires_formal_stack
def test_opentitan_sync_slice_proves_and_latency_mutant_fails(tmp_path: Path) -> None:
    upstream = CORPUS / "prim_flop_2sync.sv"
    proven = run_formal_bundle(build_formal_bundle(_config(tmp_path, upstream, "good")))
    assert proven.status is FormalStatus.PROVEN
    assert proven.cover_status.value == "REACHED"

    mutant = tmp_path / "prim_flop_2sync_mutant.sv"
    source = upstream.read_text(encoding="utf-8")
    needle = ".d_i(intq),\n    .q_o\n"
    assert source.count(needle) == 1
    mutant.write_text(source.replace(needle, ".d_i(d_o),\n    .q_o\n"), encoding="utf-8")
    failed = run_formal_bundle(build_formal_bundle(_config(tmp_path, mutant, "bad")))
    assert failed.status is FormalStatus.FAILED
    assert failed.trace_paths


def test_external_corpus_records_exact_origin_and_claim_boundary() -> None:
    provenance = (CORPUS / "PROVENANCE.md").read_text(encoding="utf-8")
    source = (CORPUS / "prim_flop_2sync.sv").read_text(encoding="utf-8")
    assert "aac7794751c9d95275100db6278914f795f9d000" in provenance
    assert "8f7864ee04e4c89ea4b1ff408afdb98ce4bd0c40" in provenance
    assert "does **not** verify OpenTitan" in provenance
    assert "SPDX-License-Identifier: Apache-2.0" in source
