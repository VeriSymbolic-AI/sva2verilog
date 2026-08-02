"""Structured real-project compilation-context tests for the slang frontend."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
from click.testing import CliRunner

from sva2rtl.cli import main
from sva2rtl.errors import SvaCompileError
from sva2rtl.frontend import SlangCompilationContext, invoke_slang
from tests.conftest import requires_slang

_SIMPLE_AST: dict[str, object] = {"design": {"members": []}}
_PROJECT_CORPUS = Path(__file__).parent / "project_corpus"


def _completed_process() -> subprocess.CompletedProcess[str]:
    proc: subprocess.CompletedProcess[str] = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = 0
    proc.stdout = ""
    proc.stderr = ""
    return proc


def _touch(path: Path, text: str = "// fixture\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_structured_context_builds_explicit_slang_argv(tmp_path: Path) -> None:
    """Every supported project option reaches slang as a separate argv token."""
    primary = _touch(tmp_path / "rtl" / "top.sv")
    extra = _touch(tmp_path / "rtl" / "assertions.sv")
    filelist = _touch(tmp_path / "files.f", "rtl/assertions.sv\n")
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    library_file = _touch(tmp_path / "lib" / "cells.sv")
    library_dir = tmp_path / "libdir"
    library_dir.mkdir()

    context = SlangCompilationContext(
        source_files=(extra,),
        filelists=(filelist,),
        include_dirs=(include_dir,),
        defines=("FEATURE=1",),
        top_modules=("project_top",),
        parameter_overrides=("WIDTH=8",),
        library_files=(library_file,),
        library_dirs=(library_dir,),
        library_extensions=(".sv",),
        library_order=("work",),
        single_unit=True,
    )

    with patch("subprocess.run", return_value=_completed_process()) as mock_run:
        with patch("builtins.open", mock_open(read_data=json.dumps(_SIMPLE_AST))):
            invoke_slang(primary, context=context)

    cmd = mock_run.call_args.args[0]
    assert isinstance(cmd, list)
    assert cmd[0] == "slang"
    assert ["-F", str(filelist.resolve())] == cmd[cmd.index("-F") : cmd.index("-F") + 2]
    assert ["-I", str(include_dir.resolve())] == cmd[cmd.index("-I") : cmd.index("-I") + 2]
    assert ["-D", "FEATURE=1"] == cmd[cmd.index("-D") : cmd.index("-D") + 2]
    assert ["--top", "project_top"] == cmd[cmd.index("--top") : cmd.index("--top") + 2]
    assert ["-G", "WIDTH=8"] == cmd[cmd.index("-G") : cmd.index("-G") + 2]
    assert ["-v", str(library_file.resolve())] == cmd[cmd.index("-v") : cmd.index("-v") + 2]
    assert ["-y", str(library_dir.resolve())] == cmd[cmd.index("-y") : cmd.index("-y") + 2]
    assert ["-Y", ".sv"] == cmd[cmd.index("-Y") : cmd.index("-Y") + 2]
    assert ["-L", "work"] == cmd[cmd.index("-L") : cmd.index("-L") + 2]
    assert "--single-unit" in cmd
    assert str(primary.resolve()) in cmd
    assert str(extra.resolve()) in cmd
    assert cmd[-3] == "--ast-json"
    assert cmd[-1] == "--ast-json-source-info"
    assert mock_run.call_args.kwargs.get("shell") is not True


@pytest.mark.parametrize(
    "context, expected",
    [
        (SlangCompilationContext(defines=("BAD-NAME=1",)), "define"),
        (SlangCompilationContext(top_modules=("bad top",)), "top module"),
        (SlangCompilationContext(parameter_overrides=("WIDTH",)), "parameter"),
        (SlangCompilationContext(library_extensions=("sv",)), "library extension"),
        (SlangCompilationContext(library_order=("bad\nlib",)), "library"),
    ],
)
def test_structured_context_rejects_invalid_option_values(
    tmp_path: Path,
    context: SlangCompilationContext,
    expected: str,
) -> None:
    """Invalid names and control characters fail before a subprocess starts."""
    primary = _touch(tmp_path / "top.sv")
    with patch("subprocess.run") as mock_run:
        with pytest.raises(SvaCompileError, match=expected):
            invoke_slang(primary, context=context)
    mock_run.assert_not_called()


def test_structured_context_rejects_missing_project_paths(tmp_path: Path) -> None:
    """API callers receive a diagnostic instead of silently dropping missing files."""
    primary = _touch(tmp_path / "top.sv")
    missing = tmp_path / "missing.f"
    context = SlangCompilationContext(filelists=(missing,))

    with patch("subprocess.run") as mock_run:
        with pytest.raises(SvaCompileError, match="filelist"):
            invoke_slang(primary, context=context)
    mock_run.assert_not_called()


def test_frontend_reports_missing_ast_output_as_compile_error(tmp_path: Path) -> None:
    """A successful exit without the compiler-owned AST file is not an internal crash."""
    primary = _touch(tmp_path / "top.sv")

    with patch("subprocess.run", return_value=_completed_process()):
        with patch("builtins.open", side_effect=FileNotFoundError):
            with pytest.raises(SvaCompileError, match="valid AST JSON"):
                invoke_slang(primary)


def test_frontend_reports_timeout_as_compile_error(tmp_path: Path) -> None:
    """Large-project timeout remains an explicit frontend diagnostic."""
    primary = _touch(tmp_path / "top.sv")

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd=["slang"], timeout=60),
    ):
        with pytest.raises(SvaCompileError, match="timed out after 60 seconds"):
            invoke_slang(primary)


def test_cli_threads_only_structured_project_context(tmp_path: Path) -> None:
    """CLI flags construct the reviewed context without raw-argument passthrough."""
    primary = _touch(tmp_path / "top.sv", "module top; endmodule\n")
    extra = _touch(tmp_path / "assertions.sv")
    filelist = _touch(tmp_path / "files.f", "assertions.sv\n")
    include_dir = tmp_path / "include"
    include_dir.mkdir()
    library_file = _touch(tmp_path / "cells.sv")
    library_dir = tmp_path / "lib"
    library_dir.mkdir()

    args = [
        str(primary),
        "--source",
        str(extra),
        "--filelist",
        str(filelist),
        "--include-dir",
        str(include_dir),
        "--define",
        "FEATURE=1",
        "--top",
        "project_top",
        "--parameter",
        "WIDTH=8",
        "--library-file",
        str(library_file),
        "--library-dir",
        str(library_dir),
        "--library-ext",
        ".sv",
        "--library",
        "work",
        "--single-unit",
        "--dump-ast",
    ]

    with patch("sva2rtl.cli.invoke_slang", return_value=_SIMPLE_AST) as mock_invoke:
        result = CliRunner().invoke(main, args)

    assert result.exit_code == 0, result.output
    context = mock_invoke.call_args.kwargs["context"]
    assert context == SlangCompilationContext(
        source_files=(extra,),
        filelists=(filelist,),
        include_dirs=(include_dir,),
        defines=("FEATURE=1",),
        top_modules=("project_top",),
        parameter_overrides=("WIDTH=8",),
        library_files=(library_file,),
        library_dirs=(library_dir,),
        library_extensions=(".sv",),
        library_order=("work",),
        single_unit=True,
    )


def test_cli_help_has_no_raw_slang_argument_escape_hatch() -> None:
    """The public CLI advertises only reviewed structured project options."""
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for option in (
        "--source",
        "--filelist",
        "--include-dir",
        "--define",
        "--top",
        "--parameter",
        "--library-file",
        "--library-dir",
        "--library-ext",
        "--library",
        "--single-unit",
    ):
        assert option in result.output
    assert "--slang-arg" not in result.output


@requires_slang
@pytest.mark.integration
def test_real_project_filelist_include_define_top_and_parameter(tmp_path: Path) -> None:
    """A versioned relative -F project elaborates through the complete CLI pipeline."""
    corpus = _PROJECT_CORPUS / "parameter_specialization"
    expected = json.loads((corpus / "expected.json").read_text(encoding="utf-8"))
    output = tmp_path / "project_check.sv"

    result = CliRunner().invoke(
        main,
        [
            str(corpus / "top.sv"),
            "--filelist",
            str(corpus / "files.f"),
            "--include-dir",
            str(corpus / "include"),
            "--define",
            expected["defines"][0],
            "--top",
            expected["top"],
            "--parameter",
            expected["parameters"][0],
            "--single-unit",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    emitted = output.read_text(encoding="utf-8")
    assert "module sva_project_check" in emitted
    assert "input  logic a" in emitted
    assert "(a == 1'b1)" in emitted
    assert "assign pass" in emitted


@requires_slang
@pytest.mark.integration
def test_real_project_library_directory_and_extension(tmp_path: Path) -> None:
    """A versioned missing module is found through reviewed -y/-Y context."""
    corpus = _PROJECT_CORPUS / "library_resolution"
    expected = json.loads((corpus / "expected.json").read_text(encoding="utf-8"))
    output = tmp_path / "library_check.sv"

    result = CliRunner().invoke(
        main,
        [
            str(corpus / "top.sv"),
            "--library-dir",
            str(corpus / "library"),
            "--library-ext",
            expected["library_extension"],
            "--top",
            expected["top"],
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    emitted = output.read_text(encoding="utf-8")
    assert f"module sva_{expected['assertion_label']}" in emitted
    assert expected["assertion_text"] in emitted
