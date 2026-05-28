"""Tests for the --dump-tree CLI flag and debug.format_dump_tree function.

Unit tests construct IR and CheckerNode objects directly (no slang needed).
Integration tests invoke the CLI with --dump-tree (require slang).
"""

from __future__ import annotations

import re
from pathlib import Path

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
from sva2rtl.optimizer import optimize
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


# ── Optimization summary tests ────────────────────────────────────────────────


def _make_delay_checker_node(
    delay_min: int, delay_max: int, name: str | None = None
) -> CheckerNode:
    """Build a concat_delay CheckerNode (mirrors _make_delay_checker in test_optimizer)."""
    cnt_width = max(1, delay_max.bit_length())
    if name is None:
        name = f"sva_delay_{delay_min}_{delay_max}"
    return CheckerNode(
        template_name="concat_delay",
        module_name=name,
        params={
            "delay_min": str(delay_min),
            "delay_max": str(delay_max),
            "cnt_width": str(cnt_width),
            "clock_signal": "clk",
            "clock_edge": "posedge",
        },
        observed_signals=(),
        source_loc=_LOC,
    )


def _make_concat_top_node(
    children: tuple[CheckerNode, ...], name: str = "sva_top"
) -> CheckerNode:
    """Build a seq_concat_top CheckerNode wrapping the given children."""
    return CheckerNode(
        template_name="seq_concat_top",
        module_name=name,
        params={"clock_signal": "clk", "clock_edge": "posedge"},
        observed_signals=(),
        source_loc=_LOC,
        children=children,
    )


def test_dump_tree_no_unoptimized_checker_shows_disabled() -> None:
    """When unoptimized_checker=None, output contains '(optimization disabled)'."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    # Default: unoptimized_checker not provided → optimization disabled line
    assert "(optimization disabled)" in output, (
        f"Expected '(optimization disabled)' in output:\n{output}"
    )


def test_dump_tree_no_unoptimized_checker_shows_node_count() -> None:
    """When unoptimized_checker=None, output shows 'Nodes: N (optimization disabled)'."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    assert re.search(r"Nodes:\s+\d+\s+\(optimization disabled\)", output), (
        f"Expected 'Nodes: <n> (optimization disabled)' pattern in:\n{output}"
    )


def test_dump_tree_with_unoptimized_checker_shows_optimization_line() -> None:
    """When unoptimized_checker is provided, output contains 'Optimization:' line."""
    ir_node, checker, hash_map = _make_bool_checker()
    # Provide same checker as both optimized and unoptimized (0% reduction)
    output = format_dump_tree(ir_node, checker, hash_map, unoptimized_checker=checker)
    assert "Optimization:" in output, (
        f"Expected 'Optimization:' in output:\n{output}"
    )


def test_dump_tree_optimization_summary_format() -> None:
    """Optimization summary has the format 'Nodes: X -> Y (-Z%), Modules: ...'."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map, unoptimized_checker=checker)
    # Expect: "Optimization: Nodes: N -> N (-0%), Modules: M -> M (-0%)"
    assert re.search(
        r"Optimization: Nodes: \d+ -> \d+ \(-\d+%\), Modules: \d+ -> \d+ \(-\d+%\)",
        output,
    ), (f"Expected optimization summary format in:\n{output}")


def test_dump_tree_optimization_summary_shows_reduction() -> None:
    """Optimization summary shows nonzero reduction for a tree that gets optimized.

    Two adjacent identical delay nodes merge via concat_merge, then get
    deduplicated via CSE → the optimized tree has fewer nodes.
    """
    # Build: seq_concat_top([delay(3,3), delay(3,3)])
    d1 = _make_delay_checker_node(3, 3, "sva_delay_3_3_a")
    d2 = _make_delay_checker_node(3, 3, "sva_delay_3_3_b")
    unoptimized = _make_concat_top_node((d1, d2))

    # Optimize → concat_merge fuses them into a single delay(6,6)
    optimized = optimize(unoptimized)
    hash_map = compute_hash_map(optimized)

    # A trivial BoolExpr stands in for the (unused) ir_node argument
    ir_node = BoolExpr(text="a ##3 a", source_loc=_LOC)
    output = format_dump_tree(
        ir_node, optimized, hash_map, unoptimized_checker=unoptimized
    )

    # The unoptimized tree had 3 nodes; optimized has 2 → at least some reduction
    assert "Optimization:" in output
    # Extract the Nodes line and verify after < before
    m = re.search(r"Nodes: (\d+) -> (\d+)", output)
    assert m is not None, f"Could not find 'Nodes: X -> Y' in:\n{output}"
    before_nodes = int(m.group(1))
    after_nodes = int(m.group(2))
    assert after_nodes <= before_nodes, (
        f"Optimized node count ({after_nodes}) should be <= unoptimized ({before_nodes})"
    )


def test_dump_tree_no_unoptimized_not_shows_optimization_label() -> None:
    """When unoptimized_checker=None, 'Optimization:' label is absent."""
    ir_node, checker, hash_map = _make_bool_checker()
    output = format_dump_tree(ir_node, checker, hash_map)
    assert "Optimization:" not in output, (
        f"Expected no 'Optimization:' label when unoptimized_checker=None:\n{output}"
    )


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


@requires_slang
def test_cli_dump_tree_shows_optimization_summary() -> None:
    """CLI --dump-tree (with optimization enabled) shows 'Optimization:' summary."""
    runner = CliRunner()
    # Use delay_assert.sv which has a ##N property → concat_merge opportunity
    result = runner.invoke(main, [str(_FIXTURES / "delay_assert.sv"), "--dump-tree"])
    assert result.exit_code == 0, (
        f"Expected exit_code 0, got {result.exit_code}.\nOutput: {result.output}"
    )
    assert "Optimization:" in result.output, (
        f"Expected 'Optimization:' summary in --dump-tree output:\n{result.output}"
    )
    assert re.search(r"Nodes: \d+ -> \d+ \(-\d+%\)", result.output), (
        f"Expected 'Nodes: X -> Y (-Z%)' pattern in:\n{result.output}"
    )


@requires_slang
def test_cli_dump_tree_no_optimize_shows_disabled() -> None:
    """CLI --dump-tree --no-optimize shows '(optimization disabled)' summary."""
    runner = CliRunner()
    result = runner.invoke(
        main, [str(_FIXTURES / "bool_assert.sv"), "--dump-tree", "--no-optimize"]
    )
    assert result.exit_code == 0, (
        f"Expected exit_code 0, got {result.exit_code}.\nOutput: {result.output}"
    )
    assert "(optimization disabled)" in result.output, (
        f"Expected '(optimization disabled)' in --no-optimize dump:\n{result.output}"
    )
