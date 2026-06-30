"""Tests for v1.4 Part A — bounded liveness operators.

Phase A1 coverage (frontend + IR + normalizer):
- LIVE-01 (frontend): ``s_eventually [m:n] p`` / ``eventually [m:n] p`` import to
  ``PropBoundedEventually`` with the correct bounds and operand.
- LIVE-04 (honesty): unbounded liveness and non-boolean operands raise
  ``UnsupportedConstruct``; inverted bounds raise.

The slang AST node shapes used here were captured by
``tools/audit/probe_liveness_ast.py`` against slang 11.0.0.
"""

from __future__ import annotations

import pytest

from sva2rtl.ast_importer import _dispatch_expr_to_ir
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import BoolExpr, PropBoundedEventually, SourceLoc
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


def test_unbounded_s_eventually_rejected() -> None:
    with pytest.raises(UnsupportedConstruct, match="unbounded"):
        _dispatch_expr_to_ir(_eventually_node("SEventually", None, None))


def test_unbounded_eventually_rejected() -> None:
    with pytest.raises(UnsupportedConstruct, match="unbounded"):
        _dispatch_expr_to_ir(_eventually_node("Eventually", None, None))


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
