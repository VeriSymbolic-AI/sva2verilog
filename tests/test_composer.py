"""Unit tests for src/sva2rtl/composer.py."""

from __future__ import annotations

import re

import pytest

from sva2rtl.composer import compose, extract_signals, module_name_from_label
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import BoolExpr, CheckerNode, ClockSpec, SeqConcat, SourceLoc

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


def test_compose_unsupported_raises_unsupported_construct() -> None:
    """SeqConcat passed to compose() raises UnsupportedConstruct."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(BoolExpr(text="a", source_loc=loc),),
        delays=((1, 1),),
    )
    with pytest.raises(UnsupportedConstruct):
        compose(node, clock, None, "a ##1 b")


def test_compose_unsupported_carries_source_loc() -> None:
    """UnsupportedConstruct raised for SeqConcat carries the node's source_loc."""
    loc = _make_loc(file="bad.sv", line=5, col=3)
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(BoolExpr(text="a", source_loc=loc),),
        delays=((1, 1),),
    )
    with pytest.raises(UnsupportedConstruct) as exc_info:
        compose(node, clock, None, "a ##1 b")
    assert exc_info.value.source_loc is not None
    assert exc_info.value.source_loc.file == "bad.sv"
