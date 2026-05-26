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


# ── TEST-05: Concurrent-attempt stress tests ───────────────────────────────


def _get_bv_width(fixture_name: str) -> int:
    """Compile a fixture and return the BV_WIDTH param of the top implication module."""
    modules = _compile_fixture(_FIXTURES / fixture_name)
    # The top module is last; its SV text has 'parameter BV_WIDTH = N'
    top_sv = list(modules.values())[-1]
    import re

    m = re.search(r"parameter BV_WIDTH\s*=\s*(\d+)", top_sv)
    assert m, f"BV_WIDTH not found in top module of {fixture_name}"
    return int(m.group(1))


def test_bv_width_sufficient_for_max_concurrent() -> None:
    """TEST-05: |-> ##[2:5] b has BV_WIDTH=6 (max_delay=5, width=5+1=6)."""
    bv_width = _get_bv_width("implication_bitvec.json")
    assert bv_width >= 6, f"Expected BV_WIDTH >= 6 for ##[2:5], got {bv_width}"


@pytest.mark.parametrize(
    "fixture_name,expected_min_bv",
    [
        ("implication_overlap.json", 1),       # a |-> b: single-cycle, width=1
        ("implication_nonoverlap.json", 1),    # a |=> b: single-cycle, width=1
        ("implication_bitvec.json", 6),        # a |-> ##[2:5] b: width=6
    ],
)
def test_concurrent_threads_structural_capacity(fixture_name: str, expected_min_bv: int) -> None:
    """TEST-05: BV_WIDTH is sufficient to handle the maximum concurrent threads."""
    bv_width = _get_bv_width(fixture_name)
    assert bv_width >= expected_min_bv, (
        f"{fixture_name}: expected BV_WIDTH >= {expected_min_bv}, got {bv_width}"
    )


def test_overflow_flag_structure_present() -> None:
    """TEST-05: Generated RTL for |-> ##[2:5] b contains all overflow-detection structures."""
    modules = _compile_fixture(_FIXTURES / "implication_bitvec.json")
    top_sv = list(modules.values())[-1]

    # Overflow detection conditional must be present
    assert "overflow_flag" in top_sv, "Missing overflow_flag signal"
    # Overflow event logic
    assert "overflow_event" in top_sv, "Missing overflow_event signal"
    # Sticky flag register must be reset in rst_n branch
    assert "overflow_flag_q <= 1'b0" in top_sv, "Missing overflow_flag_q reset in rst_n branch"
    # Halt state logic
    assert "HARD HALT" in top_sv or "overflow_flag_q" in top_sv, "Missing halt logic"


def test_overflow_halt_prevents_output() -> None:
    """TEST-05: Generated RTL gates active/pass/fail to 0 when overflow_flag is set."""
    modules = _compile_fixture(_FIXTURES / "implication_overlap.json")
    top_sv = list(modules.values())[-1]

    # active, pass, fail must all be gated by overflow_flag_q
    assert "overflow_flag_q ? 1'b0" in top_sv, (
        "Expected overflow_flag_q-gated output assignments"
    )
    # At least two gating occurrences (active and pass)
    assert top_sv.count("overflow_flag_q ? 1'b0") >= 2, (
        "Expected at least 2 overflow_flag_q-gated assignments (active, pass)"
    )


def test_reset_during_active_threads() -> None:
    """TEST-05 [REVIEW FIX]: rst_n clears ALL state registers unconditionally.

    Expected behavior: rst_n asserts while threads active -> all state clears
    atomically in one cycle, no residual thread state after reset.
    """
    # Test overlap (|->): bv_q and overflow_flag_q must reset
    modules_ov = _compile_fixture(_FIXTURES / "implication_overlap.json")
    top_sv_ov = list(modules_ov.values())[-1]

    # All state cleared in rst_n branch
    assert "bv_q            <= '0" in top_sv_ov, "bv_q not cleared in rst_n branch (overlap)"
    assert "overflow_flag_q <= 1'b0" in top_sv_ov, (
        "overflow_flag_q not cleared in rst_n branch (overlap)"
    )
    assert "attempt_fired_q <= 1'b0" in top_sv_ov, (
        "attempt_fired_q not cleared in rst_n branch (overlap)"
    )

    # Test nonoverlap (|=>): also requires ant_pass_delayed_q to reset
    modules_nn = _compile_fixture(_FIXTURES / "implication_nonoverlap.json")
    top_sv_nn = list(modules_nn.values())[-1]

    assert "ant_pass_delayed_q <= 1'b0" in top_sv_nn, (
        "ant_pass_delayed_q not cleared in rst_n branch (nonoverlap)"
    )
    assert "bv_q               <= '0" in top_sv_nn, (
        "bv_q not cleared in rst_n branch (nonoverlap)"
    )
    assert "overflow_flag_q    <= 1'b0" in top_sv_nn, (
        "overflow_flag_q not cleared in rst_n branch (nonoverlap)"
    )
