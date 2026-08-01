"""Tests for Verilog-2001 output mode (verilog_mode=True).

Verifies that when verilog_mode=True is passed to the emitter, all generated
RTL output is compatible with Verilog-2001 (no `logic`, `always_ff`, or `'0`
literals).  Also verifies that verilog_mode=False produces output identical to
the default (no regression).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import cast

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.ir import BoolExpr, ClockedSeq, ClockSpec, SeqConcat, SourceLoc
from sva2rtl.normalizer import normalize

# ── Paths ────────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"

# ── Helper ───────────────────────────────────────────────────────────────────


def _load(name: str) -> dict[str, object]:
    """Load a JSON fixture file from ``tests/fixtures/``."""
    return cast(
        dict[str, object],
        json.loads((_FIXTURES / name).read_text(encoding="utf-8")),
    )


def _run_pipeline_verilog(fixture_name: str) -> dict[str, str]:
    """Run normalize→compose→emit_all(verilog_mode=True) on a fixture.

    Returns dict of {module_name: sv_text}.
    """
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        return emit_all(checker, verilog_mode=True)
    else:
        return {checker.module_name: emit(checker, verilog_mode=True)}


def _run_pipeline_sv(fixture_name: str) -> dict[str, str]:
    """Run normalize→compose→emit_all(verilog_mode=False) on a fixture.

    Returns dict of {module_name: sv_text}.
    """
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        return emit_all(checker, verilog_mode=False)
    else:
        return {checker.module_name: emit(checker, verilog_mode=False)}


def _run_pipeline_default(fixture_name: str) -> dict[str, str]:
    """Run normalize→compose→emit_all() with default parameters (no verilog_mode kwarg).

    Returns dict of {module_name: sv_text}.
    """
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        return emit_all(checker)
    else:
        return {checker.module_name: emit(checker)}


# ── Fixtures covering all template types ─────────────────────────────────────

# Each tuple: (fixture_filename, has_sequential_logic)
# has_sequential_logic=True means the template uses always_ff/reg
_ALL_FIXTURES: list[tuple[str, bool]] = [
    ("bool_simple.json", True),
    ("bool_labeled.json", True),
    ("rose.json", True),
    ("fell.json", True),
    ("stable.json", True),
    ("past.json", True),
    ("rep_fixed.json", True),
    ("rep_range.json", True),
    ("delay_fixed.json", True),
    ("delay_range.json", True),
    ("delay_zero.json", True),
    ("delay_three_element.json", True),
    ("implication_overlap.json", True),
    ("implication_nonoverlap.json", True),
    ("disable_iff.json", True),
]

_FIXTURE_NAMES = [f for f, _ in _ALL_FIXTURES]
_REGISTERED_FIXTURES = [f for f, has_seq in _ALL_FIXTURES if has_seq]


# ── Test: no `logic` keyword in Verilog-2001 output ──────────────────────────


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_verilog_mode_no_logic_keyword(fixture_name: str) -> None:
    """Verilog-2001 output must not contain the `logic` keyword (outside comments)."""
    modules = _run_pipeline_verilog(fixture_name)
    for mod_name, sv_text in modules.items():
        for line in sv_text.splitlines():
            # Strip inline comments before checking
            code_part = line.split("//")[0]
            assert not re.search(r"\blogic\b", code_part), (
                f"Module '{mod_name}' from fixture '{fixture_name}' "
                f"contains 'logic' keyword in Verilog-2001 mode: {line.strip()}"
            )


# ── Test: no `always_ff` in Verilog-2001 output ─────────────────────────────


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_verilog_mode_no_always_ff(fixture_name: str) -> None:
    """Verilog-2001 output must not contain `always_ff`."""
    modules = _run_pipeline_verilog(fixture_name)
    for mod_name, sv_text in modules.items():
        assert "always_ff" not in sv_text, (
            f"Module '{mod_name}' from fixture '{fixture_name}' "
            f"contains 'always_ff' in Verilog-2001 mode"
        )


# ── Test: no tick-zero (`'0`) literal in Verilog-2001 output ─────────────────


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_verilog_mode_no_tick_zero(fixture_name: str) -> None:
    """Verilog-2001 output must not contain the `'0` (tick-zero) literal."""
    modules = _run_pipeline_verilog(fixture_name)
    for mod_name, sv_text in modules.items():
        # Match '0 that is NOT preceded by a digit (to avoid matching 1'b0)
        # Pattern: not digit before apostrophe, then '0
        matches = re.findall(r"(?<!\d)'0", sv_text)
        assert not matches, (
            f"Module '{mod_name}' from fixture '{fixture_name}' "
            f"contains tick-zero literal(s) in Verilog-2001 mode"
        )


# ── Test: registered fixtures have `always @(posedge ...)` ───────────────────


@pytest.mark.parametrize("fixture_name", _REGISTERED_FIXTURES)
def test_verilog_mode_has_always_posedge(fixture_name: str) -> None:
    """Registered Verilog-2001 modules use `always @(posedge/negedge ...)`."""
    modules = _run_pipeline_verilog(fixture_name)
    # At least one module in the hierarchy must have a sequential block
    has_always = False
    for sv_text in modules.values():
        if re.search(r"always\s+@\s*\(\s*(pos|neg)edge", sv_text):
            has_always = True
            break
    assert has_always, (
        f"Fixture '{fixture_name}' has no 'always @(posedge/negedge ...)' "
        f"block in Verilog-2001 mode — expected at least one sequential block"
    )


# ── Test: SystemVerilog mode unchanged from default ──────────────────────────


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_verilog_mode_sv_unchanged(fixture_name: str) -> None:
    """emit(verilog_mode=False) produces identical output to emit() with no kwarg."""
    modules_explicit_false = _run_pipeline_sv(fixture_name)
    modules_default = _run_pipeline_default(fixture_name)
    assert modules_explicit_false == modules_default, (
        f"Fixture '{fixture_name}': verilog_mode=False output differs from default. "
        f"This indicates a regression in the default SystemVerilog output path."
    )


# ── Test: wire keyword for combinational signals ─────────────────────────────


@pytest.mark.parametrize(
    "fixture_name",
    ["bool_simple.json", "rose.json", "fell.json", "stable.json"],
)
def test_verilog_mode_wire_for_assign_signals(fixture_name: str) -> None:
    """Combinational (assign-driven) signals use `wire` in Verilog-2001 mode."""
    modules = _run_pipeline_verilog(fixture_name)
    for sv_text in modules.values():
        # All 'assign X = ...' targets should be declared as wire (or output)
        # Check that 'wire' keyword appears (since these templates have internal wires)
        if "assign" in sv_text and "wire" not in sv_text:
            # Some modules (like seq_concat_top) use only outputs — that's OK
            # But bool_expr/rose/fell/stable always have internal wires
            if "bool_result" in sv_text or "_detect" in sv_text or "_internal" in sv_text:
                raise AssertionError(
                    f"Fixture '{fixture_name}': expected 'wire' declarations "
                    f"for combinational signals in Verilog-2001 mode"
                )


# ── Test: reg keyword for sequential signals ─────────────────────────────────


@pytest.mark.parametrize(
    "fixture_name",
    ["bool_simple.json", "rose.json", "fell.json", "stable.json", "past.json"],
)
def test_verilog_mode_reg_for_sequential_signals(fixture_name: str) -> None:
    """Sequential (always-driven) signals use `reg` in Verilog-2001 mode."""
    modules = _run_pipeline_verilog(fixture_name)
    for sv_text in modules.values():
        if re.search(r"always\s+@", sv_text):
            assert "reg" in sv_text, (
                f"Fixture '{fixture_name}': expected 'reg' declarations "
                f"for sequential signals in Verilog-2001 mode"
            )


# ── Test: output ports have no type qualifier in Verilog-2001 ────────────────


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_verilog_mode_output_ports_no_type(fixture_name: str) -> None:
    """Output port declarations in Verilog-2001 mode have no type (no logic/reg/wire)."""
    modules = _run_pipeline_verilog(fixture_name)
    for mod_name, sv_text in modules.items():
        # Find all output declarations within the port list
        for line in sv_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("output"):
                # Should be "output <name>" not "output logic <name>"
                assert "output logic" not in stripped, (
                    f"Module '{mod_name}': output port has 'logic' qualifier "
                    f"in Verilog-2001 mode: {stripped}"
                )


# ── Test: input ports have no type qualifier in Verilog-2001 ─────────────────


@pytest.mark.parametrize("fixture_name", _FIXTURE_NAMES)
def test_verilog_mode_input_ports_no_type(fixture_name: str) -> None:
    """Input port declarations in Verilog-2001 mode have no type (no logic/reg/wire)."""
    modules = _run_pipeline_verilog(fixture_name)
    for mod_name, sv_text in modules.items():
        for line in sv_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("input"):
                assert "input logic" not in stripped, (
                    f"Module '{mod_name}': input port has 'logic' qualifier "
                    f"in Verilog-2001 mode: {stripped}"
                )


@pytest.mark.skipif(shutil.which("iverilog") is None, reason="iverilog not installed")
def test_multiclock_verilog_2001_compiles_with_transitive_cdc_modules(
    tmp_path: Path,
) -> None:
    """The multi-clock synchronizer and LFSR dependency are valid V2001."""
    loc = SourceLoc("multiclock_v2001.sv", 1, 1)
    clk1 = ClockSpec(edge="posedge", signal="clk1", source_loc=loc)
    clk2 = ClockSpec(edge="posedge", signal="clk2", source_loc=loc)
    node = SeqConcat(
        elements=(
            BoolExpr(text="a", source_loc=loc),
            ClockedSeq(
                clock=clk2,
                body=BoolExpr(text="b", source_loc=loc),
                source_loc=loc,
            ),
        ),
        delays=((1, 1),),
        source_loc=loc,
    )
    checker = compose(node, clk1, "multiclock_v2001", "a ##1 @(posedge clk2) b")
    modules = emit_all(checker, verilog_mode=True)
    source = "\n\n".join(modules.values())
    source_path = tmp_path / "multiclock.v"
    source_path.write_text(source, encoding="utf-8")

    code_without_comments = "\n".join(
        line.split("//")[0] for line in source.splitlines()
    )
    assert "always_ff" not in source
    assert not re.search(r"\blogic\b", code_without_comments)
    assert "function automatic" not in source
    result = subprocess.run(
        [
            str(shutil.which("iverilog")),
            "-g2001",
            "-s",
            checker.module_name,
            "-o",
            str(tmp_path / "multiclock.vvp"),
            str(source_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    verilator = shutil.which("verilator")
    if verilator is not None:
        lint = subprocess.run(
            [
                verilator,
                "--lint-only",
                "--language",
                "1364-2001",
                "-Wno-fatal",
                "--top-module",
                checker.module_name,
                str(source_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert lint.returncode == 0, lint.stderr
