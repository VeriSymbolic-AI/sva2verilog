"""Tests for the --dump-tree CLI flag and debug.format_dump_tree function.

Unit tests construct IR and CheckerNode objects directly (no slang needed).
Integration tests invoke the CLI with --dump-tree (require slang).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from click.testing import CliRunner

from sva2rtl.cli import main
from sva2rtl.composer import compose, compute_hash_map
from sva2rtl.debug import format_dump_tree
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockSpec,
    PropImplication,
    SeqConcat,
    SourceLoc,
)
from sva2rtl.normalizer import normalize
from tests.conftest import requires_slang

# ── Shared test helpers ──────────────────────────────────────────────────────

_LOC = SourceLoc("test.sv", 1, 1)
_CLOCK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)
_FIXTURES = Path(__file__).parent / "fixtures"


def _make_bool_checker(text: str = "a") -> tuple[BoolExpr, CheckerNode, dict[str, str]]:
    """Create a simple BoolExpr IR node and compose it into a CheckerNode."""
    ir_node = BoolExpr(text=text, source_loc=_LOC)
    checker = compose(ir_node, _CLOCK, "test_mod", text)
    hash_map = compute_hash_map(checker)
    return ir_node, checker, hash_map


def _make_implication_checker() -> tuple[PropImplication, CheckerNode, dict[str, str]]:
    """Create a PropImplication IR node and compose it."""
    ant = BoolExpr(text="a", source_loc=_LOC)
    con = BoolExpr(text="b", source_loc=_LOC)
    ir_node = PropImplication(
        antecedent=ant, consequent=con, overlapping=True, source_loc=_LOC
    )
    normalized = normalize(ir_node)
    checker = compose(normalized, _CLOCK, "test_impl", "a |-> b")
    hash_map = compute_hash_map(checker)
    return ir_node, checker, hash_map


# ── Unit tests (no slang needed) ─────────────────────────────────────────────


def test_dump_tree_contains_ir_section() -> None:
    """Output contains the '=== Pre-normalized IR ===' header."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    assert "=== Pre-normalized IR ===" in output


def test_dump_tree_contains_checker_section() -> None:
    """Output contains the '=== Composition Tree ===' header."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    assert "=== Composition Tree ===" in output


def test_dump_tree_shows_hash() -> None:
    """Output contains [hash: followed by 8 hex chars and ]."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    assert re.search(r"\[hash:[0-9a-f]{8}\]", output), (
        f"Expected [hash:<8hex>] pattern in output:\n{output}"
    )


def test_dump_tree_shows_template_name() -> None:
    """Output contains the template_name of the node (e.g., 'bool_expr')."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    assert "bool_expr" in output


def test_dump_tree_indents_children() -> None:
    """For a parent with children, child lines have more leading spaces."""
    ir_node, checker, hash_map = _make_implication_checker()
    output = format_dump_tree(ir_node, checker, hash_map)

    # Find lines with "CheckerNode:" - children should have more indent
    checker_lines = [
        line for line in output.split("\n") if "CheckerNode:" in line
    ]
    assert len(checker_lines) >= 2, "Expected at least parent + child CheckerNode lines"

    # Parent is first, children have more leading spaces
    parent_indent = len(checker_lines[0]) - len(checker_lines[0].lstrip())
    child_indent = len(checker_lines[1]) - len(checker_lines[1].lstrip())
    assert child_indent > parent_indent, (
        f"Child indent ({child_indent}) should be > parent indent ({parent_indent})"
    )


def test_dump_tree_ir_shows_bool_expr() -> None:
    """IR section shows BoolExpr with the expression text."""
    ir_node, checker, hash_map = _make_bool_checker("(x && y)")
    output = format_dump_tree(ir_node, checker, hash_map)
    assert 'BoolExpr("(x && y)")' in output


def test_dump_tree_ir_shows_implication() -> None:
    """IR section shows PropImplication with overlapping/non-overlapping."""
    ir_node, checker, hash_map = _make_implication_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    assert "PropImplication(overlapping)" in output


def test_dump_tree_seq_concat_shows_delays() -> None:
    """IR section shows SeqConcat with delay info."""
    a = BoolExpr(text="a", source_loc=_LOC)
    b = BoolExpr(text="b", source_loc=_LOC)
    ir_node = SeqConcat(elements=(a, b), delays=((2, 5),), source_loc=_LOC)
    normalized = normalize(ir_node)
    checker = compose(normalized, _CLOCK, "test_concat", "a ##[2:5] b")
    hash_map = compute_hash_map(checker)
    output = format_dump_tree(ir_node, checker, hash_map)
    assert "SeqConcat" in output
    assert "(2,5)" in output


# ── CLI integration tests (requires slang) ───────────────────────────────────


@requires_slang
def test_cli_dump_tree_exits_0() -> None:
    """CLI with --dump-tree exits with code 0."""
    runner = CliRunner()
    result = runner.invoke(main, [str(_FIXTURES / "bool_assert.sv"), "--dump-tree"])
    assert result.exit_code == 0, (
        f"Expected exit_code 0, got {result.exit_code}.\nOutput: {result.output}"
    )


@requires_slang
def test_cli_dump_tree_no_rtl_emitted(tmp_path: Path) -> None:
    """With --dump-tree and --output specified, no output file is created."""
    runner = CliRunner()
    output_file = tmp_path / "should_not_exist.sv"
    result = runner.invoke(
        main,
        [str(_FIXTURES / "bool_assert.sv"), "--dump-tree", "--output", str(output_file)],
    )
    assert result.exit_code == 0
    assert not output_file.exists(), "RTL file should not be created when --dump-tree is used"


@requires_slang
def test_cli_dump_tree_output_has_structure() -> None:
    """CLI --dump-tree stdout contains CheckerNode: and [hash: markers."""
    runner = CliRunner()
    result = runner.invoke(main, [str(_FIXTURES / "bool_assert.sv"), "--dump-tree"])
    assert result.exit_code == 0
    assert "CheckerNode:" in result.output
    assert "[hash:" in result.output
    assert "=== Pre-normalized IR ===" in result.output
    assert "=== Composition Tree ===" in result.output
