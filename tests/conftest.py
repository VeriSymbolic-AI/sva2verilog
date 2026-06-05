"""Shared pytest fixtures and helpers for the sva2rtl test suite.

Provides:
- ``fixtures_dir`` / ``golden_dir`` path fixtures
- IR object fixtures (``sample_source_loc``, ``sample_clock``, ``sample_bool_expr``)
- ``requires_slang`` conditional skip marker
- ``assert_golden`` diff helper for golden file comparisons
"""

from __future__ import annotations

import difflib
import os
import shutil
from pathlib import Path

import pytest

from sva2rtl.ir import BoolExpr, ClockSpec, SourceLoc

# ── CLI flag registration ──────────────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the --simulator CLI flag for dual-simulator selection."""
    parser.addoption(
        "--simulator",
        action="store",
        default="iverilog",
        choices=("iverilog", "verilator"),
        help="Simulator backend: iverilog (default) or verilator",
    )


# ── Custom marker registration ─────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    """Register project-specific pytest markers."""
    config.addinivalue_line(
        "markers",
        "simulation: marks tests requiring a simulator (deselect with '-m not simulation')",
    )


# ── Simulator fixture ──────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def simulator(request: pytest.FixtureRequest) -> str:
    """Return the selected simulator backend.

    Resolves from --simulator CLI flag, with optional override via
    ``SVA2RTL_SIMULATOR`` environment variable.
    """
    sim = request.config.getoption("--simulator", default="iverilog")
    env_sim = os.environ.get("SVA2RTL_SIMULATOR")
    return env_sim if env_sim else str(sim)

# ── Conditional skip marker ────────────────────────────────────────────────

has_slang: bool = shutil.which("slang") is not None
requires_slang = pytest.mark.skipif(
    not has_slang,
    reason="slang binary not found — install from https://github.com/MikePopoloski/slang/releases",
)


# ── Path fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def fixtures_dir() -> Path:
    """Return the path to the ``tests/fixtures/`` directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def golden_dir() -> Path:
    """Return the path to the ``tests/golden/`` directory."""
    return Path(__file__).parent / "golden"


# ── IR object fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def sample_source_loc() -> SourceLoc:
    """A canonical SourceLoc used across multiple unit tests."""
    return SourceLoc("test.sv", 3, 5)


@pytest.fixture()
def sample_clock(sample_source_loc: SourceLoc) -> ClockSpec:
    """A canonical posedge ClockSpec used across unit tests."""
    return ClockSpec(
        edge="posedge",
        signal="clk",
        source_loc=SourceLoc("test.sv", 2, 3),
    )


@pytest.fixture()
def sample_bool_expr(sample_source_loc: SourceLoc) -> BoolExpr:
    """A canonical BoolExpr for a simple ``(a && b)`` property."""
    return BoolExpr(text="(a && b)", source_loc=sample_source_loc)


# ── Golden file helper ─────────────────────────────────────────────────────


def assert_golden(actual: str, golden_path: Path) -> None:
    """Assert that *actual* matches the content of *golden_path*.

    Comparison strips trailing whitespace from each line so that
    minor whitespace-only differences don't cause false failures.

    On mismatch, raises ``AssertionError`` with a unified diff between
    the expected (golden) and actual text, making failures easy to diagnose.

    Parameters
    ----------
    actual:
        The string to compare against the golden file.
    golden_path:
        Path to the golden file.  Must exist.
    """
    golden = golden_path.read_text(encoding="utf-8")

    def _norm(s: str) -> list[str]:
        return [line.rstrip() for line in s.splitlines()]

    actual_lines = _norm(actual)
    golden_lines = _norm(golden)

    if actual_lines != golden_lines:
        diff = "\n".join(
            difflib.unified_diff(
                golden_lines,
                actual_lines,
                fromfile=str(golden_path),
                tofile="<actual>",
                lineterm="",
            )
        )
        raise AssertionError(f"Output does not match golden file {golden_path}:\n{diff}")
