"""Focused semantic boundaries for mutation-sensitive composer helpers."""

from __future__ import annotations

import pytest

from sva2rtl.composer import (
    _emit_nfa_checker,
    _lift_to_nfa,
    _nfa_reachable_states,
    _render_multi_state_d_body,
    _render_state_d_body,
    _try_lift_operand,
    compose,
)
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    ClockedSeq,
    ClockSpec,
    PropBoundedAlways,
    PropImplication,
    SeqConcat,
    SeqIntersect,
    SeqThroughout,
    SeqWithin,
    SignalFunc,
    SourceLoc,
)

_LOC = SourceLoc("composer_boundaries.sv", 1, 1)


def _bool(name: str) -> BoolExpr:
    return BoolExpr(text=name, source_loc=_LOC)


def test_same_domain_concat_delay_preserves_negedge_clock() -> None:
    node = SeqConcat(
        elements=(_bool("a"), _bool("b")),
        delays=((2, 2),),
        source_loc=_LOC,
    )

    checker = compose(
        node,
        ClockSpec(edge="negedge", signal="clk", source_loc=_LOC),
        "negative_edge_delay",
        "a ##2 b",
    )

    delay_child = next(child for child in checker.children if child.template_name == "concat_delay")
    assert delay_child.params["clock_edge"] == "negedge"


def test_ranged_delay_nfa_transitions_stay_in_bounds_and_keep_earliest_exit() -> None:
    node = SeqConcat(
        elements=(_bool("a"), _bool("b")),
        delays=((2, 4),),
        source_loc=_LOC,
    )

    states, transitions, accept, _signals = _lift_to_nfa(node)

    assert accept == frozenset({5})
    assert all(0 <= source < states and 0 <= target < states for source, _, target in transitions)
    assert (2, "(b)", 5) in transitions
    assert (3, "(b)", 5) in transitions
    assert (4, "(b)", 5) in transitions


def test_zero_lower_bound_nfa_fuses_same_cycle_without_extra_edge() -> None:
    node = SeqConcat(
        elements=(_bool("a"), _bool("b")),
        delays=((0, 2),),
        source_loc=_LOC,
    )

    states, transitions, accept, _signals = _lift_to_nfa(node)

    assert states == 4
    assert accept == frozenset({3})
    assert (0, "((a)) & ((b))", 3) in transitions
    assert (1, "(b)", 3) in transitions
    assert (2, "(b)", 3) in transitions


def test_nfa_renderers_emit_zero_for_states_without_incoming_arcs() -> None:
    transitions = ((0, "a", 1),)

    single = _render_state_d_body(3, transitions)
    multi = _render_multi_state_d_body(3, transitions, 2)

    assert "assign state_d[0] = 1'b0;" in single
    assert "assign state_d[2] = 1'b0;" in single
    assert "assign state_d[3] = 1'b0;" in multi
    assert "assign state_d[5] = 1'b0;" in multi
    assert not multi.endswith("\n")


def test_nfa_reachability_requires_a_connected_source() -> None:
    transitions = ((0, "a", 1), (1, "b", 2), (4, "c", 3))

    assert _nfa_reachable_states(5, transitions) == frozenset({0, 1, 2})


def test_nfa_emitter_adds_multi_slot_logic_only_when_needed() -> None:
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)
    arguments = (
        "boundary",
        2,
        ((0, "a", 1),),
        frozenset({1}),
        ("a",),
        "sequence",
        clock,
        "nfa_boundary",
        "a",
        _LOC,
        None,
    )

    single = _emit_nfa_checker(*arguments, thread_slots=1)
    multi = _emit_nfa_checker(*arguments, thread_slots=2)

    assert "nfa_state_d_body_multi" not in single.params
    assert "nfa_state_d_body_multi" in multi.params


def test_bounded_always_positive_upper_bound_sizes_counter() -> None:
    checker = compose(
        PropBoundedAlways(body=_bool("a"), lo=1, hi=8, strong=True, source_loc=_LOC),
        ClockSpec(edge="posedge", signal="clk", source_loc=_LOC),
        "bounded_always_width",
        "s_always [1:8] a",
    )

    assert checker.params["cnt_width"] == "4"


def test_multiclock_delay_before_switch_preserves_root_negedge() -> None:
    root_clock = ClockSpec(edge="negedge", signal="clk1", source_loc=_LOC)
    switched = ClockedSeq(
        clock=ClockSpec(edge="posedge", signal="clk2", source_loc=_LOC),
        body=_bool("b"),
        source_loc=_LOC,
    )
    node = SeqConcat(
        elements=(_bool("a"), switched),
        delays=((1, 1),),
        source_loc=_LOC,
    )

    checker = compose(node, root_clock, "multiclock_negedge", "a ##1 @(posedge clk2) b")
    first_delay = next(
        child for child in checker.children if child.template_name == "concat_delay"
    )

    assert first_delay.params["clock_signal"] == "clk1"
    assert first_delay.params["clock_edge"] == "negedge"


def test_implication_nfa_thread_allocator_never_expands_past_four_slots() -> None:
    consequence = SeqConcat(
        elements=(_bool("b"), _bool("c")),
        delays=((2, 2),),
        source_loc=_LOC,
    )
    node = PropImplication(
        antecedent=_bool("a"),
        consequent=consequence,
        overlapping=True,
        source_loc=_LOC,
    )

    checker = compose(
        node,
        ClockSpec(edge="posedge", signal="clk", source_loc=_LOC),
        "thread_budget",
        "a |-> b ##2 c",
    )

    assert checker.params["nfa_thread_slots"] == "4"
    assert checker.children[0].params["nfa_thread_slots"] == "4"


def test_nested_intersect_lift_fails_closed_when_exactly_one_side_is_unsupported() -> None:
    operand = SeqIntersect(
        left=_bool("a"),
        right=SignalFunc(func_name="rose", signal="b", source_loc=_LOC),
        source_loc=_LOC,
    )

    lifted = _try_lift_operand(
        operand,
        ClockSpec(edge="posedge", signal="clk", source_loc=_LOC),
        "one_invalid_side",
        "a intersect $rose(b)",
    )

    assert lifted is None


@pytest.mark.parametrize(
    ("node", "expected_construct"),
    [
        (
            SeqIntersect(
                left=_bool("a"),
                right=SignalFunc(func_name="rose", signal="b", source_loc=_LOC),
                source_loc=_LOC,
            ),
            "intersect with multi-cycle operand",
        ),
        (
            SeqWithin(
                inner=_bool("a"),
                outer=SignalFunc(func_name="rose", signal="b", source_loc=_LOC),
                source_loc=_LOC,
            ),
            "within with multi-cycle operand",
        ),
        (
            SeqThroughout(
                condition=SignalFunc(func_name="rose", signal="a", source_loc=_LOC),
                body=_bool("b"),
                source_loc=_LOC,
            ),
            "throughout with multi-cycle operand",
        ),
    ],
)
def test_composed_nfa_route_requires_every_operand_to_be_liftable(
    node: SeqIntersect | SeqWithin | SeqThroughout,
    expected_construct: str,
) -> None:
    """One valid operand must never route an invalid pair into NFA lowering."""
    with pytest.raises(UnsupportedConstruct) as exc_info:
        compose(
            node,
            ClockSpec(edge="posedge", signal="clk", source_loc=_LOC),
            "one_invalid_nfa_operand",
            "boundary",
        )

    assert exc_info.value.construct_name == expected_construct
