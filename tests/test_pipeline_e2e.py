"""End-to-end tests through the CLI entry point.

Tests 1–4 require the slang binary and are decorated with ``@requires_slang``.
Test 3 additionally requires ``iverilog``.
Test 5 (nonexistent input) runs unconditionally.

These tests exercise the real subprocess invocation of slang (when available),
validate exit codes, and verify that the generated SV file is syntactically
valid enough for iverilog to accept.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from sva2rtl.cli import main
from tests.conftest import requires_slang

# ── Fixture helpers ────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"


# ── Test 1: happy path with bool_assert.sv ────────────────────────────────


@requires_slang
def test_e2e_bool_assert(tmp_path: Path) -> None:
    """Full pipeline on bool_assert.sv exits 0 and produces a valid SV file.

    Verifies:
    - Exit code is 0
    - Output file is created
    - Module name matches the assertion label (``sva_my_check``)
    - ``attempt_fired`` port is present
    """
    runner = CliRunner()
    output_file = tmp_path / "bool_out.sv"
    result = runner.invoke(
        main,
        [str(_FIXTURES / "bool_assert.sv"), "--output", str(output_file)],
    )

    assert result.exit_code == 0, (
        f"Expected exit code 0, got {result.exit_code}.\nOutput: {result.output}"
    )
    assert output_file.exists(), "Output file was not created"

    sv_text = output_file.read_text(encoding="utf-8")
    assert "module sva_my_check" in sv_text, "Expected labeled module name 'sva_my_check'"
    assert "attempt_fired" in sv_text, "Expected 'attempt_fired' port in generated SV"


# ── Test 2: delay_assert.sv is rejected with exit code 2 ─────────────────


@requires_slang
def test_e2e_delay_assert_rejected() -> None:
    """Full pipeline on delay_assert.sv exits 0 (SequenceConcat is now supported).

    ``a ##1 b`` (SequenceConcat) produces valid RTL via the token-passing
    architecture.  This verifies the full pipeline succeeds.
    """
    runner = CliRunner()
    result = runner.invoke(main, [str(_FIXTURES / "delay_assert.sv")])

    assert result.exit_code == 0, (
        f"Expected exit_code 0 for delay_assert.sv (SequenceConcat supported), "
        f"got {result.exit_code}.\nOutput: {result.output}"
    )


# ── Test 3: generated SV compiles with iverilog ───────────────────────────


@requires_slang
@pytest.mark.skipif(
    shutil.which("iverilog") is None,
    reason="iverilog not found — install Icarus Verilog to run this test",
)
def test_e2e_output_compiles_iverilog(tmp_path: Path) -> None:
    """Generated monitor from bool_assert.sv compiles clean with iverilog -g2012.

    This is the primary correctness gate: if the generated SV has a syntax
    error, iverilog will return non-zero.
    """
    runner = CliRunner()
    output_file = tmp_path / "monitor.sv"
    result = runner.invoke(
        main,
        [str(_FIXTURES / "bool_assert.sv"), "--output", str(output_file)],
    )
    assert result.exit_code == 0

    compile_result = subprocess.run(
        ["iverilog", "-g2012", "-o", str(tmp_path / "monitor.vvp"), str(output_file)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert compile_result.returncode == 0, f"iverilog compilation failed:\n{compile_result.stderr}"


# ── Test 4: bad slang path exits 3 ────────────────────────────────────────


@requires_slang
def test_e2e_slang_bad_path(tmp_path: Path) -> None:
    """CLI with --slang-path /nonexistent/slang exits 3 and mentions 'Install:'.

    Even when slang is available on PATH, providing a non-existent explicit
    path must trigger SlangNotFound (exit 3) with an actionable install message.
    """
    runner = CliRunner()
    sv_file = tmp_path / "dummy.sv"
    sv_file.write_text(
        "module dummy(input logic clk, a, b);\n"
        "  assert property (@(posedge clk) a && b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        main,
        [str(sv_file), "--slang-path", "/nonexistent/slang_binary"],
    )

    assert result.exit_code == 3, (
        f"Expected exit code 3 for missing slang binary, got {result.exit_code}.\n"
        f"Output: {result.output}"
    )
    assert "Install:" in result.output or "slang not found" in result.output, (
        f"Expected 'Install:' or 'slang not found' in output: {result.output}"
    )


# ── Test 5: nonexistent input file (no slang required) ────────────────────


def test_e2e_nonexistent_input() -> None:
    """CLI exits non-zero when the input file does not exist.

    click.Path(exists=True) handles this before the pipeline runs — no slang
    binary is needed.
    """
    runner = CliRunner()
    result = runner.invoke(main, ["/nonexistent/path/does_not_exist.sv"])
    assert result.exit_code != 0, (
        f"Expected non-zero exit code for nonexistent input, got {result.exit_code}"
    )


# ── Test 6: stdout mode (no --output) ────────────────────────────────────


@requires_slang
def test_e2e_bool_assert_stdout() -> None:
    """Full pipeline without --output writes SV to stdout (exit 0).

    Verifies that the CLI's default behaviour (no -o flag) produces valid
    SV text on stdout rather than writing a file.
    """
    runner = CliRunner()
    result = runner.invoke(main, [str(_FIXTURES / "bool_assert.sv")])

    assert result.exit_code == 0, (
        f"Expected exit code 0 in stdout mode, got {result.exit_code}.\nOutput: {result.output}"
    )
    assert "module sva_my_check" in result.output
    assert "endmodule" in result.output


@requires_slang
def test_e2e_bool_semantics_fixture_renders_supported_forms(tmp_path: Path) -> None:
    """Real source fixture preserves structured boolean semantics through RTL emission."""
    runner = CliRunner()
    output_dir = tmp_path / "bool_semantics_out"
    result = runner.invoke(
        main,
        [str(_FIXTURES / "bool_semantics.sv"), "--output", str(output_dir)],
    )

    assert result.exit_code == 0, (
        f"Expected exit code 0 for bool_semantics.sv, got {result.exit_code}.\n"
        f"Output: {result.output}"
    )
    assert output_dir.is_dir(), "Expected directory output for multi-assertion fixture"

    generated = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(output_dir.glob("sva_*.sv"))
    )
    assert "module sva_bool_or" in generated
    assert "module sva_bool_not" in generated
    assert "module sva_bool_nested" in generated
    assert "module sva_bool_eq" in generated
    assert "module sva_bool_ne" in generated
    assert "module sva_bool_bit" in generated
    assert "(a || b)" in generated
    assert "(!a)" in generated
    assert "((a && b) || (!c))" in generated
    assert "(data == 4'b11)" in generated
    assert "(data != 4'b0)" in generated
    assert "(data[0])" in generated
    assert "input  logic [3:0] data" in generated


# ── Test 7: --dump-tree on bool_assert.sv ────────────────────────────────────


@requires_slang
def test_e2e_dump_tree_bool_assert() -> None:
    """--dump-tree on bool_assert.sv exits 0 and prints structured tree output.

    Verifies the --dump-tree flag produces expected section headers,
    CheckerNode markers with hashes, and the bool_expr template name.
    """
    runner = CliRunner()
    result = runner.invoke(
        main, [str(_FIXTURES / "bool_assert.sv"), "--dump-tree"]
    )
    assert result.exit_code == 0, (
        f"Expected exit code 0, got {result.exit_code}.\nOutput: {result.output}"
    )
    assert "=== Pre-normalized IR ===" in result.output
    assert "=== Composition Tree ===" in result.output
    assert "CheckerNode:" in result.output
    assert "[hash:" in result.output
    assert "bool_expr" in result.output


# ── Test 8: --dump-tree does not create output file ──────────────────────────


@requires_slang
def test_e2e_dump_tree_no_output_file(tmp_path: Path) -> None:
    """--dump-tree with --output prevents RTL file creation.

    Even when --output is specified, --dump-tree should print the tree
    and exit without writing any RTL file.
    """
    runner = CliRunner()
    output_file = tmp_path / "should_not_exist.sv"
    result = runner.invoke(
        main,
        [str(_FIXTURES / "bool_assert.sv"), "--dump-tree", "--output", str(output_file)],
    )
    assert result.exit_code == 0, (
        f"Expected exit code 0, got {result.exit_code}.\nOutput: {result.output}"
    )
    assert not output_file.exists(), "RTL file should not exist when --dump-tree is used"
