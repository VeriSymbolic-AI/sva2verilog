"""Integration tests — full pipeline from JSON fixture to emitted SV.

These tests bypass the slang subprocess and exercise:
    ast_importer.import_assertion → normalizer.normalize → composer.compose → emitter.emit

No slang binary is required; all tests use pre-captured JSON fixtures in
``tests/fixtures/``.

Coverage:
- PARSE-05: source location threading from JSON through to emitted comment
- OUT-02: registered (not combinational) outputs
- OUT-03: synchronous reset on all flip-flops
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit
from sva2rtl.ir import BoolExpr
from sva2rtl.normalizer import normalize
from tests.conftest import assert_golden

# ── Fixture paths ─────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = Path(__file__).parent / "golden"


def _load(name: str) -> dict[str, object]:
    """Load a JSON fixture file from ``tests/fixtures/``."""
    return cast(dict[str, object], json.loads((_FIXTURES / name).read_text(encoding="utf-8")))


def _run(name: str) -> str:
    """Run the full pipeline on a JSON fixture and return emitted SV text."""
    ast = _load(name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    return emit(checker)


# ── Test 1: bool_simple unlabeled pipeline ────────────────────────────────


def test_pipeline_bool_simple() -> None:
    """bool_simple.json produces a hash-named SV module with all required elements."""
    sv = _run("bool_simple.json")

    # Unlabeled → hash-based module name
    assert "module sva_prop_" in sv, "Expected hash-based module name for unlabeled assertion"
    assert "always_ff" in sv, "Missing always_ff block"
    assert "attempt_fired" in sv, "Missing attempt_fired port"
    assert "endmodule" in sv


def test_pipeline_bool_simple_golden(golden_dir: Path) -> None:
    """bool_simple.json pipeline output matches tests/golden/bool_simple.sv."""
    sv = _run("bool_simple.json")
    assert_golden(sv, golden_dir / "bool_simple.sv")


# ── Test 2: bool_labeled pipeline ────────────────────────────────────────


def test_pipeline_bool_labeled() -> None:
    """bool_labeled.json produces a label-based SV module name."""
    sv = _run("bool_labeled.json")
    assert "module sva_my_check" in sv, "Expected 'module sva_my_check' for labeled assertion"
    assert "attempt_fired" in sv
    assert "always_ff" in sv


def test_pipeline_bool_labeled_golden(golden_dir: Path) -> None:
    """bool_labeled.json pipeline output matches tests/golden/bool_labeled.sv."""
    sv = _run("bool_labeled.json")
    assert_golden(sv, golden_dir / "bool_labeled.sv")


# ── Test 3: source location threading (PARSE-05) ─────────────────────────


def test_pipeline_source_loc_preserved() -> None:
    """Source location is threaded from JSON through to the emitted header comment.

    Validates PARSE-05: every IR node carries source_loc so error messages
    and generated comments point to the original SVA source.
    """
    ast = _load("bool_simple.json")
    node, _clock, _text, _label = import_assertion(ast)

    # The IR node must carry a meaningful source location
    assert isinstance(node, BoolExpr)
    assert node.source_loc.line > 0, "source_loc.line must be > 0"
    assert node.source_loc.file != "<unknown>", "source_loc.file must not be '<unknown>'"

    # The emitted SV must include the source location in a comment
    checker = compose(node, _clock, _label, _text)
    sv = emit(checker)
    assert "// Source: " in sv, "Missing '// Source: ' comment in emitted SV"
    # The exact file:line:col string from the IR must appear in the emitted SV
    expected_loc = str(node.source_loc)  # e.g. "test_bool.sv:2:3"
    assert expected_loc in sv, f"Source location '{expected_loc}' not found in emitted SV"


# ── Test 4: registered outputs (OUT-02) ───────────────────────────────────


def test_pipeline_registered_outputs() -> None:
    """All outputs are registered — no combinational glitches (OUT-02).

    Verifies that active, pass, fail, and attempt_fired are all driven by
    flip-flops (``*_q`` registers) and not by combinational assigns.
    """
    sv = _run("bool_simple.json")

    # All four _q register names must be declared
    for reg in ("active_q", "pass_q", "fail_q", "attempt_fired_q"):
        assert reg in sv, f"Missing registered signal: {reg}"

    # Outputs are driven from _q registers (via disable_i gating), not from combinational logic
    assert "assign active        = disable_i ? 1'b0 : active_q" in sv
    assert "assign pass          = disable_i ? 1'b0 : pass_q" in sv
    assert "assign fail          = disable_i ? 1'b0 : fail_q" in sv
    assert "assign attempt_fired = attempt_fired_q" in sv

    # Must NOT have direct combinational assign of outputs from inputs
    assert "assign active = start" not in sv, "active must not be combinationally driven"


# ── Test 5: synchronous reset on all FFs (OUT-03) ─────────────────────────


def test_pipeline_sync_reset() -> None:
    """All flip-flops have synchronous active-low reset (OUT-03).

    Verifies that every registered output is cleared to 0 in the
    ``if (!rst_n)`` branch of the always_ff block.
    """
    sv = _run("bool_simple.json")

    # Synchronous reset condition present (combined with disable_i since 3.3.1)
    assert "if (!rst_n" in sv, "Missing 'if (!rst_n' synchronous reset"

    # All four FFs must be explicitly reset to 0
    resets = sv.count("<= 1'b0") + sv.count("<= '0")
    assert resets >= 4, (
        f"Expected at least 4 synchronous reset assignments (<= 1'b0 or <= '0), found {resets}"
    )


# ── Test 6: SequenceConcat is now supported (Phase 2) ───────────────────


def test_pipeline_seq_concat_succeeds() -> None:
    """unsupported_delay.json (a ##1 b) now succeeds — SequenceConcat is Phase 2 supported.

    Validates that the pipeline no longer raises for simple ##N sequences.
    """
    from sva2rtl.emitter import emit_all
    from sva2rtl.ir import SeqConcat

    ast = _load("unsupported_delay.json")
    ir_node, clock, text, label = import_assertion(ast)
    assert isinstance(ir_node, SeqConcat), "Should import as SeqConcat"
    checker = compose(ir_node, clock, label, text)
    modules = emit_all(checker)
    # Should produce multiple module files
    assert len(modules) >= 3  # bool_a, delay, bool_b, top


# ── Test 7: complex expression pipeline ──────────────────────────────────


def test_pipeline_bool_complex() -> None:
    """bool_complex.json ((a && b) || (!c)) produces valid SV with all signals."""
    sv = _run("bool_complex.json")
    assert "module sva_prop_" in sv
    # The complex expression contains logical AND, OR, and NOT
    assert "&&" in sv or "||" in sv
    assert "always_ff" in sv
    assert "attempt_fired" in sv


# ── Test 8: pipeline produces valid module header ─────────────────────────


def test_pipeline_header_comments() -> None:
    """Emitted SV header contains version, source, and original property comments."""
    sv = _run("bool_labeled.json")

    assert "// Generated by sva2rtl" in sv
    assert "// Source:" in sv
    assert "// Original property:" in sv
    assert "@(posedge clk)" in sv


# ── Test 9: standard port contract ───────────────────────────────────────


def test_pipeline_standard_port_contract() -> None:
    """Generated monitor exposes all standard interface ports."""
    sv = _run("bool_simple.json")

    required_ports = ("clk", "rst_n", "start", "active", "pass", "fail", "attempt_fired")
    for port in required_ports:
        assert port in sv, f"Missing required port: {port}"


# ── Test 10: observed signals become input ports ──────────────────────────


def test_pipeline_observed_signals_as_ports() -> None:
    """Signals extracted from the boolean expression appear as input logic ports."""
    sv = _run("bool_simple.json")

    # bool_simple has 'a' and 'b' in the expression
    assert "input  logic a" in sv, "Signal 'a' must appear as 'input  logic a'"
    assert "input  logic b" in sv, "Signal 'b' must appear as 'input  logic b'"


# ═══════════════════════════════════════════════════════════════════════════════
# v1.3 Tier 2 operator pipeline tests
# ═══════════════════════════════════════════════════════════════════════════════


def test_pipeline_v13_seq_or() -> None:
    """v13_or_seq.json: full pipeline emits valid SV for prop_or."""
    sv = _run("v13_or_seq.json")
    assert "module" in sv and "endmodule" in sv
    assert "always_ff" in sv
    assert "active_q" in sv


def test_pipeline_v13_seq_and() -> None:
    """v13_and_seq.json: full pipeline emits valid SV for prop_and with matched regs."""
    sv = _run("v13_and_seq.json")
    assert "module" in sv and "endmodule" in sv
    assert "left_matched_q" in sv, "prop_and must have left_matched_q register"
    assert "right_matched_q" in sv, "prop_and must have right_matched_q register"


def test_pipeline_v13_intersect() -> None:
    """v13_intersect_seq.json: full pipeline emits valid SV for prop_intersect."""
    sv = _run("v13_intersect_seq.json")
    assert "module" in sv and "endmodule" in sv
    assert "always_ff" in sv


def test_pipeline_v13_prop_not() -> None:
    """v13_prop_not.json: full pipeline emits valid SV for prop_not (inverts pass/fail)."""
    sv = _run("v13_prop_not.json")
    assert "module" in sv and "endmodule" in sv
    assert "always_ff" in sv


def test_pipeline_v13_throughout() -> None:
    """v13_throughout_seq.json: full pipeline for prop_throughout with explicit cond wiring."""
    sv = _run("v13_throughout_seq.json")
    assert "module" in sv and "endmodule" in sv
    assert "_cond_start" in sv, "throughout must drive _cond_start = start | body_active"


def test_pipeline_v13_if_else() -> None:
    """v13_if_else_prop.json: full pipeline emits valid SV for prop_if_else."""
    sv = _run("v13_if_else_prop.json")
    assert "module" in sv and "endmodule" in sv
    assert "has_else" not in sv or "always_ff" in sv  # has_else is a param, may appear
