"""Unit tests for src/sva2rtl/composer.py."""

from __future__ import annotations

import re

import pytest

from sva2rtl.composer import (
    compose,
    compute_hash_map,
    extract_signals,
    module_name_from_label,
    structural_hash,
)
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockSpec,
    PropImplication,
    SeqConcat,
    SourceLoc,
    SVANode,
)
from sva2rtl.normalizer import normalize

# ── Helpers ───────────────────────────────────────────────────────────────


def _make_loc(file: str = "test.sv", line: int = 3, col: int = 5) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _make_clock(edge: str = "posedge", signal: str = "clk") -> ClockSpec:
    return ClockSpec(edge=edge, signal=signal, source_loc=_make_loc())


# ── module_name_from_label ────────────────────────────────────────────────


def test_module_name_with_label() -> None:
    """Label 'my_check' produces 'sva_my_check'."""
    assert module_name_from_label("my_check", "a && b") == "sva_my_check"


def test_module_name_without_label_matches_pattern() -> None:
    """No label produces a name matching sva_prop_<8 hex chars>."""
    name = module_name_from_label(None, "a && b")
    assert re.match(r"^sva_prop_[0-9a-f]{8}$", name) is not None


def test_module_name_label_special_chars_sanitized() -> None:
    """Non-alphanumeric label chars are replaced with underscores."""
    name = module_name_from_label("my-check.prop", "x")
    assert name == "sva_my_check_prop"


def test_module_name_no_label_deterministic() -> None:
    """Same property text always produces the same hash-based name."""
    a = module_name_from_label(None, "(a && b)")
    b = module_name_from_label(None, "(a && b)")
    assert a == b


def test_module_name_different_texts_give_different_names() -> None:
    """Different property texts produce different module names."""
    a = module_name_from_label(None, "a && b")
    c = module_name_from_label(None, "a || c")
    assert a != c


def test_module_name_empty_label_produces_sva_() -> None:
    """An empty-string label is treated as a valid (empty) label: 'sva_'."""
    name = module_name_from_label("", "x")
    assert name == "sva_"


# ── extract_signals ───────────────────────────────────────────────────────


def test_extract_signals_simple_pair() -> None:
    """Simple '(a && b)' yields signals 'a' and 'b'."""
    sigs = extract_signals("(a && b)")
    names = {n for n, _ in sigs}
    assert "a" in names
    assert "b" in names


def test_extract_signals_excludes_sv_keywords() -> None:
    """SV keywords like 'logic', 'not', 'or' are not extracted as signals."""
    sigs = extract_signals("logic and or")
    names = {n for n, _ in sigs}
    assert "logic" not in names
    assert "and" not in names
    assert "or" not in names


def test_extract_signals_deduplication() -> None:
    """Each signal name appears exactly once regardless of repetition."""
    sigs = extract_signals("(a && a)")
    names = [n for n, _ in sigs]
    assert names.count("a") == 1


def test_extract_signals_port_equals_signal_name() -> None:
    """In Phase 1, port_name == signal_name for every extracted pair."""
    sigs = extract_signals("(req && ack)")
    for port_name, signal_name in sigs:
        assert port_name == signal_name


def test_extract_signals_order_preserved() -> None:
    """Signals appear in first-seen order."""
    sigs = extract_signals("(a && b && c)")
    names = [n for n, _ in sigs]
    assert names.index("a") < names.index("b") < names.index("c")


def test_extract_signals_empty_expr() -> None:
    """Empty expression string returns empty tuple."""
    sigs = extract_signals("")
    assert sigs == ()


def test_extract_signals_single_signal() -> None:
    """Single-signal expression returns one pair."""
    sigs = extract_signals("my_signal")
    assert len(sigs) == 1
    assert sigs[0] == ("my_signal", "my_signal")


# ── compose ───────────────────────────────────────────────────────────────


def test_compose_bool_expr_returns_checker_node() -> None:
    """compose() on a BoolExpr returns a CheckerNode."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    assert isinstance(checker, CheckerNode)


def test_compose_bool_expr_template_name() -> None:
    """CheckerNode.template_name is 'bool_expr'."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    assert checker.template_name == "bool_expr"


def test_compose_bool_expr_module_name() -> None:
    """CheckerNode.module_name matches the label-derived name."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    assert checker.module_name == "sva_my_check"


def test_compose_params_contains_bool_expr() -> None:
    """params['bool_expr'] is the node text."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    assert checker.params["bool_expr"] == "(a && b)"


def test_compose_params_contains_clock_edge() -> None:
    """params['clock_edge'] matches the ClockSpec edge."""
    loc = _make_loc()
    clock = _make_clock(edge="posedge")
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    assert checker.params["clock_edge"] == "posedge"


def test_compose_params_contains_clock_signal() -> None:
    """params['clock_signal'] matches the ClockSpec signal."""
    loc = _make_loc()
    clock = _make_clock(signal="sys_clk")
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    assert checker.params["clock_signal"] == "sys_clk"


def test_compose_params_contains_sva2rtl_version() -> None:
    """params['sva2rtl_version'] is a non-empty string."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    assert "sva2rtl_version" in checker.params
    assert checker.params["sva2rtl_version"] != ""


def test_compose_params_contains_original_text() -> None:
    """params['original_text'] is the supplied original_text argument."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "a && b")
    assert checker.params["original_text"] == "a && b"


def test_compose_observed_signals_contain_a_and_b() -> None:
    """observed_signals contains both 'a' and 'b' for '(a && b)'."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)
    checker = compose(node, clock, "my_check", "(a && b)")
    names = {n for n, _ in checker.observed_signals}
    assert "a" in names
    assert "b" in names


def test_compose_source_loc_preserved() -> None:
    """CheckerNode.source_loc matches the input node's source_loc."""
    loc = _make_loc(file="prop.sv", line=10, col=2)
    clock = _make_clock()
    node = BoolExpr(text="req", source_loc=loc)
    checker = compose(node, clock, "my_prop", "req")
    assert checker.source_loc == loc


def test_compose_no_children_for_bool_expr() -> None:
    """Bool expression checkers have no sub-children in Phase 1."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="x", source_loc=loc)
    checker = compose(node, clock, None, "x")
    assert checker.children == ()


def test_compose_seq_concat_returns_checker_node() -> None:
    """SeqConcat passed to compose() returns a CheckerNode (no longer unsupported)."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "my_check", "a ##1 b")
    assert isinstance(checker, CheckerNode)


def test_compose_seq_concat_template_name() -> None:
    """SeqConcat checker uses template_name='seq_concat_top'."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "my_check", "a ##1 b")
    assert checker.template_name == "seq_concat_top"


def test_compose_seq_concat_module_name() -> None:
    """SeqConcat checker module_name is derived from label."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "delay_check", "a ##1 b")
    assert checker.module_name == "sva_delay_check"


def test_compose_seq_concat_children_count_two_elements() -> None:
    """a ##1 b produces 3 children: bool_a, delay_1_1, bool_b."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "my_check", "a ##1 b")
    assert len(checker.children) == 3


def test_compose_seq_concat_delay_child_template() -> None:
    """The delay child uses template_name='concat_delay'."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "my_check", "a ##1 b")
    # children: [bool_a_checker, delay_checker, bool_b_checker]
    delay_child = checker.children[1]
    assert delay_child.template_name == "concat_delay"


def test_compose_seq_concat_delay_params() -> None:
    """Delay child has correct delay_min, delay_max, cnt_width params."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((3, 3),),
    )
    checker = compose(node, clock, "my_check", "a ##3 b")
    delay_child = checker.children[1]
    assert delay_child.params["delay_min"] == "3"
    assert delay_child.params["delay_max"] == "3"
    assert delay_child.params["cnt_width"] == "2"  # ceil(log2(4)) = 2


def test_compose_seq_concat_range_delay_params() -> None:
    """Range delay ##[2:5] produces cnt_width=3."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((2, 5),),
    )
    checker = compose(node, clock, "my_check", "a ##[2:5] b")
    delay_child = checker.children[1]
    assert delay_child.params["delay_min"] == "2"
    assert delay_child.params["delay_max"] == "5"
    assert delay_child.params["cnt_width"] == "3"  # ceil(log2(6)) = 3


def test_compose_seq_concat_observed_signals() -> None:
    """Observed signals include signals from all bool_expr children."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "my_check", "a ##1 b")
    sig_names = {n for n, _ in checker.observed_signals}
    assert "a" in sig_names
    assert "b" in sig_names


def test_compose_seq_concat_source_loc_preserved() -> None:
    """CheckerNode.source_loc matches the SeqConcat source_loc."""
    loc = _make_loc(file="seq.sv", line=7, col=1)
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="x", source_loc=loc),
            BoolExpr(text="y", source_loc=loc),
        ),
        delays=((2, 2),),
    )
    checker = compose(node, clock, "check", "x ##2 y")
    assert checker.source_loc == loc


def test_compose_seq_concat_three_elements_children_count() -> None:
    """a ##1 b ##2 c produces 5 children: elem, delay, elem, delay, elem."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
            BoolExpr(text="c", source_loc=loc),
        ),
        delays=((1, 1), (2, 2)),
    )
    checker = compose(node, clock, "my_check", "a ##1 b ##2 c")
    assert len(checker.children) == 5


def test_compose_seq_concat_zero_delay_params() -> None:
    """##0 delay produces cnt_width=1, delay_min='0', delay_max='0'."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((0, 0),),
    )
    checker = compose(node, clock, "zero_check", "a ##0 b")
    delay_child = checker.children[1]
    assert delay_child.params["delay_min"] == "0"
    assert delay_child.params["delay_max"] == "0"
    assert delay_child.params["cnt_width"] == "1"


def test_compose_unsupported_type_raises() -> None:
    """An unknown SVANode subtype raises UnsupportedConstruct."""
    from dataclasses import dataclass

    from sva2rtl.ir import SVANode

    @dataclass(frozen=True)
    class _UnknownNode(SVANode):
        """Stub node not handled by compose()."""

    loc = _make_loc()
    clock = _make_clock()
    unknown = _UnknownNode(source_loc=loc)
    with pytest.raises(UnsupportedConstruct):
        compose(unknown, clock, None, "unknown")


# ── PropImplication composition ───────────────────────────────────────────


def _make_impl_node(
    overlapping: bool = True,
    consequent_delays: tuple[tuple[int, int], ...] | None = None,
) -> PropImplication:
    """Build a PropImplication IR node for testing."""
    loc = _make_loc()
    ant = BoolExpr(text="a", source_loc=loc)
    if consequent_delays is not None:
        con: SVANode = SeqConcat(
            source_loc=loc,
            elements=tuple(
                BoolExpr(text=chr(ord("a") + i + 1), source_loc=loc)
                for i in range(len(consequent_delays) + 1)
            ),
            delays=consequent_delays,
        )
    else:
        con = BoolExpr(text="b", source_loc=loc)
    return PropImplication(antecedent=ant, consequent=con, overlapping=overlapping, source_loc=loc)


def test_compose_implication_overlap_returns_checker() -> None:
    """compose(PropImplication(overlapping=True, ...)) returns a CheckerNode."""
    loc = _make_loc()
    clock = _make_clock()
    node = PropImplication(
        antecedent=BoolExpr(text="a", source_loc=loc),
        consequent=BoolExpr(text="b", source_loc=loc),
        overlapping=True,
        source_loc=loc,
    )
    checker = compose(node, clock, "impl_check", "a |-> b")
    assert isinstance(checker, CheckerNode)


def test_compose_implication_overlap_template_name() -> None:
    """PropImplication with overlapping=True uses 'overlap_bitvec' template."""
    node = _make_impl_node(overlapping=True)
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> b")
    assert checker.template_name == "overlap_bitvec"


def test_compose_implication_nonoverlap_template_name() -> None:
    """PropImplication with overlapping=False uses 'nonoverlap' template."""
    node = _make_impl_node(overlapping=False)
    clock = _make_clock()
    checker = compose(node, clock, "nonoverlap_check", "a |=> b")
    assert checker.template_name == "nonoverlap"


def test_compose_implication_children_count() -> None:
    """PropImplication checker has exactly 2 children (antecedent + consequent)."""
    node = _make_impl_node()
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> b")
    assert len(checker.children) == 2


def test_compose_implication_antecedent_child_is_bool_expr() -> None:
    """First child of PropImplication checker uses 'bool_expr' template."""
    node = _make_impl_node()
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> b")
    assert checker.children[0].template_name == "bool_expr"


def test_compose_implication_consequent_child_is_bool_expr() -> None:
    """Second child of PropImplication checker uses 'bool_expr' template for BoolExpr consequent."""
    node = _make_impl_node()
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> b")
    assert checker.children[1].template_name == "bool_expr"


def test_compose_implication_bv_width_bool_consequent() -> None:
    """BoolExpr consequent produces bv_width='1' (single-cycle, max_delay=0)."""
    node = _make_impl_node(consequent_delays=None)
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> b")
    assert checker.params["bv_width"] == "1"


def test_compose_implication_bv_width_delay_consequent() -> None:
    """SeqConcat consequent with delays=((2,5),) produces bv_width='6'."""
    node = _make_impl_node(consequent_delays=((2, 5),))
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> a ##[2:5] b")
    assert checker.params["bv_width"] == "6"


def test_compose_implication_bv_width_multi_delay() -> None:
    """SeqConcat consequent with delays=((2,2),(3,3)) -> bv_width='6'."""
    node = _make_impl_node(consequent_delays=((2, 2), (3, 3)))
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> a ##2 b ##3 c")
    assert checker.params["bv_width"] == "6"


def test_compose_implication_with_delay_consequent_has_seq_children() -> None:
    """PropImplication with SeqConcat consequent: second child is seq_concat_top."""
    node = _make_impl_node(consequent_delays=((2, 5),))
    clock = _make_clock()
    checker = compose(node, clock, "impl_check", "a |-> a ##[2:5] b")
    # consequent child should be seq_concat_top with its own sub-children
    assert checker.children[1].template_name == "seq_concat_top"
    assert len(checker.children[1].children) > 0


def test_compose_implication_does_not_raise() -> None:
    """compose() on PropImplication does NOT raise UnsupportedConstruct."""
    loc = _make_loc()
    clock = _make_clock()
    node = PropImplication(
        antecedent=BoolExpr(text="a", source_loc=loc),
        consequent=BoolExpr(text="b", source_loc=loc),
        overlapping=True,
        source_loc=loc,
    )
    # Should not raise
    checker = compose(node, clock, None, "a |-> b")
    assert checker is not None


# ── Normalize->Compose parity (Phase 4) ─────────────────────────────────


def test_normalize_compose_parity_bool_expr() -> None:
    """BoolExpr through normalize->compose gives same CheckerNode as compose alone."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="(a && b)", source_loc=loc)

    direct = compose(node, clock, "parity_bool", "(a && b)")
    normalized_node = normalize(node)
    via_normalize = compose(normalized_node, clock, "parity_bool", "(a && b)")

    assert direct == via_normalize


def test_normalize_compose_parity_seq_concat() -> None:
    """Flat SeqConcat through normalize->compose matches compose alone."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((2, 2),),
    )

    direct = compose(node, clock, "parity_concat", "a ##2 b")
    normalized_node = normalize(node)
    via_normalize = compose(normalized_node, clock, "parity_concat", "a ##2 b")

    assert direct == via_normalize


def test_normalize_compose_parity_implication_overlap() -> None:
    """Overlapping PropImplication through normalize->compose matches compose alone."""
    loc = _make_loc()
    clock = _make_clock()
    node = PropImplication(
        antecedent=BoolExpr(text="a", source_loc=loc),
        consequent=BoolExpr(text="b", source_loc=loc),
        overlapping=True,
        source_loc=loc,
    )

    direct = compose(node, clock, "parity_impl", "a |-> b")
    normalized_node = normalize(node)
    via_normalize = compose(normalized_node, clock, "parity_impl", "a |-> b")

    assert direct == via_normalize


def test_normalize_compose_parity_implication_nonoverlap() -> None:
    """Non-overlapping PropImplication through normalize->compose matches compose alone."""
    loc = _make_loc()
    clock = _make_clock()
    node = PropImplication(
        antecedent=BoolExpr(text="a", source_loc=loc),
        consequent=BoolExpr(text="b", source_loc=loc),
        overlapping=False,
        source_loc=loc,
    )

    direct = compose(node, clock, "parity_nonoverlap", "a |=> b")
    normalized_node = normalize(node)
    via_normalize = compose(normalized_node, clock, "parity_nonoverlap", "a |=> b")

    assert direct == via_normalize


# ── Structural hash (Phase 4) ────────────────────────────────────────────


def test_structural_hash_deterministic() -> None:
    """Same node produces same hash across two calls."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="x", source_loc=loc)
    checker = compose(node, clock, "hash_det", "x")

    h1 = structural_hash(checker)
    h2 = structural_hash(checker)

    assert h1 == h2
    assert re.match(r"^[0-9a-f]{8}$", h1)


def test_structural_hash_ignores_module_name() -> None:
    """Two nodes differing only in module_name produce same hash."""
    loc = _make_loc()
    clock = _make_clock()
    node = BoolExpr(text="sig", source_loc=loc)

    checker_a = compose(node, clock, "name_a", "sig")
    checker_b = compose(node, clock, "name_b", "sig")

    # module_name differs
    assert checker_a.module_name != checker_b.module_name
    # structural hash should be identical
    assert structural_hash(checker_a) == structural_hash(checker_b)


def test_structural_hash_differs_on_template() -> None:
    """Two nodes with different template_name produce different hashes."""
    loc = _make_loc()
    node_a = CheckerNode(
        template_name="bool_expr",
        module_name="sva_test",
        params={"clock_signal": "clk", "clock_edge": "posedge", "bool_expr": "a"},
        observed_signals=(("a", "a"),),
        source_loc=loc,
        children=(),
    )
    node_b = CheckerNode(
        template_name="concat_delay",
        module_name="sva_test",
        params={"clock_signal": "clk", "clock_edge": "posedge", "bool_expr": "a"},
        observed_signals=(("a", "a"),),
        source_loc=loc,
        children=(),
    )

    assert structural_hash(node_a) != structural_hash(node_b)


def test_compute_hash_map_includes_children() -> None:
    """A parent with 2 children produces a hash_map with 3 entries."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "hash_map_check", "a ##1 b")
    # seq_concat_top has 3 children: bool_a, delay, bool_b
    assert len(checker.children) == 3

    hm = compute_hash_map(checker)
    # 1 parent + 3 children = 4 entries
    assert len(hm) == 4
    # All values are 8-char hex
    for name, h in hm.items():
        assert re.match(r"^[0-9a-f]{8}$", h), f"Bad hash for {name}: {h}"
