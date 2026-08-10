"""Independent cycle-accurate regressions for NFA lowering defects.

These tests deliberately do not use ``simulate_checker_hierarchy`` as an
oracle: that simulator consumes the transition table produced by the composer
and therefore cannot detect a wrong transition table.  Expected vectors below
are derived directly from the source-level sequence timing and must agree under
both supported RTL simulators.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import (
    BoolConst,
    BoolExpr,
    BoolIdent,
    CheckerNode,
    ClockSpec,
    PropImplication,
    SeqAnd,
    SeqConcat,
    SeqOr,
    SeqRepetition,
    SeqWithin,
    SourceLoc,
)
from tests.simulation.tb_generator import (
    checker_has_overflow_flag,
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_LOC = SourceLoc("nfa_semantic_regressions.sv", 1, 1)
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


def _seq(left: str, right: str, delay: int) -> SeqConcat:
    return SeqConcat(
        elements=(_b(left), _b(right)),
        delays=((delay, delay),),
        source_loc=_LOC,
    )


def _c3() -> SeqRepetition:
    return SeqRepetition(expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC)


def _run(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str,
) -> list[dict[str, bool]]:
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    has_overflow = checker_has_overflow_flag(checker)
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=checker.params["clock_signal"],
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=has_overflow,
    )
    return run_simulation(
        checker.module_name,
        list(modules.values()),
        tb,
        work_dir=tmp_path,
        has_overflow_flag=has_overflow,
        simulator=simulator,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
    )


def _bits(outputs: list[dict[str, bool]], name: str) -> list[bool]:
    return [bool(output.get(name, False)) for output in outputs]


@pytest.mark.parametrize(
    ("ack_offset", "pass_index", "fail_index"),
    [(1, 2, None), (2, 3, None), (3, 4, None), (4, None, 4)],
)
def test_ranged_delay_enforces_every_window_boundary(
    tmp_path: Path,
    simulator: str,
    ack_offset: int,
    pass_index: int | None,
    fail_index: int | None,
) -> None:
    """``req |-> ##[1:3] ack`` accepts 1..3 and rejects the +4 boundary."""
    consequent = SeqConcat(
        elements=(_true(), _b("ack")),
        delays=((1, 3),),
        source_loc=_LOC,
    )
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=consequent,
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "range_lower_bound",
        "req |-> ##[1:3] ack",
    )
    stimulus = [
        {
            "start": cycle == 0,
            "req": cycle == 0,
            "ack": cycle == ack_offset,
        }
        for cycle in range(6)
    ]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    expected_pass = [False] * len(stimulus)
    expected_fail = [False] * len(stimulus)
    if pass_index is not None:
        expected_pass[pass_index] = True
    if fail_index is not None:
        expected_fail[fail_index] = True
    assert _bits(outputs, "pass") == expected_pass
    assert _bits(outputs, "fail") == expected_fail


def test_specialized_window_does_not_accept_before_nontrivial_lower_bound(
    tmp_path: Path, simulator: str
) -> None:
    """An ACK at +1 is too early for ``##[2:3]`` and cannot retire the attempt."""
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=SeqConcat(
                elements=(_true(), _b("ack")),
                delays=((2, 3),),
                source_loc=_LOC,
            ),
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "range_lower_bound_two",
        "req |-> ##[2:3] ack",
    )
    stimulus = [{"start": cycle == 0, "req": cycle == 0, "ack": cycle == 1} for cycle in range(6)]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert _bits(outputs, "pass") == [False] * 6
    assert _bits(outputs, "fail") == [False, False, False, False, True, False]


def test_delay_window_handles_continuous_overlapping_attempts_without_overflow(
    tmp_path: Path, simulator: str
) -> None:
    """One ACK retires all eligible attempts; a same-cycle new attempt remains pending."""
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=SeqConcat(
                elements=(_true(), _b("ack")),
                delays=((1, 3),),
                source_loc=_LOC,
            ),
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "range_overlap_capacity",
        "req |-> ##[1:3] ack",
    )
    stimulus = [
        {
            "start": cycle in {0, 1, 2},
            "req": cycle in {0, 1, 2},
            "ack": cycle == 2,
        }
        for cycle in range(8)
    ]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert checker.template_name == "implication_delay_window"
    assert _bits(outputs, "pass") == [False, False, False, True, False, False, False, False]
    assert _bits(outputs, "fail") == [False, False, False, False, False, False, True, False]
    assert not any(_bits(outputs, "overflow"))


def test_nonoverlap_delay_window_begins_one_cycle_after_antecedent(
    tmp_path: Path, simulator: str
) -> None:
    """``|=> ##1`` must not accidentally collapse to overlapping ``|-> ##1`` timing."""
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=SeqConcat(
                elements=(_true(), _b("ack")),
                delays=((1, 3),),
                source_loc=_LOC,
            ),
            overlapping=False,
            source_loc=_LOC,
        ),
        _CLK,
        "range_nonoverlap",
        "req |=> ##[1:3] ack",
    )
    stimulus = [{"start": cycle == 0, "req": cycle == 0, "ack": cycle == 2} for cycle in range(7)]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert checker.template_name == "implication_delay_window"
    assert _bits(outputs, "pass") == [False, False, False, True, False, False, False]
    assert not any(_bits(outputs, "fail"))


def test_nested_or_samples_short_branch_on_start_cycle(
    tmp_path: Path,
    simulator: str,
) -> None:
    """The NFA union fork must not consume a cycle before checking ``b``."""
    consequent = SeqOr(
        left=_b("b"),
        right=_seq("x", "y", 2),
        source_loc=_LOC,
    )
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=consequent,
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "or_start_cycle",
        "req |-> (b or (x ##2 y))",
    )
    stimulus = [
        {"start": True, "req": True, "b": True, "x": False, "y": False},
        {"start": False, "req": False, "b": False, "x": False, "y": False},
        {"start": False, "req": False, "b": False, "x": False, "y": False},
    ]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert _bits(outputs, "pass") == [False, True, False]
    assert not any(_bits(outputs, "fail"))


def test_within_allows_late_inner_and_finishes_with_outer(
    tmp_path: Path,
    simulator: str,
) -> None:
    """``a within c[*3]`` starts ``a`` at t+1 and ends with ``c[*3]``."""
    checker = compose(
        SeqWithin(inner=_b("a"), outer=_c3(), source_loc=_LOC),
        _CLK,
        "within_late_inner",
        "a within c[*3]",
    )
    stimulus = [
        {"start": True, "a": False, "c": True},
        {"start": False, "a": True, "c": True},
        {"start": False, "a": False, "c": True},
        {"start": False, "a": False, "c": False},
        {"start": False, "a": False, "c": False},
    ]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert _bits(outputs, "pass") == [False, False, False, True, False]


def test_multicycle_and_finishes_at_later_endpoint(
    tmp_path: Path,
    simulator: str,
) -> None:
    """An early ``a`` completion is remembered until ``x ##2 y`` completes."""
    checker = compose(
        SeqAnd(left=_b("a"), right=_seq("x", "y", 2), source_loc=_LOC),
        _CLK,
        "and_later_endpoint",
        "a and (x ##2 y)",
    )
    stimulus = [
        {"start": True, "a": True, "x": True, "y": False},
        {"start": False, "a": False, "x": False, "y": False},
        {"start": False, "a": False, "x": False, "y": True},
        {"start": False, "a": False, "x": False, "y": False},
        {"start": False, "a": False, "x": False, "y": False},
    ]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert checker.template_name == "nfa_generic"
    assert _bits(outputs, "pass") == [False, False, False, True, False]


def test_nested_within_consequent_lowers_without_router_crash(
    tmp_path: Path,
    simulator: str,
) -> None:
    """A documented NFA-liftable consequent must not fall into primitive-only lowering."""
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=SeqWithin(inner=_b("a"), outer=_c3(), source_loc=_LOC),
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "implication_within",
        "req |-> (a within c[*3])",
    )
    stimulus = [
        {"start": True, "req": True, "a": False, "c": True},
        {"start": False, "req": False, "a": True, "c": True},
        {"start": False, "req": False, "a": False, "c": True},
        {"start": False, "req": False, "a": False, "c": False},
        {"start": False, "req": False, "a": False, "c": False},
    ]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert checker.template_name == "implication_nfa"
    assert _bits(outputs, "pass") == [False, False, False, True, False]
    assert not any(_bits(outputs, "fail"))


def test_unsatisfied_within_fails_at_outer_endpoint(
    tmp_path: Path,
    simulator: str,
) -> None:
    """A terminal non-accept state must not delay failure by another cycle."""
    checker = compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=SeqWithin(inner=_b("a"), outer=_c3(), source_loc=_LOC),
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "implication_within_fail",
        "req |-> (a within c[*3])",
    )
    stimulus = [
        {"start": True, "req": True, "a": False, "c": True},
        {"start": False, "req": False, "a": False, "c": True},
        {"start": False, "req": False, "a": False, "c": True},
        {"start": False, "req": False, "a": False, "c": False},
        {"start": False, "req": False, "a": False, "c": False},
    ]

    outputs = _run(checker, stimulus, tmp_path, simulator)

    assert _bits(outputs, "pass") == [False, False, False, False, False]
    assert _bits(outputs, "fail") == [False, False, False, True, False]
