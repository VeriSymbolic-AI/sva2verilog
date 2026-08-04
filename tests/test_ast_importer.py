"""Unit tests for src/sva2rtl/ast_importer.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sva2rtl.ast_importer import (
    UNSUPPORTED_KINDS_PHASE1,
    _dispatch_expr_to_ir,
    _is_boolean_binary,
    build_bool_expr,
    expr_to_sv,
    extract_source_loc,
    import_assertion,
    parse_slang_integral_type,
)
from sva2rtl.bool_semantics import render_bool_expr
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolBinary,
    BoolBitSelect,
    BoolCompare,
    BoolConst,
    BoolExpr,
    BoolIdent,
    BoolUnary,
    ClockSpec,
    DisableIff,
    PropImplication,
    SeqConcat,
    SeqNonconsecRep,
    SourceLoc,
)

# Fixture directory
_FIXTURES = Path(__file__).parent / "fixtures"


def test_dispatch_legacy_nonconsecutive_repetition() -> None:
    """The legacy v7 SimpleAssertionExpr representation keeps [=N] semantics."""
    node = {
        "kind": "SimpleAssertionExpr",
        "expr": {"kind": "NamedValue", "symbol": "a"},
        "repetition": {"kind": "Nonconsecutive", "min": 2, "max": 2},
    }
    result = _dispatch_expr_to_ir(node)
    assert isinstance(result, SeqNonconsecRep)
    assert (result.rep_min, result.rep_max) == (2, 2)


def test_import_legacy_nonconsecutive_repetition_through_property_spec() -> None:
    """The v7 PropertySpec entry point routes SimpleAssertionExpr [=N]."""
    ast = json.loads((_FIXTURES / "fell.json").read_text(encoding="utf-8"))
    assertion = ast["design"]["members"][0]["body"]["members"][-1]
    assertion["body"]["expr"] = {
        "kind": "SimpleAssertionExpr",
        "expr": {"kind": "NamedValue", "symbol": "2 sig"},
        "repetition": {"kind": "Nonconsecutive", "min": 2, "max": 2},
    }

    result, _clock, _text, _label = import_assertion(ast)
    assert isinstance(result, SeqNonconsecRep)
    assert (result.rep_min, result.rep_max) == (2, 2)


def test_boolean_binary_classification_covers_all_terminal_paths() -> None:
    assert _is_boolean_binary(
        {"left": {"kind": "Simple"}, "right": {"kind": "NamedValue"}}
    )
    assert _is_boolean_binary(
        {
            "left": {"kind": "Simple"},
            "right": {
                "kind": "BinaryPropertyExpr",
                "left": {"kind": "Simple"},
                "right": {"kind": "SequenceExpr"},
            },
        }
    )
    assert not _is_boolean_binary(
        {"left": {"kind": "Simple"}, "right": {"kind": "Simple"}}
    )


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


def test_build_bool_expr_nested_structure_and_source_locations() -> None:
    """Nested property boolean syntax becomes concrete BoolNode structure."""
    node = {
        "kind": "BinaryPropertyExpr",
        "op": "Or",
        "source_file_start": "nested.sv",
        "source_line_start": 10,
        "source_column_start": 4,
        "left": {
            "kind": "BinaryPropertyExpr",
            "op": "And",
            "source_file_start": "nested.sv",
            "source_line_start": 10,
            "source_column_start": 5,
            "left": {
                "kind": "SequenceExpr",
                "expr": {
                    "kind": "NamedValue",
                    "symbol": "1 a",
                    "source_file_start": "nested.sv",
                    "source_line_start": 10,
                    "source_column_start": 5,
                },
            },
            "right": {
                "kind": "SequenceExpr",
                "expr": {
                    "kind": "NamedValue",
                    "symbol": "2 b",
                    "source_file_start": "nested.sv",
                    "source_line_start": 10,
                    "source_column_start": 10,
                },
            },
        },
        "right": {
            "kind": "UnaryPropertyExpr",
            "op": "Not",
            "source_file_start": "nested.sv",
            "source_line_start": 10,
            "source_column_start": 16,
            "expr": {
                "kind": "SequenceExpr",
                "expr": {
                    "kind": "NamedValue",
                    "symbol": "3 c",
                    "source_file_start": "nested.sv",
                    "source_line_start": 10,
                    "source_column_start": 17,
                },
            },
        },
    }

    expr = build_bool_expr(node)

    assert isinstance(expr, BoolBinary)
    assert expr.op == "or"
    assert expr.source_loc == SourceLoc("nested.sv", 10, 4)
    assert isinstance(expr.left, BoolBinary)
    assert expr.left.op == "and"
    assert isinstance(expr.left.left, BoolIdent)
    assert expr.left.left.name == "a"
    assert expr.left.left.source_loc == SourceLoc("nested.sv", 10, 5)
    assert isinstance(expr.left.right, BoolIdent)
    assert expr.left.right.name == "b"
    assert isinstance(expr.right, BoolUnary)
    assert expr.right.op == "not"
    assert isinstance(expr.right.operand, BoolIdent)
    assert expr.right.operand.source_loc == SourceLoc("nested.sv", 10, 17)
    assert render_bool_expr(expr) == "((a && b) || (!c))"


def test_build_bool_expr_constants_comparisons_and_bit_select() -> None:
    """Constants, eq/ne comparisons, and single-bit selects are structured."""
    eq_node = {
        "kind": "BinaryOp",
        "op": "Equality",
        "left": {
            "kind": "ElementSelect",
            "value": {"kind": "NamedValue", "symbol": "1 data"},
            "selector": {"kind": "IntegerLiteral", "value": "2"},
        },
        "right": {"kind": "IntegerLiteral", "value": "1'b1"},
    }
    ne_node = {
        "kind": "BinaryOp",
        "op": "Inequality",
        "left": {"kind": "NamedValue", "symbol": "2 vec"},
        "right": {"kind": "IntegerLiteral", "value": "4'hf"},
    }

    eq_expr = build_bool_expr(eq_node)
    ne_expr = build_bool_expr(ne_node)

    assert isinstance(eq_expr, BoolCompare)
    assert eq_expr.op == "eq"
    assert isinstance(eq_expr.left, BoolBitSelect)
    assert eq_expr.left.index == 2
    assert isinstance(eq_expr.right, BoolConst)
    assert eq_expr.right.value == 1
    assert eq_expr.right.width == 1
    assert expr_to_sv(eq_node) == "(data[2] == 1'b1)"
    assert isinstance(ne_expr, BoolCompare)
    assert ne_expr.op == "ne"
    assert expr_to_sv(ne_node) == "(vec != 4'hf)"

    unsized = build_bool_expr({"kind": "IntegerLiteral", "value": "7"})
    assert isinstance(unsized, BoolConst)
    assert unsized.signed is False


def test_build_bool_expr_preserves_named_value_packed_width() -> None:
    """slang packed-vector type metadata reaches BoolIdent IR."""
    expr = build_bool_expr(
        {
            "kind": "NamedValue",
            "symbol": "1 data",
            "type": "logic[7:4]",
        }
    )

    assert isinstance(expr, BoolIdent)
    assert expr.width == 4
    assert expr.signed is False


@pytest.mark.parametrize(
    ("type_text", "expected"),
    [
        ("logic", (1, False)),
        ("logic[7:4]", (4, False)),
        ("logic signed[7:0]", (8, True)),
        ("int", (32, True)),
        ("int unsigned", (32, False)),
    ],
)
def test_parse_slang_integral_type_accepts_only_exact_supported_shapes(
    type_text: str,
    expected: tuple[int, bool],
) -> None:
    assert parse_slang_integral_type(type_text) == expected


@pytest.mark.parametrize(
    "type_text",
    [
        "logic[1:0][3:0]",
        "logic[7:0]$[0:1]",
        "structpacked{logic[7:0]payload;}",
    ],
)
def test_parse_slang_integral_type_rejects_trailing_or_complex_type_syntax(
    type_text: str,
) -> None:
    with pytest.raises(UnsupportedConstruct, match="boolean identifier type"):
        parse_slang_integral_type(type_text)


def test_build_bool_expr_rejects_multidimensional_packed_identifier() -> None:
    with pytest.raises(UnsupportedConstruct, match="boolean identifier type"):
        build_bool_expr(
            {
                "kind": "NamedValue",
                "symbol": "1 data",
                "type": "logic[1:0][3:0]",
            }
        )


def test_build_bool_expr_conversion_unwraps_to_inner_structure() -> None:
    """Conversion wrappers do not erase the underlying BoolNode structure."""
    node = {
        "kind": "Conversion",
        "expr": {
            "kind": "BinaryOp",
            "op": "LogicalOr",
            "left": {"kind": "NamedValue", "symbol": "1 a"},
            "right": {"kind": "NamedValue", "symbol": "2 b"},
        },
    }

    expr = build_bool_expr(node)

    assert isinstance(expr, BoolBinary)
    assert expr.op == "or"
    assert render_bool_expr(expr) == "(a || b)"


@pytest.mark.parametrize(
    "node",
    [
        {
            "kind": "BinaryOp",
            "op": "Add",
            "left": {"kind": "NamedValue", "symbol": "1 a"},
            "right": {"kind": "NamedValue", "symbol": "2 b"},
        },
        {
            "kind": "UnaryOp",
            "op": "ReductionAnd",
            "operand": {"kind": "NamedValue", "symbol": "1 a"},
        },
        {"kind": "PartSelect", "value": {"kind": "NamedValue", "symbol": "1 data"}},
        {"kind": "CallExpression", "subroutineName": "$foo", "arguments": []},
    ],
)
def test_build_bool_expr_rejects_unsupported_boolean_subforms(
    node: dict[str, Any],
) -> None:
    """Out-of-scope boolean forms raise rather than producing text-only leaves."""
    with pytest.raises(UnsupportedConstruct):
        build_bool_expr(node)


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


# ── P0-2: never silently flatten an unknown temporal kind to a boolean ─────


def test_dispatch_unknown_temporal_kind_raises_not_silent() -> None:
    """An unrecognized temporal/property node must error, not become a BoolExpr.

    Regression for the silent-degradation defect: the dispatcher default case
    used to fall through to ``expr_to_sv`` (BoolExpr) for any kind outside the
    1-element Phase-1 whitelist, producing a compilable but semantically wrong
    monitor with no diagnostic.  An ``until`` property node must now raise.
    """
    node = {
        "kind": "UntilPropertyExpr",
        "source_file_start": "foo.sv",
        "source_line_start": 7,
        "source_column_start": 2,
    }
    with pytest.raises(UnsupportedConstruct) as exc_info:
        _dispatch_expr_to_ir(node)
    # Source location is preserved and the friendly operator name is reported.
    assert exc_info.value.source_loc is not None
    assert "until" in str(exc_info.value)


def test_dispatch_boolean_kind_still_flattens() -> None:
    """A genuine boolean leaf (NamedValue) still becomes a BoolExpr (no regression)."""
    node = {
        "kind": "NamedValue",
        "symbol": "Variable sig",
        "source_file_start": "foo.sv",
        "source_line_start": 1,
        "source_column_start": 1,
    }
    ir = _dispatch_expr_to_ir(node)
    assert isinstance(ir, BoolExpr)
    assert ir.text == "sig"
    assert isinstance(ir.expr, BoolIdent)
    assert ir.expr.name == "sig"


# ── import_assertion tests using fixture files ────────────────────────────


def test_import_assertion_bool_simple_returns_bool_expr() -> None:
    """bool_simple.json produces a BoolExpr node."""
    ast = json.loads((_FIXTURES / "bool_simple.json").read_text())
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, BoolExpr)
    assert node.expr is not None
    assert node.text == render_bool_expr(node.expr)
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
    node, _, text, _ = import_assertion(ast)
    assert isinstance(node, BoolExpr)
    assert isinstance(node.expr, BoolBinary)
    assert node.text == render_bool_expr(node.expr)
    assert "||" in text
    assert "&&" in text
    assert "!" in text


def test_import_assertion_disable_iff_condition_has_structured_expr() -> None:
    """disable iff conditions are imported through the structure-first bool path."""
    ast = json.loads((_FIXTURES / "disable_iff.json").read_text())
    node, _, _, _ = import_assertion(ast)

    assert isinstance(node, DisableIff)
    assert isinstance(node.condition, BoolExpr)
    assert node.condition.expr is not None
    assert node.condition.text == render_bool_expr(node.condition.expr)


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
    assert node.elements[0].expr is not None
    assert node.elements[1].expr is not None


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


def test_extract_source_loc_redacts_absolute_host_path() -> None:
    """Diagnostics retain the filename without exposing host directories."""
    loc = extract_source_loc(
        {
            "source_file": "/private/workstation/customer/design.sv",
            "source_line": 4,
            "source_column": 2,
        }
    )

    assert loc == SourceLoc("design.sv", 4, 2)


# ── UNSUPPORTED_KINDS_PHASE1 sanity check ────────────────────────────────


def test_unsupported_kinds_table_is_empty() -> None:
    """UNSUPPORTED_KINDS_PHASE1 lists only constructs explicitly deferred to future versions."""
    # strong()/weak() are the only remaining explicitly unsupported constructs
    assert UNSUPPORTED_KINDS_PHASE1 == {"StrongWeakAssertionExpr": "strong()/weak()"}


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
    assert node.antecedent.expr is not None


def test_import_implication_consequent_is_bool_expr() -> None:
    """PropImplication consequent from simple 'a |-> b' is a BoolExpr."""
    ast = json.loads((_FIXTURES / "implication_overlap.json").read_text())
    node, _, _, _ = import_assertion(ast)
    assert isinstance(node, PropImplication)
    assert isinstance(node.consequent, BoolExpr)
    assert node.consequent.expr is not None


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
