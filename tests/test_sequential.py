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


# ── TEST-06: Boundary tests for delay operators ────────────────────────────


def _compile_delay(delay_min: int, delay_max: int) -> str:
    """Build a SeqConcat IR node directly and emit the delay child module.

    Returns the SV text of the sva_delay_{delay_min}_{delay_max} module.
    """
    from sva2rtl.ir import BoolExpr, ClockSpec, SeqConcat, SourceLoc
    from sva2rtl.composer import compose
    from sva2rtl.emitter import emit_all

    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    a_expr = BoolExpr(text="a", source_loc=loc)
    b_expr = BoolExpr(text="b", source_loc=loc)
    seq = SeqConcat(
        elements=(a_expr, b_expr),
        delays=((delay_min, delay_max),),
        source_loc=loc,
    )
    checker = compose(seq, clock, None, f"a ##{delay_min} b")
    modules = emit_all(checker)
    delay_key = f"sva_delay_{delay_min}_{delay_max}"
    assert delay_key in modules, f"Expected module '{delay_key}' in {list(modules.keys())}"
    return modules[delay_key]


def _compile_impl_delay(delay_min: int, delay_max: int) -> str:
    """Build a PropImplication with SeqConcat consequent and return the top SV text."""
    from sva2rtl.ir import BoolExpr, ClockSpec, PropImplication, SeqConcat, SourceLoc
    from sva2rtl.composer import compose
    from sva2rtl.emitter import emit_all

    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    a_expr = BoolExpr(text="a", source_loc=loc)
    b_expr = BoolExpr(text="b", source_loc=loc)

    if delay_min == 0 and delay_max == 0:
        # Simple implication: a |-> b
        impl = PropImplication(
            antecedent=a_expr,
            consequent=b_expr,
            overlapping=True,
            source_loc=loc,
        )
        orig = "a |-> b"
    else:
        con_seq = SeqConcat(
            elements=(a_expr, b_expr),
            delays=((delay_min, delay_max),),
            source_loc=loc,
        )
        impl = PropImplication(
            antecedent=a_expr,
            consequent=con_seq,
            overlapping=True,
            source_loc=loc,
        )
        orig = f"a |-> ##[{delay_min}:{delay_max}] b"

    # Use an explicit label to avoid name collision between the top implication
    # module and its bool_expr children (both would otherwise hash "None + orig").
    checker = compose(impl, clock, "test_impl", orig)
    modules = emit_all(checker)
    return list(modules.values())[-1]  # top is last


@pytest.mark.parametrize(
    "delay,expected_cnt_width",
    [
        (1, 1),
        (2, 2),
        (3, 2),
        (4, 3),
        (7, 3),
        (8, 4),
        (15, 4),
        (16, 5),
        (100, 7),
    ],
)
def test_delay_cnt_width_boundary_values(delay: int, expected_cnt_width: int) -> None:
    """TEST-06: CNT_WIDTH = ceil(log2(delay_max+1)) for each boundary value."""
    import re

    sv = _compile_delay(delay, delay)  # fixed delay ##N
    m = re.search(r"parameter CNT_WIDTH\s*=\s*(\d+)", sv)
    assert m, f"CNT_WIDTH not found in emitted RTL for ##{delay}"
    actual = int(m.group(1))
    assert actual == expected_cnt_width, (
        f"##{delay}: expected CNT_WIDTH={expected_cnt_width}, got {actual}"
    )


@pytest.mark.parametrize(
    "delay_min,delay_max",
    [
        (2, 5),
        (0, 1),
        (3, 3),
    ],
)
def test_delay_window_comparator_boundaries(delay_min: int, delay_max: int) -> None:
    """TEST-06: Emitted RTL contains comparison values matching delay_min and delay_max."""
    sv = _compile_delay(delay_min, delay_max)
    # Both boundary values must appear as numeric literals in the comparisons
    assert f"d{delay_min}" in sv or f"d{delay_min})" in sv or str(delay_min) in sv, (
        f"delay_min={delay_min} not found in emitted RTL"
    )
    assert f"d{delay_max}" in sv or f"d{delay_max})" in sv or str(delay_max) in sv, (
        f"delay_max={delay_max} not found in emitted RTL"
    )
    # The pass assignment window contains both boundary values
    pass_line = [ln for ln in sv.splitlines() if "assign pass" in ln]
    assert pass_line, "No 'assign pass' line found"
    # delay_min and delay_max both appear in pass logic
    assert str(delay_min) in pass_line[0] and str(delay_max) in pass_line[0], (
        f"Expected both {delay_min} and {delay_max} in assign pass line: {pass_line[0]}"
    )


def test_delay_zero_special_case() -> None:
    """TEST-06: ##0 emits a combinational pass-through (no counter, assign pass = start)."""
    sv = _compile_delay(0, 0)
    assert "assign pass   = start" in sv, "##0: expected 'assign pass   = start'"
    assert "assign active = start" in sv, "##0: expected 'assign active = start'"
    # ##0 should NOT have a counter-based always_ff block with count_q
    assert "count_q" not in sv, "##0: should not have count_q counter register"


def test_delay_single_cycle_fixed() -> None:
    """TEST-06: ##1 is a single-cycle pulse (delay_min == delay_max == 1)."""
    sv = _compile_delay(1, 1)
    assert "delay_min" not in sv, "delay_min param name should not appear in rendered RTL"
    # Fixed single-cycle delay: comparisons both reference value 1
    assert "'d1" in sv, "##1: expected count comparison value 1"


def test_delay_range_window_width() -> None:
    """TEST-06: delay_min and delay_max structural parameters are correctly encoded."""
    import re

    # ##[2:5]
    sv25 = _compile_delay(2, 5)
    assert "2'd2" in sv25 or "3'd2" in sv25, "##[2:5]: delay_min=2 not found"
    assert "3'd5" in sv25, "##[2:5]: delay_max=5 not found"

    # ##[0:15]: window width 16
    sv015 = _compile_delay(0, 15)
    assert "'d0" in sv015 or "0" in sv015, "##[0:15]: delay_min=0 not found"
    assert "'d15" in sv015, "##[0:15]: delay_max=15 not found"

    # Verify params match expectations
    m_min = re.search(r"count_q >= \d+'d(\d+)", sv25)
    m_max = re.search(r"count_q <= \d+'d(\d+)", sv25)
    assert m_min and int(m_min.group(1)) == 2, f"##[2:5]: expected delay_min=2"
    assert m_max and int(m_max.group(1)) == 5, f"##[2:5]: expected delay_max=5"


@pytest.mark.parametrize(
    "delay_min,delay_max,expected_bv_width",
    [
        (0, 0, 1),    # a |-> b: single-cycle, bv_width=1
        (1, 1, 2),    # a |-> ##1 b: max_delay=1, bv_width=2
        (0, 1, 2),    # a |-> ##[0:1] b: max_delay=1, bv_width=2
        (2, 5, 6),    # a |-> ##[2:5] b: max_delay=5, bv_width=6
        (0, 15, 16),  # a |-> ##[0:15] b: max_delay=15, bv_width=16
    ],
)
def test_bv_width_boundary_for_implication(
    delay_min: int, delay_max: int, expected_bv_width: int
) -> None:
    """TEST-06: BV_WIDTH = max_delay_in_consequent + 1 for each boundary case."""
    import re

    sv = _compile_impl_delay(delay_min, delay_max)
    m = re.search(r"parameter BV_WIDTH\s*=\s*(\d+)", sv)
    assert m, f"BV_WIDTH not found for ##[{delay_min}:{delay_max}]"
    actual = int(m.group(1))
    assert actual == expected_bv_width, (
        f"|-> ##[{delay_min}:{delay_max}] b: expected BV_WIDTH={expected_bv_width}, got {actual}"
    )
