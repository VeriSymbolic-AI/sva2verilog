"""Conftest for the simulation test subdirectory.

All tests in this directory require Icarus Verilog (iverilog + vvp) to
compile and execute the generated SystemVerilog modules.  When iverilog is
not present on PATH the entire subdirectory is skipped rather than failed so
that CI environments without a simulator can still run the unit tests.
"""

from __future__ import annotations

import shutil

import pytest


@pytest.fixture(autouse=True)
def check_iverilog() -> None:
    """Skip simulation tests when iverilog is not installed."""
    if shutil.which("iverilog") is None:
        pytest.skip(
            "iverilog not found — install Icarus Verilog to run simulation tests"
        )
