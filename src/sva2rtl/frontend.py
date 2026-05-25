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
import subprocess
import tempfile
from pathlib import Path

from sva2rtl.errors import SlangNotFound, SvaCompileError


def invoke_slang(sv_file: Path, slang_path: str = "slang") -> dict[str, object]:
    """Invoke slang on *sv_file* and return the parsed AST JSON dict.

    Parameters
    ----------
    sv_file:
        Path to the SystemVerilog source file to parse.
    slang_path:
        Name or absolute path of the slang binary.  Defaults to ``"slang"``
        (resolved via PATH).

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

        cmd = [
            slang_path,
            "--ast-json",
            tmp_path,
            "--ast-json-source-info",
            str(sv_file),
        ]

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

        if result.returncode != 0:
            raise SvaCompileError(
                message=f"slang failed (exit {result.returncode}):\n{result.stderr}",
            )

        with open(tmp_path, encoding="utf-8") as fh:
            raw = json.loads(fh.read())
        if not isinstance(raw, dict):
            raise SvaCompileError(message="slang JSON output was not a JSON object")
        return raw

    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass  # best-effort cleanup; ignore errors
