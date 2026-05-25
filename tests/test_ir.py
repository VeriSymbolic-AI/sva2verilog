"""Unit tests for src/sva2rtl/ir.py."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockSpec,
    PropImplication,
    SeqConcat,
    SourceLoc,
    SVANode,
)

# ── SourceLoc ──────────────────────────────────────────────────────────────


def test_source_loc_str() -> None:
    """SourceLoc.__str__ returns 'file:line:col' format."""
    loc = SourceLoc("foo.sv", 10, 3)
    assert str(loc) == "foo.sv:10:3"


def test_source_loc_fields() -> None:
    """SourceLoc stores file, line, col correctly."""
    loc = SourceLoc("bar.sv", 1, 1)
    assert loc.file == "bar.sv"
    assert loc.line == 1
    assert loc.col == 1


def test_source_loc_frozen() -> None:
    """SourceLoc is immutable (frozen dataclass)."""
    loc = SourceLoc("x.sv", 1, 1)
    with pytest.raises(FrozenInstanceError):
        loc.line = 99  # type: ignore[misc]


# ── BoolExpr ───────────────────────────────────────────────────────────────


def test_bool_expr_frozen() -> None:
    """BoolExpr cannot be mutated — FrozenInstanceError on field assignment."""
    loc = SourceLoc("f.sv", 1, 1)
    expr = BoolExpr(text="(a && b)", source_loc=loc)
    with pytest.raises(FrozenInstanceError):
        expr.text = "changed"  # type: ignore[misc]


def test_bool_expr_hashable() -> None:
    """Two BoolExpr instances with identical fields have the same hash."""
    loc = SourceLoc("f.sv", 1, 1)
    e1 = BoolExpr(text="(a && b)", source_loc=loc)
    e2 = BoolExpr(text="(a && b)", source_loc=loc)
    assert hash(e1) == hash(e2)
    assert e1 == e2


def test_bool_expr_different_hash() -> None:
    """BoolExpr instances with different text produce different hashes."""
    loc = SourceLoc("f.sv", 1, 1)
    e1 = BoolExpr(text="a", source_loc=loc)
    e2 = BoolExpr(text="b", source_loc=loc)
    assert e1 != e2
    # Hash collisions are theoretically possible but extremely unlikely:
    assert hash(e1) != hash(e2)


# ── SVANode inheritance ────────────────────────────────────────────────────


def test_sva_node_inheritance() -> None:
    """BoolExpr, SeqConcat, and PropImplication all inherit from SVANode."""
    loc = SourceLoc("f.sv", 1, 1)
    expr = BoolExpr(text="x", source_loc=loc)
    assert isinstance(expr, SVANode)

    # SeqConcat
    concat = SeqConcat(elements=(expr,), delays=(), source_loc=loc)
    assert isinstance(concat, SVANode)

    # PropImplication
    impl = PropImplication(antecedent=expr, consequent=expr, source_loc=loc)
    assert isinstance(impl, SVANode)


# ── ClockSpec ──────────────────────────────────────────────────────────────


def test_clock_spec_fields() -> None:
    """ClockSpec stores edge and signal name correctly."""
    loc = SourceLoc("top.sv", 5, 3)
    cs = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    assert cs.edge == "posedge"
    assert cs.signal == "clk"
    assert cs.source_loc == loc


def test_clock_spec_negedge() -> None:
    """ClockSpec supports negedge."""
    loc = SourceLoc("top.sv", 1, 1)
    cs = ClockSpec(edge="negedge", signal="clk_n", source_loc=loc)
    assert cs.edge == "negedge"
    assert cs.signal == "clk_n"


# ── CheckerNode ────────────────────────────────────────────────────────────


def test_checker_node_creation() -> None:
    """CheckerNode stores all fields and is accessible."""
    loc = SourceLoc("p.sv", 2, 1)
    cn = CheckerNode(
        template_name="bool_expr",
        module_name="sva_my_check",
        params={"bool_expr": "(a && b)", "clock_signal": "clk"},
        observed_signals=(("a", "dut.a"), ("b", "dut.b")),
        source_loc=loc,
    )
    assert cn.template_name == "bool_expr"
    assert cn.module_name == "sva_my_check"
    assert cn.params["bool_expr"] == "(a && b)"
    assert cn.observed_signals == (("a", "dut.a"), ("b", "dut.b"))
    assert cn.source_loc == loc
    assert cn.children == ()


def test_checker_node_hashable() -> None:
    """CheckerNode is hashable via explicit __hash__ override."""
    loc = SourceLoc("p.sv", 1, 1)
    cn1 = CheckerNode(
        template_name="bool_expr",
        module_name="sva_x",
        params={"k": "v"},
        observed_signals=(("a", "a"),),
        source_loc=loc,
    )
    cn2 = CheckerNode(
        template_name="bool_expr",
        module_name="sva_x",
        params={"k": "v"},
        observed_signals=(("a", "a"),),
        source_loc=loc,
    )
    assert hash(cn1) == hash(cn2)
    assert cn1 == cn2


def test_checker_node_hash_unordered_params() -> None:
    """CheckerNode hash is independent of dict insertion order (frozenset)."""
    loc = SourceLoc("p.sv", 1, 1)
    base: dict[str, str] = {"bool_expr": "(a)", "clock_signal": "clk"}
    reversed_: dict[str, str] = {"clock_signal": "clk", "bool_expr": "(a)"}
    cn1 = CheckerNode(
        template_name="bool_expr",
        module_name="sva_x",
        params=base,
        observed_signals=(),
        source_loc=loc,
    )
    cn2 = CheckerNode(
        template_name="bool_expr",
        module_name="sva_x",
        params=reversed_,
        observed_signals=(),
        source_loc=loc,
    )
    assert hash(cn1) == hash(cn2)
    assert cn1 == cn2


def test_checker_node_with_children() -> None:
    """CheckerNode can nest children for hierarchical composition."""
    loc = SourceLoc("p.sv", 1, 1)
    child = CheckerNode(
        template_name="bool_expr",
        module_name="sva_child",
        params={},
        observed_signals=(),
        source_loc=loc,
    )
    parent = CheckerNode(
        template_name="bool_expr",
        module_name="sva_parent",
        params={},
        observed_signals=(),
        source_loc=loc,
        children=(child,),
    )
    assert len(parent.children) == 1
    assert parent.children[0] == child


# ── SeqConcat ─────────────────────────────────────────────────────────────


def test_seq_concat_fields() -> None:
    """SeqConcat stores elements and delays tuples."""
    loc = SourceLoc("f.sv", 1, 1)
    e = BoolExpr(text="a", source_loc=loc)
    f = BoolExpr(text="b", source_loc=loc)
    sc = SeqConcat(elements=(e, f), delays=((1, 1),), source_loc=loc)
    assert len(sc.elements) == 2
    assert sc.delays == ((1, 1),)


# ── PropImplication ───────────────────────────────────────────────────────


def test_prop_implication_overlapping_default() -> None:
    """PropImplication defaults to overlapping (|->)."""
    loc = SourceLoc("f.sv", 1, 1)
    e = BoolExpr(text="a", source_loc=loc)
    impl = PropImplication(antecedent=e, consequent=e, source_loc=loc)
    assert impl.overlapping is True


def test_prop_implication_non_overlapping() -> None:
    """PropImplication can be constructed for |=>."""
    loc = SourceLoc("f.sv", 1, 1)
    e = BoolExpr(text="a", source_loc=loc)
    impl = PropImplication(antecedent=e, consequent=e, overlapping=False, source_loc=loc)
    assert impl.overlapping is False
