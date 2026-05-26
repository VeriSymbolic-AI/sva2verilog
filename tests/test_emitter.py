"""Unit tests for src/sva2rtl/emitter.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl import __version__
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all, write_output, write_output_dir
from sva2rtl.ir import CheckerNode, SourceLoc

# ── Helpers ───────────────────────────────────────────────────────────────


def _make_loc(file: str = "test.sv", line: int = 3, col: int = 5) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _labeled_checker() -> CheckerNode:
    """Return the CheckerNode that should match tests/golden/bool_labeled.sv.

    The source location matches the ConcurrentAssertion position in
    tests/fixtures/bool_labeled.json so that the integration golden comparison
    and the emitter unit test both use the same reference.
    """
    loc = _make_loc(file="test_labeled.sv", line=2, col=14)
    return CheckerNode(
        template_name="bool_expr",
        module_name="sva_my_check",
        params={
            "module_name": "sva_my_check",
            "bool_expr": "(a && b)",
            "clock_signal": "clk",
            "clock_edge": "posedge",
            "source_loc": str(loc),
            "sva2rtl_version": __version__,
            "original_text": "(a && b)",
        },
        observed_signals=(("a", "a"), ("b", "b")),
        source_loc=loc,
        children=(),
    )


# ── emit ──────────────────────────────────────────────────────────────────


def test_emit_bool_simple() -> None:
    """emit() returns a non-empty string for a simple bool checker."""
    checker = _labeled_checker()
    result = emit(checker)
    assert isinstance(result, str)
    assert len(result) > 0


def test_emit_contains_module_name() -> None:
    """Emitted SV contains 'module sva_my_check'."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "module sva_my_check" in result


def test_emit_contains_reset() -> None:
    """Emitted SV contains synchronous reset 'if (!rst_n)'."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "if (!rst_n)" in result


def test_emit_contains_bool_expr() -> None:
    """Emitted SV contains the boolean expression text."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "(a && b)" in result


def test_emit_all_ports_present() -> None:
    """Emitted SV contains all required standard output ports."""
    checker = _labeled_checker()
    result = emit(checker)
    for port in ("active", "pass", "fail", "attempt_fired"):
        assert port in result, f"Missing required port: {port}"


def test_emit_contains_clock_signal() -> None:
    """Emitted SV contains the clock signal name."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "clk" in result


def test_emit_contains_always_ff() -> None:
    """Emitted SV contains an 'always_ff' block for registered outputs."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "always_ff" in result


def test_emit_contains_attempt_fired_sticky() -> None:
    """Emitted SV contains the sticky attempt_fired accumulator logic."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "attempt_fired_q | start" in result


def test_emit_ends_with_newline() -> None:
    """Emitted SV text ends with exactly one newline (tool compliance)."""
    checker = _labeled_checker()
    result = emit(checker)
    assert result.endswith("\n")


def test_emit_contains_endmodule() -> None:
    """Emitted SV contains 'endmodule'."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "endmodule" in result


def test_emit_contains_observed_signals_as_ports() -> None:
    """Emitted SV lists each observed signal as an 'input logic' port."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "input  logic a" in result
    assert "input  logic b" in result


def test_emit_contains_version_comment() -> None:
    """Header comment includes the sva2rtl version string."""
    checker = _labeled_checker()
    result = emit(checker)
    assert f"sva2rtl {__version__}" in result


def test_emit_contains_source_loc_comment() -> None:
    """Header comment includes the source location (matches bool_labeled.json fixture)."""
    checker = _labeled_checker()
    result = emit(checker)
    assert "test_labeled.sv:2:14" in result


def test_emit_golden_match() -> None:
    """emit() output matches tests/golden/bool_labeled.sv line-by-line."""
    checker = _labeled_checker()
    result = emit(checker)
    golden_path = Path(__file__).parent / "golden" / "bool_labeled.sv"
    golden = golden_path.read_text(encoding="utf-8")

    def norm(s: str) -> list[str]:
        """Strip trailing whitespace per line for whitespace-insensitive compare."""
        return [line.rstrip() for line in s.splitlines()]

    assert norm(result) == norm(golden)


def test_emit_negedge_clock() -> None:
    """Emitted SV correctly reflects a negedge clock spec."""
    loc = _make_loc()
    checker = CheckerNode(
        template_name="bool_expr",
        module_name="sva_neg_test",
        params={
            "module_name": "sva_neg_test",
            "bool_expr": "req",
            "clock_signal": "sys_clk",
            "clock_edge": "negedge",
            "source_loc": str(loc),
            "sva2rtl_version": __version__,
            "original_text": "req",
        },
        observed_signals=(("req", "req"),),
        source_loc=loc,
        children=(),
    )
    result = emit(checker)
    assert "negedge sys_clk" in result
    assert "module sva_neg_test" in result


# ── write_output ──────────────────────────────────────────────────────────


def test_write_output_to_file(tmp_path: Path) -> None:
    """write_output() writes the correct content to the specified file."""
    checker = _labeled_checker()
    sv = emit(checker)
    out_file = tmp_path / "sub" / "output.sv"
    write_output(sv, out_file)
    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == sv


def test_write_output_creates_parent_dirs(tmp_path: Path) -> None:
    """write_output() creates intermediate directories that do not yet exist."""
    checker = _labeled_checker()
    sv = emit(checker)
    out_file = tmp_path / "a" / "b" / "c" / "out.sv"
    write_output(sv, out_file)
    assert out_file.exists()


def test_write_output_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """write_output(sv, None) writes the SV text to stdout."""
    checker = _labeled_checker()
    sv = emit(checker)
    write_output(sv, None)
    captured = capsys.readouterr()
    assert captured.out == sv


# ── Helpers for SeqConcat / delay tests ──────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"


def _load_fixture_checker(fixture_name: str) -> CheckerNode:
    """Load a fixture JSON, run import_assertion + compose, return CheckerNode."""
    ast = json.loads((FIXTURES_DIR / f"{fixture_name}.json").read_text(encoding="utf-8"))
    ir_node, clock, original_text, label = import_assertion(ast)
    return compose(ir_node, clock, label, original_text)


# ── emit_all ─────────────────────────────────────────────────────────────────


def test_emit_all_delay_fixed_returns_dict() -> None:
    """emit_all() returns a dict for a ##3 fixture."""
    checker = _load_fixture_checker("delay_fixed")
    result = emit_all(checker)
    assert isinstance(result, dict)
    assert len(result) > 0


def test_emit_all_delay_fixed_module_names() -> None:
    """emit_all() for a ##3 property yields exactly the 4 expected module names."""
    checker = _load_fixture_checker("delay_fixed")
    result = emit_all(checker)
    assert set(result.keys()) == {
        "sva_prop_81cf66e0_e0",
        "sva_delay_3_3",
        "sva_prop_81cf66e0_e1",
        "sva_prop_81cf66e0",
    }


def test_emit_all_delay_fixed_order_children_before_parent() -> None:
    """emit_all() for ##3 emits child modules before the parent wrapper."""
    checker = _load_fixture_checker("delay_fixed")
    result = emit_all(checker)
    keys = list(result.keys())
    assert keys.index("sva_prop_81cf66e0") > keys.index("sva_delay_3_3")
    assert keys.index("sva_prop_81cf66e0") > keys.index("sva_prop_81cf66e0_e0")


def test_emit_all_delay_range_module_names() -> None:
    """emit_all() for a ##[2:5] property yields exactly the 4 expected module names."""
    checker = _load_fixture_checker("delay_range")
    result = emit_all(checker)
    assert set(result.keys()) == {
        "sva_prop_e9edaa37_e0",
        "sva_delay_2_5",
        "sva_prop_e9edaa37_e1",
        "sva_prop_e9edaa37",
    }


def test_emit_all_delay_zero_has_combinational_pass() -> None:
    """emit_all() for a ##0 property generates a module with combinational pass-through."""
    checker = _load_fixture_checker("delay_zero")
    result = emit_all(checker)
    delay_mod = result.get("sva_delay_0_0", "")
    assert "assign pass   = start" in delay_mod


def test_emit_all_delay_three_element_six_modules() -> None:
    """emit_all() for a ##1 b ##2 c yields 6 modules (3 bool + 2 delay + 1 top)."""
    checker = _load_fixture_checker("delay_three_element")
    result = emit_all(checker)
    assert len(result) == 6


def test_emit_all_delay_three_element_module_names() -> None:
    """emit_all() for a ##1 b ##2 c yields the 6 expected module names."""
    checker = _load_fixture_checker("delay_three_element")
    result = emit_all(checker)
    assert set(result.keys()) == {
        "sva_prop_5c9caf75_e0",
        "sva_delay_1_1",
        "sva_prop_5c9caf75_e1",
        "sva_delay_2_2",
        "sva_prop_5c9caf75_e2",
        "sva_prop_5c9caf75",
    }


def test_emit_all_delay_fixed_cnt_width_in_delay_module() -> None:
    """Delay module for ##3 uses CNT_WIDTH=2 (ceil(log2(4))=2)."""
    checker = _load_fixture_checker("delay_fixed")
    result = emit_all(checker)
    delay_sv = result["sva_delay_3_3"]
    assert "CNT_WIDTH = 2" in delay_sv


def test_emit_all_delay_range_cnt_width_in_delay_module() -> None:
    """Delay module for ##[2:5] uses CNT_WIDTH=3 (ceil(log2(6))=3)."""
    checker = _load_fixture_checker("delay_range")
    result = emit_all(checker)
    delay_sv = result["sva_delay_2_5"]
    assert "CNT_WIDTH = 3" in delay_sv


def test_emit_all_top_instantiates_delay_child() -> None:
    """Top wrapper for ##3 instantiates sva_delay_3_3 by name."""
    checker = _load_fixture_checker("delay_fixed")
    result = emit_all(checker)
    top_sv = result["sva_prop_81cf66e0"]
    assert "sva_delay_3_3 u_sva_delay_3_3" in top_sv


def test_emit_all_top_token_passing_chain() -> None:
    """Top wrapper passes w_pass_0 as start to the second child."""
    checker = _load_fixture_checker("delay_fixed")
    result = emit_all(checker)
    top_sv = result["sva_prop_81cf66e0"]
    assert ".start    (w_pass_0)" in top_sv


def test_emit_all_top_final_pass_is_last_child() -> None:
    """Top wrapper assigns pass from the last child's wire (w_pass_2)."""
    checker = _load_fixture_checker("delay_fixed")
    result = emit_all(checker)
    top_sv = result["sva_prop_81cf66e0"]
    assert "assign pass   = w_pass_2" in top_sv


# ── Golden comparisons for delay modules ─────────────────────────────────────


def _norm(text: str) -> list[str]:
    """Strip trailing whitespace per line for whitespace-insensitive comparison."""
    return [line.rstrip() for line in text.splitlines()]


@pytest.mark.parametrize(
    "fixture_name,golden_module",
    [
        ("delay_fixed", "sva_delay_3_3"),
        ("delay_fixed", "sva_prop_81cf66e0"),
        ("delay_range", "sva_delay_2_5"),
        ("delay_range", "sva_prop_e9edaa37"),
        ("delay_zero", "sva_delay_0_0"),
        ("delay_zero", "sva_prop_75080d6b"),
        ("delay_three_element", "sva_delay_1_1"),
        ("delay_three_element", "sva_delay_2_2"),
        ("delay_three_element", "sva_prop_5c9caf75"),
    ],
)
def test_emit_all_golden_match(fixture_name: str, golden_module: str) -> None:
    """emit_all() output matches the corresponding golden SV file."""
    checker = _load_fixture_checker(fixture_name)
    result = emit_all(checker)
    actual = result[golden_module]
    golden_path = GOLDEN_DIR / f"{golden_module}.sv"
    expected = golden_path.read_text(encoding="utf-8")
    assert _norm(actual) == _norm(expected), (
        f"Golden mismatch for {golden_module}:\n"
        f"First differing lines detected — regenerate golden with emit_all()."
    )


# ── write_output_dir ─────────────────────────────────────────────────────────


def test_write_output_dir_creates_files(tmp_path: Path) -> None:
    """write_output_dir() creates one .sv file per module in the output dir."""
    checker = _load_fixture_checker("delay_fixed")
    modules = emit_all(checker)
    write_output_dir(modules, tmp_path)
    for mod_name in modules:
        assert (tmp_path / f"{mod_name}.sv").exists()


def test_write_output_dir_file_contents(tmp_path: Path) -> None:
    """write_output_dir() writes the correct SV text to each file."""
    checker = _load_fixture_checker("delay_fixed")
    modules = emit_all(checker)
    write_output_dir(modules, tmp_path)
    for mod_name, sv_text in modules.items():
        actual = (tmp_path / f"{mod_name}.sv").read_text(encoding="utf-8")
        assert actual == sv_text


def test_write_output_dir_creates_dir_if_missing(tmp_path: Path) -> None:
    """write_output_dir() creates the output directory if it does not exist."""
    checker = _load_fixture_checker("delay_range")
    modules = emit_all(checker)
    new_dir = tmp_path / "out" / "nested"
    write_output_dir(modules, new_dir)
    assert new_dir.is_dir()
    assert len(list(new_dir.iterdir())) == len(modules)


# ── Implication (|-> and |=>) emitter tests ───────────────────────────────


def _load_impl_checker(fixture_name: str) -> "CheckerNode":
    """Load an implication fixture and return its top CheckerNode."""
    return _load_fixture_checker(fixture_name)


def test_emit_overlap_bitvec_contains_overflow_flag() -> None:
    """Emitted overlap_bitvec module contains 'overflow_flag' output port."""
    checker = _load_impl_checker("implication_overlap")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "overflow_flag" in top_sv


def test_emit_overlap_bitvec_contains_bv_register() -> None:
    """Emitted overlap_bitvec module contains 'bv_q' shift register."""
    checker = _load_impl_checker("implication_overlap")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "bv_q" in top_sv


def test_emit_overlap_bitvec_contains_halt_gating() -> None:
    """Emitted overlap_bitvec module gates active/pass/fail to 0 when halted."""
    checker = _load_impl_checker("implication_overlap")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    # The halt gating pattern: overflow_flag_q ? 1'b0 : ...
    assert "overflow_flag_q ? 1'b0" in top_sv


def test_emit_overlap_bitvec_contains_endmodule() -> None:
    """Emitted overlap_bitvec module ends with 'endmodule'."""
    checker = _load_impl_checker("implication_overlap")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "endmodule" in top_sv


def test_emit_overlap_bitvec_bv_width_param() -> None:
    """Emitted overlap_bitvec module for 'a |-> b' has BV_WIDTH = 1."""
    checker = _load_impl_checker("implication_overlap")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "BV_WIDTH = 1" in top_sv


def test_emit_nonoverlap_contains_delay_register() -> None:
    """Emitted nonoverlap module contains 'ant_pass_delayed_q' 1-cycle register."""
    checker = _load_impl_checker("implication_nonoverlap")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "ant_pass_delayed" in top_sv


def test_emit_nonoverlap_contains_overflow_flag() -> None:
    """Emitted nonoverlap module contains 'overflow_flag' output."""
    checker = _load_impl_checker("implication_nonoverlap")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "overflow_flag" in top_sv


def test_emit_bitvec_impl_bv_width_six() -> None:
    """Emitted bitvec implication module for 'a |-> a ##[2:5] b' has BV_WIDTH = 6."""
    checker = _load_impl_checker("implication_bitvec")
    modules = emit_all(checker)
    top_sv = modules[checker.module_name]
    assert "BV_WIDTH = 6" in top_sv


def test_emit_all_implication_overlap_module_count() -> None:
    """emit_all for 'a |-> b' returns at least 2 modules (top + children)."""
    checker = _load_impl_checker("implication_overlap")
    modules = emit_all(checker)
    assert len(modules) >= 2


def test_emit_all_implication_bitvec_module_count() -> None:
    """emit_all for 'a |-> a ##[2:5] b' returns at least 2 modules (top + child)."""
    checker = _load_impl_checker("implication_bitvec")
    modules = emit_all(checker)
    assert len(modules) >= 2


# ── Golden comparisons for implication modules ───────────────────────────────


@pytest.mark.parametrize(
    "fixture_name,golden_file,module_key_attr",
    [
        ("implication_overlap", "overlap_impl", "module_name"),
        ("implication_nonoverlap", "nonoverlap_impl", "module_name"),
        ("implication_bitvec", "sva_bitvec_impl", "module_name"),
    ],
)
def test_emit_implication_golden_match(
    fixture_name: str, golden_file: str, module_key_attr: str
) -> None:
    """emit_all() for implication fixtures matches corresponding golden SV files."""
    checker = _load_fixture_checker(fixture_name)
    modules = emit_all(checker)
    module_key = getattr(checker, module_key_attr)
    actual = modules[module_key]
    golden_path = GOLDEN_DIR / f"{golden_file}.sv"
    expected = golden_path.read_text(encoding="utf-8")
    assert _norm(actual) == _norm(expected), (
        f"Golden mismatch for {golden_file}:\n"
        f"Regenerate golden with emit_all() and save to tests/golden/{golden_file}.sv"
    )
