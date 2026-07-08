"""End-to-end integration tests for Phase 6 requirements.

Validates CLI-01, CLI-02, CLI-03, CLI-04, OUT-05 as a post-integration
verification layer. Tests exercise the full assembled pipeline after
Plans 6.1 and 6.2 are merged.

All tests use CliRunner or direct API calls — no slang binary required
unless marked with @pytest.mark.simulation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from sva2rtl.ast_importer import import_assertion
from sva2rtl.cli import main
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.ir import BoolExpr, ClockSpec, SourceLoc
from sva2rtl.normalizer import normalize

# ── Fixture paths ─────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
_LOC = SourceLoc(file="test.sv", line=1, col=1)
_CLOCK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _load(name: str) -> dict[str, Any]:
    """Load a JSON fixture file."""
    return cast(dict[str, Any], json.loads((_FIXTURES / name).read_text(encoding="utf-8")))


@pytest.fixture()
def runner() -> CliRunner:
    """Shared CliRunner instance."""
    return CliRunner()


@pytest.fixture()
def sv_file(tmp_path: Path) -> Path:
    """Create a temporary .sv file for CLI tests."""
    sv = tmp_path / "test.sv"
    sv.write_text(
        "module t(input logic clk, a, b);\n"
        "  assert property (@(posedge clk) a && b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return sv


# ── CLI-01: All flags accepted ────────────────────────────────────────────


def test_cli01_all_flags_accepted(runner: CliRunner) -> None:
    """Validates CLI-01: single entry point with all required flags."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    # All required flags from CLI-01
    assert "--output" in result.output
    assert "--property" in result.output
    assert "--verilog" in result.output
    assert "--slang-path" in result.output
    # Debug flags (CLI-02, CLI-03, CLI-04)
    assert "--dump-ast" in result.output
    assert "--dump-ir" in result.output
    assert "--dump-tree" in result.output
    # Optimization + version
    assert "--no-optimize" in result.output
    assert "--version" in result.output


# ── CLI-02: --dump-ast prints valid JSON ──────────────────────────────────


def test_cli02_dump_ast_valid_json(runner: CliRunner, sv_file: Path) -> None:
    """Validates CLI-02: --dump-ast prints raw slang JSON AST and exits 0."""
    mock_ast = {"design": {"members": [{"kind": "Instance", "name": "t"}]}}
    with patch("sva2rtl.cli.invoke_slang", return_value=mock_ast):
        result = runner.invoke(main, [str(sv_file), "--dump-ast"])
    assert result.exit_code == 0
    # Output must be valid JSON
    parsed = json.loads(result.output)
    assert parsed == mock_ast


# ── CLI-03: --dump-ir shows normalized tree ───────────────────────────────


def test_cli03_dump_ir_shows_tree(runner: CliRunner, sv_file: Path) -> None:
    """Validates CLI-03: --dump-ir prints normalized IR tree and exits 0."""
    node = BoolExpr(text="a && b", source_loc=_LOC)
    assertions = [(node, _CLOCK, "a && b", None)]
    with (
        patch("sva2rtl.cli.invoke_slang", return_value={"design": {}}),
        patch("sva2rtl.cli.import_all_assertions", return_value=assertions),
    ):
        result = runner.invoke(main, [str(sv_file), "--dump-ir"])
    assert result.exit_code == 0
    assert "=== Normalized IR ===" in result.output
    assert "BoolExpr" in result.output


# ── CLI-04: --dump-tree shows CheckerNode tree ────────────────────────────


def test_cli04_dump_tree_shows_checker(runner: CliRunner, sv_file: Path) -> None:
    """Validates CLI-04: --dump-tree prints CheckerNode tree and exits 0."""
    ast = _load("bool_simple.json")
    with patch("sva2rtl.cli.invoke_slang", return_value=ast):
        result = runner.invoke(main, [str(sv_file), "--dump-tree"])
    assert result.exit_code == 0
    assert "=== Composition Tree ===" in result.output
    assert "CheckerNode:" in result.output


# ── OUT-05: Verilog-2001 output has no SV keywords ───────────────────────


@pytest.mark.parametrize(
    "fixture",
    [
        "bool_simple.json",
        "bool_labeled.json",
        "delay_fixed.json",
        "delay_range.json",
        "rose.json",
        "fell.json",
        "stable.json",
        "past.json",
        "rep_fixed.json",
    ],
)
def test_out05_verilog_no_sv_keywords(fixture: str) -> None:
    """Validates OUT-05: --verilog output contains no SystemVerilog keywords."""
    ast = _load(fixture)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker, verilog_mode=True)

    for mod_name, sv_text in modules.items():
        # Filter out comments for keyword checks
        code_lines = [
            ln for ln in sv_text.splitlines() if not ln.strip().startswith("//")
        ]
        code = "\n".join(code_lines)
        assert "logic" not in code, f"{mod_name}: 'logic' found in Verilog-2001 output"
        assert "always_ff" not in code, f"{mod_name}: 'always_ff' in Verilog-2001 output"
        assert "<= '0" not in code, f"{mod_name}: tick-zero literal in Verilog-2001 output"


# ── OUT-05: Verilog-2001 compiles with iverilog -g2001 ─────────────────────


@pytest.mark.simulation
def test_out05_verilog_compiles_iverilog(tmp_path: Path, simulator: str) -> None:
    """Validates OUT-05: Verilog-2001 output compiles clean with iverilog -g2001."""
    import subprocess

    if simulator != "iverilog":
        pytest.skip("Icarus-specific Verilog-2001 compile check")

    ast = _load("bool_simple.json")
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    sv_text = emit(checker, verilog_mode=True)

    out_file = tmp_path / "monitor.v"
    out_file.write_text(sv_text, encoding="utf-8")

    result = subprocess.run(
        ["iverilog", "-g2001", "-o", "/dev/null", str(out_file)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"iverilog -g2001 failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ── Multi-property: all assertions compiled ──────────────────────────────


def test_multi_property_all_compiled(runner: CliRunner, sv_file: Path, tmp_path: Path) -> None:
    """Without --property, all assertions in the file are compiled."""
    node_a = BoolExpr(text="a", source_loc=_LOC)
    node_b = BoolExpr(text="b", source_loc=_LOC)
    assertions = [
        (node_a, _CLOCK, "a", "check_a"),
        (node_b, _CLOCK, "b", "check_b"),
    ]
    out_dir = tmp_path / "out"
    with (
        patch("sva2rtl.cli.invoke_slang", return_value={"design": {}}),
        patch("sva2rtl.cli.import_all_assertions", return_value=assertions),
    ):
        result = runner.invoke(main, [str(sv_file), "--output", str(out_dir)])
    assert result.exit_code == 0
    # Both assertions should produce output files
    files = list(out_dir.glob("*.sv"))
    assert len(files) >= 2, f"Expected >=2 SV files, got {len(files)}: {files}"


# ── --property filter: single assertion ──────────────────────────────────


def test_property_filter_single(runner: CliRunner, sv_file: Path, tmp_path: Path) -> None:
    """--property selects only the named assertion for compilation."""
    node_a = BoolExpr(text="a", source_loc=_LOC)
    node_b = BoolExpr(text="b", source_loc=_LOC)
    assertions = [
        (node_a, _CLOCK, "a", "check_a"),
        (node_b, _CLOCK, "b", "check_b"),
    ]
    out_file = tmp_path / "out.sv"
    with (
        patch("sva2rtl.cli.invoke_slang", return_value={"design": {}}),
        patch("sva2rtl.cli.import_all_assertions", return_value=assertions),
    ):
        result = runner.invoke(
            main, [str(sv_file), "--property", "check_a", "--output", str(out_file)]
        )
    assert result.exit_code == 0
    sv_text = out_file.read_text(encoding="utf-8")
    # Should contain the check_a module
    assert "check_a" in sv_text


# ── --property no-match lists available ──────────────────────────────────


def test_property_filter_not_found_lists_available(
    runner: CliRunner, sv_file: Path
) -> None:
    """--property with non-existent name exits 2 and lists available labels."""
    node_a = BoolExpr(text="a", source_loc=_LOC)
    node_b = BoolExpr(text="b", source_loc=_LOC)
    assertions = [
        (node_a, _CLOCK, "a", "check_a"),
        (node_b, _CLOCK, "b", "check_b"),
    ]
    with (
        patch("sva2rtl.cli.invoke_slang", return_value={"design": {}}),
        patch("sva2rtl.cli.import_all_assertions", return_value=assertions),
    ):
        result = runner.invoke(main, [str(sv_file), "--property", "nonexistent"])
    assert result.exit_code == 2
    assert "SVA-E005" in result.output
    assert "check_a" in result.output
    assert "check_b" in result.output
