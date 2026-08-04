"""Phase 22 open liveness routing, fairness, and evidence contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sva2rtl.composer import compose
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.formal_flow import (
    CoverStatus,
    FormalRunConfig,
    FormalStatus,
    PropertyClass,
    build_formal_bundle,
    classify_live_result,
    discover_live_backend,
    run_formal_bundle,
)
from sva2rtl.ir import BoolExpr, ClockSpec, PropEventually, SourceLoc

requires_cover_stack = pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("sby", "slang", "yosys", "yices-smt2")),
    reason="requires SBY, slang, Yosys, and yices-smt2 for the cover task",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sources(
    tmp_path: Path,
    *,
    property_body: str = "req |-> s_eventually ack",
) -> tuple[Path, Path]:
    dut = tmp_path / "dut.sv"
    prop = tmp_path / "property.sv"
    dut.write_text(
        "module dut(input logic clk, input logic rst_n, input logic req, "
        "input logic hold, input logic ready, output logic ack);\n"
        "  assign ack = ready;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module spec(input logic clk, rst_n, req, hold, ready, ack);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) "
        f"{property_body});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return dut, prop


def _config(
    tmp_path: Path,
    *,
    property_body: str = "req |-> s_eventually ack",
    suprove_path: str = "sva2rtl-missing-suprove",
    fairness: tuple[str, ...] = (),
    output_name: str = "evidence",
) -> FormalRunConfig:
    dut, prop = _sources(tmp_path, property_body=property_body)
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / output_name,
        depth=12,
        timeout_seconds=90,
        suprove_path=suprove_path,
        fairness_signals=fairness,
    )


def test_formal_only_eventually_cannot_enter_monitor_composer() -> None:
    loc = SourceLoc("live.sv", 1, 1)
    node = PropEventually(
        body=BoolExpr(text="ack", source_loc=loc),
        strong=True,
        source_loc=loc,
    )
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    with pytest.raises(UnsupportedConstruct, match="PropEventually"):
        compose(node, clock, "p", "s_eventually ack")


@pytest.mark.formal
def test_live_bundle_uses_yosys_primitives_and_excludes_original_sva(
    tmp_path: Path,
) -> None:
    evidence = build_formal_bundle(_config(tmp_path))
    assert evidence.property_class is PropertyClass.LIVENESS
    assert evidence.manifest["backend"] == "open-live-suprove"
    assert evidence.manifest["live_engine"]["available"] is False
    assert "evidence/property.sv" not in evidence.manifest["yosys_inputs"]
    bind = (evidence.bundle_dir / "formal_bind.sv").read_text(encoding="utf-8")
    sby = (evidence.bundle_dir / "formal.sby").read_text(encoding="utf-8")
    cover_sby = (evidence.bundle_dir / "formal_cover.sby").read_text(encoding="utf-8")
    assert r"\$live" in bind
    assert "witness_select" in bind and "pending_q" in bind
    assert "mode live" in sby and "aiger suprove" in sby
    assert "depth " not in sby
    assert r"delete =\$live" in sby
    assert r"delete =\$fair" not in sby
    assert "mode cover" in cover_sby and "smtbmc yices" in cover_sby


@pytest.mark.formal
@requires_cover_stack
def test_missing_live_engine_is_actionable_unknown_with_cover_evidence(
    tmp_path: Path,
) -> None:
    evidence = build_formal_bundle(_config(tmp_path))
    result = run_formal_bundle(evidence)
    assert result.status is FormalStatus.UNKNOWN
    assert result.cover_status is CoverStatus.REACHED
    assert "suprove" in result.message.lower()
    assert "bounded" in result.message.lower()
    assert (evidence.bundle_dir / "result.json").is_file()


@pytest.mark.formal
@pytest.mark.parametrize(
    ("property_body", "expected_safety"),
    [
        ("hold s_until ack", "(obs_0) || (obs_1)"),
        ("hold s_until_with ack", "obs_0"),
    ],
)
def test_strong_until_splits_safety_and_eventual_discharge(
    tmp_path: Path,
    property_body: str,
    expected_safety: str,
) -> None:
    evidence = build_formal_bundle(_config(tmp_path, property_body=property_body))
    bind = (evidence.bundle_dir / "formal_bind.sv").read_text(encoding="utf-8")
    assert "strong-until safety obligation" in bind
    assert expected_safety in bind
    assert r"\$live" in bind
    assert evidence.manifest["obligations"] == [
        "weak-until-safety",
        "eventual-discharge",
    ]


def test_live_engine_discovery_records_executable_and_version(tmp_path: Path) -> None:
    executable = tmp_path / "suprove-test"
    executable.write_text("#!/bin/sh\necho suprove-test-1.0\n", encoding="utf-8")
    executable.chmod(0o755)
    config = _config(tmp_path, suprove_path=str(executable))
    info = discover_live_backend(config)
    assert info.available is True
    assert info.path == str(executable)
    assert "suprove-test-1.0" in info.version


@pytest.mark.parametrize(
    ("returncode", "output", "timed_out", "expected"),
    [
        (0, "DONE (PASS, rc=0)", False, FormalStatus.PROVEN),
        (1, "DONE (FAIL, rc=2)", False, FormalStatus.FAILED),
        (1, "inconclusive", False, FormalStatus.ERROR),
        (-9, "", True, FormalStatus.TIMEOUT),
    ],
)
def test_live_result_classification_is_fail_closed(
    returncode: int,
    output: str,
    timed_out: bool,
    expected: FormalStatus,
) -> None:
    status, _message = classify_live_result(
        returncode=returncode,
        output=output,
        timed_out=timed_out,
    )
    assert status is expected


@pytest.mark.formal
@requires_cover_stack
def test_fairness_is_explicit_hashed_and_changes_evidence(tmp_path: Path) -> None:
    no_fair = build_formal_bundle(_config(tmp_path, output_name="no-fair"))
    with_fair = build_formal_bundle(
        _config(tmp_path, fairness=("ready",), output_name="with-fair")
    )
    fair_entry = with_fair.manifest["fairness"]
    fair_path = with_fair.bundle_dir / fair_entry["path"]
    payload = json.loads(fair_path.read_text(encoding="utf-8"))
    assert fair_entry["sha256"] == _sha256(fair_path)
    assert payload["assumptions"] == [
        {
            "kind": "user/model-assumption",
            "semantics": "GF(ready)",
            "signal": "ready",
        }
    ]
    assert fair_entry["sha256"] != no_fair.manifest["fairness"]["sha256"]
    bind = (with_fair.bundle_dir / "formal_bind.sv").read_text(encoding="utf-8")
    live_sby = (with_fair.bundle_dir / "formal.sby").read_text(encoding="utf-8")
    assert r"\$fair" in bind
    assert r"delete =\$fair" in live_sby
    result = run_formal_bundle(with_fair)
    assert result.status is FormalStatus.UNKNOWN
    assert result.cover_status is CoverStatus.REACHED


def test_vector_fairness_signal_rejects_instead_of_truncating(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    dut.write_text(
        "module dut(input logic clk, input logic rst_n, input logic req, "
        "input logic hold, input logic [1:0] ready, output logic ack);\n"
        "  assign ack = ready[0];\n"
        "endmodule\n",
        encoding="utf-8",
    )
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / "evidence",
        fairness_signals=("ready",),
    )

    with pytest.raises(SvaCompileError, match="fairness.*type mismatch"):
        build_formal_bundle(config)


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("sby", "slang", "yosys", "false")),
    reason="requires SBY, slang, Yosys, and a no-op executable",
)
@pytest.mark.formal
def test_live_bundle_prepares_aiger_model_without_a_live_solver(tmp_path: Path) -> None:
    evidence = build_formal_bundle(_config(tmp_path))
    completed = subprocess.run(
        [
            "sby",
            "-f",
            "formal.sby",
            "--suprove",
            shutil.which("false") or "false",
        ],
        cwd=evidence.bundle_dir,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode != 0
    assert "aig: finished (returncode=0)" in output
    assert "Unused option: depth" not in output


@pytest.mark.skipif(shutil.which("suprove") is None, reason="suprove is not installed")
@pytest.mark.formal
@pytest.mark.parametrize("good", [True, False])
def test_real_live_engine_distinguishes_good_and_bad_liveness(
    tmp_path: Path,
    good: bool,
) -> None:
    dut, prop = _sources(tmp_path)
    dut.write_text(
        "module dut(input logic clk, input logic rst_n, input logic req, "
        "input logic hold, input logic ready, output logic ack);\n"
        f"  assign ack = 1'b{1 if good else 0};\n"
        "endmodule\n",
        encoding="utf-8",
    )
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / "live",
        depth=12,
        suprove_path="suprove",
    )
    result = run_formal_bundle(build_formal_bundle(config))
    expected = FormalStatus.PROVEN if good else FormalStatus.FAILED
    assert result.status is expected
