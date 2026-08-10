"""Real `.sv` source E2E fixtures for constructs that previously only had JSON fixtures.

These tests close the SUPPORT_MATRIX real-source gap by running each fixture
through the full pipeline: slang CLI → ast_importer → normalizer → composer →
emitter. Each test asserts:
- Exit code 0 (slang parses + compiler accepts)
- Output directory contains generated `.sv` files
- Generated RTL contains the expected monitor interface ports (clk, rst_n,
  start, pass, fail, active, attempt_fired)

Note: `disable_iff` and `named_seq` have slang v11 AST representation
differences (disableIff key / AssertionInstance kind) that are tracked
separately; they retain their existing JSON fixture evidence. The fixtures
below cover the constructs whose slang→RTL pipeline is confirmed working.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from sva2rtl.cli import main
from tests.conftest import requires_slang

_SV_FIXTURES = Path(__file__).parent / "sv_fixtures"


def _run_e2e(fixture_name: str, tmp_path: Path) -> str:
    """Compile a real `.sv` fixture through the full CLI pipeline.

    Uses directory output mode (trailing slash) because most fixtures produce
    multi-module hierarchies. Returns the concatenation of all generated SV.
    Asserts exit code 0 and output directory existence.
    """
    runner = CliRunner()
    output_dir = tmp_path / "out"
    result = runner.invoke(
        main,
        [str(_SV_FIXTURES / fixture_name), "--output", str(output_dir) + "/"],
    )
    assert result.exit_code == 0, (
        f"Expected exit code 0 for {fixture_name}, got {result.exit_code}.\n"
        f"Output: {result.output}"
    )
    assert output_dir.is_dir(), f"Output directory was not created for {fixture_name}"
    sv_files = sorted(output_dir.glob("sva_*.sv"))
    assert sv_files, f"No sva_*.sv files generated for {fixture_name}"
    return "\n".join(p.read_text(encoding="utf-8") for p in sv_files)


def _assert_monitor_interface(sv_text: str, fixture_name: str) -> None:
    """Assert the generated RTL contains the standard monitor interface ports."""
    assert "clk" in sv_text, f"{fixture_name}: missing 'clk' in generated RTL"
    assert "rst_n" in sv_text, f"{fixture_name}: missing 'rst_n' in generated RTL"
    assert "start" in sv_text, f"{fixture_name}: missing 'start' in generated RTL"
    assert "pass" in sv_text, f"{fixture_name}: missing 'pass' in generated RTL"
    assert "fail" in sv_text, f"{fixture_name}: missing 'fail' in generated RTL"
    assert "active" in sv_text, f"{fixture_name}: missing 'active' in generated RTL"
    assert "attempt_fired" in sv_text, (
        f"{fixture_name}: missing 'attempt_fired' in generated RTL"
    )
    assert "module sva_" in sv_text, (
        f"{fixture_name}: expected 'module sva_' prefix in generated RTL"
    )
    assert "endmodule" in sv_text, f"{fixture_name}: missing 'endmodule'"


# ── Repetition fixtures ────────────────────────────────────────────────────


@requires_slang
def test_e2e_rep_fixed(tmp_path: Path) -> None:
    """`a |-> b[*3]` — fixed consecutive repetition, real source E2E."""
    sv = _run_e2e("rep_fixed.sv", tmp_path)
    _assert_monitor_interface(sv, "rep_fixed.sv")


@requires_slang
def test_e2e_rep_range(tmp_path: Path) -> None:
    """`a |-> b[*2:5]` — ranged consecutive repetition, real source E2E."""
    sv = _run_e2e("rep_range.sv", tmp_path)
    _assert_monitor_interface(sv, "rep_range.sv")


@requires_slang
def test_e2e_implication_ranged_delay_lower_bound(tmp_path: Path) -> None:
    """The reported ``req |-> ##[1:3] ack`` source shape reaches NFA RTL."""
    sv = _run_e2e("imp_overlap_delay_range.sv", tmp_path)
    _assert_monitor_interface(sv, "imp_overlap_delay_range.sv")
    assert "module sva_range_lower_bound" in sv
    assert "output  logic overflow_flag" in sv


# ── Goto / nonconsecutive repetition fixtures ──────────────────────────────


@requires_slang
def test_e2e_goto_rep(tmp_path: Path) -> None:
    """`a |-> b[->3]` — goto repetition, real source E2E."""
    sv = _run_e2e("goto_rep.sv", tmp_path)
    _assert_monitor_interface(sv, "goto_rep.sv")


@requires_slang
def test_e2e_nonconsec_rep(tmp_path: Path) -> None:
    """`a |-> b[=3]` — nonconsecutive repetition, real source E2E."""
    sv = _run_e2e("nonconsec_rep.sv", tmp_path)
    _assert_monitor_interface(sv, "nonconsec_rep.sv")


# ── Sampled value function fixtures ────────────────────────────────────────


@requires_slang
def test_e2e_rose(tmp_path: Path) -> None:
    """`$rose(a) |-> b` — rising edge sampled value, real source E2E."""
    sv = _run_e2e("rose.sv", tmp_path)
    _assert_monitor_interface(sv, "rose.sv")


@requires_slang
def test_e2e_fell(tmp_path: Path) -> None:
    """`$fell(a) |-> b` — falling edge sampled value, real source E2E."""
    sv = _run_e2e("fell.sv", tmp_path)
    _assert_monitor_interface(sv, "fell.sv")


@requires_slang
def test_e2e_stable(tmp_path: Path) -> None:
    """`$stable(a) |-> b` — stability sampled value, real source E2E."""
    sv = _run_e2e("stable.sv", tmp_path)
    _assert_monitor_interface(sv, "stable.sv")


@requires_slang
def test_e2e_changed(tmp_path: Path) -> None:
    """`$changed(a) |-> b` — change sampled value, real source E2E."""
    sv = _run_e2e("changed.sv", tmp_path)
    _assert_monitor_interface(sv, "changed.sv")


@requires_slang
def test_e2e_past(tmp_path: Path) -> None:
    """`a |-> $past(b, 2)` — delayed sampled value, real source E2E."""
    sv = _run_e2e("past.sv", tmp_path)
    _assert_monitor_interface(sv, "past.sv")


# ── first_match fixture ───────────────────────────────────────────────────


@requires_slang
def test_e2e_first_match(tmp_path: Path) -> None:
    """`first_match(a ##1 b ##1 c)` — earliest completion, real source E2E."""
    sv = _run_e2e("first_match.sv", tmp_path)
    _assert_monitor_interface(sv, "first_match.sv")


# ── disable iff fixture ──────────────────────────────────────────────────


@requires_slang
def test_e2e_disable_iff(tmp_path: Path) -> None:
    """`disable iff (!rst_n) (a |-> b)` — disable condition, real source E2E.

    This closes the slang v11 AST compatibility gap: slang v11 represents
    disable iff as expr.kind == "DisableIff" (v7 used body.disableIff).
    The importer now handles both formats.
    """
    sv = _run_e2e("disable_iff.sv", tmp_path)
    _assert_monitor_interface(sv, "disable_iff.sv")


# ── named sequence fixture ───────────────────────────────────────────────


@requires_slang
def test_e2e_named_seq(tmp_path: Path) -> None:
    """Named sequence `seq_ab(a,b)` referenced in implication, real source E2E.

    This closes the slang v11 AST compatibility gap: slang v11 represents
    named sequence references as ``Simple`` wrapping ``AssertionInstance``
    with an inlined ``body`` (v7 used ``SequenceInstance``). The importer
    now handles both formats.
    """
    sv = _run_e2e("named_seq.sv", tmp_path)
    _assert_monitor_interface(sv, "named_seq.sv")


# ── iverilog compilation gate ─────────────────────────────────────────────
# When iverilog is available, verify generated RTL from a representative
# fixture compiles clean with -g2012.

_IVERILOG_AVAILABLE = shutil.which("iverilog") is not None


@requires_slang
@pytest.mark.skipif(not _IVERILOG_AVAILABLE, reason="iverilog not found")
def test_e2e_rose_compiles_iverilog(tmp_path: Path) -> None:
    """Generated monitor from rose.sv compiles clean with iverilog -g2012."""
    import subprocess

    runner = CliRunner()
    output_dir = tmp_path / "out"
    result = runner.invoke(
        main,
        [str(_SV_FIXTURES / "rose.sv"), "--output", str(output_dir) + "/"],
    )
    assert result.exit_code == 0

    sv_files = sorted(output_dir.glob("sva_*.sv"))
    compile_result = subprocess.run(
        ["iverilog", "-g2012", "-o", str(tmp_path / "monitor.vvp")]
        + [str(p) for p in sv_files],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert compile_result.returncode == 0, (
        f"iverilog compilation failed for rose.sv:\n{compile_result.stderr}"
    )
