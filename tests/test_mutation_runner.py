"""Regression tests for mutation-quality gate enforcement."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.mutation import run_mutation


def test_run_module_rejects_a_failing_test_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "composer.py"
    source.write_text("def predicate(value: int) -> bool:\n    return value == 1\n")
    monkeypatch.setattr(run_mutation, "run_tests", lambda _files: False)

    with pytest.raises(RuntimeError, match="baseline tests failed"):
        run_mutation.run_module(source, "composer.py")


@pytest.mark.parametrize(
    ("total", "killed", "expected"),
    [(0, 0, 0), (100, 85, 0), (100, 84, 1)],
)
def test_mutation_exit_code_enforces_target(
    total: int,
    killed: int,
    expected: int,
) -> None:
    assert run_mutation.mutation_exit_code(total, killed) == expected


def test_run_tests_uses_an_isolated_bytecode_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_env: dict[str, str] = {}

    def fake_run(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = kwargs["env"]
        assert isinstance(env, dict)
        captured_env.update(env)
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(run_mutation.subprocess, "run", fake_run)
    assert run_mutation.run_tests(["tests/test_composer.py"])
    assert "PYTHONPYCACHEPREFIX" in captured_env
    assert "sva2rtl-mutation-pycache-" in captured_env["PYTHONPYCACHEPREFIX"]
