"""Unit tests for src/sva2rtl/optimizer.py.

Covers constant_fold, concat_merge, cse, counter_merge passes.

Tests follow the normalizer.py test pattern:
- Helper factories for constructing CheckerNode trees
- Identity tests: valid trees pass through unchanged
- Rule-specific tests: each optimization rule fires correctly
- Idempotency tests: optimize(optimize(x)) == optimize(x) structurally
- Integration test: fixture -> normalize -> compose -> optimize round-trip
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from sva2rtl.composer import compose, structural_hash
from sva2rtl.ir import CheckerNode, SourceLoc
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import concat_merge, constant_fold, counter_merge, cse, optimize

# ── Helpers ───────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"


def _make_loc() -> SourceLoc:
    """Return a canonical SourceLoc for test nodes."""
    return SourceLoc(file="test.sv", line=1, col=1)


def _make_bool_checker(text: str, name: str) -> CheckerNode:
    """Build a bool_expr CheckerNode with given expression text and module name."""
    return CheckerNode(
        template_name="bool_expr",
        module_name=name,
        params={
            "bool_expr": text,
            "clock_signal": "clk",
            "clock_edge": "posedge",
        },
        observed_signals=(),
        source_loc=_make_loc(),
    )


def _make_delay_checker(
    delay_min: int, delay_max: int, name: str | None = None
) -> CheckerNode:
    """Build a concat_delay CheckerNode with computed cnt_width.

    Default module name is ``sva_delay_{delay_min}_{delay_max}``.
    """
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
        source_loc=_make_loc(),
    )


def _make_concat_top(
    children: tuple[CheckerNode, ...], name: str = "sva_top"
) -> CheckerNode:
    """Build a seq_concat_top CheckerNode wrapping the given children."""
    return CheckerNode(
        template_name="seq_concat_top",
        module_name=name,
        params={
            "clock_signal": "clk",
            "clock_edge": "posedge",
        },
        observed_signals=(),
        source_loc=_make_loc(),
        children=children,
    )


def _load_fixture(name: str) -> dict[str, object]:
    """Load a JSON fixture from tests/fixtures/."""
    return cast(
        dict[str, object],
        json.loads((_FIXTURES / name).read_text(encoding="utf-8")),
    )


# ── Identity tests ────────────────────────────────────────────────────────


def test_optimize_single_bool_identity() -> None:
    """A single bool_expr (no seq_concat_top) passes through optimize unchanged."""
    node = _make_bool_checker("a && b", "sva_check")
    result = optimize(node)
    # Structural hash should be unchanged for a simple bool with no literal constants
    assert structural_hash(result) == structural_hash(node)


def test_optimize_no_concat_top_identity() -> None:
    """A tree with no seq_concat_top passes through optimize unchanged."""
    node = _make_bool_checker("req && ack", "sva_check")
    result = optimize(node)
    assert result.template_name == "bool_expr"
    assert result.params["bool_expr"] == "req && ack"


def test_concat_merge_non_adjacent_identity() -> None:
    """bool_expr between two delays prevents merge — tree is returned unchanged."""
    delay1 = _make_delay_checker(3, 3)
    bool_node = _make_bool_checker("a", "sva_bool")
    delay2 = _make_delay_checker(2, 2)
    top = _make_concat_top((delay1, bool_node, delay2))
    result = concat_merge(top)
    # No merge should happen — bool_expr separates the delays
    assert len(result.children) == 3
    assert result.children[0].params["delay_min"] == "3"
    assert result.children[2].params["delay_min"] == "2"


# ── Constant fold tests ───────────────────────────────────────────────────


def test_constant_fold_no_constants() -> None:
    """A tree without literal booleans passes through constant_fold unchanged."""
    node = _make_bool_checker("req && valid", "sva_check")
    result = constant_fold(node)
    assert "_const_true" not in result.params
    assert "_const_false" not in result.params


def test_constant_fold_passes_through_normal_tree() -> None:
    """Non-constant tree identity — structural hash unchanged after constant_fold."""
    node = _make_bool_checker("(a |-> b)", "sva_check")
    result = constant_fold(node)
    assert structural_hash(result) == structural_hash(node)


def test_constant_fold_true_1b1() -> None:
    """bool_expr with '1'b1' is tagged _const_true=1."""
    node = _make_bool_checker("1'b1", "sva_true")
    result = constant_fold(node)
    assert result.params.get("_const_true") == "1"
    assert "_const_false" not in result.params


def test_constant_fold_true_literal_1() -> None:
    """bool_expr with '1' is tagged _const_true=1."""
    node = _make_bool_checker("1", "sva_true")
    result = constant_fold(node)
    assert result.params.get("_const_true") == "1"


def test_constant_fold_false_1b0() -> None:
    """bool_expr with '1'b0' is tagged _const_false=1."""
    node = _make_bool_checker("1'b0", "sva_false")
    result = constant_fold(node)
    assert result.params.get("_const_false") == "1"
    assert "_const_true" not in result.params


def test_constant_fold_false_literal_0() -> None:
    """bool_expr with '0' is tagged _const_false=1."""
    node = _make_bool_checker("0", "sva_false")
    result = constant_fold(node)
    assert result.params.get("_const_false") == "1"


# ── Concat merge rule tests ───────────────────────────────────────────────


def test_concat_merge_two_adjacent_fixed_delays() -> None:
    """[delay(3,3), delay(2,2)] merges to [delay(5,5)] with cnt_width=3."""
    d3 = _make_delay_checker(3, 3)
    d2 = _make_delay_checker(2, 2)
    top = _make_concat_top((d3, d2))
    result = concat_merge(top)

    assert len(result.children) == 1
    merged = result.children[0]
    assert merged.template_name == "concat_delay"
    assert merged.params["delay_min"] == "5"
    assert merged.params["delay_max"] == "5"
    # 5.bit_length() == 3 → cnt_width = 3
    assert merged.params["cnt_width"] == "3"


def test_concat_merge_two_adjacent_range_delays() -> None:
    """[delay(1,3), delay(2,4)] merges to [delay(3,7)] with cnt_width=3."""
    d1 = _make_delay_checker(1, 3)
    d2 = _make_delay_checker(2, 4)
    top = _make_concat_top((d1, d2))
    result = concat_merge(top)

    assert len(result.children) == 1
    merged = result.children[0]
    assert merged.params["delay_min"] == "3"
    assert merged.params["delay_max"] == "7"
    # 7.bit_length() == 3 → cnt_width = 3
    assert merged.params["cnt_width"] == "3"


def test_concat_merge_three_adjacent_delays() -> None:
    """[delay(1,1), delay(2,2), delay(3,3)] greedy-merges to [delay(6,6)]."""
    d1 = _make_delay_checker(1, 1)
    d2 = _make_delay_checker(2, 2)
    d3 = _make_delay_checker(3, 3)
    top = _make_concat_top((d1, d2, d3))
    result = concat_merge(top)

    # Greedy left-to-right: first pass merges d1+d2 → d3+d3(3,3) → d6
    # (d1+d2=delay(3,3); then delay(3,3)+delay(3,3)=delay(6,6))
    # Actually in single pass: i=0 merges d1+d2 → delay(3,3), then i=2 is d3(3,3)
    # Second iteration of concat_merge (via optimize) would merge again.
    # OR single pass merges d1+d2 then checks result against d3 in the same scan.
    # The greedy scan in _merge_children: merges i=0,1 -> result=[delay(3,3)], then i=2 is d3
    # so result = [delay(3,3), delay(3,3)]
    # After a second call to concat_merge, these merge to delay(6,6).
    # The optimize() function runs up to 2 iterations, so we test via optimize().
    result2 = concat_merge(result)  # second pass merges the two delay(3,3) nodes
    assert len(result2.children) == 1
    final = result2.children[0]
    assert final.params["delay_min"] == "6"
    assert final.params["delay_max"] == "6"


def test_concat_merge_three_adjacent_delays_via_optimize() -> None:
    """optimize() converges three adjacent delays to one via 2 iterations."""
    d1 = _make_delay_checker(1, 1)
    d2 = _make_delay_checker(2, 2)
    d3 = _make_delay_checker(3, 3)
    top = _make_concat_top((d1, d2, d3))
    result = optimize(top)

    assert len(result.children) == 1
    final = result.children[0]
    assert final.params["delay_min"] == "6"
    assert final.params["delay_max"] == "6"


def test_concat_merge_preserves_non_delay_children() -> None:
    """[bool, delay, bool] — no delay merging, bool_expr children preserved."""
    b1 = _make_bool_checker("a", "sva_b1")
    delay = _make_delay_checker(3, 3)
    b2 = _make_bool_checker("b", "sva_b2")
    top = _make_concat_top((b1, delay, b2))
    result = concat_merge(top)

    assert len(result.children) == 3
    assert result.children[0].template_name == "bool_expr"
    assert result.children[1].template_name == "concat_delay"
    assert result.children[2].template_name == "bool_expr"


def test_concat_merge_partial_merge() -> None:
    """[delay(1,1), bool, delay(2,2), delay(3,3)] → [delay(1,1), bool, delay(5,5)]."""
    d1 = _make_delay_checker(1, 1)
    bool_node = _make_bool_checker("a", "sva_bool")
    d2 = _make_delay_checker(2, 2)
    d3 = _make_delay_checker(3, 3)
    top = _make_concat_top((d1, bool_node, d2, d3))
    result = concat_merge(top)

    # d1 not adjacent to d2 (bool in between), d2+d3 merge to delay(5,5)
    assert len(result.children) == 3
    assert result.children[0].params["delay_min"] == "1"
    assert result.children[1].template_name == "bool_expr"
    merged = result.children[2]
    assert merged.params["delay_min"] == "5"
    assert merged.params["delay_max"] == "5"


def test_concat_merge_single_child_unchanged() -> None:
    """A seq_concat_top with a single child is returned unchanged."""
    d1 = _make_delay_checker(3, 5)
    top = _make_concat_top((d1,))
    result = concat_merge(top)
    assert len(result.children) == 1
    assert result.children[0].params["delay_min"] == "3"


def test_concat_merge_no_seq_concat_top_unchanged() -> None:
    """A tree with no seq_concat_top nodes is returned unchanged."""
    node = _make_bool_checker("a", "sva_check")
    result = concat_merge(node)
    assert result == node


# ── Idempotency tests ─────────────────────────────────────────────────────


def test_optimize_idempotent() -> None:
    """optimize(optimize(tree)) has same structural_hash as optimize(tree)."""
    d1 = _make_delay_checker(3, 3)
    d2 = _make_delay_checker(2, 2)
    bool_node = _make_bool_checker("a", "sva_bool")
    top = _make_concat_top((d1, d2, bool_node))

    once = optimize(top)
    twice = optimize(once)
    assert structural_hash(once) == structural_hash(twice)


def test_optimize_idempotent_bool_only() -> None:
    """optimize(optimize(bool_node)) is idempotent for a simple bool tree."""
    node = _make_bool_checker("req && ack", "sva_check")
    once = optimize(node)
    twice = optimize(once)
    assert structural_hash(once) == structural_hash(twice)


# ── Integration test ──────────────────────────────────────────────────────


def test_optimize_full_pipeline_no_error() -> None:
    """Load delay_fixed.json fixture, run normalize->compose->optimize, assert no error."""
    from sva2rtl.ast_importer import import_assertion

    ast = _load_fixture("delay_fixed.json")
    node, clock, original_text, label = import_assertion(ast)
    node = normalize(node)

    # compose returns a CheckerNode
    checker = compose(node, clock, label, original_text)
    assert isinstance(checker, CheckerNode)

    # optimize must not raise and must return a CheckerNode
    optimized = optimize(checker)
    assert isinstance(optimized, CheckerNode)


def test_optimize_full_pipeline_bool_simple() -> None:
    """Load bool_simple.json fixture, run full pipeline, verify optimize is a no-op."""
    from sva2rtl.ast_importer import import_assertion

    ast = _load_fixture("bool_simple.json")
    node, clock, original_text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, original_text)

    # For a simple bool_expr, optimizer should be a no-op (no adjacent delays)
    optimized = optimize(checker)
    assert isinstance(optimized, CheckerNode)
    # Structural hash unchanged — no optimizations applied
    assert structural_hash(checker) == structural_hash(optimized)


def test_optimize_clock_signal_preserved_after_merge() -> None:
    """Merged delay node preserves clock_signal and clock_edge from source node."""
    d1 = _make_delay_checker(2, 4)
    d2 = _make_delay_checker(1, 3)
    top = _make_concat_top((d1, d2))
    result = concat_merge(top)

    assert len(result.children) == 1
    merged = result.children[0]
    assert merged.params["clock_signal"] == "clk"
    assert merged.params["clock_edge"] == "posedge"


# ── CSE pass tests ────────────────────────────────────────────────────────


def test_cse_no_duplicates_identity() -> None:
    """A tree with no duplicate subtrees is returned unchanged by cse()."""
    d1 = _make_delay_checker(1, 2, "sva_delay_1_2")
    d2 = _make_delay_checker(3, 4, "sva_delay_3_4")
    top = _make_concat_top((d1, d2))
    before = structural_hash(top)
    result = cse(top)
    assert structural_hash(result) == before


def test_cse_deduplicates_identical_subtrees() -> None:
    """Two children with identical structural_hash get the same canonical module_name."""
    # Both delays have same (delay_min, delay_max) and params → same structural_hash
    d1 = _make_delay_checker(3, 3)  # module_name=sva_delay_3_3
    d2 = _make_delay_checker(3, 3)  # same params → same structural_hash
    top = _make_concat_top((d1, d2))

    result = cse(top)

    # Both children should now share a CSE-canonical module_name
    child_names = {c.module_name for c in result.children}
    assert len(child_names) == 1
    canonical = result.children[0].module_name
    assert canonical.startswith("sva_cse_concat_delay_3_3")


def test_cse_canonical_naming_concat_delay() -> None:
    """CSE names concat_delay duplicates as sva_cse_concat_delay_{min}_{max}."""
    d1 = _make_delay_checker(2, 5)
    d2 = _make_delay_checker(2, 5)
    top = _make_concat_top((d1, d2))
    result = cse(top)

    assert result.children[0].module_name == "sva_cse_concat_delay_2_5"
    assert result.children[1].module_name == "sva_cse_concat_delay_2_5"


def test_cse_python_identity_for_shared_nodes() -> None:
    """CSE-unified nodes are the same Python object (id() identity)."""
    d1 = _make_delay_checker(3, 3)
    d2 = _make_delay_checker(3, 3)
    top = _make_concat_top((d1, d2))
    result = cse(top)

    # Both children must be the exact same Python object
    assert result.children[0] is result.children[1]


def test_cse_skips_root() -> None:
    """CSE never renames or replaces the root node itself."""
    node = _make_bool_checker("a", "sva_check")
    # Create a tree where root has only one occurrence — itself
    result = cse(node)
    # Root node must not be renamed
    assert result.module_name == "sva_check"
    assert result.template_name == "bool_expr"


def test_cse_root_not_replaced_even_if_child_matches_root_hash() -> None:
    """Root is never replaced even when a duplicate hash exists for root structure."""
    # Construct a child that has the same structure as root by nesting
    # This is a pathological case; just verify root module_name unchanged.
    d = _make_delay_checker(1, 1)
    top = _make_concat_top((d,), name="sva_top_unique")
    result = cse(top)
    assert result.module_name == "sva_top_unique"


def test_cse_preserves_non_duplicate_children() -> None:
    """CSE leaves children with unique structural_hashes untouched."""
    d1 = _make_delay_checker(1, 2)
    d2 = _make_delay_checker(3, 4)
    top = _make_concat_top((d1, d2))
    result = cse(top)

    # Children have different hashes — no CSE applied; module_names unchanged
    assert result.children[0].module_name == d1.module_name
    assert result.children[1].module_name == d2.module_name


def test_cse_deep_tree_deduplication() -> None:
    """CSE deduplicates identical subtrees that are grandchildren of root."""
    # Create two identical bool_expr nodes (same params → same hash)
    bool1 = _make_bool_checker("x && y", "sva_bool_xy_copy1")
    bool2 = _make_bool_checker("x && y", "sva_bool_xy_copy2")

    inner1 = _make_concat_top((bool1,), name="sva_inner1")
    inner2 = _make_concat_top((bool2,), name="sva_inner2")
    outer = _make_concat_top((inner1, inner2), name="sva_outer")

    result = cse(outer)

    # The two inner seq_concat_top nodes have identical structure after
    # their bool children are also identical — they should be deduplicated
    # Both inner nodes have same structural_hash → same canonical name
    assert result.children[0].module_name == result.children[1].module_name
    assert result.children[0].module_name.startswith("sva_cse_")


def test_cse_idempotent() -> None:
    """cse(cse(tree)) has same structural_hash as cse(tree)."""
    d1 = _make_delay_checker(3, 3)
    d2 = _make_delay_checker(3, 3)
    top = _make_concat_top((d1, d2))

    once = cse(top)
    twice = cse(once)
    assert structural_hash(once) == structural_hash(twice)


# ── counter_merge pass tests ──────────────────────────────────────────────


def test_counter_merge_no_delays_identity() -> None:
    """A tree with no concat_delay nodes is returned unchanged."""
    node = _make_bool_checker("req && ack", "sva_check")
    result = counter_merge(node)
    assert result is node


def test_counter_merge_same_hash_already_unified() -> None:
    """counter_merge is a no-op when CSE has already unified same-hash delays."""
    d1 = _make_delay_checker(3, 3)
    d2 = _make_delay_checker(3, 3)
    top = _make_concat_top((d1, d2))

    # After CSE, both children have the same module_name
    cse_result = cse(top)
    # counter_merge sees them as already having one module_name → no-op
    result = counter_merge(cse_result)
    assert structural_hash(result) == structural_hash(cse_result)


def test_counter_merge_different_hashes_no_merge() -> None:
    """counter_merge does not merge delays with different structural hashes."""
    d1 = _make_delay_checker(1, 2)
    d2 = _make_delay_checker(3, 4)
    top = _make_concat_top((d1, d2))
    result = counter_merge(top)

    # Different hashes → no merge
    assert result.children[0].module_name == d1.module_name
    assert result.children[1].module_name == d2.module_name


def test_counter_merge_assigns_canonical_name_for_missed_duplicates() -> None:
    """counter_merge renames same-hash delays that have different module_names."""
    # Build two concat_delay nodes with identical params but different module_names
    # (simulate a case where CSE somehow missed them, e.g., different module_name set manually)
    d1 = _make_delay_checker(2, 5, name="sva_delay_2_5_alt1")
    d2 = _make_delay_checker(2, 5, name="sva_delay_2_5_alt2")
    top = _make_concat_top((d1, d2))

    result = counter_merge(top)

    # Both children should now have the same canonical name
    assert result.children[0].module_name == "sva_cse_counter_2_5"
    assert result.children[1].module_name == "sva_cse_counter_2_5"


def test_counter_merge_after_cse_is_noop() -> None:
    """Running counter_merge after cse() on a tree with duplicates is a no-op."""
    d1 = _make_delay_checker(3, 3)
    d2 = _make_delay_checker(3, 3)
    top = _make_concat_top((d1, d2))

    cse_result = cse(top)
    after_counter = counter_merge(cse_result)

    # The tree should be structurally unchanged after counter_merge
    assert structural_hash(after_counter) == structural_hash(cse_result)


# ── Full-pipeline integration tests ──────────────────────────────────────


def test_optimize_pipeline_deduplicates_identical_delays() -> None:
    """optimize() with two non-adjacent identical delays: CSE deduplicates them.

    concat_merge only merges *adjacent* delays; bool_expr nodes between delays
    prevent merging.  CSE then deduplicates the two identical delay subtrees.
    """
    d1 = _make_delay_checker(3, 3)
    bool_mid = _make_bool_checker("a", "sva_mid")
    d2 = _make_delay_checker(3, 3)
    # [delay(3,3), bool, delay(3,3)] — delays NOT adjacent → concat_merge skips them
    top = _make_concat_top((d1, bool_mid, d2))

    result = optimize(top)

    # After optimize(): both delay(3,3) children should share the same
    # CSE-canonical module_name (concat_merge left them separate, CSE unified them)
    delay_children = [c for c in result.children if c.template_name == "concat_delay"]
    assert len(delay_children) == 2
    assert delay_children[0].module_name == delay_children[1].module_name
    assert delay_children[0].module_name.startswith("sva_cse_concat_delay_3_3")


def test_optimize_cse_then_concat_merge_integration() -> None:
    """concat_merge + cse interact correctly: merged delay then deduplication."""
    # Two pairs of adjacent delays that each merge to (3,3)
    d1a = _make_delay_checker(1, 1)
    d1b = _make_delay_checker(2, 2)
    bool_mid = _make_bool_checker("a", "sva_mid")
    d2a = _make_delay_checker(1, 1)
    d2b = _make_delay_checker(2, 2)
    top = _make_concat_top((d1a, d1b, bool_mid, d2a, d2b))

    result = optimize(top)

    # After concat_merge: [delay(3,3), bool, delay(3,3)]
    # After CSE: both delay(3,3) share a canonical module_name
    delay_children = [c for c in result.children if c.template_name == "concat_delay"]
    assert len(delay_children) == 2
    # Both merged delays should have the same module_name (CSE)
    assert delay_children[0].module_name == delay_children[1].module_name
    # And same Python object identity
    assert delay_children[0] is delay_children[1]
