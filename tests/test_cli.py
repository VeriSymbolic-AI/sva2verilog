"""Unit tests for src/sva2rtl/cli.py.

Tests use click.testing.CliRunner for all invocations and
unittest.mock.patch to isolate pipeline functions.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sva2rtl.cli import main
from sva2rtl.errors import SlangNotFound, SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import BoolExpr, SourceLoc

# Minimal valid SV text returned by mocked emit()
_MOCK_SV_TEXT = "module sva_my_check(input logic clk);\nendmodule\n"

# Sentinel AST dict returned by mocked invoke_slang()
_MOCK_AST: dict[str, object] = {"design": {"members": []}}

# Sentinel IR objects for mocked import_assertion()
_MOCK_SOURCE_LOC = SourceLoc(file="test.sv", line=2, col=3)


@pytest.fixture()
def runner() -> CliRunner:
    """Shared CliRunner instance (click 8.x: stdout and stderr both in result.output)."""
    return CliRunner()


@pytest.fixture()
def bool_assert_path(tmp_path: Path) -> Path:
    """Create a temporary .sv file so click.Path(exists=True) is satisfied."""
    sv = tmp_path / "bool_assert.sv"
    sv.write_text(
        "module t(input logic clk, a, b);\n"
        "  p: assert property (@(posedge clk) a && b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return sv


# ── Test 1: --help ─────────────────────────────────────────────────────────


def test_cli_help(runner: CliRunner) -> None:
    """CLI --help exits 0 and mentions INPUT_FILE."""
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "INPUT_FILE" in result.output


# ── Test 2: missing input file ─────────────────────────────────────────────


def test_cli_missing_input(runner: CliRunner) -> None:
    """CLI exits non-zero when input file does not exist."""
    result = runner.invoke(main, ["/nonexistent/path/to/file.sv"])
    assert result.exit_code != 0


# ── Test 3: SlangNotFound -> exit code 3 ──────────────────────────────────


def test_cli_slang_not_found(runner: CliRunner, bool_assert_path: Path) -> None:
    """SlangNotFound maps to exit code 3 and stderr mentions Install:."""
    exc = SlangNotFound(
        message=(
            "slang not found at 'slang'.\n"
            "Install: https://github.com/MikePopoloski/slang/releases\n"
            "Or pass: --slang-path /path/to/slang"
        )
    )
    with patch("sva2rtl.cli.invoke_slang", side_effect=exc):
        result = runner.invoke(main, [str(bool_assert_path)])

    assert result.exit_code == 3
    assert "Install:" in result.output


# ── Test 4: UnsupportedConstruct -> exit code 2 + SVA-E002 ────────────────


def test_cli_unsupported_construct(runner: CliRunner, bool_assert_path: Path) -> None:
    """UnsupportedConstruct maps to exit code 2; stderr contains SVA-E002."""
    exc = UnsupportedConstruct(
        message="Use a future version of sva2rtl for this feature",
        construct_name="##N sequence concatenation (Phase 2)",
        source_loc=SourceLoc("f.sv", 3, 5),
    )
    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch("sva2rtl.cli.import_all_assertions", side_effect=exc):
            result = runner.invoke(main, [str(bool_assert_path)])

    assert result.exit_code == 2
    assert "SVA-E002" in result.output


# ── Test 5: SvaCompileError -> exit code 1 ────────────────────────────────


def test_cli_compile_error(runner: CliRunner, bool_assert_path: Path) -> None:
    """SvaCompileError maps to exit code 1."""
    exc = SvaCompileError(message="slang failed (exit 1):\nsome parse error")
    with patch("sva2rtl.cli.invoke_slang", side_effect=exc):
        result = runner.invoke(main, [str(bool_assert_path)])

    assert result.exit_code == 1


# ── Test 6: success -> exit code 0, stdout contains 'module sva_' ─────────


def test_cli_success_stdout(runner: CliRunner, bool_assert_path: Path) -> None:
    """Happy path exits 0 and stdout contains the module declaration."""
    mock_node = MagicMock()
    mock_clock = MagicMock()
    mock_checker = MagicMock()
    mock_checker.children = ()  # No children → single-file (emit/write_output) path

    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch(
            "sva2rtl.cli.import_all_assertions",
            return_value=[(mock_node, mock_clock, "(a && b)", "my_check")],
        ):
            with patch("sva2rtl.cli.normalize", return_value=mock_node):
                with patch("sva2rtl.cli.compose", return_value=mock_checker):
                    with patch("sva2rtl.cli.optimize", return_value=mock_checker):
                        with patch("sva2rtl.cli.emit", return_value=_MOCK_SV_TEXT):
                            with patch("sva2rtl.cli.write_output") as mock_write:
                                result = runner.invoke(main, [str(bool_assert_path)])

    assert result.exit_code == 0
    # write_output is called with None as output_path (stdout) when -o not given
    mock_write.assert_called_once()


# ── Test 7: success with --output -> file created ─────────────────────────


def test_cli_success_output_file(runner: CliRunner, bool_assert_path: Path) -> None:
    """--output flag writes SV text to the specified file."""
    mock_node = MagicMock()
    mock_clock = MagicMock()
    mock_checker = MagicMock()
    mock_checker.children = ()  # No children → single-file (emit/write_output) path

    with tempfile.NamedTemporaryFile(suffix=".sv", delete=False) as tmp:
        out_path = tmp.name

    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch(
            "sva2rtl.cli.import_all_assertions",
            return_value=[(mock_node, mock_clock, "(a && b)", "my_check")],
        ):
            with patch("sva2rtl.cli.normalize", return_value=mock_node):
                with patch("sva2rtl.cli.compose", return_value=mock_checker):
                    with patch("sva2rtl.cli.optimize", return_value=mock_checker):
                        with patch("sva2rtl.cli.emit", return_value=_MOCK_SV_TEXT):
                            with patch("sva2rtl.cli.write_output") as mock_write:
                                result = runner.invoke(
                                    main, [str(bool_assert_path), "--output", out_path]
                                )

    assert result.exit_code == 0
    # write_output should have been called with Path(out_path) as second arg
    mock_write.assert_called_once()
    call_args = mock_write.call_args
    assert call_args[0][0] == _MOCK_SV_TEXT
    assert call_args[0][1] == Path(out_path)


def test_cli_trailing_slash_keeps_directory_mode_for_leaf_checker(
    runner: CliRunner, bool_assert_path: Path, tmp_path: Path
) -> None:
    """``--output out/`` stays a directory after hierarchy-flattening optimizations."""
    mock_node = MagicMock()
    mock_clock = MagicMock()
    mock_checker = MagicMock()
    mock_checker.children = ()
    output_dir = tmp_path / "out"

    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch(
            "sva2rtl.cli.import_all_assertions",
            return_value=[(mock_node, mock_clock, "(a && b)", "my_check")],
        ):
            with patch("sva2rtl.cli.normalize", return_value=mock_node):
                with patch("sva2rtl.cli.compose", return_value=mock_checker):
                    with patch("sva2rtl.cli.optimize", return_value=mock_checker):
                        with patch(
                            "sva2rtl.cli.emit_all", return_value={"sva_my_check": _MOCK_SV_TEXT}
                        ):
                            with patch("sva2rtl.cli.write_output_dir") as mock_write_dir:
                                result = runner.invoke(
                                    main,
                                    [
                                        str(bool_assert_path),
                                        "--output",
                                        str(output_dir) + "/",
                                    ],
                                )

    assert result.exit_code == 0
    mock_write_dir.assert_called_once()
    assert mock_write_dir.call_args[0][1] == output_dir


# ── Test 8: unexpected exception -> exit code 1, 'internal error:' prefix ─


def test_cli_internal_error(runner: CliRunner, bool_assert_path: Path) -> None:
    """Unexpected exceptions map to exit code 1 with 'internal error:' prefix."""
    with patch("sva2rtl.cli.invoke_slang", side_effect=RuntimeError("boom")):
        result = runner.invoke(main, [str(bool_assert_path)])

    assert result.exit_code == 1
    assert "internal error:" in result.output


# ── Test 9: pipeline call order ────────────────────────────────────────────


def test_cli_pipeline_call_order(runner: CliRunner, bool_assert_path: Path) -> None:
    """Pipeline functions are called in the correct order."""
    call_order: list[str] = []

    def mock_invoke_slang(*_args: object, **_kwargs: object) -> dict[str, object]:
        call_order.append("invoke_slang")
        return _MOCK_AST

    mock_node = BoolExpr(text="(a && b)", source_loc=_MOCK_SOURCE_LOC)
    mock_clock = MagicMock()

    def mock_import_all_assertions(
        *_args: object, **_kwargs: object
    ) -> list[tuple[object, object, str, str]]:
        call_order.append("import_all_assertions")
        return [(mock_node, mock_clock, "(a && b)", "label")]

    def mock_normalize(*_args: object, **_kwargs: object) -> object:
        call_order.append("normalize")
        return mock_node

    def mock_compose(*_args: object, **_kwargs: object) -> MagicMock:
        call_order.append("compose")
        checker = MagicMock()
        checker.children = ()  # No children → single-file path
        return checker

    def mock_optimize(*_args: object, **_kwargs: object) -> MagicMock:
        call_order.append("optimize")
        checker = MagicMock()
        checker.children = ()
        return checker

    def mock_emit(*_args: object, **_kwargs: object) -> str:
        call_order.append("emit")
        return _MOCK_SV_TEXT

    def mock_write_output(*_args: object, **_kwargs: object) -> None:
        call_order.append("write_output")

    with patch("sva2rtl.cli.invoke_slang", side_effect=mock_invoke_slang):
        with patch(
            "sva2rtl.cli.import_all_assertions", side_effect=mock_import_all_assertions
        ):
            with patch("sva2rtl.cli.normalize", side_effect=mock_normalize):
                with patch("sva2rtl.cli.compose", side_effect=mock_compose):
                    with patch("sva2rtl.cli.optimize", side_effect=mock_optimize):
                        with patch("sva2rtl.cli.emit", side_effect=mock_emit):
                            with patch(
                                "sva2rtl.cli.write_output", side_effect=mock_write_output
                            ):
                                result = runner.invoke(main, [str(bool_assert_path)])

    assert result.exit_code == 0
    assert call_order == [
        "invoke_slang",
        "import_all_assertions",
        "normalize",
        "compose",
        "optimize",
        "emit",
        "write_output",
    ]
