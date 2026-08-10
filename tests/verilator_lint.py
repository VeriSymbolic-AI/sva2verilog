"""Shared strict Verilator lint command construction for generated RTL tests."""

from __future__ import annotations

from pathlib import Path


def build_verilator_lint_command(
    verilator: str,
    top_module: str,
    sv_files: list[Path],
) -> list[str]:
    """Build a strict lint command with only ABI-related warnings disabled.

    Generated checkers intentionally expose a stable interface even when a
    particular operator does not consume every parameter or child diagnostic
    output.  Those warnings are expected.  All other ``-Wall`` warnings remain
    fatal so structural and width regressions still fail the gate.
    """
    return [
        verilator,
        "--lint-only",
        "-Wall",
        "-Wno-PINCONNECTEMPTY",
        "-Wno-UNUSEDSIGNAL",
        "-Wno-UNUSEDPARAM",
        "-Wno-DECLFILENAME",
        "--top-module",
        top_module,
        *[str(path) for path in sv_files],
    ]
