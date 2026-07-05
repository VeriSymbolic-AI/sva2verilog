"""Integration tests for Phase 2 sequential operators — golden file harness,
determinism, and debug output verification.

Requirements covered:
- TEST-02: deterministic codegen — byte-for-byte golden match
- OUT-06: attempt_fired and overflow_flag present in all emitted modules
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
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


def test_bitvec_sequence_consequent_implication_rejected() -> None:
    """BV_WIDTH>1 sequence-consequent implication (`a |-> a ##[2:5] b`) is rejected
    at compile time rather than emitting a wrong monitor.

    The legacy bv_q token-passing path for multi-cycle sequence consequents is a
    confirmed correctness defect (BUG-IMPL-01); a correct implementation needs the
    v1.5 NFA composition engine. Until then the compiler must error (never fail
    silently), not emit a monitor whose pass never fires.
    """
    from sva2rtl.errors import UnsupportedConstruct

    ast = json.loads((_FIXTURES / "implication_bitvec.json").read_text())
    node, clock, label, text = import_assertion(ast)
    with pytest.raises(UnsupportedConstruct, match="sequence consequent"):
        compose(node, clock, label, text)


# ── OUT-06: Debug output verification ─────────────────────────────────────


@pytest.mark.parametrize(
    "fixture_name",
    [
        "delay_fixed.json",
        "delay_range.json",
        "implication_overlap.json",
        "implication_nonoverlap.json",
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


def test_bv_width_computation_for_ranged_consequent() -> None:
    """TEST-05: _compute_bv_width(a ##[2:5] b) == 6 (max_delay=5, width=5+1=6).

    The ranged sequence consequent itself is rejected for use in an implication
    (BV_WIDTH>1, v1.5 boundary); this verifies the width computation that gates
    that rejection decision.
    """
    from sva2rtl.composer import _compute_bv_width
    from sva2rtl.ir import BoolExpr, SeqConcat, SourceLoc

    loc = SourceLoc("test.sv", 1, 1)
    seq = SeqConcat(
        elements=(BoolExpr(text="a", source_loc=loc), BoolExpr(text="b", source_loc=loc)),
        delays=((2, 5),),
        source_loc=loc,
    )
    assert _compute_bv_width(seq) == 6


@pytest.mark.parametrize(
    "fixture_name,expected_min_bv",
    [
        ("implication_overlap.json", 1),       # a |-> b: single-cycle, width=1
        ("implication_nonoverlap.json", 1),    # a |=> b: single-cycle, width=1
    ],
)
def test_concurrent_threads_structural_capacity(fixture_name: str, expected_min_bv: int) -> None:
    """TEST-05: BV_WIDTH is sufficient to handle the maximum concurrent threads.

    Only single-cycle-consequent implications (BV_WIDTH==1) remain supported;
    multi-cycle sequence consequents (BV_WIDTH>1) are rejected at compile time.
    """
    bv_width = _get_bv_width(fixture_name)
    assert bv_width >= expected_min_bv, (
        f"{fixture_name}: expected BV_WIDTH >= {expected_min_bv}, got {bv_width}"
    )


def test_reset_during_active_threads() -> None:
    """TEST-05 [REVIEW FIX]: rst_n clears ALL state registers unconditionally.

    Single-cycle-consequent |=> (BV_WIDTH==1): the parallel design has no bv_q
    or ant_pass_delayed_q; the ##1 alignment is con_start_w = ant_pass_w. The
    leaf children (ant/con) own their reset; the only top-level state is
    attempt_fired_q, which must reset to 0. (The BV_WIDTH>1 sequence-consequent
    path that used bv_q is now rejected at compile time, BUG-IMPL-01 / v1.5.)
    """
    modules_nn = _compile_fixture(_FIXTURES / "implication_nonoverlap.json")
    top_sv_nn = list(modules_nn.values())[-1]

    assert "con_start_w = ant_pass_w" in top_sv_nn, (
        "con_start_w not driven by ant_pass_w (nonoverlap |=> ##1 alignment)"
    )
    assert ("attempt_fired_q <= 1'b0" in top_sv_nn or "attempt_fired_q <= '0" in top_sv_nn), (
        "attempt_fired_q not cleared in rst_n branch (nonoverlap)"
    )


# ── TEST-06: Boundary tests for delay operators ────────────────────────────


def _compile_delay(delay_min: int, delay_max: int) -> str:
    """Build a SeqConcat IR node directly and emit the delay child module.

    Returns the SV text of the sva_delay_{delay_min}_{delay_max} module.
    """
    from sva2rtl.composer import compose
    from sva2rtl.emitter import emit_all
    from sva2rtl.ir import BoolExpr, ClockSpec, SeqConcat, SourceLoc

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
    """TEST-06 / BUG-DELAY-01: emitted RTL encodes the CORRECTED (shifted) window.

    The pass logic now asserts at start+(N-1): a start-cycle combinational term
    ``(start && (delay_min <= 1) && (delay_max >= 1))`` plus, when delay_max>=2, a
    counter term over the SHIFTED window ``count_q in [max(min-2,0), max(max-2,0)]``
    so the net chain a->b gap equals the operator window.
    """
    import re

    sv = _compile_delay(delay_min, delay_max)
    # Start-cycle term references the operator boundaries verbatim.
    assert f"({delay_min} <= 1)" in sv, f"start-term delay_min={delay_min} missing"
    assert f"({delay_max} >= 1)" in sv, f"start-term delay_max={delay_max} missing"
    # Counter term (only present for delay_max>=2) uses the down-shifted bounds.
    if delay_max >= 2:
        cmin = max(delay_min - 2, 0)
        cmax = max(delay_max - 2, 0)
        assert re.search(rf"count_q >= \d+'d{cmin}\b", sv), (
            f"shifted lower bound {cmin} not found for ##[{delay_min}:{delay_max}]"
        )
        assert re.search(rf"count_q <= \d+'d{cmax}\b", sv), (
            f"shifted upper bound {cmax} not found for ##[{delay_min}:{delay_max}]"
        )


def test_delay_zero_special_case() -> None:
    """TEST-06: ##0 emits a combinational pass-through (no counter, pass driven from start)."""
    sv = _compile_delay(0, 0)
    # disable_i gating wraps start: assign pass = disable_i ? 1'b0 : start
    assert "assign pass   = " in sv and "start" in sv, "##0: expected pass driven from start"
    assert "assign active = " in sv and "start" in sv, "##0: expected active driven from start"
    # ##0 should NOT have a counter-based always_ff block with count_q
    assert "count_q" not in sv, "##0: should not have count_q counter register"


def test_delay_single_cycle_fixed() -> None:
    """TEST-06: ##1 is a single-cycle pulse (delay_min == delay_max == 1)."""
    sv = _compile_delay(1, 1)
    assert "delay_min" not in sv, "delay_min param name should not appear in rendered RTL"
    # Fixed single-cycle delay: comparisons both reference value 1
    assert "'d1" in sv, "##1: expected count comparison value 1"


def test_delay_range_window_width() -> None:
    """TEST-06 / BUG-DELAY-01: the counter window is the operator window shifted -2.

    The corrected concat_delay compares count_q against [max(min-2,0), max(max-2,0)]
    (the start-cycle term covers the gap-1 boundary), so the net chain gap spans
    the operator window [min, max].
    """
    import re

    # ##[2:5] -> shifted counter window [0, 3]
    sv25 = _compile_delay(2, 5)
    m_min = re.search(r"count_q >= \d+'d(\d+)", sv25)
    m_max = re.search(r"count_q <= \d+'d(\d+)", sv25)
    assert m_min and int(m_min.group(1)) == 0, "##[2:5]: expected shifted lower bound 0"
    assert m_max and int(m_max.group(1)) == 3, "##[2:5]: expected shifted upper bound 3"

    # ##[0:15] -> shifted counter window [0, 13]
    sv015 = _compile_delay(0, 15)
    m015_min = re.search(r"count_q >= \d+'d(\d+)", sv015)
    m015_max = re.search(r"count_q <= \d+'d(\d+)", sv015)
    assert m015_min and int(m015_min.group(1)) == 0, "##[0:15]: expected shifted lower 0"
    assert m015_max and int(m015_max.group(1)) == 13, "##[0:15]: expected shifted upper 13"


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
    """TEST-06: BV_WIDTH = max_delay_in_consequent + 1 for each boundary case.

    Computed directly via ``_compute_bv_width`` because an implication whose
    consequent yields BV_WIDTH>1 is now rejected at compose time (v1.5 boundary);
    only the width computation that gates that decision is exercised here.
    """
    from sva2rtl.composer import _compute_bv_width
    from sva2rtl.ir import BoolExpr, SeqConcat, SourceLoc

    loc = SourceLoc("test.sv", 1, 1)
    consequent: BoolExpr | SeqConcat
    if delay_min == 0 and delay_max == 0:
        consequent = BoolExpr(text="b", source_loc=loc)
    else:
        consequent = SeqConcat(
            elements=(BoolExpr(text="a", source_loc=loc), BoolExpr(text="b", source_loc=loc)),
            delays=((delay_min, delay_max),),
            source_loc=loc,
        )
    actual = _compute_bv_width(consequent)
    assert actual == expected_bv_width, (
        f"|-> ##[{delay_min}:{delay_max}] b: expected BV_WIDTH={expected_bv_width}, got {actual}"
    )


# ── TEST-02/Phase 1 regression tests ──────────────────────────────────────────


def test_phase1_bool_still_works() -> None:
    """TEST-02: Phase 1 BoolExpr pipeline still produces valid SV with no regression."""
    modules = _compile_fixture(_FIXTURES / "bool_simple.json")
    assert len(modules) >= 1, "Expected at least one module from bool_simple.json"
    for mod_name, sv_text in modules.items():
        assert "module sva_" in sv_text or f"module {mod_name}" in sv_text, (
            f"Module '{mod_name}' does not contain a valid module declaration"
        )
        assert "endmodule" in sv_text, f"Module '{mod_name}' is missing endmodule"


def test_phase1_golden_unchanged() -> None:
    """TEST-02: bool_labeled golden file is byte-for-byte unchanged (Phase 1 regression)."""
    modules = _compile_fixture(_FIXTURES / "bool_labeled.json")
    assert "sva_my_check" in modules, (
        f"Expected 'sva_my_check' in {list(modules.keys())}"
    )
    assert_golden(modules["sva_my_check"], _GOLDEN / "bool_labeled.sv")


# ── End-to-end pipeline tests ──────────────────────────────────────────────────


def test_e2e_delay_fixed_compiles() -> None:
    """TEST-02: delay_fixed.json passes through full import→compose→emit pipeline."""
    modules = _compile_fixture(_FIXTURES / "delay_fixed.json")
    assert len(modules) >= 1, "Expected at least one emitted module"
    for mod_name, sv_text in modules.items():
        assert "module " in sv_text,    f"'{mod_name}': missing module declaration"
        assert "endmodule" in sv_text,  f"'{mod_name}': missing endmodule"


def test_e2e_implication_overlap_compiles() -> None:
    """TEST-02: implication_overlap.json passes through full pipeline, produces hierarchy."""
    modules = _compile_fixture(_FIXTURES / "implication_overlap.json")
    # Hierarchical: at least the top module plus at least one child
    assert len(modules) >= 2, (
        f"Expected hierarchical output (≥ 2 modules), got {list(modules.keys())}"
    )
    for mod_name, sv_text in modules.items():
        assert "module " in sv_text,   f"'{mod_name}': missing module declaration"
        assert "endmodule" in sv_text, f"'{mod_name}': missing endmodule"


def test_e2e_complex_impl_delay_rejected() -> None:
    """TEST-02: PropImplication with a multi-cycle SeqConcat consequent
    (`a |-> ##[2:5] b`) is rejected at compile time.

    This is the sequence-consequent path whose bv_q implementation is a confirmed
    correctness defect (BUG-IMPL-01); a correct implementation needs the v1.5 NFA
    engine. Until then compose must raise rather than emit a wrong monitor.
    """
    from sva2rtl.errors import UnsupportedConstruct
    from sva2rtl.ir import BoolExpr, ClockSpec, PropImplication, SeqConcat, SourceLoc

    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    a_expr = BoolExpr(text="a", source_loc=loc)
    b_expr = BoolExpr(text="b", source_loc=loc)
    seq = SeqConcat(
        elements=(a_expr, b_expr),
        delays=((2, 5),),
        source_loc=loc,
    )
    impl = PropImplication(
        antecedent=a_expr,
        consequent=seq,
        overlapping=True,
        source_loc=loc,
    )
    with pytest.raises(UnsupportedConstruct, match="sequence consequent"):
        compose(impl, clock, "complex_test", "a |-> ##[2:5] b")


# ── Structural soundness tests ─────────────────────────────────────────────────


_PHASE2_FIXTURES = [
    "delay_fixed.json",
    "delay_range.json",
    "implication_overlap.json",
    "implication_nonoverlap.json",
]

_STANDARD_PORT_STRINGS = ["clk", "rst_n", "active", "pass", "fail"]


@pytest.mark.parametrize("fixture_name", _PHASE2_FIXTURES)
def test_all_modules_have_standard_ports(fixture_name: str) -> None:
    """TEST-02: Every emitted module declares the standard monitor port set.

    Required ports: clk, rst_n, active, pass, fail (start is on leaf modules).
    """
    modules = _compile_fixture(_FIXTURES / fixture_name)
    for mod_name, sv_text in modules.items():
        for port in _STANDARD_PORT_STRINGS:
            assert port in sv_text, (
                f"Module '{mod_name}' from {fixture_name} is missing port '{port}'"
            )


@pytest.mark.parametrize("fixture_name", _PHASE2_FIXTURES)
def test_all_modules_have_sync_reset(fixture_name: str) -> None:
    """TEST-02: Every module with sequential logic uses synchronous active-low reset.

    Pure structural wrapper modules (seq_concat_top) have no always_ff and are
    intentionally excluded — only modules that contain always_ff are checked.
    """
    modules = _compile_fixture(_FIXTURES / fixture_name)
    for mod_name, sv_text in modules.items():
        if "always_ff" in sv_text:
            assert "if (!rst_n" in sv_text, (
                f"Module '{mod_name}' from {fixture_name} is missing synchronous rst_n reset"
            )


@pytest.mark.parametrize("fixture_name", _PHASE2_FIXTURES)
def test_no_duplicate_module_names(fixture_name: str) -> None:
    """TEST-02: emit_all returns a dict of unique module names — no duplicate emissions."""
    modules = _compile_fixture(_FIXTURES / fixture_name)
    # dict keys are inherently unique; verify count matches a set
    names = list(modules.keys())
    unique_names = set(names)
    assert len(names) == len(unique_names), (
        f"{fixture_name}: duplicate module names in emit_all output: "
        f"{[n for n in names if names.count(n) > 1]}"
    )
    # Also ensure every module name is a valid SV identifier starting with 'sva_'
    for name in names:
        assert name.startswith("sva_"), (
            f"{fixture_name}: module name '{name}' does not start with 'sva_'"
        )


# ── [REVIEW FIX] Verilator lint gate ──────────────────────────────────────────

_HAS_VERILATOR = shutil.which("verilator") is not None


@pytest.mark.skipif(not _HAS_VERILATOR, reason="verilator not installed")
@pytest.mark.parametrize("fixture_name", _PHASE2_FIXTURES)
def test_verilator_lint_clean(fixture_name: str) -> None:
    """[REVIEW FIX] Verilator lint-only pass: zero errors/warnings on generated RTL.

    Catches undeclared signals, width mismatches, and undriven nets that
    iverilog may miss.  Skipped gracefully when verilator is not installed.

    CI step: verilator --lint-only -Wall output/*.sv
    """
    modules = _compile_fixture(_FIXTURES / fixture_name)
    with tempfile.TemporaryDirectory() as tmpdir:
        sv_files: list[str] = []
        for mod_name, sv_text in modules.items():
            fpath = Path(tmpdir) / f"{mod_name}.sv"
            fpath.write_text(sv_text, encoding="utf-8")
            sv_files.append(str(fpath))

        result = subprocess.run(
            ["verilator", "--lint-only", "-Wall", *sv_files],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Verilator lint failed for {fixture_name}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
