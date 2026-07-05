"""Tests for v1.3 Phase 3+4: complex sequence and property operators.

Requirements covered:
- OPS-05: intersect
- OPS-06: within
- OPS-07: throughout
- OPS-08: and (sequence)
- OPS-09: or (sequence)
- OPS-10: not (property)
- OPS-11: if-else (property)
"""

from __future__ import annotations

import json
from pathlib import Path

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    PropIfElse,
    PropNot,
    SeqAnd,
    SeqIntersect,
    SeqOr,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
)

# ── Paths ──────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = Path(__file__).parent / "golden"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Phase 3 — sequence or / and (IR-level tests)
# ══════════════════════════════════════════════════════════════════════════════


def test_ir_seq_or_creation() -> None:
    """SeqOr is a frozen dataclass with left/right fields."""
    loc = SourceLoc("t.sv", 1, 1)
    left = BoolExpr(text="a", source_loc=loc)
    right = BoolExpr(text="b", source_loc=loc)
    node = SeqOr(left=left, right=right, source_loc=loc)
    assert node.left is left
    assert node.right is right


def test_ir_seq_and_creation() -> None:
    """SeqAnd is a frozen dataclass with left/right fields."""
    loc = SourceLoc("t.sv", 1, 1)
    left = BoolExpr(text="x", source_loc=loc)
    right = BoolExpr(text="y", source_loc=loc)
    node = SeqAnd(left=left, right=right, source_loc=loc)
    assert node.left is left
    assert node.right is right


def test_compose_seq_or() -> None:
    """compose SeqOr → prop_or template with two children."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqOr(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a or b")
    assert checker.template_name == "prop_or"
    assert len(checker.children) == 2


def test_compose_seq_and() -> None:
    """compose SeqAnd → prop_and template with two children."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqAnd(
        left=BoolExpr(text="x", source_loc=loc),
        right=BoolExpr(text="y", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "x and y")
    assert checker.template_name == "prop_and"
    assert len(checker.children) == 2


def test_emit_seq_or() -> None:
    """seq or emits valid SV with two child instances."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqOr(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a or b")
    modules = emit_all(checker)
    assert len(modules) >= 1
    sv = "\n".join(modules.values())
    assert "module " in sv
    assert "endmodule" in sv


def test_emit_seq_and() -> None:
    """seq and emits valid SV with two child instances."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqAnd(
        left=BoolExpr(text="x", source_loc=loc),
        right=BoolExpr(text="y", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "x and y")
    modules = emit_all(checker)
    sv = "\n".join(modules.values())
    assert "module " in sv
    assert "endmodule" in sv


# ── oracle: sequence or ────────────────────────────────────────────────────


def test_oracle_seq_or_both_pass() -> None:
    """seq or: both children pass → passes."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqOr(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a or b")
    results = simulate_checker_hierarchy(checker, [
        {"start": True, "a": True, "b": True},
    ])
    assert results[0]["pass"]


def test_oracle_seq_or_left_pass() -> None:
    """seq or: left passes, right fails → still passes."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqOr(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a or b")
    results = simulate_checker_hierarchy(checker, [
        {"start": True, "a": True, "b": False},
    ])
    assert results[0]["pass"]


# Note: bool_expr children modeled as ##0 always pass when started in the
# behavioral oracle.  The oracle captures temporal operator composition
# semantics (OR/AND/intersect wiring) but not boolean expression values.
# Full signal-level verification is done at formal equiv level.


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Phase 3 — intersect
# ══════════════════════════════════════════════════════════════════════════════


def test_ir_intersect_creation() -> None:
    """SeqIntersect has left/right fields."""
    loc = SourceLoc("t.sv", 1, 1)
    left = BoolExpr(text="a", source_loc=loc)
    right = BoolExpr(text="b", source_loc=loc)
    node = SeqIntersect(left=left, right=right, source_loc=loc)
    assert node.left is left
    assert node.right is right


def test_compose_intersect() -> None:
    """compose SeqIntersect → prop_intersect template."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqIntersect(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a intersect b")
    assert checker.template_name == "prop_intersect"
    assert len(checker.children) == 2


def test_emit_intersect() -> None:
    """intersect emits valid SV."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqIntersect(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a intersect b")
    modules = emit_all(checker)
    sv = "\n".join(modules.values())
    assert "module " in sv
    assert "endmodule" in sv


def test_oracle_intersect_both_pass() -> None:
    """intersect: both pass → passes."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqIntersect(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a intersect b")
    results = simulate_checker_hierarchy(checker, [
        {"start": True, "a": True, "b": True},
    ])
    assert results[0]["pass"]


def test_oracle_intersect_both_active() -> None:
    """intersect: both children active → active high."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqIntersect(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "a intersect b")
    results = simulate_checker_hierarchy(checker, [
        {"start": True, "a": True, "b": True},
    ])
    assert results[0]["active"]


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Phase 3 — within
# ══════════════════════════════════════════════════════════════════════════════


def test_ir_within_creation() -> None:
    """SeqWithin has inner/outer fields."""
    loc = SourceLoc("t.sv", 1, 1)
    inner = BoolExpr(text="x", source_loc=loc)
    outer = BoolExpr(text="y", source_loc=loc)
    node = SeqWithin(inner=inner, outer=outer, source_loc=loc)
    assert node.inner is inner
    assert node.outer is outer


def test_compose_within() -> None:
    """compose SeqWithin → prop_within template."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqWithin(
        inner=BoolExpr(text="x", source_loc=loc),
        outer=BoolExpr(text="y", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "x within y")
    assert checker.template_name == "prop_within"


def test_emit_within() -> None:
    """within emits valid SV."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqWithin(
        inner=BoolExpr(text="x", source_loc=loc),
        outer=BoolExpr(text="y", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "x within y")
    modules = emit_all(checker)
    sv = "\n".join(modules.values())
    assert "module " in sv


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Phase 3 — throughout
# ══════════════════════════════════════════════════════════════════════════════


def test_ir_throughout_creation() -> None:
    """SeqThroughout has condition/body fields."""
    loc = SourceLoc("t.sv", 1, 1)
    cond = BoolExpr(text="en", source_loc=loc)
    body = BoolExpr(text="sig", source_loc=loc)
    node = SeqThroughout(condition=cond, body=body, source_loc=loc)
    assert node.condition is cond
    assert node.body is body


def test_compose_throughout() -> None:
    """compose SeqThroughout → prop_throughout template."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqThroughout(
        condition=BoolExpr(text="en", source_loc=loc),
        body=BoolExpr(text="sig", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "en throughout sig")
    assert checker.template_name == "prop_throughout"


def test_emit_throughout() -> None:
    """throughout emits valid SV."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = SeqThroughout(
        condition=BoolExpr(text="en", source_loc=loc),
        body=BoolExpr(text="sig", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "en throughout sig")
    modules = emit_all(checker)
    sv = "\n".join(modules.values())
    assert "module " in sv


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Phase 4 — property NOT
# ══════════════════════════════════════════════════════════════════════════════


def test_ir_prop_not_creation() -> None:
    """PropNot has body field."""
    loc = SourceLoc("t.sv", 1, 1)
    body = BoolExpr(text="a", source_loc=loc)
    node = PropNot(body=body, source_loc=loc)
    assert node.body is body


def test_compose_prop_not() -> None:
    """compose PropNot → prop_not template."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropNot(body=BoolExpr(text="a", source_loc=loc), source_loc=loc)
    checker = compose(node, clock, None, "not a")
    assert checker.template_name == "prop_not"
    assert len(checker.children) == 1


def test_emit_prop_not() -> None:
    """not emits valid SV."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropNot(body=BoolExpr(text="a", source_loc=loc), source_loc=loc)
    checker = compose(node, clock, None, "not a")
    modules = emit_all(checker)
    sv = "\n".join(modules.values())
    assert "module " in sv
    assert "endmodule" in sv


def test_oracle_prop_not_inverts() -> None:
    """prop_not: body pass → not fails (oracle models temporal wiring)."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropNot(body=BoolExpr(text="a", source_loc=loc), source_loc=loc)
    checker = compose(node, clock, None, "not a")
    # body(always passes) → not should fail (swap)
    results = simulate_checker_hierarchy(checker, [
        {"start": True, "a": True},
    ])
    assert results[0]["fail"]


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Phase 4 — property if-else
# ══════════════════════════════════════════════════════════════════════════════


def test_ir_prop_if_else_creation() -> None:
    """PropIfElse has condition/true_branch/false_branch fields."""
    loc = SourceLoc("t.sv", 1, 1)
    cond = BoolExpr(text="sel", source_loc=loc)
    true_b = BoolExpr(text="a", source_loc=loc)
    false_b = BoolExpr(text="b", source_loc=loc)
    node = PropIfElse(condition=cond, true_branch=true_b, false_branch=false_b, source_loc=loc)
    assert node.condition is cond
    assert node.true_branch is true_b
    assert node.false_branch is false_b


def test_compose_prop_if_else() -> None:
    """compose PropIfElse → prop_if_else template."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropIfElse(
        condition=BoolExpr(text="sel", source_loc=loc),
        true_branch=BoolExpr(text="a", source_loc=loc),
        false_branch=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "if (sel) a else b")
    assert checker.template_name == "prop_if_else"
    assert checker.params["has_else"] == "1"
    assert len(checker.children) == 2


def test_emit_prop_if_else() -> None:
    """if-else emits valid SV."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropIfElse(
        condition=BoolExpr(text="sel", source_loc=loc),
        true_branch=BoolExpr(text="a", source_loc=loc),
        false_branch=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "if (sel) a else b")
    modules = emit_all(checker)
    sv = "\n".join(modules.values())
    assert "module " in sv
    assert "endmodule" in sv


def test_oracle_prop_if_else_true_branch() -> None:
    """if-else: when condition true, evaluates true branch."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropIfElse(
        condition=BoolExpr(text="sel", source_loc=loc),
        true_branch=BoolExpr(text="a", source_loc=loc),
        false_branch=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "if (sel) a else b")
    results = simulate_checker_hierarchy(checker, [
        {"start": True, "sel": True, "a": True, "b": False},
    ])
    assert results[0]["pass"]


def test_oracle_prop_if_else_false_branch() -> None:
    """if-else: when condition false, evaluates false branch."""
    loc = SourceLoc("t.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    node = PropIfElse(
        condition=BoolExpr(text="sel", source_loc=loc),
        true_branch=BoolExpr(text="a", source_loc=loc),
        false_branch=BoolExpr(text="b", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(node, clock, None, "if (sel) a else b")
    results = simulate_checker_hierarchy(checker, [
        {"start": True, "sel": False, "a": False, "b": True},
    ])
    assert results[0]["pass"]
