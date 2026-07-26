"""Focused temporal boundaries for mutation-sensitive oracle state."""

from __future__ import annotations

from sva2rtl.behavioral_oracle import SVABehavioralSim


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
