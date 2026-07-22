"""Tests for differential stimulus and oracle comparison helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.conftest import requires_slang
from tests.differential_cases import (
    CycleObservation,
    GeneratedSvaCase,
    assert_traces_match,
    compile_generated_case,
    deterministic_stimulus,
    example_generated_cases,
    find_trace_mismatch,
    generated_sva_cases,
    make_generated_case,
    normalize_observation,
    run_oracle_trace,
    stimulus_input_names,
    stimulus_traces,
)
from tests.differential_reference import SourceBoolExpr, SourceReferenceSpec


def test_deterministic_stimulus_drives_start_and_signals() -> None:
    case = make_generated_case("(a && b)", ("bool", "structured_bool"), ("a", "b"))

    stimulus = deterministic_stimulus(case)

    assert len(stimulus) == case.trace_length
    assert all(tuple(cycle) == ("start", "a", "b") for cycle in stimulus)
    assert any(cycle["start"] for cycle in stimulus)
    assert all(isinstance(value, bool) for cycle in stimulus for value in cycle.values())


def test_stimulus_input_names_can_use_checker_observed_signals() -> None:
    case = make_generated_case("(a && b)", ("bool", "structured_bool"), ("a", "b"))

    names = stimulus_input_names(case)

    assert names == ("start", "a", "b")


@given(case=generated_sva_cases(), data=st.data())
@settings(max_examples=10, deadline=None)
def test_stimulus_strategy_is_bounded(
    case: GeneratedSvaCase,
    data: st.DataObject,
) -> None:
    stimulus = data.draw(stimulus_traces(case))

    assert len(stimulus) == case.trace_length
    assert all(tuple(cycle) == stimulus_input_names(case) for cycle in stimulus)
    assert all(isinstance(value, bool) for cycle in stimulus for value in cycle.values())


def test_normalize_observation_reports_missing_keys() -> None:
    with pytest.raises(ValueError, match="missing keys"):
        normalize_observation({"active": True, "pass": False}, cycle=3, backend="unit")


def test_run_oracle_trace_rejects_cases_without_source_reference() -> None:
    case = make_generated_case("a", ("bool",), ("a",))

    with pytest.raises(ValueError, match="independent source reference"):
        run_oracle_trace(case, deterministic_stimulus(case))


def test_source_reference_models_boolean_or_without_checker_ir() -> None:
    a = SourceBoolExpr.signal("a")
    b = SourceBoolExpr.signal("b")
    spec = SourceReferenceSpec("bool", SourceBoolExpr.disjunction(a, b))
    case = make_generated_case(
        spec.render(),
        ("bool", "structured_bool"),
        spec.signal_names(),
        source_reference=spec,
    )
    stimulus = [
        {"start": True, "a": False, "b": True},
        {"start": False, "a": False, "b": False},
    ]

    trace = run_oracle_trace(case, stimulus)

    assert trace[0].pass_value is False
    assert trace[1].pass_value is True
    assert trace[1].fail is False


@requires_slang
def test_run_oracle_trace_preserves_cycle_order(tmp_path: Path) -> None:
    case = example_generated_cases()[0]
    compiled = compile_generated_case(case, tmp_path)
    stimulus = deterministic_stimulus(case, compiled.checker)

    trace = run_oracle_trace(case, stimulus)

    assert [obs.cycle for obs in trace] == list(range(len(stimulus)))
    assert all(obs.backend == "oracle" for obs in trace)
    assert all(isinstance(obs.active, bool) for obs in trace)


def test_assert_traces_match_passes_for_identical_trace() -> None:
    case = make_generated_case("a", ("bool",), ("a",))
    stimulus = deterministic_stimulus(case)
    oracle = [
        CycleObservation(cycle=0, active=False, pass_value=False, fail=False, backend="oracle")
    ]
    actual = [
        CycleObservation(cycle=0, active=False, pass_value=False, fail=False, backend="unit")
    ]

    assert_traces_match(case, stimulus, oracle, actual, backend="unit")


def test_find_trace_mismatch_reports_value_mismatch() -> None:
    case = make_generated_case("a", ("bool",), ("a",))
    stimulus = deterministic_stimulus(case)
    oracle = [
        CycleObservation(cycle=0, active=True, pass_value=False, fail=False, backend="oracle")
    ]
    actual = [
        CycleObservation(cycle=0, active=False, pass_value=False, fail=False, backend="unit")
    ]

    mismatch = find_trace_mismatch(case, stimulus, oracle, actual, backend="unit")

    assert mismatch is not None
    assert mismatch.cycle == 0
    assert mismatch.signal == "active"
    assert mismatch.expected is True
    assert mismatch.actual is False
    assert mismatch.reason == "value mismatch"
    assert case.source_text in mismatch.format_message()


def test_find_trace_mismatch_reports_missing_cycle() -> None:
    case = make_generated_case("a", ("bool",), ("a",))
    stimulus = deterministic_stimulus(case)
    oracle = [
        CycleObservation(cycle=0, active=False, pass_value=False, fail=False, backend="oracle")
    ]

    mismatch = find_trace_mismatch(case, stimulus, oracle, [], backend="unit")

    assert mismatch is not None
    assert mismatch.signal == "trace_length"
    assert mismatch.reason == "backend missing cycle"


def test_find_trace_mismatch_reports_extra_cycle() -> None:
    case = make_generated_case("a", ("bool",), ("a",))
    stimulus = deterministic_stimulus(case)
    actual = [
        CycleObservation(cycle=0, active=False, pass_value=False, fail=False, backend="unit")
    ]

    mismatch = find_trace_mismatch(case, stimulus, [], actual, backend="unit")

    assert mismatch is not None
    assert mismatch.signal == "trace_length"
    assert mismatch.reason == "backend produced extra cycle"


def test_mismatch_payload_is_serializable() -> None:
    case = make_generated_case("a", ("bool",), ("a",))
    stimulus = deterministic_stimulus(case)
    oracle = [
        CycleObservation(cycle=0, active=True, pass_value=False, fail=False, backend="oracle")
    ]
    actual = [
        CycleObservation(cycle=0, active=False, pass_value=False, fail=False, backend="unit")
    ]

    mismatch = find_trace_mismatch(case, stimulus, oracle, actual, backend="unit")

    assert mismatch is not None
    payload = mismatch.as_dict()
    assert payload["case_id"] == case.case_id
    assert payload["backend"] == "unit"
    assert payload["stimulus_slice"]
