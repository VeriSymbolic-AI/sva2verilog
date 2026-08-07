"""Phase 21 evidence, decomposition, and anti-vacuity contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from sva2rtl.errors import UnsupportedConstruct
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


def _write_certificate(tmp_path: Path, dut: Path, property_path: Path) -> Path:
    subproperty = tmp_path / "subproperty.sv"
    relation_property = tmp_path / "relation-property.sv"
    subproperty.write_text(
        "module sub_spec(input logic clk, rst_n, req, ack);\n"
        "  sub_p: assert property (@(posedge clk) disable iff (!rst_n) ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    relation_property.write_text(
        "module relation_spec(input logic clk, rst_n, req, ack);\n"
        "  relation_p: assert property (@(posedge clk) disable iff (!rst_n) ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    property_hash = _sha256(property_path)
    subproperty_hash = _sha256(subproperty)
    dut_hashes = [_sha256(dut)]
    sub_evidence = build_formal_bundle(
        FormalRunConfig(
            dut_sources=(dut,),
            property_file=subproperty,
            property_name="sub_p",
            top="dut",
            output_dir=tmp_path / "sub-proof",
            timeout_seconds=60,
        )
    )
    sub_result = run_formal_bundle(sub_evidence)
    assert sub_result.status is FormalStatus.PROVEN
    proof = sub_evidence.bundle_dir / "result.json"
    checker = sub_result.checker

    relation_evidence = build_formal_bundle(
        FormalRunConfig(
            dut_sources=(dut,),
            property_file=relation_property,
            property_name="relation_p",
            top="dut",
            output_dir=tmp_path / "relation-proof",
            timeout_seconds=60,
        )
    )
    relation_result = run_formal_bundle(relation_evidence)
    assert relation_result.status is FormalStatus.PROVEN
    relation_proof = relation_evidence.bundle_dir / "result.json"
    relation_payload = json.loads(relation_proof.read_text(encoding="utf-8"))
    relation_payload.update(
        {
            "relation": "equivalent",
            "original_property_sha256": property_hash,
            "subproperty_sha256s": [subproperty_hash],
            "dut_source_sha256s": dut_hashes,
        }
    )
    relation_proof.write_text(
        json.dumps(relation_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    relation_checker = relation_result.checker
    certificate = tmp_path / "decomposition.json"
    certificate.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "relation": "equivalent",
                "relation_status": "PROVEN",
                "relation_checker": relation_checker,
                "relation_proof_artifact_path": relation_proof.relative_to(
                    tmp_path
                ).as_posix(),
                "relation_proof_artifact_sha256": _sha256(relation_proof),
                "original_property_sha256": property_hash,
                "dut_source_sha256s": dut_hashes,
                "subproperties": [
                    {
                        "id": "bounded_obligation_1",
                        "property_path": subproperty.name,
                        "property_sha256": subproperty_hash,
                        "obligation_status": "PROVEN",
                        "checker": checker,
                        "proof_artifact_path": proof.relative_to(tmp_path).as_posix(),
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
    certificate = _write_certificate(tmp_path, dut, prop)
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
    assert payload["subproperties"][0]["property_path"].startswith("decomposition/")
    assert str(tmp_path) not in normalized.read_text(encoding="utf-8")


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_unverified_artifact_hash(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    payload = json.loads(certificate.read_text(encoding="utf-8"))
    payload["subproperties"][0]["proof_artifact_sha256"] = "0" * 64
    certificate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="proof artifact hash"):
        build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_fabricated_proven_json(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    fabricated = tmp_path / "fabricated-result.json"
    fabricated.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "status": "PROVEN",
                "mode": "prove",
                "cover_status": "REACHED",
                "returncode": 0,
                "cover_returncode": 0,
            }
        ),
        encoding="utf-8",
    )
    payload = json.loads(certificate.read_text(encoding="utf-8"))
    payload["subproperties"][0]["proof_artifact_path"] = fabricated.name
    payload["subproperties"][0]["proof_artifact_sha256"] = _sha256(fabricated)
    certificate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="replay manifest"):
        build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_tampered_pass_log(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    payload = json.loads(certificate.read_text(encoding="utf-8"))
    proof = tmp_path / payload["subproperties"][0]["proof_artifact_path"]
    proof_result = json.loads(proof.read_text(encoding="utf-8"))
    proof_log = proof.parent / proof_result["log_path"]
    proof_log.write_text(
        proof_log.read_text(encoding="utf-8") + "tampered after proof\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="log_path hash"):
        build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_unexecuted_replay_contract(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    certificate_payload = json.loads(certificate.read_text(encoding="utf-8"))
    proof = tmp_path / certificate_payload["subproperties"][0][
        "proof_artifact_path"
    ]
    proof_payload = json.loads(proof.read_text(encoding="utf-8"))
    proof_payload["executed_commands"] = []
    proof.write_text(
        json.dumps(proof_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    certificate_payload["subproperties"][0]["proof_artifact_sha256"] = _sha256(
        proof
    )
    certificate.write_text(
        json.dumps(certificate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="complete replay contract"):
        build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_a_proof_with_different_context(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    original_certificate = certificate.read_text(encoding="utf-8")
    certificate_payload = json.loads(original_certificate)
    proof = tmp_path / certificate_payload["subproperties"][0]["proof_artifact_path"]
    original_proof = proof.read_text(encoding="utf-8")
    manifest = proof.parent / "manifest.json"
    original_manifest = manifest.read_text(encoding="utf-8")

    for field, value in (
        ("top", "different_top"),
        ("mode", "bmc"),
        ("attempt_mode", "monitor"),
    ):
        manifest_payload = json.loads(original_manifest)
        manifest_payload["config"][field] = value
        manifest.write_text(
            json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        proof_payload = json.loads(original_proof)
        proof_payload["manifest_sha256"] = _sha256(manifest)
        proof.write_text(
            json.dumps(proof_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        certificate_payload = json.loads(original_certificate)
        certificate_payload["subproperties"][0]["proof_artifact_sha256"] = _sha256(
            proof
        )
        certificate.write_text(
            json.dumps(certificate_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="formal context"):
            build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_checker_not_bound_to_manifest(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    certificate_payload = json.loads(certificate.read_text(encoding="utf-8"))
    proof = tmp_path / certificate_payload["subproperties"][0]["proof_artifact_path"]
    proof_payload = json.loads(proof.read_text(encoding="utf-8"))
    proof_payload["checker"] = "fabricated_checker"
    proof.write_text(
        json.dumps(proof_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    certificate_payload["subproperties"][0]["proof_artifact_sha256"] = _sha256(
        proof
    )
    certificate_payload["subproperties"][0]["checker"] = "fabricated_checker"
    certificate.write_text(
        json.dumps(certificate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="checker is not bound"):
        build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.formal
@requires_formal_stack
def test_decomposition_rejects_relation_proof_for_different_dut(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    certificate_payload = json.loads(certificate.read_text(encoding="utf-8"))
    relation_result = (
        tmp_path / certificate_payload["relation_proof_artifact_path"]
    )
    result_payload = json.loads(relation_result.read_text(encoding="utf-8"))
    manifest = relation_result.parent / "manifest.json"
    manifest_payload = json.loads(manifest.read_text(encoding="utf-8"))
    relation_dut = relation_result.parent / manifest_payload["dut_sources"][0]["path"]
    relation_dut.write_text(
        "module dut(input logic clk, rst_n, req, output logic ack);\n"
        "  assign ack = 1'b0;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    manifest_payload["dut_sources"][0]["sha256"] = _sha256(relation_dut)
    manifest.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result_payload["manifest_sha256"] = _sha256(manifest)
    relation_result.write_text(
        json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    certificate_payload["relation_proof_artifact_sha256"] = _sha256(
        relation_result
    )
    certificate.write_text(
        json.dumps(certificate_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="DUT inputs"):
        build_formal_bundle(_config(tmp_path, certificate=certificate))


@pytest.mark.formal
@requires_formal_stack
def test_verified_decomposition_routes_an_unsupported_original_without_yosys(
    tmp_path: Path,
) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / "aggregate-evidence",
        decomposition_certificate=certificate,
    )
    unsupported = UnsupportedConstruct(
        message="test-only unsupported original shape",
        construct_name="test-only decomposition boundary",
    )

    with patch("sva2rtl.formal_flow._compile_checker", side_effect=unsupported):
        evidence = build_formal_bundle(config)

    assert evidence.manifest["backend"] == "verified-decomposition"
    assert evidence.manifest["yosys_inputs"] == []
    assert not (evidence.bundle_dir / "formal.sby").exists()
    dut.write_text("changed after evidence snapshot\n", encoding="utf-8")
    prop.write_text("changed after evidence snapshot\n", encoding="utf-8")
    result = run_formal_bundle(evidence)
    assert result.status is FormalStatus.PROVEN
    assert result.cover_status is CoverStatus.REACHED
    assert result.replay_commands == ()


@pytest.mark.formal
@requires_formal_stack
def test_verified_decomposition_rejects_bmc_mode(tmp_path: Path) -> None:
    dut, prop = _sources(tmp_path)
    certificate = _write_certificate(tmp_path, dut, prop)
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / "aggregate-evidence",
        mode=FormalMode.BMC,
        decomposition_certificate=certificate,
    )
    unsupported = UnsupportedConstruct(
        message="test-only unsupported original shape",
        construct_name="test-only decomposition boundary",
    )

    with (
        patch("sva2rtl.formal_flow._compile_checker", side_effect=unsupported),
        pytest.raises(ValueError, match="requires --mode prove"),
    ):
        build_formal_bundle(config)
    assert not config.output_dir.exists()


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
