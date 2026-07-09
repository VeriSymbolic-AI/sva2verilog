"""Simulator-backed differential tests for generated source cases."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.conftest import requires_slang
from tests.differential_cases import (
    GeneratedSvaCase,
    assert_traces_match,
    compile_generated_case,
    deterministic_stimulus,
    example_generated_cases,
    generated_sva_cases,
    run_oracle_trace,
    run_simulator_trace,
    stimulus_input_names_from_checker,
    stimulus_traces,
)

pytestmark = [pytest.mark.simulation, pytest.mark.differential]


def _require_simulator(simulator: str) -> None:
    if shutil.which(simulator) is None:
        pytest.skip(f"{simulator} not found - differential simulation skipped")


def _compare_case(
    case: GeneratedSvaCase,
    stimulus: list[dict[str, bool]],
    *,
    simulator: str,
    tmp_path: Path,
) -> None:
    compiled = compile_generated_case(case, tmp_path)
    oracle = run_oracle_trace(compiled.checker, stimulus)
    actual = run_simulator_trace(
        compiled.checker,
        stimulus,
        backend=simulator,
        tmp_path=tmp_path,
    )
    assert_traces_match(
        case,
        stimulus,
        oracle,
        actual,
        backend=simulator,
        artifact_dir=tmp_path / "differential-artifacts",
    )


@requires_slang
def test_differential_smoke_oracle_matches_simulator(
    simulator: str,
    tmp_path: Path,
) -> None:
    _require_simulator(simulator)
    case = example_generated_cases()[0]
    compiled = compile_generated_case(case, tmp_path)
    stimulus = deterministic_stimulus(case, compiled.checker)
    oracle = run_oracle_trace(compiled.checker, stimulus)
    actual = run_simulator_trace(
        compiled.checker,
        stimulus,
        backend=simulator,
        tmp_path=tmp_path,
    )

    assert_traces_match(
        case,
        stimulus,
        oracle,
        actual,
        backend=simulator,
        artifact_dir=tmp_path / "differential-artifacts",
    )


@requires_slang
@given(case_index=st.integers(min_value=0, max_value=6), data=st.data())
@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_generated_differential_fast(
    case_index: int,
    data: st.DataObject,
    simulator: str,
    tmp_path: Path,
) -> None:
    _require_simulator(simulator)
    case = example_generated_cases()[case_index]
    compiled = compile_generated_case(case, tmp_path)
    input_names = stimulus_input_names_from_checker(compiled.checker)
    stimulus = data.draw(stimulus_traces(case, input_names=input_names))
    oracle = run_oracle_trace(compiled.checker, stimulus)
    actual = run_simulator_trace(
        compiled.checker,
        stimulus,
        backend=simulator,
        tmp_path=tmp_path,
    )

    assert_traces_match(
        case,
        stimulus,
        oracle,
        actual,
        backend=simulator,
        artifact_dir=tmp_path / "differential-artifacts",
    )


@requires_slang
@pytest.mark.differential_slow
@given(case=generated_sva_cases(), data=st.data())
@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_generated_differential_slow_sweep(
    case: GeneratedSvaCase,
    data: st.DataObject,
    simulator: str,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    if "differential_slow" not in request.config.option.markexpr:
        pytest.skip("select with -m differential_slow to run the slow differential sweep")
    _require_simulator(simulator)
    compiled = compile_generated_case(case, tmp_path)
    input_names = stimulus_input_names_from_checker(compiled.checker)
    stimulus = data.draw(stimulus_traces(case, input_names=input_names))

    _compare_case(case, stimulus, simulator=simulator, tmp_path=tmp_path)
