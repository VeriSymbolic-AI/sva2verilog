"""Dual-simulator regression for packed-vector boolean expressions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all, observed_signal_widths
from sva2rtl.ir import BoolCompare, BoolConst, BoolExpr, BoolIdent, ClockSpec, SourceLoc
from tests.simulation.tb_generator import (
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation


def test_vector_equality_matches_oracle_on_selected_simulator(
    tmp_path: Path,
    simulator: str,
) -> None:
    """A 4-bit comparison must distinguish 3 from non-equal nonzero values."""
    loc = SourceLoc("vector_bool.sv", 1, 1)
    semantic = BoolCompare(
        op="eq",
        left=BoolIdent(name="data", width=4, source_loc=loc),
        right=BoolConst(value=3, width=4, raw="4'b0011", source_loc=loc),
        source_loc=loc,
    )
    checker = compose(
        BoolExpr(text="data == 4'b0011", expr=semantic, source_loc=loc),
        ClockSpec(edge="posedge", signal="clk", source_loc=loc),
        "vector_eq",
        "data == 4'b0011",
    )
    stimulus: list[dict[str, Any]] = [
        {"start": True, "data": 3},
        {"start": True, "data": 7},
        {"start": True, "data": 0},
        {"start": False, "data": 3},
    ]
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    widths = observed_signal_widths(checker)
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal="clk",
        extra_inputs=extra_inputs,
        input_widths=widths,
        stimulus=stimulus,
    )

    rtl = run_simulation(
        simulator=simulator,
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
    )
    oracle = simulate_checker_hierarchy(checker, stimulus)

    assert [row["pass"] for row in rtl] == [row["pass"] for row in oracle]
    assert [row["fail"] for row in rtl] == [row["fail"] for row in oracle]
