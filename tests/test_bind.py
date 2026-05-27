"""Tests for bind statement generation (OUT-04)."""

from __future__ import annotations

import json
from pathlib import Path

from sva2rtl import __version__
from sva2rtl.ast_importer import extract_dut_module, import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_bind
from sva2rtl.ir import CheckerNode, SourceLoc

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_loc(file: str = "test.sv", line: int = 1, col: int = 1) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _simple_checker() -> CheckerNode:
    """Return a minimal CheckerNode with two observed signals."""
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
    )


def _load_checker(fixture_name: str) -> CheckerNode:
    ast = json.loads((FIXTURES_DIR / f"{fixture_name}.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    return compose(ir_node, clock, label, text)


# ── emit_bind basic output ────────────────────────────────────────────────────


def test_emit_bind_basic_returns_string() -> None:
    """emit_bind() returns a non-empty string."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert isinstance(result, str)
    assert len(result) > 0


def test_emit_bind_contains_bind_keyword() -> None:
    """emit_bind() output starts with a 'bind' statement."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert "bind" in result


def test_bind_dut_module_name_in_output() -> None:
    """'bind <dut_name>' appears with the correct DUT module name."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert "bind my_dut" in result


def test_bind_monitor_module_instantiation() -> None:
    """Bind statement instantiates the monitor with 'sva_my_check u_sva_my_check'."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert "sva_my_check u_sva_my_check" in result


def test_bind_default_start() -> None:
    """Bind output contains '.start        (1'b1)'."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert "1'b1" in result
    assert ".start" in result


def test_bind_default_disable_i() -> None:
    """Bind output contains '.disable_i    (1'b0)'."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert "1'b0" in result
    assert ".disable_i" in result


def test_bind_port_connections_observed_signals() -> None:
    """All observed signals appear as named port connections in the bind statement."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert ".a(a)" in result
    assert ".b(b)" in result


def test_bind_clock_port_connection() -> None:
    """Bind output contains the clock port connection."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert ".clk" in result and "(clk)" in result


def test_bind_rst_n_port_connection() -> None:
    """Bind output contains '.rst_n(rst_n)' connection."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert ".rst_n" in result and "(rst_n)" in result


def test_bind_ends_with_newline() -> None:
    """emit_bind() output ends with a newline (tool compliance)."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert result.endswith("\n")


def test_bind_contains_version_comment() -> None:
    """Bind output header comment includes the sva2rtl version string."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert f"sva2rtl {__version__}" in result


def test_bind_semicolon_terminator() -> None:
    """Bind instantiation ends with ');' terminator."""
    checker = _simple_checker()
    result = emit_bind(checker, "my_dut")
    assert ");" in result


# ── extract_dut_module ────────────────────────────────────────────────────────


def test_extract_dut_module_bool_labeled() -> None:
    """extract_dut_module() returns the Instance name from bool_labeled.json."""
    ast = json.loads((FIXTURES_DIR / "bool_labeled.json").read_text(encoding="utf-8"))
    dut = extract_dut_module(ast)
    assert isinstance(dut, str)
    assert len(dut) > 0


def test_extract_dut_module_not_unknown() -> None:
    """extract_dut_module() returns a non-placeholder name for known fixtures."""
    ast = json.loads((FIXTURES_DIR / "delay_fixed.json").read_text(encoding="utf-8"))
    dut = extract_dut_module(ast)
    assert dut != "<unknown>"


def test_extract_dut_module_empty_design() -> None:
    """extract_dut_module() returns '<unknown>' for an empty design."""
    dut = extract_dut_module({"design": {"members": []}})
    assert dut == "<unknown>"


# ── Integration: full pipeline to bind ───────────────────────────────────────


def test_emit_bind_from_fixture_pipeline() -> None:
    """Full pipeline: fixture → import → compose → emit_bind produces valid output."""
    ast = json.loads((FIXTURES_DIR / "bool_labeled.json").read_text(encoding="utf-8"))
    dut = extract_dut_module(ast)
    ir_node, clock, text, label = import_assertion(ast)
    checker = compose(ir_node, clock, label, text)
    result = emit_bind(checker, dut)
    assert f"bind {dut}" in result
    assert checker.module_name in result
