"""Integration tests for Phase 2 sequential operators — golden file harness,
determinism, and debug output verification.

Requirements covered:
- TEST-02: deterministic codegen — byte-for-byte golden match
- OUT-06: attempt_fired and overflow_flag present in all emitted modules
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from tests.conftest import assert_golden

# ── Paths ──────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = Path(__file__).parent / "golden"


# ── Helpers ────────────────────────────────────────────────────────────────


def _compile_fixture(fixture_json_path: Path) -> dict[str, str]:
    """Load a JSON fixture, run import_assertion → compose → emit_all.

    Returns
    -------
    dict[str, str]
        Mapping of module_name → sv_text for every module in the hierarchy.
    """
    ast = json.loads(fixture_json_path.read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    return emit_all(checker)


def _assert_golden_match(actual: str, golden_path: Path) -> None:
    """Assert *actual* matches *golden_path* line-by-line (strips trailing whitespace).

    On mismatch, shows a unified diff with the first differing line highlighted.
    Delegates to the shared ``assert_golden`` helper from conftest.
    """
    assert_golden(actual, golden_path)


# ── TEST-02: Golden file integration tests ─────────────────────────────────


def test_golden_delay_fixed_3() -> None:
    """TEST-02: sva_delay_3_3 module matches golden byte-for-byte."""
    modules = _compile_fixture(_FIXTURES / "delay_fixed.json")
    assert "sva_delay_3_3" in modules, f"Expected 'sva_delay_3_3' in {list(modules.keys())}"
    _assert_golden_match(modules["sva_delay_3_3"], _GOLDEN / "sva_delay_3_3.sv")


def test_golden_delay_range_2_5() -> None:
    """TEST-02: sva_delay_2_5 module matches golden byte-for-byte."""
    modules = _compile_fixture(_FIXTURES / "delay_range.json")
    assert "sva_delay_2_5" in modules, f"Expected 'sva_delay_2_5' in {list(modules.keys())}"
    _assert_golden_match(modules["sva_delay_2_5"], _GOLDEN / "sva_delay_2_5.sv")


def test_golden_overlap_impl() -> None:
    """TEST-02: sva_impl_check (|-> ) top module matches golden byte-for-byte."""
    modules = _compile_fixture(_FIXTURES / "implication_overlap.json")
    assert "sva_impl_check" in modules, f"Expected 'sva_impl_check' in {list(modules.keys())}"
    _assert_golden_match(modules["sva_impl_check"], _GOLDEN / "overlap_impl.sv")


def test_golden_nonoverlap_impl() -> None:
    """TEST-02: sva_nonoverlap_check (|=>) top module matches golden byte-for-byte."""
    modules = _compile_fixture(_FIXTURES / "implication_nonoverlap.json")
    assert "sva_nonoverlap_check" in modules, (
        f"Expected 'sva_nonoverlap_check' in {list(modules.keys())}"
    )
    _assert_golden_match(modules["sva_nonoverlap_check"], _GOLDEN / "nonoverlap_impl.sv")


# ── TEST-02: Determinism tests ─────────────────────────────────────────────


def test_codegen_deterministic_delay() -> None:
    """TEST-02: Compiling the same delay fixture 5× produces identical output."""
    results = [_compile_fixture(_FIXTURES / "delay_fixed.json") for _ in range(5)]
    for i in range(1, 5):
        assert results[i] == results[0], f"Run {i} output differs from run 0"


def test_codegen_deterministic_implication() -> None:
    """TEST-02: Compiling the same implication fixture 5× produces identical output."""
    results = [_compile_fixture(_FIXTURES / "implication_overlap.json") for _ in range(5)]
    for i in range(1, 5):
        assert results[i] == results[0], f"Run {i} output differs from run 0"


def test_codegen_deterministic_nonoverlap() -> None:
    """TEST-02: Compiling the same nonoverlap fixture 5× produces identical output."""
    results = [_compile_fixture(_FIXTURES / "implication_nonoverlap.json") for _ in range(5)]
    for i in range(1, 5):
        assert results[i] == results[0], f"Run {i} output differs from run 0"


def test_codegen_deterministic_bitvec() -> None:
    """TEST-02: Compiling the bitvec (|-> with delay) fixture 5× produces identical output."""
    results = [_compile_fixture(_FIXTURES / "implication_bitvec.json") for _ in range(5)]
    for i in range(1, 5):
        assert results[i] == results[0], f"Run {i} output differs from run 0"


# ── OUT-06: Debug output verification ─────────────────────────────────────


@pytest.mark.parametrize(
    "fixture_name",
    [
        "delay_fixed.json",
        "delay_range.json",
        "implication_overlap.json",
        "implication_nonoverlap.json",
        "implication_bitvec.json",
    ],
)
def test_attempt_fired_in_all_modules(fixture_name: str) -> None:
    """OUT-06: Every emitted module in every Phase 2 fixture contains 'attempt_fired'."""
    modules = _compile_fixture(_FIXTURES / fixture_name)
    for mod_name, sv_text in modules.items():
        assert "attempt_fired" in sv_text, (
            f"Module '{mod_name}' from {fixture_name} is missing 'attempt_fired'"
        )


@pytest.mark.parametrize(
    "fixture_name",
    [
        "implication_overlap.json",
        "implication_nonoverlap.json",
        "implication_bitvec.json",
    ],
)
def test_overflow_flag_in_implication_modules(fixture_name: str) -> None:
    """OUT-06: The top-level implication module contains 'overflow_flag'."""
    modules = _compile_fixture(_FIXTURES / fixture_name)
    # The top module is last in emit_all (dependency order)
    top_name = list(modules.keys())[-1]
    sv_text = modules[top_name]
    assert "overflow_flag" in sv_text, (
        f"Top module '{top_name}' from {fixture_name} is missing 'overflow_flag'"
    )
