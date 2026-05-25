"""Unit tests for src/sva2rtl/emitter.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from sva2rtl import __version__
from sva2rtl.emitter import emit, write_output
from sva2rtl.ir import CheckerNode, SourceLoc

# ── Helpers ───────────────────────────────────────────────────────────────


def _make_loc(file: str = "test.sv", line: int = 3, col: int = 5) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _labeled_checker() -> CheckerNode:
    """Return the CheckerNode that should match tests/golden/bool_labeled.sv."""
    loc = _make_loc()
    return CheckerNode(
        template_name="bool_expr",
        module_name="sva_my_check",
        params={
            "module_name": "sva_my_check",
            "bool_expr": "(a && b)",
            "clock_signal": "clk",
            "clock_edge": "posedge",
            "source_loc": str(loc),
            "sva2rtl_version": __version__,
            "original_text": "(a && b)",
        },
        observed_signals=(("a", "a"), ("b", "b")),
        source_loc=loc,
        children=(),
    )


# ── emit ──────────────────────────────────────────────────────────────────


def test_emit_bool_simple() -> None:
    """emit() returns a non-empty string for a simple bool checker."""
    checker = _labeled_checker()
    result = emit(checker)
    assert isinstance(result, str)
    assert len(result) > 0


def test_emit_contains_module_name() -> None:
    """Emitted SV contains 'module sva_my_check'."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "module sva_my_check" in result


def test_emit_contains_reset() -> None:
    """Emitted SV contains synchronous reset 'if (!rst_n)'."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "if (!rst_n)" in result


def test_emit_contains_bool_expr() -> None:
    """Emitted SV contains the boolean expression text."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "(a && b)" in result


def test_emit_all_ports_present() -> None:
    """Emitted SV contains all required standard output ports."""
    checker = _labeled_checker()
    result = emit(checker)
    for port in ("active", "pass", "fail", "attempt_fired"):
        assert port in result, f"Missing required port: {port}"


def test_emit_contains_clock_signal() -> None:
    """Emitted SV contains the clock signal name."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "clk" in result


def test_emit_contains_always_ff() -> None:
    """Emitted SV contains an 'always_ff' block for registered outputs."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "always_ff" in result


def test_emit_contains_attempt_fired_sticky() -> None:
    """Emitted SV contains the sticky attempt_fired accumulator logic."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "attempt_fired_q | start" in result


def test_emit_ends_with_newline() -> None:
    """Emitted SV text ends with exactly one newline (tool compliance)."""
    checker = _labeled_checker()
    result = emit(checker)
    assert result.endswith("\n")


def test_emit_contains_endmodule() -> None:
    """Emitted SV contains 'endmodule'."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "endmodule" in result


def test_emit_contains_observed_signals_as_ports() -> None:
    """Emitted SV lists each observed signal as an 'input logic' port."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "input  logic a" in result
    assert "input  logic b" in result


def test_emit_contains_version_comment() -> None:
    """Header comment includes the sva2rtl version string."""
    checker = _labeled_checker()
    result = emit(checker)
    assert f"sva2rtl {__version__}" in result


def test_emit_contains_source_loc_comment() -> None:
    """Header comment includes the source location."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "test.sv:3:5" in result


def test_emit_golden_match() -> None:
    """emit() output matches tests/golden/bool_labeled.sv line-by-line."""
    checker = _labeled_checker()
    result = emit(checker)
    golden_path = Path(__file__).parent / "golden" / "bool_labeled.sv"
    golden = golden_path.read_text(encoding="utf-8")

    def norm(s: str) -> list[str]:
        """Strip trailing whitespace per line for whitespace-insensitive compare."""
        return [line.rstrip() for line in s.splitlines()]

    assert norm(result) == norm(golden)


def test_emit_negedge_clock() -> None:
    """Emitted SV correctly reflects a negedge clock spec."""
    loc = _make_loc()
    checker = CheckerNode(
        template_name="bool_expr",
        module_name="sva_neg_test",
        params={
            "module_name": "sva_neg_test",
            "bool_expr": "req",
            "clock_signal": "sys_clk",
            "clock_edge": "negedge",
            "source_loc": str(loc),
            "sva2rtl_version": __version__,
            "original_text": "req",
        },
        observed_signals=(("req", "req"),),
        source_loc=loc,
        children=(),
    )
    result = emit(checker)
    assert "negedge sys_clk" in result
    assert "module sva_neg_test" in result


# ── write_output ──────────────────────────────────────────────────────────


def test_write_output_to_file(tmp_path: Path) -> None:
    """write_output() writes the correct content to the specified file."""
    checker = _labeled_checker()
    sv = emit(checker)
    out_file = tmp_path / "sub" / "output.sv"
    write_output(sv, out_file)
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == sv


def test_write_output_creates_parent_dirs(tmp_path: Path) -> None:
    """write_output() creates intermediate directories that do not yet exist."""
    checker = _labeled_checker()
    sv = emit(checker)
    out_file = tmp_path / "a" / "b" / "c" / "out.sv"
    write_output(sv, out_file)
    assert out_file.exists()


def test_write_output_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """write_output(sv, None) writes the SV text to stdout."""
    checker = _labeled_checker()
    sv = emit(checker)
    write_output(sv, None)
    captured = capsys.readouterr()
    assert captured.out == sv
