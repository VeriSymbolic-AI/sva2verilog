"""Tests for v1.4 Part A — bounded liveness operators.

Phase A1 coverage (frontend + IR + normalizer):
- LIVE-01 (frontend): ``s_eventually [m:n] p`` / ``eventually [m:n] p`` import to
  ``PropBoundedEventually`` with the correct bounds and operand.
- LIVE-04 (honesty): unbounded liveness and non-boolean operands raise
  formal-only liveness IR; inverted bounds raise.

The slang AST node shapes used here were captured by
``tools/audit/probe_liveness_ast.py`` against slang 11.0.0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sva2rtl.ast_importer import _dispatch_expr_to_ir, import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockSpec,
    PropAlways,
    PropBoundedAlways,
    PropBoundedEventually,
    PropEventually,
    PropStrongUntil,
    PropUntil,
    SourceLoc,
)
from sva2rtl.normalizer import normalize

# ── slang AST node builders (v11.0.0 shapes) ───────────────────────────────


def _bool_operand(sig: str = "a") -> dict:
    """`{kind:Simple, expr:<NamedValue>}` — a boolean operand wrapper."""
    return {"kind": "Simple", "expr": {"kind": "NamedValue", "symbol": f"1 {sig}"}}


def _eventually_node(
    op: str = "SEventually",
    lo: int | None = 1,
    hi: int | None = 3,
    operand: dict | None = None,
) -> dict:
    node: dict = {"kind": "Unary", "op": op, "expr": operand or _bool_operand()}
    if lo is not None:
        node["min"] = lo
    if hi is not None:
        node["max"] = hi
    return node


def _always_node(
    op: str = "Always",
    lo: int | None = 1,
    hi: int | None = 3,
    operand: dict | None = None,
) -> dict:
    node: dict = {"kind": "Unary", "op": op, "expr": operand or _bool_operand()}
    if lo is not None:
        node["min"] = lo
    if hi is not None:
        node["max"] = hi
    return node


def _until_node(
    op: str = "Until",
    left: dict | None = None,
    right: dict | None = None,
) -> dict:
    return {
        "kind": "Binary",
        "op": op,
        "left": left or _bool_operand("a"),
        "right": right or _bool_operand("b"),
    }


# ── LIVE-01 frontend: bounded eventually imports correctly ─────────────────


def test_s_eventually_bounded_imports() -> None:
    ir = _dispatch_expr_to_ir(_eventually_node("SEventually", 1, 3))
    assert isinstance(ir, PropBoundedEventually)
    assert (ir.lo, ir.hi, ir.strong) == (1, 3, True)
    assert isinstance(ir.body, BoolExpr)
    assert ir.body.text == "a"


def test_eventually_weak_bounded_imports() -> None:
    ir = _dispatch_expr_to_ir(_eventually_node("Eventually", 2, 4))
    assert isinstance(ir, PropBoundedEventually)
    assert (ir.lo, ir.hi, ir.strong) == (2, 4, False)


def test_s_eventually_single_offset() -> None:
    ir = _dispatch_expr_to_ir(_eventually_node("SEventually", 2, 2))
    assert isinstance(ir, PropBoundedEventually)
    assert (ir.lo, ir.hi) == (2, 2)


# ── LIVE-04 honesty: rejections ────────────────────────────────────────────


def test_unbounded_s_eventually_imports_formal_only_ir() -> None:
    ir = _dispatch_expr_to_ir(_eventually_node("SEventually", None, None))
    assert isinstance(ir, PropEventually)
    assert ir.strong is True


def test_unbounded_eventually_imports_formal_only_ir() -> None:
    ir = _dispatch_expr_to_ir(_eventually_node("Eventually", None, None))
    assert isinstance(ir, PropEventually)
    assert ir.strong is False


def test_inverted_bounds_rejected() -> None:
    with pytest.raises(SvaCompileError, match=r"\[3:1\]"):
        _dispatch_expr_to_ir(_eventually_node("SEventually", 3, 1))


def test_non_boolean_operand_rejected() -> None:
    # operand is a $rose signal-function call -> SignalFunc, not BoolExpr
    sig_call = {
        "kind": "Simple",
        "expr": {
            "kind": "CallExpression",
            "subroutineName": "$rose",
            "arguments": [{"kind": "NamedValue", "symbol": "1 a"}],
        },
    }
    with pytest.raises(UnsupportedConstruct, match="boolean-expression operand"):
        _dispatch_expr_to_ir(_eventually_node("SEventually", 1, 3, operand=sig_call))


# ── normalizer: idempotent + recurses into body ────────────────────────────


def test_normalize_bounded_eventually_idempotent() -> None:
    loc = SourceLoc("t.sv", 1, 1)
    node = PropBoundedEventually(
        body=BoolExpr(text="a", source_loc=loc), lo=1, hi=3, strong=True, source_loc=loc
    )
    once = normalize(node)
    assert once == node
    assert normalize(once) == once
    assert isinstance(once, PropBoundedEventually)


# ── LIVE-02 frontend: bounded always imports correctly ─────────────────────


def test_always_bounded_imports() -> None:
    ir = _dispatch_expr_to_ir(_always_node("Always", 1, 3))
    assert isinstance(ir, PropBoundedAlways)
    assert (ir.lo, ir.hi, ir.strong) == (1, 3, False)
    assert isinstance(ir.body, BoolExpr)
    assert ir.body.text == "a"


def test_s_always_strong_bounded_imports() -> None:
    ir = _dispatch_expr_to_ir(_always_node("SAlways", 2, 4))
    assert isinstance(ir, PropBoundedAlways)
    assert (ir.lo, ir.hi, ir.strong) == (2, 4, True)


def test_always_single_offset() -> None:
    ir = _dispatch_expr_to_ir(_always_node("Always", 2, 2))
    assert isinstance(ir, PropBoundedAlways)
    assert (ir.lo, ir.hi) == (2, 2)


def test_unbounded_always_imports_as_formal_only_safety() -> None:
    ir = _dispatch_expr_to_ir(_always_node("Always", None, None))
    assert isinstance(ir, PropAlways)
    assert ir.strong is False


def test_unbounded_s_always_imports_as_formal_only_safety() -> None:
    ir = _dispatch_expr_to_ir(_always_node("SAlways", None, None))
    assert isinstance(ir, PropAlways)
    assert ir.strong is True


def test_always_inverted_bounds_rejected() -> None:
    with pytest.raises(SvaCompileError, match=r"\[4:2\]"):
        _dispatch_expr_to_ir(_always_node("Always", 4, 2))


def test_always_non_boolean_operand_rejected() -> None:
    sig_call = {
        "kind": "Simple",
        "expr": {
            "kind": "CallExpression",
            "subroutineName": "$rose",
            "arguments": [{"kind": "NamedValue", "symbol": "1 a"}],
        },
    }
    with pytest.raises(UnsupportedConstruct, match="boolean-expression operand"):
        _dispatch_expr_to_ir(_always_node("Always", 1, 3, operand=sig_call))


def test_normalize_bounded_always_idempotent() -> None:
    loc = SourceLoc("t.sv", 1, 1)
    node = PropBoundedAlways(
        body=BoolExpr(text="a", source_loc=loc), lo=1, hi=3, strong=False, source_loc=loc
    )
    once = normalize(node)
    assert once == node
    assert normalize(once) == once
    assert isinstance(once, PropBoundedAlways)


# ── LIVE-03 frontend: weak until / until_with imports; strong rejected ──────


def test_until_weak_imports() -> None:
    ir = _dispatch_expr_to_ir(_until_node("Until"))
    assert isinstance(ir, PropUntil)
    assert ir.with_ is False
    assert isinstance(ir.left, BoolExpr) and isinstance(ir.right, BoolExpr)
    assert (ir.left.text, ir.right.text) == ("a", "b")


def test_until_with_weak_imports() -> None:
    ir = _dispatch_expr_to_ir(_until_node("UntilWith"))
    assert isinstance(ir, PropUntil)
    assert ir.with_ is True


def test_strong_s_until_imports_formal_only_ir() -> None:
    ir = _dispatch_expr_to_ir(_until_node("SUntil"))
    assert isinstance(ir, PropStrongUntil)
    assert ir.with_ is False


def test_strong_s_until_with_imports_formal_only_ir() -> None:
    ir = _dispatch_expr_to_ir(_until_node("SUntilWith"))
    assert isinstance(ir, PropStrongUntil)
    assert ir.with_ is True


def test_until_non_boolean_operand_rejected() -> None:
    sig_call = {
        "kind": "Simple",
        "expr": {
            "kind": "CallExpression",
            "subroutineName": "$rose",
            "arguments": [{"kind": "NamedValue", "symbol": "1 b"}],
        },
    }
    with pytest.raises(UnsupportedConstruct, match="boolean-expression operand"):
        _dispatch_expr_to_ir(_until_node("Until", right=sig_call))


def test_normalize_until_idempotent() -> None:
    loc = SourceLoc("t.sv", 1, 1)
    node = PropUntil(
        left=BoolExpr(text="a", source_loc=loc),
        right=BoolExpr(text="b", source_loc=loc),
        with_=False,
        source_loc=loc,
    )
    once = normalize(node)
    assert once == node
    assert normalize(once) == once
    assert isinstance(once, PropUntil)


# ── LIVE-05 (A5.1) edge cases: M=0, M==N, counter width, nested rejection ──


_LOC = SourceLoc("t.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _compose_se(lo: int, hi: int) -> CheckerNode:
    node = PropBoundedEventually(
        body=BoolExpr(text="a", source_loc=_LOC), lo=lo, hi=hi, strong=True,
        source_loc=_LOC,
    )
    return compose(normalize(node), _CLK, "se", f"s_eventually [{lo}:{hi}] a")


def _compose_sa(lo: int, hi: int) -> CheckerNode:
    node = PropBoundedAlways(
        body=BoolExpr(text="a", source_loc=_LOC), lo=lo, hi=hi, strong=False,
        source_loc=_LOC,
    )
    return compose(normalize(node), _CLK, "sa", f"always [{lo}:{hi}] a")


@pytest.mark.parametrize(
    "hi,expected_width",
    [(1, 1), (3, 2), (7, 3), (8, 4), (15, 4), (16, 5)],
)
def test_eventually_counter_width(hi: int, expected_width: int) -> None:
    """cnt_width = ceil(log2(hi+1)) sizes the offset counter (mirrors concat_delay)."""
    checker = _compose_se(1, hi)
    assert checker.params["cnt_width"] == str(expected_width)


def test_eventually_zero_window_is_bool_check() -> None:
    """s_eventually [0:0] a degenerates to a start-cycle boolean check (hi==0 branch)."""
    checker = _compose_se(0, 0)
    sv = emit_all(checker)[checker.module_name]
    assert "start &  bool_result" in sv  # pass path
    assert "start & ~bool_result" in sv  # fail path


def test_always_zero_window_is_bool_check() -> None:
    """always [0:0] a degenerates to a start-cycle boolean check (hi==0 branch)."""
    checker = _compose_sa(0, 0)
    sv = emit_all(checker)[checker.module_name]
    assert "start &  bool_result" in sv
    assert "start & ~bool_result" in sv


def test_eventually_single_offset_compiles() -> None:
    """M==N single-offset window compiles to valid RTL (counter window collapses)."""
    checker = _compose_se(3, 3)
    sv = emit_all(checker)[checker.module_name]
    assert "module" in sv and "endmodule" in sv


def test_large_window_compiles() -> None:
    """A large window (wide counter) composes and emits without error."""
    checker = _compose_se(2, 20)
    assert checker.params["cnt_width"] == "5"
    sv = emit_all(checker)[checker.module_name]
    assert "endmodule" in sv


def _try_compile(prop: str) -> None:
    src = Path("/tmp/_liveness_edge.sv")
    src.write_text(
        "module m(input logic clk, a, b, c);\n"
        f"  ap: assert property (@(posedge clk) {prop});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    ast = invoke_slang(src, "slang")
    node, clock, text, label = import_assertion(ast)
    compose(normalize(node), clock, label, text)


@pytest.mark.parametrize(
    "prop",
    [
        "a |-> s_eventually [1:3] b",
        "a |-> always [1:2] b",
        "a |-> (b until c)",
    ],
)
def test_liveness_under_implication_rejected(prop: str) -> None:
    """Liveness nested under implication is cleanly rejected (not crashed) — v1.5."""
    with pytest.raises(UnsupportedConstruct):
        _try_compile(prop)
