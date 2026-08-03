"""Phase 21 evidence, decomposition, and anti-vacuity contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sva2rtl.formal_flow import (
    CoverStatus,
    FormalMode,
    FormalRunConfig,
    FormalStatus,
    build_formal_bundle,
    classify_cover_result,
    run_formal_bundle,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _sources(tmp_path: Path, *, reachable: bool = True) -> tuple[Path, Path]:
    dut = tmp_path / "dut.sv"
    prop = tmp_path / "property.sv"
    req_port = "input logic req" if reachable else "output logic req"
    req_assign = "" if reachable else "  assign req = 1'b0;\n"
    dut.write_text(
        f"module dut(input logic clk, input logic rst_n, {req_port}, "
        "output logic ack);\n"
        f"{req_assign}"
        "  assign ack = 1'b1;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module spec(input logic clk, rst_n, req, ack);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) "
        "req |-> nexttime[2] ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return dut, prop


def _config(
    tmp_path: Path,
    *,
    reachable: bool = True,
    certificate: Path | None = None,
) -> FormalRunConfig:
    dut, prop = _sources(tmp_path, reachable=reachable)
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / "evidence",
        mode=FormalMode.PROVE,
        depth=12,
        timeout_seconds=90,
        decomposition_certificate=certificate,
    )


@pytest.mark.formal
@requires_formal_stack
def test_bundle_records_hashed_logical_property_slice(tmp_path: Path) -> None:
    evidence = build_formal_bundle(_config(tmp_path))
    slice_entry = evidence.manifest["property_slice"]
    slice_path = evidence.bundle_dir / slice_entry["path"]
    payload = json.loads(slice_path.read_text(encoding="utf-8"))

    assert slice_entry["sha256"] == _sha256(slice_path)
    assert payload["kind"] == "logical-property-cone"
    assert payload["source_scope"] == "complete-dut-sources"
    assert payload["pruning_boundary"] == "yosys-prep-and-formal-cone"
    assert payload["top"] == "dut"
    assert {item["dut_signal"] for item in payload["observed_signals"]} == {
        "req",
        "ack",
    }
    assert all(item["width"] == 1 for item in payload["observed_signals"])
    assert "formal_cover.sby" in evidence.manifest


def _write_certificate(tmp_path: Path, property_path: Path) -> Path:
    subproperty = tmp_path / "subproperty.sv"
    proof = tmp_path / "subproperty-result.json"
    relation_proof = tmp_path / "relation-result.json"
    subproperty.write_text("assert property (p);\n", encoding="utf-8")
    property_hash = _sha256(property_path)
    subproperty_hash = _sha256(subproperty)
    checker = "independent-sby-run"
    relation_checker = "independent-sby-relation-run"
    proof.write_text(
        json.dumps(
            {
                "status": "PROVEN",
                "property_sha256": subproperty_hash,
                "checker": checker,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    relation_proof.write_text(
        json.dumps(
            {
                "status": "PROVEN",
                "relation": "equivalent",
                "original_property_sha256": property_hash,
                "subproperty_sha256s": [subproperty_hash],
                "checker": relation_checker,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    certificate = tmp_path / "decomposition.json"
    certificate.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "relation": "equivalent",
                "relation_status": "PROVEN",
                "relation_checker": relation_checker,
                "relation_proof_artifact_path": relation_proof.name,
                "relation_proof_artifact_sha256": _sha256(relation_proof),
                "original_property_sha256": property_hash,
                "subproperties": [
                    {
                        "id": "bounded_obligation_1",
                        "property_path": subproperty.name,
                        "property_sha256": subproperty_hash,
                        "obligation_status": "PROVEN",
                        "checker": checker,
                        "proof_artifact_path": proof.name,
                        "proof_artifact_sha256": _sha256(proof),
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return certificate


@pytest.mark.formal
@requires_formal_stack
def test_checked_decomposition_is_sanitized_and_hashed(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, prop)
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / "evidence",
        decomposition_certificate=certificate,
    )
    evidence = build_formal_bundle(config)

    entry = evidence.manifest["decomposition"]
    normalized = evidence.bundle_dir / entry["path"]
    payload = json.loads(normalized.read_text(encoding="utf-8"))
    assert entry["sha256"] == _sha256(normalized)
    assert payload["relation"] == "equivalent"
    assert payload["relation_status"] == "PROVEN"
    assert payload["subproperties"][0]["obligation_status"] == "PROVEN"
    assert payload["subproperties"][0]["property_path"].startswith(
        "evidence/decomposition/"
    )
    assert str(tmp_path) not in normalized.read_text(encoding="utf-8")


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_unverified_artifact_hash(tmp_path: Path) -> None:
    _dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, prop)
    payload = json.loads(certificate.read_text(encoding="utf-8"))
    payload["subproperties"][0]["proof_artifact_sha256"] = "0" * 64
    certificate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="proof artifact hash"):
        build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.parametrize(
    ("returncode", "output", "timed_out", "expected"),
    [
        (0, "DONE (PASS, rc=0)", False, CoverStatus.REACHED),
        (1, "DONE (FAIL, rc=2)", False, CoverStatus.UNREACHED),
        (1, "engine vanished", False, CoverStatus.ERROR),
        (-9, "", True, CoverStatus.TIMEOUT),
    ],
)
def test_cover_result_classification_is_fail_closed(
    returncode: int,
    output: str,
    timed_out: bool,
    expected: CoverStatus,
) -> None:
    status, _message = classify_cover_result(
        returncode=returncode,
        output=output,
        timed_out=timed_out,
    )
    assert status is expected


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize(
    ("reachable", "expected_status", "expected_cover"),
    [
        (True, FormalStatus.PROVEN, CoverStatus.REACHED),
        (False, FormalStatus.UNKNOWN, CoverStatus.UNREACHED),
    ],
)
def test_critical_cover_gates_an_otherwise_successful_proof(
    tmp_path: Path,
    reachable: bool,
    expected_status: FormalStatus,
    expected_cover: CoverStatus,
) -> None:
    evidence = build_formal_bundle(_config(tmp_path, reachable=reachable))
    result = run_formal_bundle(evidence)
    assert result.status is expected_status
    assert result.cover_status is expected_cover
    assert (evidence.bundle_dir / "cover.log").is_file()
    if not reachable:
        assert "critical cover" in result.message
