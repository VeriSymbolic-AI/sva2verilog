"""Tests for source-level differential case generation."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given, settings

from tests.conftest import requires_slang
from tests.differential_cases import (
    DEFAULT_BUDGET,
    DEFERRED_FAMILIES,
    DifferentialBudget,
    GeneratedSvaCase,
    compile_generated_case,
    example_generated_cases,
    generated_sva_cases,
    make_generated_case,
    metadata_is_sanitized,
)
from tests.differential_reference import SourceBoolExpr, SourceReferenceSpec


def test_default_budget_trace_range() -> None:
    assert DEFAULT_BUDGET.min_trace_length == 8
    assert DEFAULT_BUDGET.max_trace_length == 24
    assert DEFAULT_BUDGET.max_delay == 8
    assert DEFAULT_BUDGET.max_repeat == 6


def test_budget_rejects_invalid_trace_range() -> None:
    with pytest.raises(ValueError, match="max_trace_length"):
        DifferentialBudget(min_trace_length=12, max_trace_length=6)


def test_rendered_source_contains_complete_module_and_assertion() -> None:
    case = make_generated_case("(a && b)", ("bool", "structured_bool"), ("a", "b"))

    assert case.source_text.startswith(f"module {case.module_name}(")
    assert f"{case.property_label}: assert property (@(posedge clk)" in case.source_text
    assert "input logic clk" in case.source_text
    assert "input logic rst_n" in case.source_text
    assert "input logic a" in case.source_text
    assert "input logic b" in case.source_text
    assert case.source_text.endswith("endmodule\n")


def test_generated_metadata_is_sanitized() -> None:
    case = make_generated_case("a |-> b", ("implication_overlap",), ("a", "b"))

    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", case.case_id)
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", case.module_name)
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", case.property_label)
    assert metadata_is_sanitized(case.metadata())


def test_generated_case_rejects_deferred_family() -> None:
    with pytest.raises(ValueError, match="unsupported generated families"):
        GeneratedSvaCase(
            case_id="diff_bad",
            module_name="diff_bad_mod",
            property_label="p_bad",
            assertion_expr="a",
            source_text="module diff_bad_mod(input logic clk, input logic rst_n, input logic a);"
            "p_bad: assert property (@(posedge clk) a); endmodule\n",
            signal_names=("a",),
            family_tags=("multi_clock",),
            trace_length=6,
        )


def test_generated_case_rejects_source_reference_text_drift() -> None:
    spec = SourceReferenceSpec("bool", SourceBoolExpr.signal("a"))

    with pytest.raises(ValueError, match="exact assertion expression"):
        make_generated_case("!a", ("bool",), ("a",), source_reference=spec)


@given(generated_sva_cases())
@settings(max_examples=12, deadline=None)
def test_strategy_produces_bounded_supported_families(case: GeneratedSvaCase) -> None:
    assert DEFAULT_BUDGET.min_trace_length <= case.trace_length <= DEFAULT_BUDGET.max_trace_length
    assert case.family_tags
    assert not (set(case.family_tags) & DEFERRED_FAMILIES)
    assert metadata_is_sanitized(case.metadata())
    assert case.source_text.count("assert property") == 1


def test_example_catalog_covers_expected_families() -> None:
    families = {family for case in example_generated_cases() for family in case.family_tags}

    assert "bool" in families
    assert "sampled" in families
    assert "past" in families
    assert "delay_fixed" in families
    assert "delay_range" in families
    assert "implication_overlap" in families
    assert "implication_nonoverlap" in families
    assert "rep_consecutive_fixed" in families
    assert "rep_consecutive_range" in families
    assert "disable_iff" in families
    assert not (families & DEFERRED_FAMILIES)
    assert all(case.source_reference is not None for case in example_generated_cases())


@requires_slang
@pytest.mark.parametrize("case", example_generated_cases()[:7], ids=lambda c: c.case_id)
def test_compile_generated_case_smoke(
    case: GeneratedSvaCase,
    tmp_path: Path,
) -> None:
    compiled = compile_generated_case(case, tmp_path)

    assert compiled.case == case
    assert compiled.clock.signal == "clk"
    observed = {port for port, _signal in compiled.checker.observed_signals}
    assert set(case.signal_names).issubset(observed)
