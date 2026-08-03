"""Restricted formal-only automatic local-variable capture semantics."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.formal_flow import (
    AttemptMode,
    FormalRunConfig,
    FormalStatus,
    build_formal_bundle,
    run_formal_bundle,
)
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import DisableIff, PropLocalCapture
from sva2rtl.normalizer import normalize

pytestmark = pytest.mark.skipif(
    shutil.which("slang") is None, reason="slang is not installed"
)


def _property_source(
    tmp_path: Path,
    *,
    local_decl: str = "logic saved;",
    implication: str = "|->",
    delay: str = "##1",
) -> Path:
    source = tmp_path / "property.sv"
    source.write_text(
        "module spec(input logic clk, rst_n, req, ack, data);\n"
        "  sequence capture_then_check;\n"
        f"    {local_decl}\n"
        f"    (req, saved = data) {delay} (ack && (data == saved));\n"
        "  endsequence\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) "
        f"req {implication} capture_then_check);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return source


def _dut_source(tmp_path: Path, *, good: bool, stable_data: bool = True) -> Path:
    source = tmp_path / "dut.sv"
    source.write_text(
        "module dut(input logic clk, rst_n, req, output logic ack, data);\n"
        f"  assign ack = 1'b{1 if good else 0};\n"
        f"  assign data = {"1'b0" if stable_data else "req"};\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return source


def _config(tmp_path: Path, *, good: bool = True) -> FormalRunConfig:
    return FormalRunConfig(
        dut_sources=(_dut_source(tmp_path, good=good),),
        property_file=_property_source(tmp_path),
        property_name="p",
        top="dut",
        output_dir=tmp_path / "evidence",
        depth=12,
        timeout_seconds=60,
    )


def test_real_source_imports_one_typed_per_attempt_local() -> None:
    # tmp_path is intentionally avoided here so the source lifecycle is visible
    # in the caller-facing tests below.
    from tempfile import TemporaryDirectory

    with TemporaryDirectory(prefix="sva2rtl-local-") as directory:
        source = _property_source(Path(directory))
        node, clock, text, label = import_assertion(invoke_slang(source))
    assert isinstance(node, DisableIff)
    assert isinstance(node.body, PropLocalCapture)
    assert node.body.local_name == "saved"
    assert node.body.delay_cycles == 1
    assert node.body.overlapping is True
    assert clock.signal == "clk"
    assert label == "p"
    assert "saved = data" in text
    with pytest.raises(UnsupportedConstruct, match="PropLocalCapture"):
        compose(normalize(node), clock, label, text)


@pytest.mark.formal
def test_bundle_uses_private_witness_register_not_a_dut_local_port(
    tmp_path: Path,
) -> None:
    evidence = build_formal_bundle(_config(tmp_path))
    bind = (evidence.bundle_dir / "formal_bind.sv").read_text(encoding="utf-8")
    assert evidence.manifest["backend"] == "symbolic-witness-local"
    assert "logic captured_q" in bind
    assert "captured_q <= obs_" in bind
    assert "== captured_q" in bind
    assert ".saved(" not in bind and "input logic saved" not in bind
    assert "evidence/property.sv" not in evidence.manifest["yosys_inputs"]


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("sby", "yosys", "yices-smt2")),
    reason="requires the local safety formal toolchain",
)
@pytest.mark.formal
@pytest.mark.parametrize(
    ("good", "expected"),
    [(True, FormalStatus.PROVEN), (False, FormalStatus.FAILED)],
)
def test_real_solver_distinguishes_good_and_bad_local_capture(
    tmp_path: Path, good: bool, expected: FormalStatus
) -> None:
    result = run_formal_bundle(build_formal_bundle(_config(tmp_path, good=good)))
    assert result.status is expected
    if good:
        assert result.cover_status.value == "REACHED"
    else:
        assert result.trace_paths


@pytest.mark.skipif(
    any(shutil.which(tool) is None for tool in ("sby", "yosys", "yices-smt2")),
    reason="requires the local safety formal toolchain",
)
@pytest.mark.formal
def test_solver_checks_saved_value_instead_of_current_capture_expression(
    tmp_path: Path,
) -> None:
    config = FormalRunConfig(
        dut_sources=(_dut_source(tmp_path, good=True, stable_data=False),),
        property_file=_property_source(tmp_path),
        property_name="p",
        top="dut",
        output_dir=tmp_path / "evidence",
        depth=12,
        timeout_seconds=60,
    )
    result = run_formal_bundle(build_formal_bundle(config))
    assert result.status is FormalStatus.FAILED
    assert result.trace_paths


@pytest.mark.parametrize(
    ("local_decl", "implication", "delay", "construct"),
    [
        ("logic [1:0] saved;", "|->", "##1", "local-variable type or lifetime"),
        ("logic saved; logic other;", "|->", "##1", "multiple local variables"),
        ("logic saved;", "|=>", "##1", "non-overlapping local-variable capture"),
        ("logic saved;", "|->", "##[1:2]", "local-variable delay"),
    ],
)
def test_non_whitelisted_local_shapes_reject_precisely(
    tmp_path: Path,
    local_decl: str,
    implication: str,
    delay: str,
    construct: str,
) -> None:
    source = _property_source(
        tmp_path,
        local_decl=local_decl,
        implication=implication,
        delay=delay,
    )
    with pytest.raises(UnsupportedConstruct) as caught:
        import_assertion(invoke_slang(source))
    assert caught.value.construct_name == construct


def test_monitor_attempt_mode_rejects_formal_only_local_capture(
    tmp_path: Path,
) -> None:
    config = FormalRunConfig(
        **{**_config(tmp_path).__dict__, "attempt_mode": AttemptMode.MONITOR}
    )
    with pytest.raises(UnsupportedConstruct, match="formal-only"):
        build_formal_bundle(config)
