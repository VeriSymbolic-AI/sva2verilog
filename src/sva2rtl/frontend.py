"""Slang subprocess wrapper — invokes slang --ast-json and returns the parsed dict.

Critical design decisions (from Research Q1 + Q7):
- Always write JSON to a temp file, never use stdout. slang prefixes stdout with
  non-JSON status messages ("Top level design units: ...\\nBuild succeeded: ...")
  that break json.loads().
- Use list form of subprocess.run (never shell=True) to prevent injection.
- Timeout=60 to prevent hangs on large files.
- Clean up temp file unconditionally in a finally block.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sva2rtl.errors import SlangNotFound, SvaCompileError

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_LIBRARY_EXTENSION_RE = re.compile(r"^\.[A-Za-z0-9_]+$")


@dataclass(frozen=True, slots=True)
class SlangCompilationContext:
    """Reviewed, structured subset of slang's real-project compilation options.

    The frontend intentionally does not expose a raw argument escape hatch.
    Every value below is validated and emitted as a separate subprocess argv
    token, preserving the no-shell security boundary.
    """

    source_files: tuple[Path, ...] = ()
    filelists: tuple[Path, ...] = ()
    include_dirs: tuple[Path, ...] = ()
    defines: tuple[str, ...] = ()
    top_modules: tuple[str, ...] = ()
    parameter_overrides: tuple[str, ...] = ()
    library_files: tuple[Path, ...] = ()
    library_dirs: tuple[Path, ...] = ()
    library_extensions: tuple[str, ...] = ()
    library_order: tuple[str, ...] = ()
    single_unit: bool = False


def _checked_text(value: str, label: str) -> str:
    if not value or any(char in value for char in ("\x00", "\n", "\r")):
        raise SvaCompileError(message=f"invalid {label}: {value!r}")
    return value


def _checked_identifier(value: str, label: str) -> str:
    value = _checked_text(value, label)
    if _IDENTIFIER_RE.fullmatch(value) is None:
        raise SvaCompileError(message=f"invalid {label}: {value!r}")
    return value


def _checked_define(value: str) -> str:
    value = _checked_text(value, "define")
    name, _separator, _macro_value = value.partition("=")
    _checked_identifier(name, "define name")
    return value


def _checked_parameter_override(value: str) -> str:
    value = _checked_text(value, "parameter override")
    name, separator, parameter_value = value.partition("=")
    if not separator or not parameter_value:
        raise SvaCompileError(
            message=f"invalid parameter override (expected NAME=VALUE): {value!r}"
        )
    _checked_identifier(name, "parameter name")
    return value


def _checked_path(path: Path, label: str, *, directory: bool) -> Path:
    raw = _checked_text(str(path), f"{label} path")
    resolved = Path(raw).expanduser().resolve()
    expected = resolved.is_dir() if directory else resolved.is_file()
    if not expected:
        kind = "directory" if directory else "file"
        raise SvaCompileError(message=f"{label} {kind} does not exist: {path}")
    return resolved


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def _build_slang_command(
    sv_file: Path,
    slang_path: str,
    ast_json_path: str,
    context: SlangCompilationContext,
) -> list[str]:
    """Build a validated argv list while reserving internal AST options."""
    command = [_checked_text(slang_path, "slang path")]

    for path in _unique_paths(
        [_checked_path(item, "filelist", directory=False) for item in context.filelists]
    ):
        command.extend(("-F", str(path)))
    for path in _unique_paths(
        [_checked_path(item, "include", directory=True) for item in context.include_dirs]
    ):
        command.extend(("-I", str(path)))
    for value in context.defines:
        command.extend(("-D", _checked_define(value)))
    for value in context.top_modules:
        command.extend(("--top", _checked_identifier(value, "top module")))
    for value in context.parameter_overrides:
        command.extend(("-G", _checked_parameter_override(value)))
    for path in _unique_paths(
        [
            _checked_path(item, "library", directory=False)
            for item in context.library_files
        ]
    ):
        command.extend(("-v", str(path)))
    for path in _unique_paths(
        [_checked_path(item, "library", directory=True) for item in context.library_dirs]
    ):
        command.extend(("-y", str(path)))
    for value in context.library_extensions:
        value = _checked_text(value, "library extension")
        if _LIBRARY_EXTENSION_RE.fullmatch(value) is None:
            raise SvaCompileError(message=f"invalid library extension: {value!r}")
        command.extend(("-Y", value))
    for value in context.library_order:
        command.extend(("-L", _checked_identifier(value, "library name")))
    if context.single_unit:
        command.append("--single-unit")

    primary = _checked_path(sv_file, "input source", directory=False)
    sources = _unique_paths(
        [primary]
        + [
            _checked_path(item, "source", directory=False)
            for item in context.source_files
        ]
    )
    command.extend(str(path) for path in sources)

    # Keep compiler-owned output controls last so structured project context
    # cannot accidentally replace the AST evidence file.
    command.extend(("--ast-json", ast_json_path, "--ast-json-source-info"))
    return command


def invoke_slang(
    sv_file: Path,
    slang_path: str = "slang",
    *,
    context: SlangCompilationContext | None = None,
) -> dict[str, object]:
    """Invoke slang on *sv_file* and return the parsed AST JSON dict.

    Parameters
    ----------
    sv_file:
        Path to the SystemVerilog source file to parse.
    slang_path:
        Name or absolute path of the slang binary.  Defaults to ``"slang"``
        (resolved via PATH).
    context:
        Structured additional sources and compilation options for a real
        project. Raw compiler argument passthrough is intentionally excluded.

    Returns
    -------
    dict[str, object]
        Parsed JSON dict from slang's ``--ast-json`` output.

    Raises
    ------
    SlangNotFound
        When the slang binary is not found at *slang_path*.
    SvaCompileError
        When slang exits with a non-zero return code (syntax error, etc.).
    """
    tmp_path: str | None = None
    try:
        # Create temp file; we close it immediately so slang can write to it
        # on all platforms (Windows file-locking would block otherwise).
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = tmp.name

        cmd = _build_slang_command(
            sv_file,
            slang_path,
            tmp_path,
            context or SlangCompilationContext(),
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except FileNotFoundError:
            raise SlangNotFound(
                message=(
                    f"slang not found at '{slang_path}'.\n"
                    "Install: https://github.com/MikePopoloski/slang/releases\n"
                    "Or pass: --slang-path /path/to/slang"
                ),
            )
        except subprocess.TimeoutExpired as exc:
            raise SvaCompileError(message="slang timed out after 60 seconds") from exc

        if result.returncode != 0:
            raise SvaCompileError(
                message=f"slang failed (exit {result.returncode}):\n{result.stderr}",
            )

        try:
            with open(tmp_path, encoding="utf-8") as fh:
                raw = json.loads(fh.read())
        except (OSError, json.JSONDecodeError) as exc:
            raise SvaCompileError(
                message=(
                    "slang did not produce valid AST JSON "
                    f"({type(exc).__name__})"
                )
            ) from exc
        if not isinstance(raw, dict):
            raise SvaCompileError(message="slang JSON output was not a JSON object")
        return raw

    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass  # best-effort cleanup; ignore errors
