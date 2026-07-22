"""Tests for differential failure artifacts and fixed regression fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.differential_cases import (
    FAILURE_ARTIFACT_SCHEMA_VERSION,
    CycleObservation,
    DifferentialMismatch,
    GeneratedSvaCase,
    assert_traces_match,
    build_failure_artifact,
    deterministic_stimulus,
    find_trace_mismatch,
    load_regression_case,
    make_generated_case,
    normalize_observation,
    run_oracle_trace,
    write_failure_artifact,
)

_REGRESSION_DIR = Path(__file__).parent / "differential" / "regressions"


def _mismatch() -> tuple[
    GeneratedSvaCase,
    list[dict[str, bool]],
    list[CycleObservation],
    list[CycleObservation],
    DifferentialMismatch,
]:
    case = make_generated_case("a", ("bool",), ("a",))
    stimulus = deterministic_stimulus(case)
    oracle = [
        CycleObservation(cycle=0, active=True, pass_value=False, fail=False, backend="oracle")
    ]
    actual = [
        CycleObservation(cycle=0, active=False, pass_value=False, fail=False, backend="unit")
    ]
    mismatch = DifferentialMismatch(
        case_id=case.case_id,
        backend="unit",
        cycle=0,
        signal="active",
        expected=True,
        actual=False,
        source_text=case.source_text,
        stimulus_slice=tuple(stimulus[:2]),
        oracle_observation=oracle[0].as_dict(),
        actual_observation=actual[0].as_dict(),
        family_tags=case.family_tags,
        reason="value mismatch",
    )
    return case, stimulus, oracle, actual, mismatch


def test_failure_artifact_schema_is_stable_and_deterministic() -> None:
    case, stimulus, oracle, actual, mismatch = _mismatch()

    artifact = build_failure_artifact(
        case,
        mismatch,
        stimulus=stimulus,
        oracle=oracle,
        actual=actual,
    )
    encoded = artifact.to_json()
    decoded = json.loads(encoded)

    assert artifact.schema_version == FAILURE_ARTIFACT_SCHEMA_VERSION
    assert artifact.as_dict()["schema_version"] == FAILURE_ARTIFACT_SCHEMA_VERSION
    assert decoded["case"]["case_id"] == case.case_id
    assert artifact.as_dict()["stimulus"] == stimulus
    assert decoded["oracle_trace"][0]["backend"] == "oracle"
    assert decoded["backend_trace"][0]["backend"] == "unit"
    assert encoded == artifact.to_json()


def test_failure_artifact_rejects_unsafe_source_metadata() -> None:
    case, stimulus, oracle, actual, mismatch = _mismatch()
    unsafe = DifferentialMismatch(
        case_id=mismatch.case_id,
        backend=mismatch.backend,
        cycle=mismatch.cycle,
        signal=mismatch.signal,
        expected=mismatch.expected,
        actual=mismatch.actual,
        source_text="module bad; // /Users/private/token\nendmodule\n",
        stimulus_slice=mismatch.stimulus_slice,
        oracle_observation=mismatch.oracle_observation,
        actual_observation=mismatch.actual_observation,
        family_tags=mismatch.family_tags,
        reason=mismatch.reason,
    )

    with pytest.raises(ValueError, match="unsafe"):
        build_failure_artifact(
            case,
            unsafe,
            stimulus=stimulus,
            oracle=oracle,
            actual=actual,
        )


def test_write_failure_artifact_is_deterministic(tmp_path: Path) -> None:
    case, stimulus, oracle, actual, mismatch = _mismatch()

    first = write_failure_artifact(
        case,
        mismatch,
        tmp_path,
        stimulus=stimulus,
        oracle=oracle,
        actual=actual,
    )
    first_text = first.read_text(encoding="utf-8")
    second = write_failure_artifact(
        case,
        mismatch,
        tmp_path,
        stimulus=stimulus,
        oracle=oracle,
        actual=actual,
    )

    assert second == first
    assert second.read_text(encoding="utf-8") == first_text
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert "/Users/" not in first_text
    assert "token" not in first_text.lower()


def test_assert_traces_match_writes_artifact_before_failure(tmp_path: Path) -> None:
    case, stimulus, oracle, actual, _mismatch_obj = _mismatch()

    with pytest.raises(AssertionError, match=r"artifact=.*_failure\.json"):
        assert_traces_match(
            case,
            stimulus,
            oracle,
            actual,
            backend="unit",
            artifact_dir=tmp_path,
        )

    artifacts = list(tmp_path.glob("*.json"))
    assert len(artifacts) == 1
    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["schema_version"] == FAILURE_ARTIFACT_SCHEMA_VERSION
    assert payload["mismatch"]["reason"] == "value mismatch"


def test_committed_regression_fixture_replay_entrypoint() -> None:
    fixtures = sorted(_REGRESSION_DIR.glob("*.json"))
    if not fixtures:
        pytest.skip("no promoted differential failure fixtures yet")

    for fixture in fixtures:
        case, stimulus, payload = load_regression_case(fixture)
        assert payload["schema_version"] == FAILURE_ARTIFACT_SCHEMA_VERSION
        assert "source_text" in payload["mismatch"]
        assert payload["stimulus"]
        assert payload["oracle_trace"]
        assert payload["backend_trace"]

        current = run_oracle_trace(case, stimulus)
        backend = [
            normalize_observation(raw, cycle=index, backend="recorded-backend")
            for index, raw in enumerate(payload["backend_trace"])
        ]
        historical = [
            normalize_observation(raw, cycle=index, backend="historical-oracle")
            for index, raw in enumerate(payload["oracle_trace"])
        ]

        assert find_trace_mismatch(
            case, stimulus, current, backend, backend="recorded-backend"
        ) is None
        assert find_trace_mismatch(
            case, stimulus, historical, backend, backend="historical-oracle"
        ) is not None
