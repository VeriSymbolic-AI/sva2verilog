"""Unit tests for src/sva2rtl/frontend.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sva2rtl.errors import SlangNotFound, SvaCompileError
from sva2rtl.frontend import invoke_slang

# ── helpers ────────────────────────────────────────────────────────────────

_SIMPLE_AST: dict[str, object] = {
    "design": {
        "members": [
            {
                "kind": "Instance",
                "name": "test",
                "body": {"kind": "InstanceBody", "members": []},
            }
        ]
    }
}


def _make_completed_process(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    proc: subprocess.CompletedProcess[str] = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


# ── tests ──────────────────────────────────────────────────────────────────


def test_slang_not_found(tmp_path: Path) -> None:
    """When slang binary is absent, SlangNotFound is raised with install URL."""
    sv_file = tmp_path / "test.sv"
    sv_file.write_text("module m; endmodule\n")

    with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
        with pytest.raises(SlangNotFound) as exc_info:
            invoke_slang(sv_file, slang_path="slang-nonexistent")

    assert "Install:" in str(exc_info.value)
    assert "github.com/MikePopoloski/slang" in str(exc_info.value)
    assert "slang-nonexistent" in str(exc_info.value)


def test_slang_compile_error(tmp_path: Path) -> None:
    """When slang exits non-zero, SvaCompileError is raised with stderr text."""
    sv_file = tmp_path / "bad.sv"
    sv_file.write_text("module bad; endmodule\n")

    error_stderr = "test.sv:1:1: error: unexpected token\n"
    proc = _make_completed_process(returncode=1, stderr=error_stderr)

    with patch("subprocess.run", return_value=proc):
        with patch("builtins.open", side_effect=FileNotFoundError):
            with pytest.raises(SvaCompileError) as exc_info:
                invoke_slang(sv_file, slang_path="slang")

    assert "exit 1" in str(exc_info.value)
    assert "unexpected token" in str(exc_info.value)


def test_slang_success(tmp_path: Path) -> None:
    """When slang succeeds and writes valid JSON, a dict is returned."""
    sv_file = tmp_path / "ok.sv"
    sv_file.write_text("module ok; endmodule\n")

    json_content = json.dumps(_SIMPLE_AST)
    proc = _make_completed_process(returncode=0)

    # Patch subprocess.run so it returns success, then patch the open() that
    # reads the temp file so it returns our fixture JSON.
    with patch("subprocess.run", return_value=proc):
        with patch(
            "builtins.open",
            unittest_mock_open(read_data=json_content),
        ):
            result = invoke_slang(sv_file, slang_path="slang")

    assert isinstance(result, dict)
    assert "design" in result


def test_slang_never_uses_shell(tmp_path: Path) -> None:
    """subprocess.run must never be called with shell=True."""
    sv_file = tmp_path / "test.sv"
    sv_file.write_text("module m; endmodule\n")

    captured_kwargs: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_kwargs.update(kwargs)
        raise FileNotFoundError("slang not found")

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SlangNotFound):
            invoke_slang(sv_file)

    assert captured_kwargs.get("shell") is not True


def test_slang_uses_timeout(tmp_path: Path) -> None:
    """subprocess.run must be called with a timeout."""
    sv_file = tmp_path / "test.sv"
    sv_file.write_text("module m; endmodule\n")

    captured_kwargs: dict[str, object] = {}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured_kwargs.update(kwargs)
        raise FileNotFoundError("slang not found")

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SlangNotFound):
            invoke_slang(sv_file)

    assert "timeout" in captured_kwargs
    assert captured_kwargs["timeout"] == 60


# ── helpers ────────────────────────────────────────────────────────────────


def unittest_mock_open(read_data: str = "") -> MagicMock:
    """Thin wrapper around unittest.mock.mock_open that works with 'with open'."""
    from unittest.mock import mock_open

    result: MagicMock = mock_open(read_data=read_data)
    return result
