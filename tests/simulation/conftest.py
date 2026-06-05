"""Conftest for the simulation test subdirectory.

All tests in this directory require a SystemVerilog simulator (iverilog or
Verilator) to compile and execute the generated modules.  When the requested
simulator is not present on PATH the entire subdirectory is skipped rather
than failed so that CI environments without a specific simulator can still
run other test axes.
"""

from __future__ import annotations

import os
import shutil

import pytest


@pytest.fixture(autouse=True)
def check_simulator(request: pytest.FixtureRequest) -> None:
    """Skip simulation tests when the requested simulator is not installed.

    Resolves the simulator from ``--simulator`` CLI flag, with optional
    override via ``SVA2RTL_SIMULATOR`` environment variable.
    """
    sim = request.config.getoption("--simulator", default="iverilog")
    env_sim = os.environ.get("SVA2RTL_SIMULATOR")
    if env_sim:
        sim = env_sim

    if sim == "iverilog" and shutil.which("iverilog") is None:
        pytest.skip(
            "iverilog not found — install Icarus Verilog to run simulation tests"
        )
    elif sim == "verilator" and shutil.which("verilator") is None:
        pytest.skip(
            "verilator not found — install Verilator to run simulation tests"
        )
