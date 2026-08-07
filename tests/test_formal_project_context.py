"""Real-project context and self-contained formal replay tests."""

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


def _project(tmp_path: Path) -> FormalRunConfig:
    include_dir = tmp_path / "include"
    library_dir = tmp_path / "library"
    include_dir.mkdir()
    library_dir.mkdir()
    (include_dir / "project_defs.svh").write_text(
        "`define PROJECT_ACK_EXPRESSION req_i\n",
        encoding="utf-8",
    )
    (library_dir / "project_leaf.sv").write_text(
        "module project_leaf #(parameter int Width = 1) (\n"
        "  input logic [Width-1:0] i, output logic [Width-1:0] o\n"
        ");\n"
        "  assign o = i;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    package = tmp_path / "project_pkg.sv"
    package.write_text(
        "package project_pkg; parameter int DefaultWidth = 2; endpackage\n",
        encoding="utf-8",
    )
    filelist = tmp_path / "project.f"
    filelist.write_text(f"{package.name}\n", encoding="utf-8")
    dut = tmp_path / "dut.sv"
    dut.write_text(
        '`include "project_defs.svh"\n'
        "module dut #(parameter int Width = project_pkg::DefaultWidth) (\n"
        "  input logic clk, rst_n,\n"
        "  input logic [Width-1:0] req_i,\n"
        "  output logic [Width-1:0] ack_o\n"
        ");\n"
        "`ifdef ENABLE_PROJECT_ACK\n"
        "  project_leaf #(.Width(Width)) u_leaf "
        "(.i(`PROJECT_ACK_EXPRESSION), .o(ack_o));\n"
        "`else\n"
        "  assign ack_o = '0;\n"
        "`endif\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop = tmp_path / "property.sv"
    prop.write_text(
        "module project_spec(\n"
        "  input logic clk, rst_n,\n"
        "  input logic [1:0] req_i, ack_o\n"
        ");\n"
        "  p_context: assert property (@(posedge clk) disable iff (!rst_n) "
        "req_i[0] |-> ack_o[0]);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p_context",
        top="dut",
        output_dir=tmp_path / "evidence",
        mode=FormalMode.PROVE,
        depth=12,
        timeout_seconds=90,
        filelists=(filelist,),
        include_dirs=(include_dir,),
        defines=("ENABLE_PROJECT_ACK=1",),
        parameter_overrides=("Width=2",),
        library_dirs=(library_dir,),
        library_extensions=(".sv",),
        single_unit=True,
    )


@pytest.mark.formal
@requires_formal_stack
def test_project_context_is_flattened_private_and_replayable(tmp_path: Path) -> None:
    evidence = build_formal_bundle(_project(tmp_path))
    manifest = evidence.manifest
    sby = (evidence.bundle_dir / "formal.sby").read_text(encoding="utf-8")
    dut_snapshot = (evidence.bundle_dir / "dut_preprocessed.sv").read_text(encoding="utf-8")

    assert manifest["yosys_inputs"][0] == "dut_preprocessed.sv"
    assert "property.sv" not in sby
    assert "-G Width=2" in sby
    assert "module project_leaf" in dut_snapshot
    assert "PROJECT_ACK_EXPRESSION" not in dut_snapshot
    serialized = json.dumps(manifest, sort_keys=True)
    assert str(tmp_path.resolve()) not in serialized
    assert str(tmp_path.resolve()) not in dut_snapshot
    assert {item["basename"] for item in manifest["project_context"]["dut_dependencies"]} >= {
        "dut.sv",
        "project_defs.svh",
        "project_leaf.sv",
        "project_pkg.sv",
    }

    result = run_formal_bundle(evidence)
    assert result.status is FormalStatus.PROVEN
    assert result.cover_status.value == "REACHED"


def test_project_context_decomposition_is_fail_closed(tmp_path: Path) -> None:
    config = _project(tmp_path)
    certificate = tmp_path / "decomposition.json"
    certificate.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="certificate schema v3"):
        FormalRunConfig(
            **{
                **config.__dict__,
                "decomposition_certificate": certificate,
            }
        )


def test_parameter_override_rejects_sby_script_injection(tmp_path: Path) -> None:
    config = _project(tmp_path)
    with pytest.raises(ValueError, match="atomic NAME=VALUE"):
        FormalRunConfig(
            **{
                **config.__dict__,
                "parameter_overrides": ("Width=2; delete dut",),
            }
        )
