"""Focused temporal boundaries for mutation-sensitive oracle state."""

from __future__ import annotations

import pytest

from sva2rtl.behavioral_oracle import (
    SVABehavioralSim,
    _eval_nfa_guard,
    simulate_checker_hierarchy,
)
from sva2rtl.ir import CheckerNode, SourceLoc

_LOC = SourceLoc("mutation-boundary.sv", 1, 1)


def _hierarchy_node(
    template_name: str,
    module_name: str,
    params: dict[str, str],
    *,
    observed_signal: str | None = None,
    children: tuple[CheckerNode, ...] = (),
) -> CheckerNode:
    observed = () if observed_signal is None else ((observed_signal, observed_signal),)
    return CheckerNode(
        template_name=template_name,
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=_LOC,
        children=children,
    )


def test_zero_lower_bound_delay_range_is_not_zero_delay_fusion() -> None:
    sim = SVABehavioralSim("delay_range", {"delay_min": 0, "delay_max": 2})

    output = sim.tick({"start": True})

    assert output["pass"] is True
    assert output["active"] is False


def test_goto_repetition_does_not_arm_without_start() -> None:
    sim = SVABehavioralSim("goto_rep", {"rep_min": 2, "rep_max": 2})

    first = sim.tick({"start": False, "sig": False})
    second = sim.tick({"start": False, "sig": False})

    assert first["active"] is False
    assert second["active"] is False


def test_nonconsecutive_false_start_does_not_count_an_occurrence() -> None:
    sim = SVABehavioralSim("nonconsec_rep", {"rep_min": 2, "rep_max": 2})

    sim.tick({"start": True, "sig": False})
    first_hit = sim.tick({"start": False, "sig": True})
    second_hit = sim.tick({"start": False, "sig": True})

    assert first_hit["pass"] is False
    assert second_hit["pass"] is True


def test_past_true_history_is_suppressed_when_start_is_low() -> None:
    sim = SVABehavioralSim("past", {"depth": 1})

    sim.tick({"start": False, "sig": True})
    output = sim.tick({"start": False, "sig": False})

    assert output["pass"] is False
    assert output["active"] is False


def test_nonoverlap_stays_active_while_shifted_thread_remains() -> None:
    sim = SVABehavioralSim("implication_nonoverlap", {"bv_width": 2})

    sim.tick({"ant_pass": True, "con_pass": False})
    sim.tick({"ant_pass": False, "con_pass": False})
    output = sim.tick({"ant_pass": False, "con_pass": False})

    assert output["active"] is True


def test_eventually_ignores_true_operand_before_lower_bound() -> None:
    node = _hierarchy_node(
        "s_eventually",
        "eventually_lower_bound",
        {"lo": "1", "hi": "2"},
        observed_signal="p",
    )

    outputs = simulate_checker_hierarchy(
        node,
        [
            {"start": True, "p": True},
            {"start": False, "p": False},
            {"start": False, "p": True},
            {"start": False, "p": False},
        ],
    )

    assert outputs[1]["pass"] is False
    assert outputs[3]["pass"] is True
    assert all(not output["fail"] for output in outputs)


def test_eventually_no_hit_fails_immediately_after_upper_bound() -> None:
    node = _hierarchy_node(
        "s_eventually",
        "eventually_upper_bound_fail",
        {"lo": "1", "hi": "2"},
        observed_signal="p",
    )

    outputs = simulate_checker_hierarchy(
        node,
        [
            {"start": True, "p": False},
            {"start": False, "p": False},
            {"start": False, "p": False},
            {"start": False, "p": False},
        ],
    )

    assert outputs[2]["fail"] is False
    assert outputs[3]["fail"] is True
    assert outputs[3]["active"] is False


def test_eventually_early_hit_cannot_fail_at_upper_bound() -> None:
    node = _hierarchy_node(
        "s_eventually",
        "eventually_no_late_fail",
        {"lo": "1", "hi": "2"},
        observed_signal="p",
    )

    outputs = simulate_checker_hierarchy(
        node,
        [
            {"start": True, "p": False},
            {"start": False, "p": True},
            {"start": False, "p": False},
            {"start": False, "p": False},
        ],
    )

    assert outputs[2]["pass"] is True
    assert all(not output["fail"] for output in outputs)


def test_property_nfa_dead_end_fails_after_started_attempt() -> None:
    node = _hierarchy_node(
        "nfa_generic",
        "property_nfa_dead_end",
        {"nfa_transitions": "0,a,1", "nfa_accept": "1", "nfa_kind": "property"},
    )

    outputs = simulate_checker_hierarchy(
        node,
        [{"start": True, "a": False}, {"start": False, "a": False}],
    )

    assert outputs[0]["fail"] is False
    assert outputs[1]["fail"] is True


def test_sequence_nfa_dead_end_is_vacuous_no_match() -> None:
    node = _hierarchy_node(
        "nfa_generic",
        "sequence_nfa_dead_end",
        {"nfa_transitions": "0,a,1", "nfa_accept": "1", "nfa_kind": "sequence"},
    )

    outputs = simulate_checker_hierarchy(
        node,
        [{"start": True, "a": False}, {"start": False, "a": False}],
    )

    assert all(not output["fail"] for output in outputs)


def test_property_nfa_cannot_fail_before_any_attempt() -> None:
    node = _hierarchy_node(
        "nfa_generic",
        "property_nfa_not_started",
        {"nfa_transitions": "0,a,1", "nfa_accept": "1", "nfa_kind": "property"},
    )

    outputs = simulate_checker_hierarchy(
        node,
        [{"start": False, "a": False}, {"start": False, "a": False}],
    )

    assert all(not output["fail"] for output in outputs)


def test_external_disable_i_resets_sampled_leaf_state() -> None:
    node = _hierarchy_node(
        "rose",
        "rose_external_disable",
        {"depth": "1"},
        observed_signal="sig",
    )

    outputs = simulate_checker_hierarchy(
        node,
        [
            {"start": True, "sig": False},
            {"start": False, "sig": True, "disable_i": True},
            {"start": True, "sig": True},
        ],
    )

    assert outputs[1] == {
        "pass": False,
        "fail": False,
        "active": False,
        "overflow": False,
    }
    assert outputs[2]["pass"] is True


def test_external_disable_i_cancels_pending_composite_verdict() -> None:
    node = _hierarchy_node(
        "s_eventually",
        "eventually_external_disable",
        {"lo": "0", "hi": "2"},
        observed_signal="p",
    )

    outputs = simulate_checker_hierarchy(
        node,
        [
            {"start": True, "p": False},
            {"start": False, "p": False, "disable_i": True},
            {"start": False, "p": False},
            {"start": False, "p": False},
        ],
    )

    assert all(not output["pass"] and not output["fail"] for output in outputs[1:])


@pytest.mark.parametrize("disable_signal", ["disable", "disable_i"])
def test_public_disable_aliases_abort_nfa_state_identically(disable_signal: str) -> None:
    """The hierarchy boundary owns alias normalization for every NFA path."""
    node = _hierarchy_node(
        "nfa_generic",
        f"nfa_disable_{disable_signal}",
        {
            "nfa_transitions": "0,a,1;1,b,2",
            "nfa_accept": "2",
            "nfa_kind": "property",
        },
    )

    outputs = simulate_checker_hierarchy(
        node,
        [
            {"start": True, "a": True, "b": False},
            {"start": False, "a": False, "b": False, disable_signal: True},
            {"start": False, "a": False, "b": False},
        ],
    )

    assert outputs[1:] == [
        {"pass": False, "fail": False, "active": False, "overflow": False},
        {"pass": False, "fail": False, "active": False, "overflow": False},
    ]


def test_concat_only_first_child_receives_external_start() -> None:
    first = _hierarchy_node("rose", "concat_first", {"depth": "1"}, observed_signal="a")
    second = _hierarchy_node("rose", "concat_second", {"depth": "1"}, observed_signal="b")
    top = _hierarchy_node(
        "seq_concat_top",
        "concat_start_routing",
        {},
        children=(first, second),
    )

    outputs = simulate_checker_hierarchy(
        top,
        [{"start": True, "a": False, "b": True}],
    )

    assert outputs[0]["pass"] is False


def test_first_match_waits_for_delayed_body_completion_before_locking() -> None:
    body = _hierarchy_node(
        "delay_fixed",
        "first_match_delayed_body",
        {"delay_min": "2", "delay_max": "2"},
    )
    top = _hierarchy_node(
        "first_match_top",
        "first_match_delayed",
        {},
        children=(body,),
    )

    outputs = simulate_checker_hierarchy(
        top,
        [{"start": True}, {"start": False}, {"start": False}],
    )

    assert outputs[0]["pass"] is False
    assert outputs[1]["pass"] is True


def test_first_match_suppresses_later_completions_in_same_range() -> None:
    body = _hierarchy_node(
        "delay_range",
        "first_match_ranged_body",
        {"delay_min": "2", "delay_max": "3"},
    )
    top = _hierarchy_node(
        "first_match_top",
        "first_match_ranged",
        {},
        children=(body,),
    )

    outputs = simulate_checker_hierarchy(
        top,
        [{"start": True}, {"start": False}, {"start": False}],
    )

    assert [output["pass"] for output in outputs] == [False, True, False]


@pytest.mark.parametrize("early_side", ["left", "right"])
def test_prop_or_retains_early_failure_until_other_side_finishes(early_side: str) -> None:
    immediate = _hierarchy_node(
        "rose",
        f"or_immediate_{early_side}",
        {"depth": "1"},
        observed_signal="a",
    )
    delayed = _hierarchy_node(
        "s_eventually",
        f"or_delayed_{early_side}",
        {"lo": "0", "hi": "1"},
        observed_signal="b",
    )
    children = (immediate, delayed) if early_side == "left" else (delayed, immediate)
    top = _hierarchy_node("prop_or", f"or_latched_{early_side}", {}, children=children)

    outputs = simulate_checker_hierarchy(
        top,
        [
            {"start": True, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
        ],
    )

    assert [output["fail"] for output in outputs] == [False, False, True]


def test_prop_or_clears_latched_failures_before_next_attempt() -> None:
    immediate = _hierarchy_node(
        "rose", "or_clear_immediate", {"depth": "1"}, observed_signal="a"
    )
    delayed = _hierarchy_node(
        "s_eventually",
        "or_clear_delayed",
        {"lo": "0", "hi": "1"},
        observed_signal="b",
    )
    top = _hierarchy_node(
        "prop_or", "or_clear_after_verdict", {}, children=(immediate, delayed)
    )

    outputs = simulate_checker_hierarchy(
        top,
        [
            {"start": True, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": True, "a": False, "b": False},
        ],
    )

    assert outputs[2]["fail"] is True
    assert outputs[3]["fail"] is False


def test_prop_and_retains_early_pass_until_other_side_finishes() -> None:
    immediate = _hierarchy_node(
        "stable",
        "and_immediate",
        {"depth": "1"},
        observed_signal="a",
    )
    delayed = _hierarchy_node(
        "s_eventually",
        "and_delayed",
        {"lo": "1", "hi": "1"},
        observed_signal="b",
    )
    top = _hierarchy_node("prop_and", "and_latched", {}, children=(immediate, delayed))

    outputs = simulate_checker_hierarchy(
        top,
        [
            {"start": True, "a": False, "b": False},
            {"start": False, "a": False, "b": True},
            {"start": False, "a": False, "b": False},
        ],
    )

    assert outputs[2]["pass"] is True


def test_hierarchical_implication_requires_two_children_and_evaluates_both() -> None:
    antecedent = _hierarchy_node(
        "delay_fixed", "imp_ant", {"delay_min": "0", "delay_max": "0"}
    )
    consequent = _hierarchy_node(
        "delay_fixed", "imp_cons", {"delay_min": "0", "delay_max": "0"}
    )
    top = _hierarchy_node(
        "overlap_bitvec",
        "hierarchical_implication",
        {"bv_width": "1"},
        children=(antecedent, consequent),
    )

    outputs = simulate_checker_hierarchy(top, [{"start": True}])

    assert outputs[0]["pass"] is True


def test_sampled_leaf_uses_observed_port_name_instead_of_fallback() -> None:
    node = _hierarchy_node("rose", "named_observed", {"depth": "1"}, observed_signal="data")

    outputs = simulate_checker_hierarchy(
        node,
        [
            {"start": True, "data": False},
            {"start": True, "data": True},
        ],
    )

    assert outputs[1]["pass"] is True


def test_nfa_guard_rejects_missing_closing_parenthesis() -> None:
    with pytest.raises(ValueError, match="unbalanced parens"):
        _eval_nfa_guard("(a", {"a": True})
