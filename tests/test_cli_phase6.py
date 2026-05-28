"""Tests for Phase 6 CLI flags: --version, --dump-ast, --dump-ir, --property, --verilog.

All tests use CliRunner + unittest.mock.patch — no slang binary required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sva2rtl.cli import main
from sva2rtl.debug import format_dump_ir
from sva2rtl.ir import BoolExpr, ClockSpec, SourceLoc

# ── Shared fixtures ────────────────────────────────────────────────────────

_LOC = SourceLoc(file="test.sv", line=3, col=5)
_CLOCK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)
_MOCK_AST: dict[str, object] = {"design": {"members": []}}
_MOCK_SV_TEXT = "module sva_my_check(input logic clk);\nendmodule\n"


@pytest.fixture()
def runner() -> CliRunner:
    """Shared CliRunner instance."""
    return CliRunner()


@pytest.fixture()
def sv_file(tmp_path: Path) -> Path:
    """Create a temporary .sv file so click.Path(exists=True) is satisfied."""
    sv = tmp_path / "test.sv"
    sv.write_text(
        "module t(input logic clk, a, b);\n"
        "  p: assert property (@(posedge clk) a && b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return sv


# ── Test 1: --version ──────────────────────────────────────────────────────


def test_version_flag(runner: CliRunner) -> None:
    """--version exits 0 and prints version string."""
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "version" in result.output
    # Version should contain a number
    assert any(c.isdigit() for c in result.output)


# ── Test 2: --dump-ast exits 0 with valid JSON ────────────────────────────


def test_dump_ast_exits_0(runner: CliRunner, sv_file: Path) -> None:
    """--dump-ast exits 0."""
    mock_ast = {"design": {"members": [{"kind": "Instance", "name": "t"}]}}
    with patch("sva2rtl.cli.invoke_slang", return_value=mock_ast):
        result = runner.invoke(main, [str(sv_file), "--dump-ast"])

    assert result.exit_code == 0


def test_dump_ast_valid_json(runner: CliRunner, sv_file: Path) -> None:
    """--dump-ast output is valid JSON."""
    mock_ast = {"design": {"members": [{"kind": "Instance", "name": "t"}]}}
    with patch("sva2rtl.cli.invoke_slang", return_value=mock_ast):
        result = runner.invoke(main, [str(sv_file), "--dump-ast"])

    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "design" in parsed


def test_dump_ast_no_rtl_emitted(runner: CliRunner, sv_file: Path) -> None:
    """--dump-ast does not emit RTL (import_all_assertions is never called)."""
    mock_ast = {"design": {"members": []}}
    with patch("sva2rtl.cli.invoke_slang", return_value=mock_ast):
        with patch("sva2rtl.cli.import_all_assertions") as mock_import:
            result = runner.invoke(main, [str(sv_file), "--dump-ast"])

    assert result.exit_code == 0
    mock_import.assert_not_called()


# ── Test 3: --dump-ir exits 0 and shows header ───────────────────────────


def test_dump_ir_exits_0(runner: CliRunner, sv_file: Path) -> None:
    """--dump-ir exits 0."""
    node = BoolExpr(text="(a && b)", source_loc=_LOC)
    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch(
            "sva2rtl.cli.import_all_assertions",
            return_value=[(node, _CLOCK, "(a && b)", "p")],
        ):
            result = runner.invoke(main, [str(sv_file), "--dump-ir"])

    assert result.exit_code == 0


def test_dump_ir_shows_header(runner: CliRunner, sv_file: Path) -> None:
    """--dump-ir output contains '=== Normalized IR ===' header."""
    node = BoolExpr(text="(a && b)", source_loc=_LOC)
    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch(
            "sva2rtl.cli.import_all_assertions",
            return_value=[(node, _CLOCK, "(a && b)", "p")],
        ):
            result = runner.invoke(main, [str(sv_file), "--dump-ir"])

    assert result.exit_code == 0
    assert "=== Normalized IR ===" in result.output


def test_dump_ir_no_rtl_emitted(runner: CliRunner, sv_file: Path) -> None:
    """--dump-ir does not call compose or emit."""
    node = BoolExpr(text="(a && b)", source_loc=_LOC)
    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch(
            "sva2rtl.cli.import_all_assertions",
            return_value=[(node, _CLOCK, "(a && b)", "p")],
        ):
            with patch("sva2rtl.cli.compose") as mock_compose:
                result = runner.invoke(main, [str(sv_file), "--dump-ir"])

    assert result.exit_code == 0
    mock_compose.assert_not_called()


# ── Test 4: --property match ──────────────────────────────────────────────


def test_property_filter_match(runner: CliRunner, sv_file: Path) -> None:
    """--property selects the matching assertion by label."""
    node_a = BoolExpr(text="a", source_loc=_LOC)
    node_b = BoolExpr(text="b", source_loc=_LOC)
    assertions = [
        (node_a, _CLOCK, "a", "check_a"),
        (node_b, _CLOCK, "b", "check_b"),
    ]
    mock_checker = MagicMock()
    mock_checker.children = ()

    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch("sva2rtl.cli.import_all_assertions", return_value=assertions):
            with patch("sva2rtl.cli.compose", return_value=mock_checker) as mock_compose:
                with patch("sva2rtl.cli.optimize", return_value=mock_checker):
                    with patch("sva2rtl.cli.emit", return_value=_MOCK_SV_TEXT):
                        with patch("sva2rtl.cli.write_output"):
                            result = runner.invoke(
                                main, [str(sv_file), "--property", "check_b"]
                            )

    assert result.exit_code == 0
    # compose should have been called with the normalized version of node_b
    mock_compose.assert_called_once()


# ── Test 5: --property no-match -> exit code 2 + SVA-E005 ────────────────


def test_property_filter_no_match(runner: CliRunner, sv_file: Path) -> None:
    """--property with non-existent label exits 2 with SVA-E005."""
    node = BoolExpr(text="a", source_loc=_LOC)
    assertions = [(node, _CLOCK, "a", "check_a")]

    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch("sva2rtl.cli.import_all_assertions", return_value=assertions):
            result = runner.invoke(main, [str(sv_file), "--property", "nonexistent"])

    assert result.exit_code == 2
    assert "SVA-E005" in result.output
    assert "nonexistent" in result.output
    assert "check_a" in result.output


# ── Test 6: --verilog flag threading ──────────────────────────────────────


def test_verilog_flag_threaded_to_emit(runner: CliRunner, sv_file: Path) -> None:
    """--verilog flag is passed through to emit() as verilog_mode=True."""
    node = BoolExpr(text="(a && b)", source_loc=_LOC)
    mock_checker = MagicMock()
    mock_checker.children = ()

    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch(
            "sva2rtl.cli.import_all_assertions",
            return_value=[(node, _CLOCK, "(a && b)", "p")],
        ):
            with patch("sva2rtl.cli.compose", return_value=mock_checker):
                with patch("sva2rtl.cli.optimize", return_value=mock_checker):
                    with patch("sva2rtl.cli.emit", return_value=_MOCK_SV_TEXT) as mock_emit:
                        with patch("sva2rtl.cli.write_output"):
                            result = runner.invoke(
                                main, [str(sv_file), "--verilog"]
                            )

    assert result.exit_code == 0
    mock_emit.assert_called_once()
    _, kwargs = mock_emit.call_args
    assert kwargs.get("verilog_mode") is True


# ── Test 7: multi-property default (no --property) emits all ──────────────


def test_multi_property_emits_all(runner: CliRunner, sv_file: Path) -> None:
    """Without --property, all assertions are compiled."""
    node_a = BoolExpr(text="a", source_loc=_LOC)
    node_b = BoolExpr(text="b", source_loc=_LOC)
    assertions = [
        (node_a, _CLOCK, "a", "check_a"),
        (node_b, _CLOCK, "b", "check_b"),
    ]
    mock_checker = MagicMock()
    mock_checker.children = ()

    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch("sva2rtl.cli.import_all_assertions", return_value=assertions):
            with patch("sva2rtl.cli.compose", return_value=mock_checker) as mock_compose:
                with patch("sva2rtl.cli.optimize", return_value=mock_checker):
                    with patch(
                        "sva2rtl.cli.emit_all",
                        return_value={"mod_a": _MOCK_SV_TEXT, "mod_b": _MOCK_SV_TEXT},
                    ):
                        with patch("sva2rtl.cli.write_output_dir"):
                            result = runner.invoke(main, [str(sv_file)])

    assert result.exit_code == 0
    # compose should be called once per assertion (2 times)
    assert mock_compose.call_count == 2


# ── Test 8: format_dump_ir shows source location ─────────────────────────


def test_format_dump_ir_includes_loc() -> None:
    """format_dump_ir() includes source location info."""
    node = BoolExpr(text="(a && b)", source_loc=SourceLoc("my_file.sv", 10, 3))
    output = format_dump_ir(node)
    assert "=== Normalized IR ===" in output
    assert "BoolExpr" in output
    assert "my_file.sv:10:3" in output


# ── Test 9: PropertyNotFound error format ─────────────────────────────────


def test_property_not_found_error_format() -> None:
    """PropertyNotFound.__str__ matches expected SVA-E005 format."""
    from sva2rtl.errors import PropertyNotFound

    err = PropertyNotFound(
        message="property 'foo' not found",
        property_name="foo",
        available=["bar", "baz"],
    )
    s = str(err)
    assert "SVA-E005" in s
    assert "'foo'" in s
    assert "bar" in s
    assert "baz" in s
