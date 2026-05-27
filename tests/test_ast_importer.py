"""Unit tests for src/sva2rtl/ast_importer.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import (
    UNSUPPORTED_KINDS_PHASE1,
    expr_to_sv,
    extract_source_loc,
    import_assertion,
)
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import BoolExpr, ClockSpec, PropImplication, SeqConcat, SourceLoc

# Fixture directory
_FIXTURES = Path(__file__).parent / "fixtures"


# ── expr_to_sv unit tests ─────────────────────────────────────────────────


def test_expr_to_sv_named_value() -> None:
    """NamedValue node returns just the signal name, stripping the address prefix."""
    node = {"kind": "NamedValue", "symbol": "123456 a"}
    assert expr_to_sv(node) == "a"


def test_expr_to_sv_named_value_long_address() -> None:
    """Symbol with long numeric address prefix is correctly stripped."""
    node = {"kind": "NamedValue", "symbol": "6338700060480 clk"}
    assert expr_to_sv(node) == "clk"


def test_expr_to_sv_binary_op_logical_and() -> None:
    """BinaryOp LogicalAnd produces '(a && b)' with parentheses."""
    node = {
        "kind": "BinaryOp",
        "op": "LogicalAnd",
        "left": {"kind": "NamedValue", "symbol": "1 a"},
        "right": {"kind": "NamedValue", "symbol": "2 b"},
    }
    assert expr_to_sv(node) == "(a && b)"


def test_expr_to_sv_binary_op_logical_or() -> None:
    """BinaryOp LogicalOr produces '(a || b)'."""
    node = {
        "kind": "BinaryOp",
        "op": "LogicalOr",
        "left": {"kind": "NamedValue", "symbol": "1 a"},
        "right": {"kind": "NamedValue", "symbol": "2 b"},
    }
    assert expr_to_sv(node) == "(a || b)"


def test_expr_to_sv_unary_op_logical_not() -> None:
    """UnaryOp LogicalNot produces '(!a)'."""
    node = {
        "kind": "UnaryOp",
        "op": "LogicalNot",
        "operand": {"kind": "NamedValue", "symbol": "1 a"},
    }
    assert expr_to_sv(node) == "(!a)"


def test_expr_to_sv_integer_literal() -> None:
    """IntegerLiteral returns the value as a string."""
    node = {"kind": "IntegerLiteral", "value": "1"}
    assert expr_to_sv(node) == "1"


def test_expr_to_sv_sequence_expr_unwraps() -> None:
    """SequenceExpr delegates to its inner expr."""
    node = {
        "kind": "SequenceExpr",
        "expr": {"kind": "NamedValue", "symbol": "1 req"},
    }
    assert expr_to_sv(node) == "req"


def test_expr_to_sv_binary_property_expr_and() -> None:
    """BinaryPropertyExpr op=And maps to '&&'."""
    node = {
        "kind": "BinaryPropertyExpr",
        "op": "And",
        "left": {
            "kind": "SequenceExpr",
            "expr": {"kind": "NamedValue", "symbol": "1 a"},
        },
        "right": {
            "kind": "SequenceExpr",
            "expr": {"kind": "NamedValue", "symbol": "2 b"},
        },
    }
    assert expr_to_sv(node) == "(a && b)"


def test_expr_to_sv_unary_property_expr_not() -> None:
    """UnaryPropertyExpr op=Not maps to '(!...)'."""
    node = {
        "kind": "UnaryPropertyExpr",
        "op": "Not",
        "expr": {
            "kind": "SequenceExpr",
            "expr": {"kind": "NamedValue", "symbol": "1 c"},
        },
    }
    assert expr_to_sv(node) == "(!c)"


def test_expr_to_sv_nested() -> None:
    """Nested binary ops produce correctly parenthesized output."""
    # ((a && b) || c)
    node = {
        "kind": "BinaryPropertyExpr",
        "op": "Or",
        "left": {
            "kind": "BinaryPropertyExpr",
            "op": "And",
            "left": {
                "kind": "SequenceExpr",
                "expr": {"kind": "NamedValue", "symbol": "1 a"},
            },
            "right": {
                "kind": "SequenceExpr",
                "expr": {"kind": "NamedValue", "symbol": "2 b"},
            },
        },
        "right": {
            "kind": "SequenceExpr",
            "expr": {"kind": "NamedValue", "symbol": "3 c"},
        },
    }
    assert expr_to_sv(node) == "((a && b) || c)"


def test_expr_to_sv_unsupported_kind_raises() -> None:
    """Unknown kind raises UnsupportedConstruct with source loc."""
    node = {
        "kind": "SequenceConcat",
        "source_file_start": "foo.sv",
        "source_line_start": 5,
        "source_column_start": 3,
    }
    with pytest.raises(UnsupportedConstruct) as exc_info:
        expr_to_sv(node)
    assert exc_info.value.source_loc is not None


# ── import_assertion tests using fixture files ────────────────────────────


def test_import_assertion_bool_simple_returns_bool_expr() -> None:
    """bool_simple.json produces a BoolExpr node."""
    ast = json.loads((_FIXTURES / "bool_simple.json").read_text())
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, BoolExpr)
    assert text != ""


def test_import_assertion_bool_simple_text() -> None:
    """bool_simple.json expression text contains '&&' for 'a && b'."""
    ast = json.loads((_FIXTURES / "bool_simple.json").read_text())
    _, _, text, _ = import_assertion(ast)
    assert "&&" in text
    assert "a" in text
    assert "b" in text


def test_import_assertion_clock_extraction() -> None:
    """Clock spec has edge='posedge' and signal='clk'."""
    ast = json.loads((_FIXTURES / "bool_simple.json").read_text())
    _, clock, _, _ = import_assertion(ast)
    assert isinstance(clock, ClockSpec)
    assert clock.edge == "posedge"
    assert clock.signal == "clk"


def test_import_assertion_source_loc() -> None:
    """Returned BoolExpr has a meaningful source location."""
    ast = json.loads((_FIXTURES / "bool_simple.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, BoolExpr)
    assert node.source_loc.line > 0
    assert node.source_loc.file != "<unknown>"


def test_import_assertion_labeled() -> None:
    """bool_labeled.json returns label='my_check'."""
    ast = json.loads((_FIXTURES / "bool_labeled.json").read_text())
    _, _, _, label = import_assertion(ast)
    assert label == "my_check"


def test_import_assertion_complex_expr() -> None:
    """bool_complex.json ((a && b) || (!c)) parses with || and ! in output."""
    ast = json.loads((_FIXTURES / "bool_complex.json").read_text())
    _, _, text, _ = import_assertion(ast)
    assert "||" in text
    assert "&&" in text
    assert "!" in text


def test_import_assertion_seq_concat_returns_seq_concat() -> None:
    """unsupported_delay.json (a ##1 b) now returns SeqConcat — no longer unsupported."""
    ast = json.loads((_FIXTURES / "unsupported_delay.json").read_text())
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SeqConcat)


def test_import_assertion_seq_concat_delays() -> None:
    """a ##1 b produces delays=((1, 1),) — one delay for two elements."""
    ast = json.loads((_FIXTURES / "unsupported_delay.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, SeqConcat)
    assert node.delays == ((1, 1),)


def test_import_assertion_seq_concat_element_count() -> None:
    """a ##1 b produces exactly two child elements."""
    ast = json.loads((_FIXTURES / "unsupported_delay.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, SeqConcat)
    assert len(node.elements) == 2


def test_import_assertion_seq_concat_elements_are_bool_expr() -> None:
    """Each element of a ##1 b is a BoolExpr."""
    ast = json.loads((_FIXTURES / "unsupported_delay.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, SeqConcat)
    assert isinstance(node.elements[0], BoolExpr)
    assert isinstance(node.elements[1], BoolExpr)


def test_import_assertion_seq_concat_element_texts() -> None:
    """Elements of a ##1 b have texts 'a' and 'b'."""
    ast = json.loads((_FIXTURES / "unsupported_delay.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, SeqConcat)
    assert isinstance(node.elements[0], BoolExpr)
    assert isinstance(node.elements[1], BoolExpr)
    assert node.elements[0].text == "a"
    assert node.elements[1].text == "b"


def test_import_assertion_seq_concat_text_reconstruction() -> None:
    """Text for a ##1 b is reconstructed as 'a ##1 b'."""
    ast = json.loads((_FIXTURES / "unsupported_delay.json").read_text())
    _, _, text, _ = import_assertion(ast)
    assert "##1" in text or "##" in text
    assert "a" in text
    assert "b" in text


def test_import_assertion_seq_concat_clock() -> None:
    """Clock extracted from unsupported_delay.json is posedge clk."""
    ast = json.loads((_FIXTURES / "unsupported_delay.json").read_text())
    _, clock, _, _ = import_assertion(ast)
    assert clock.edge == "posedge"
    assert clock.signal == "clk"


def test_import_assertion_sequence_repetition_now_supported() -> None:
    """SequenceRepetition is now supported in Phase 3 — not in UNSUPPORTED_KINDS_PHASE1."""
    assert "SequenceRepetition" not in UNSUPPORTED_KINDS_PHASE1


# ── extract_source_loc tests ──────────────────────────────────────────────


def test_extract_source_loc_all_fields() -> None:
    """extract_source_loc reads all three source location fields."""
    node = {
        "source_file_start": "my_prop.sv",
        "source_line_start": 5,
        "source_column_start": 12,
    }
    loc = extract_source_loc(node)
    assert isinstance(loc, SourceLoc)
    assert loc.file == "my_prop.sv"
    assert loc.line == 5
    assert loc.col == 12


def test_extract_source_loc_missing_fields() -> None:
    """extract_source_loc falls back to '<unknown>' and 0 for missing fields."""
    loc = extract_source_loc({})
    assert loc.file == "<unknown>"
    assert loc.line == 0
    assert loc.col == 0


def test_extract_source_loc_partial_fields() -> None:
    """extract_source_loc handles partial fields gracefully."""
    node = {"source_file_start": "partial.sv"}
    loc = extract_source_loc(node)
    assert loc.file == "partial.sv"
    assert loc.line == 0


# ── UNSUPPORTED_KINDS_PHASE1 sanity check ────────────────────────────────


def test_unsupported_kinds_table_is_empty() -> None:
    """UNSUPPORTED_KINDS_PHASE1 is now empty — all Phase 1/2/3 constructs are supported."""
    assert len(UNSUPPORTED_KINDS_PHASE1) == 0


# ── PropImplication import tests ─────────────────────────────────────────


def test_import_implication_overlap_returns_prop_implication() -> None:
    """implication_overlap.json produces a PropImplication node."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)


def test_import_implication_overlap_is_overlapping() -> None:
    """implication_overlap.json PropImplication has overlapping=True."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert node.overlapping is True


def test_import_implication_nonoverlap_returns_prop_implication() -> None:
    """implication_nonoverlap.json produces a PropImplication node."""
    ast = json.loads((_FIXTURES / "implication_nonoverlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)


def test_import_implication_nonoverlap_is_not_overlapping() -> None:
    """implication_nonoverlap.json PropImplication has overlapping=False."""
    ast = json.loads((_FIXTURES / "implication_nonoverlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert node.overlapping is False


def test_import_implication_antecedent_is_bool_expr() -> None:
    """PropImplication antecedent from simple 'a |-> b' is a BoolExpr."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert isinstance(node.antecedent, BoolExpr)


def test_import_implication_consequent_is_bool_expr() -> None:
    """PropImplication consequent from simple 'a |-> b' is a BoolExpr."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert isinstance(node.consequent, BoolExpr)


def test_import_implication_antecedent_text() -> None:
    """PropImplication antecedent has text='a'."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert isinstance(node.antecedent, BoolExpr)
    assert node.antecedent.text == "a"


def test_import_implication_consequent_text() -> None:
    """PropImplication consequent has text='b'."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert isinstance(node.consequent, BoolExpr)
    assert node.consequent.text == "b"


def test_import_implication_overlap_label() -> None:
    """implication_overlap.json label is 'impl_check'."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    _, _, _, label = import_assertion(ast)
    assert label == "impl_check"


def test_import_implication_bitvec_consequent_is_seq_concat() -> None:
    """implication_bitvec.json has a SeqConcat consequent (a |-> a ##[2:5] b)."""
    ast = json.loads((_FIXTURES / "implication_bitvec.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert isinstance(node.consequent, SeqConcat)


def test_import_implication_bitvec_consequent_delays() -> None:
    """implication_bitvec.json consequent SeqConcat has delays=((2,5),)."""
    ast = json.loads((_FIXTURES / "implication_bitvec.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert isinstance(node.consequent, SeqConcat)
    assert node.consequent.delays == ((2, 5),)
