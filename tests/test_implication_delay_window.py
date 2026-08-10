"""Unit contracts for the compact ``##[M:N]`` implication backend."""

from __future__ import annotations

import pytest

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.checker_contract import checker_has_overflow_flag
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolConst,
    BoolExpr,
    BoolIdent,
    CheckerNode,
    ClockSpec,
    PropImplication,
    SeqConcat,
    SourceLoc,
)

_LOC = SourceLoc("implication_delay_window.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(name: str) -> BoolExpr:
    return BoolExpr(
        text=name,
        expr=BoolIdent(name=name, source_loc=_LOC),
        source_loc=_LOC,
    )


def _true() -> BoolExpr:
    return BoolExpr(
        text="1'b1",
        expr=BoolConst(value=1, width=1, signed=False, source_loc=_LOC),
        source_loc=_LOC,
    )


def _build(
    delay_min: int = 1,
    delay_max: int = 3,
    *,
    overlapping: bool = True,
    first: BoolExpr | None = None,
) -> CheckerNode:
    consequent = SeqConcat(
        elements=(first or _true(), _b("ack")),
        delays=((delay_min, delay_max),),
        source_loc=_LOC,
    )
    return compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=consequent,
            overlapping=overlapping,
            source_loc=_LOC,
        ),
        _CLK,
        "delay_window",
        "req |-> ##[1:3] ack",
    )


def test_leading_true_range_selects_compact_backend() -> None:
    checker = _build()
    assert checker.template_name == "implication_delay_window"
    assert checker.children == ()
    assert checker_has_overflow_flag(checker)
    sv = emit(checker)
    assert "logic [MAX_DELAY-1:0] pending_q" in sv
    assert "assign overflow_flag = 1'b0" in sv
    assert "nfa_state" not in sv


def test_nonleading_sequence_stays_on_general_nfa_backend() -> None:
    checker = _build(first=_b("b"))
    assert checker.template_name == "implication_nfa"


def test_exact_one_cycle_window_renders_without_zero_width_vectors() -> None:
    checker = _build(1, 1)
    sv = emit(checker)
    assert "localparam MAX_DELAY = 1" in sv
    assert "localparam [MAX_DELAY-1:0] ELIGIBLE_MASK = 1'b1" in sv
    assert "pending_d[1]" not in sv


def test_compact_backend_has_verilog_2001_compatible_rendering() -> None:
    sv = emit(_build(), verilog_mode=True)
    code = "\n".join(line.split("//", maxsplit=1)[0] for line in sv.splitlines())
    assert "always_ff" not in code
    assert "logic" not in code
    assert "'0" not in code
    assert "reg [MAX_DELAY-1:0] pending_q" in code


def test_hierarchy_oracle_models_specialized_backend_instead_of_zero_trace() -> None:
    checker = _build()
    stimulus = [{"start": cycle == 0, "req": cycle == 0, "ack": cycle == 2} for cycle in range(6)]
    outputs = simulate_checker_hierarchy(checker, stimulus)
    assert [item["pass"] for item in outputs] == [False, False, False, True, False, False]
    assert not any(item["fail"] for item in outputs)


def test_delay_window_rejects_oversized_hardware_before_rendering() -> None:
    with pytest.raises(UnsupportedConstruct, match="requires 33 age bits"):
        _build(1, 33)


def test_general_nfa_preflights_huge_delay_before_transition_materialization() -> None:
    with pytest.raises(UnsupportedConstruct, match="1000002 states"):
        _build(1, 1_000_000, first=_b("b"))


def test_specialized_backend_preserves_reserved_dut_signal_alias() -> None:
    consequent = SeqConcat(
        elements=(_true(), _b("ack")),
        delays=((1, 3),),
        source_loc=_LOC,
    )
    checker = compose(
        PropImplication(
            antecedent=_b("start"),
            consequent=consequent,
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "reserved_delay_window",
        "start |-> ##[1:3] ack",
    )
    assert ("dut_start", "start") in checker.observed_signals
    sv = emit(checker)
    assert "input  logic dut_start," in sv
    assert "assign ant_at_s = start & (dut_start)" in sv


def test_general_nfa_preserves_reserved_dut_signal_alias_across_wrapper() -> None:
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=SeqConcat(
                elements=(_b("disable_i"), _b("b")),
                delays=((2, 2),),
                source_loc=_LOC,
            ),
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "reserved_nfa",
        "req |-> (disable_i ##2 b)",
    )
    assert checker.template_name == "implication_nfa"
    child = checker.children[0]
    assert ("dut_disable_i", "disable_i") in child.observed_signals
    assert ("dut_disable_i", "disable_i") in checker.observed_signals
    modules = emit_all(checker)
    assert "input  logic dut_disable_i," in modules[child.module_name]
    assert ".dut_disable_i(dut_disable_i)" in modules[checker.module_name]
