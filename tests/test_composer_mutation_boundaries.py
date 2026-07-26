"""Focused semantic boundaries for mutation-sensitive composer helpers."""

from __future__ import annotations

from sva2rtl.composer import (
    _emit_nfa_checker,
    _lift_to_nfa,
    _nfa_reachable_states,
    _render_multi_state_d_body,
    _render_state_d_body,
    compose,
)
from sva2rtl.ir import BoolExpr, ClockSpec, PropBoundedAlways, SeqConcat, SourceLoc

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
    assert (3, "(b)", 5) in transitions
    assert (4, "(b)", 5) in transitions


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
