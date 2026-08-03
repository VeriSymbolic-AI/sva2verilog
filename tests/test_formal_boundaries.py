"""Phase 23 explicit multi-clock and value-domain boundary evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from sva2rtl.formal_cli import main


def _write_sources(tmp_path: Path, property_text: str) -> tuple[Path, Path]:
    dut = tmp_path / "dut.sv"
    prop = tmp_path / "property.sv"
    dut.write_text(
        "module dut(input logic clk, clk2, rst_n, a, b); endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module spec(input logic clk, clk2, rst_n, a, b);\n"
        f"  p: assert property ({property_text});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return dut, prop


def _invoke(
    tmp_path: Path, property_text: str, *extra: str
) -> tuple[Result, Path]:
    dut, prop = _write_sources(tmp_path, property_text)
    output = tmp_path / "evidence"
    result = CliRunner().invoke(
        main,
        [
            "--dut",
            str(dut),
            "--property-file",
            str(prop),
            "--property",
            "p",
            "--top",
            "dut",
            "--output",
            str(output),
            *extra,
        ],
    )
    return result, output


@pytest.mark.skipif(shutil.which("slang") is None, reason="slang is not installed")
def test_multiclock_is_sanitized_unsupported_evidence_not_clock_collapse(
    tmp_path: Path,
) -> None:
    result, output = _invoke(
        tmp_path,
        "@(posedge clk) a ##1 @(posedge clk2) b",
        "--clock",
        "clk",
        "--compile-only",
    )
    assert result.exit_code == 12
    assert "UNSUPPORTED" not in result.output  # diagnostic names the exact boundary
    assert "single-clock" in result.output
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    outcome = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "UNSUPPORTED"
    assert manifest["backend"] == "unsupported-boundary"
    assert manifest["yosys_inputs"] == []
    assert manifest["semantic_profile"]["sha256"] == hashlib.sha256(
        (output / "evidence" / "semantic_profile.json").read_bytes()
    ).hexdigest()
    assert outcome["status"] == "UNSUPPORTED"
    assert not (output / "formal.sby").exists()
    serialized = json.dumps(manifest, sort_keys=True)
    assert str(tmp_path.resolve()) not in serialized
    assert "/private/" not in serialized and "pytest-of-" not in serialized


@pytest.mark.skipif(shutil.which("slang") is None, reason="slang is not installed")
@pytest.mark.parametrize("literal", ["1'bx", "1'bz"])
def test_x_z_literals_reject_under_named_two_state_profile(
    tmp_path: Path, literal: str
) -> None:
    result, output = _invoke(
        tmp_path,
        f"@(posedge clk) a == {literal}",
        "--logic-semantics",
        "two-state",
        "--compile-only",
    )
    assert result.exit_code == 12
    profile = json.loads(
        (output / "evidence" / "semantic_profile.json").read_text(encoding="utf-8")
    )
    outcome = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert profile["logic_semantics"] == "two-state"
    assert profile["x_z_semantics"] == "unsupported"
    assert outcome["status"] == "UNSUPPORTED"
    assert "Four-state literal" in outcome["message"]


def test_unknown_logic_profile_is_a_usage_error(tmp_path: Path) -> None:
    result, output = _invoke(
        tmp_path,
        "@(posedge clk) a",
        "--logic-semantics",
        "four-state",
        "--compile-only",
    )
    assert result.exit_code == 2
    assert "Invalid value" in result.output
    assert not output.exists()
