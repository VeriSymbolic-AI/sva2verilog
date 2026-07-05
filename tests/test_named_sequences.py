"""Tests for named sequence inline expansion (PARSE-03) and CSE tagging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.errors import SvaCompileError
from sva2rtl.ir import CheckerNode, SeqConcat, SourceLoc

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _make_loc(file: str = "test.sv", line: int = 1, col: int = 1) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


# ── CheckerNode cse_origin field ──────────────────────────────────────────────


def test_cse_origin_field_default_none() -> None:
    """CheckerNode.cse_origin defaults to None when not supplied."""
    loc = _make_loc()
    checker = CheckerNode(
        template_name="bool_expr",
        module_name="sva_test",
        params={},
        observed_signals=(),
        source_loc=loc,
    )
    assert checker.cse_origin is None


def test_cse_origin_field_set() -> None:
    """CheckerNode.cse_origin can be set to a string value."""
    loc = _make_loc()
    checker = CheckerNode(
        template_name="bool_expr",
        module_name="sva_test",
        params={},
        observed_signals=(),
        source_loc=loc,
        cse_origin="my_sequence",
    )
    assert checker.cse_origin == "my_sequence"


def test_cse_origin_in_hash() -> None:
    """Two CheckerNodes differing only in cse_origin have different hashes."""
    loc = _make_loc()
    base = dict(
        template_name="bool_expr",
        module_name="sva_test",
        params={},
        observed_signals=(),
        source_loc=loc,
    )
    c1 = CheckerNode(**base, cse_origin=None)
    c2 = CheckerNode(**base, cse_origin="my_seq")
    assert hash(c1) != hash(c2)
    assert c1 != c2


def test_cse_origin_hashable() -> None:
    """CheckerNode with cse_origin set is hashable (can be stored in a set)."""
    loc = _make_loc()
    checker = CheckerNode(
        template_name="bool_expr",
        module_name="sva_test",
        params={},
        observed_signals=(),
        source_loc=loc,
        cse_origin="named_seq",
    )
    s = {checker}
    assert checker in s


# ── Named sequence expansion ──────────────────────────────────────────────────


def test_named_seq_expansion_returns_seq_concat() -> None:
    """Named sequence fixture expands inline to a SeqConcat IR node."""
    ast = json.loads((FIXTURES_DIR / "named_seq.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    assert isinstance(ir_node, SeqConcat), (
        f"Expected SeqConcat from inline expansion, got {type(ir_node).__name__}"
    )


def test_named_seq_expansion_correct_delay() -> None:
    """Expanded named sequence 'req_ack' (a ##1 b) has one delay of (1,1)."""
    ast = json.loads((FIXTURES_DIR / "named_seq.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    assert isinstance(ir_node, SeqConcat)
    assert len(ir_node.delays) == 1
    assert ir_node.delays[0] == (1, 1)


def test_named_seq_expansion_text() -> None:
    """Reconstructed text for expanded named sequence matches the body (a ##1 b)."""
    ast = json.loads((FIXTURES_DIR / "named_seq.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    assert "a" in text and "b" in text
    assert "##1" in text


def test_named_seq_compose_produces_checker() -> None:
    """Expanded named sequence composes successfully into a CheckerNode."""
    ast = json.loads((FIXTURES_DIR / "named_seq.json").read_text(encoding="utf-8"))
    ir_node, clock, text, label = import_assertion(ast)
    checker = compose(ir_node, clock, label, text)
    assert isinstance(checker, CheckerNode)
    assert checker.module_name.startswith("sva_")


# ── Circular reference detection ──────────────────────────────────────────────


def test_circular_ref_rejected_with_sva_e003() -> None:
    """Circular named sequence reference raises SvaCompileError with 'SVA-E003'."""
    ast = json.loads(
        (FIXTURES_DIR / "named_seq_circular.json").read_text(encoding="utf-8")
    )
    with pytest.raises(SvaCompileError) as exc_info:
        import_assertion(ast)
    assert "SVA-E003" in str(exc_info.value)


def test_circular_ref_error_mentions_sequence_name() -> None:
    """SVA-E003 error message contains the circular sequence name."""
    ast = json.loads(
        (FIXTURES_DIR / "named_seq_circular.json").read_text(encoding="utf-8")
    )
    with pytest.raises(SvaCompileError) as exc_info:
        import_assertion(ast)
    assert "self_ref" in str(exc_info.value)
