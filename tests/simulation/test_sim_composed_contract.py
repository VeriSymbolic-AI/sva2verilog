"""Dual-simulator regressions for the standard composed-monitor contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    PropIfElse,
    PropNot,
    SeqAnd,
    SeqIntersect,
    SeqOr,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
    SVANode,
)
from tests.simulation.tb_generator import (
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_LOC = SourceLoc("composed_contract.sv", 1, 1)
_CLOCK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(name: str) -> BoolExpr:
    return BoolExpr(text=name, source_loc=_LOC)


def _nodes() -> tuple[tuple[str, SVANode], ...]:
    return (
        ("or", SeqOr(left=_b("a"), right=_b("b"), source_loc=_LOC)),
        ("and", SeqAnd(left=_b("a"), right=_b("b"), source_loc=_LOC)),
        ("intersect", SeqIntersect(left=_b("a"), right=_b("b"), source_loc=_LOC)),
        ("within", SeqWithin(inner=_b("a"), outer=_b("b"), source_loc=_LOC)),
        ("throughout", SeqThroughout(condition=_b("a"), body=_b("b"), source_loc=_LOC)),
        ("not", PropNot(body=_b("a"), source_loc=_LOC)),
        (
            "if_else",
            PropIfElse(
                condition=_b("sel"),
                true_branch=_b("a"),
                false_branch=_b("b"),
                source_loc=_LOC,
            ),
        ),
    )


@pytest.mark.parametrize(("name", "node"), _nodes(), ids=lambda value: str(value))
def test_composed_monitor_reports_external_disable(
    name: str,
    node: SVANode,
    simulator: str,
    tmp_path: Path,
) -> None:
    checker = compose(node, _CLOCK, f"contract_{name}", name)
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    stimulus = [
        {input_name: False for input_name in extra_inputs} | {"disable_i": True},
        {input_name: False for input_name in extra_inputs} | {"disable_i": False},
    ]
    tb = generate_testbench(
        checker.module_name,
        "clk",
        extra_inputs,
        stimulus,
        capture_contract=True,
    )

    trace = run_simulation(
        checker.module_name,
        list(modules.values()),
        tb,
        work_dir=tmp_path,
        simulator=simulator,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
        capture_contract=True,
    )

    assert trace[0]["disabled_o"] is True
    assert trace[0]["active"] is False
    assert trace[0]["pass"] is False
    assert trace[0]["fail"] is False
    assert trace[1]["disabled_o"] is False
