"""Fast contract tests for the user-DUT formal evidence workflow."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sva2rtl.formal_flow import (
    FormalMode,
    FormalRunConfig,
    FormalStatus,
    build_formal_bundle,
    classify_sby_result,
    render_formal_bind,
)
from sva2rtl.ir import CheckerNode, SourceLoc


def _checker() -> CheckerNode:
    return CheckerNode(
        template_name="bool_expr",
        module_name="sva_req_ack",
        params={
            "module_name": "sva_req_ack",
            "clock_signal": "clk",
            "clock_edge": "posedge",
            "expression": "(!req) || ack",
            "source_loc": "property.sv:2:3",
            "original_sva": "req |-> ack",
            "property_label": "req_ack",
            "sva2rtl_version": "test",
        },
        observed_signals=(("req", "req"), ("ack", "ack")),
        observed_signal_widths=(("req", 1), ("ack", 1)),
        source_loc=SourceLoc("property.sv", 2, 3),
    )


def _config(tmp_path: Path, *, mode: FormalMode = FormalMode.PROVE) -> FormalRunConfig:
    dut = tmp_path / "dut.sv"
    prop = tmp_path / "property.sv"
    dut.write_text("module dut(input clk, rst_n, req, ack); endmodule\n", encoding="utf-8")
    prop.write_text(
        "module spec(input clk, rst_n, req, ack);\n"
        "req_ack: assert property (@(posedge clk) req |-> ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        top="dut",
        output_dir=tmp_path / "evidence",
        property_name="req_ack",
        mode=mode,
        depth=12,
        timeout_seconds=15,
    )


@pytest.mark.parametrize("field", ["top", "clock", "reset"])
def test_config_rejects_unsafe_identifiers(tmp_path: Path, field: str) -> None:
    config = _config(tmp_path)
    values = {**config.__dict__, field: "bad; shell"}
    with pytest.raises(ValueError, match="identifier"):
        FormalRunConfig(**values)


def test_config_rejects_nonpositive_limits(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with pytest.raises(ValueError, match="depth"):
        FormalRunConfig(**{**config.__dict__, "depth": 0})
    with pytest.raises(ValueError, match="timeout"):
        FormalRunConfig(**{**config.__dict__, "timeout_seconds": -1})


def test_classify_prove_pass_as_proven() -> None:
    status, _ = classify_sby_result(
        mode=FormalMode.PROVE,
        returncode=0,
        output="SBY 1: DONE (PASS, rc=0)",
    )
    assert status is FormalStatus.PROVEN


def test_classify_bmc_pass_as_unknown_not_proven() -> None:
    status, message = classify_sby_result(
        mode=FormalMode.BMC,
        returncode=0,
        output="SBY 1: DONE (PASS, rc=0)",
    )
    assert status is FormalStatus.UNKNOWN
    assert "bounded" in message.lower()


def test_classify_counterexample_timeout_and_ambiguous_failure() -> None:
    failed, _ = classify_sby_result(
        mode=FormalMode.PROVE,
        returncode=1,
        output="SBY 1: DONE (FAIL, rc=2) counterexample trace.vcd",
    )
    timed_out, _ = classify_sby_result(
        mode=FormalMode.PROVE,
        returncode=-9,
        output="partial",
        timed_out=True,
    )
    error, _ = classify_sby_result(
        mode=FormalMode.PROVE,
        returncode=1,
        output="engine crashed",
    )
    assert failed is FormalStatus.FAILED
    assert timed_out is FormalStatus.TIMEOUT
    assert error is FormalStatus.ERROR


def test_formal_bind_uses_explicit_ports_assert_and_cover() -> None:
    text = render_formal_bind(_checker(), top="dut", clock="clk", reset="rst_n")
    assert "bind dut sva2rtl_formal_bind" in text
    assert ".req(req)" in text
    assert ".ack(ack)" in text
    assert ".fail(monitor_fail)" in text
    assert "assert (!monitor_fail);" in text
    assert "cover (monitor_attempt_fired);" in text
    assert ".*" not in text


def test_bundle_excludes_property_from_sby_and_uses_relative_manifest_paths(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    with patch("sva2rtl.formal_flow._compile_checker", return_value=_checker()):
        evidence = build_formal_bundle(config)

    sby_text = (evidence.bundle_dir / "formal.sby").read_text(encoding="utf-8")
    manifest = json.loads(
        (evidence.bundle_dir / "manifest.json").read_text(encoding="utf-8")
    )

    assert "evidence/property.sv" not in sby_text
    assert "property.sv" not in sby_text
    assert "dut_000.sv" in sby_text
    assert "formal_bind.sv" in sby_text
    assert (evidence.bundle_dir / "evidence" / "property.sv").exists()
    assert manifest["property"]["path"] == "evidence/property.sv"
    assert len(manifest["property"]["sha256"]) == 64
    serialized = json.dumps(manifest, sort_keys=True)
    assert str(tmp_path.resolve()) not in serialized
    assert manifest["assumptions"] == [
        "reset is asserted on the first sampled cycle",
        "reset is deasserted on every later sampled cycle",
        "monitor start is asserted on every non-reset cycle",
        "monitor disable_i is held low",
    ]


def test_existing_nonempty_bundle_requires_force(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.output_dir.mkdir()
    (config.output_dir / "keep.txt").write_text("do not overwrite\n", encoding="utf-8")
    with patch("sva2rtl.formal_flow._compile_checker", return_value=_checker()):
        with pytest.raises(FileExistsError, match="--force"):
            build_formal_bundle(config)
