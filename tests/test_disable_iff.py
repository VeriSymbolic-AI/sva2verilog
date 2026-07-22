"""Tests for disable iff IR node, AST importer dispatch, composer, and emitter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import BoolExpr, CheckerNode, DisableIff, SourceLoc

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_loc(file: str = "test.sv", line: int = 1, col: int = 1) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _load_disable_iff_checker() -> CheckerNode:
    """Load the disable_iff fixture and return a compiled CheckerNode."""
    ast = json.loads((FIXTURES_DIR / "disable_iff.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    return compose(ir_node, clock, label, text)


# ── IR node tests ─────────────────────────────────────────────────────────────


def test_ir_disable_iff_creation() -> None:
    """DisableIff frozen dataclass can be constructed and is hashable."""
    loc = _make_loc()
    cond = BoolExpr(text="!rst_n", source_loc=loc)
    body = BoolExpr(text="a", source_loc=loc)
    node = DisableIff(condition=cond, body=body, source_loc=loc)
    assert node.condition is cond
    assert node.body is body
    # frozen dataclass — must be hashable
    h = hash(node)
    assert isinstance(h, int)


def test_ir_disable_iff_is_frozen() -> None:
    """DisableIff raises FrozenInstanceError when mutated (frozen=True)."""
    loc = _make_loc()
    node = DisableIff(
        condition=BoolExpr(text="x", source_loc=loc),
        body=BoolExpr(text="y", source_loc=loc),
        source_loc=loc,
    )
    with pytest.raises(Exception):  # FrozenInstanceError or AttributeError
        node.condition = BoolExpr(text="z", source_loc=loc)  # type: ignore[misc]


def test_ir_disable_iff_equality() -> None:
    """Two DisableIff nodes with same contents compare equal."""
    loc = _make_loc()
    cond = BoolExpr(text="!rst_n", source_loc=loc)
    body = BoolExpr(text="a", source_loc=loc)
    n1 = DisableIff(condition=cond, body=body, source_loc=loc)
    n2 = DisableIff(condition=cond, body=body, source_loc=loc)
    assert n1 == n2


# ── AST importer tests ────────────────────────────────────────────────────────


def test_import_disable_iff_returns_disable_iff_node() -> None:
    """import_assertion on disable_iff.json returns a DisableIff IR node."""
    ast = json.loads((FIXTURES_DIR / "disable_iff.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    assert isinstance(ir_node, DisableIff), (
        f"Expected DisableIff, got {type(ir_node).__name__}"
    )


def test_import_disable_iff_condition_text() -> None:
    """DisableIff.condition is a BoolExpr containing the disable condition text."""
    ast = json.loads((FIXTURES_DIR / "disable_iff.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    assert isinstance(ir_node, DisableIff)
    assert isinstance(ir_node.condition, BoolExpr)
    # condition is !rst_n — should contain "rst_n"
    assert "rst_n" in ir_node.condition.text


def test_import_disable_iff_body_is_prop_implication() -> None:
    """DisableIff.body is a PropImplication (a |-> b from the fixture)."""
    from sva2rtl.ir import PropImplication
    ast = json.loads((FIXTURES_DIR / "disable_iff.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    assert isinstance(ir_node, DisableIff)
    assert isinstance(ir_node.body, PropImplication)


def test_import_disable_iff_text_contains_disable_iff() -> None:
    """Reconstructed text for a disable iff property starts with 'disable iff'."""
    ast = json.loads((FIXTURES_DIR / "disable_iff.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    assert text.startswith("disable iff")


# ── Composer tests ────────────────────────────────────────────────────────────


def test_compose_disable_iff_template_name() -> None:
    """compose() for DisableIff returns CheckerNode with template_name='disable_iff_top'."""
    checker = _load_disable_iff_checker()
    assert checker.template_name == "disable_iff_top"


def test_compose_disable_iff_single_child() -> None:
    """compose() for DisableIff gives CheckerNode with exactly one child (body)."""
    checker = _load_disable_iff_checker()
    assert len(checker.children) == 1


def test_compose_disable_iff_observed_signals() -> None:
    """CheckerNode for disable iff includes signals from both condition and body.

    rst_n is a reserved port hardcoded in every generated module template, so it
    must NOT appear in observed_signals (to avoid duplicate port declarations).
    """
    checker = _load_disable_iff_checker()
    port_names = {p for p, _ in checker.observed_signals}
    # rst_n is reserved — must be excluded from observed_signals
    assert "rst_n" not in port_names
    # a and b come from the body (a |-> b)
    assert "a" in port_names
    assert "b" in port_names


# ── Emitter tests ─────────────────────────────────────────────────────────────


def test_emit_disable_iff_contains_cond_result() -> None:
    """emit_all() for disable iff top module contains 'cond_result'."""
    checker = _load_disable_iff_checker()
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "cond_result" in top_sv


def test_emit_disable_iff_contains_effective_disable() -> None:
    """emit_all() for disable iff top module contains 'effective_disable'."""
    checker = _load_disable_iff_checker()
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "effective_disable" in top_sv


def test_emit_disable_iff_contains_disable_i_input() -> None:
    """emit_all() for disable iff top module contains 'disable_i' input port."""
    checker = _load_disable_iff_checker()
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "disable_i" in top_sv


def test_emit_disable_iff_body_receives_effective_disable() -> None:
    """Body child instantiation in disable_iff_top receives effective_disable."""
    checker = _load_disable_iff_checker()
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "effective_disable" in top_sv
    # body's disable_i driven by effective_disable
    assert ".disable_i" in top_sv


def test_emit_disable_iff_propagates_body_overflow_flag() -> None:
    """An implication body cannot lose its explicit overflow diagnostic."""
    checker = _load_disable_iff_checker()
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "output  logic overflow_flag" in top_sv
    assert ".overflow_flag (overflow_flag)" in top_sv


def test_emit_disable_iff_all_modules_contain_endmodule() -> None:
    """All modules emitted for a disable iff property end with 'endmodule'."""
    checker = _load_disable_iff_checker()
    modules = emit_all(checker)
    for mod_name, sv_text in modules.items():
        assert "endmodule" in sv_text, f"Missing endmodule in {mod_name}"


def test_emit_disable_iff_outputs_gated() -> None:
    """Child checker modules gate their outputs when disable is asserted."""
    checker = _load_disable_iff_checker()
    modules = emit_all(checker)
    # Find the body child (overlap_bitvec template for a |-> b)
    child_sv = modules[checker.children[0].module_name]
    # Gating pattern: disable_i ? 1'b0 : ...
    assert "disable_i ? 1'b0" in child_sv
