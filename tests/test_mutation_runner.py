"""Regression tests for mutation-quality gate enforcement."""

from __future__ import annotations

import ast
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


def test_mutation_exit_code_accepts_module_specific_floor() -> None:
    assert run_mutation.mutation_exit_code(100, 90, target=0.90) == 0
    assert run_mutation.mutation_exit_code(100, 89, target=0.90) == 1


def test_every_semantic_module_has_an_explicit_kill_rate_floor() -> None:
    assert set(run_mutation.MUTATION_TARGETS) == set(run_mutation.MODULE_KILL_RATE_FLOORS)


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


def test_collected_mutations_preserve_complete_statements(tmp_path: Path) -> None:
    source = tmp_path / "composer.py"
    source.write_text(
        "def predicate(value: int) -> bool:\n"
        "    if value == 1 and value < 3:\n"
        "        return True\n"
        "    return not False\n",
        encoding="utf-8",
    )

    mutations = run_mutation.collect_mutations(source, "composer.py")
    mutated_sources = [
        run_mutation.apply_mutation(source.read_text(encoding="utf-8"), mutation)
        for mutation in mutations
    ]

    assert mutations
    assert all("if " in candidate for candidate in mutated_sources)
    assert all(ast.parse(candidate) is not None for candidate in mutated_sources)


def test_all_configured_mutants_are_syntax_valid() -> None:
    for module_name in run_mutation.MUTATION_TARGETS:
        source_path = run_mutation.SRC_DIR / module_name
        source = source_path.read_text(encoding="utf-8")
        for mutation in run_mutation.collect_mutations(source_path, module_name):
            ast.parse(run_mutation.apply_mutation(source, mutation))


def test_run_module_scores_only_covered_mutations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "composer.py"
    source.write_text(
        "def predicate(value: int) -> bool:\n"
        "    first = value == 1\n"
        "    second = value == 2\n"
        "    return first or second\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_mutation, "run_tests", lambda _files: True)
    monkeypatch.setattr(run_mutation, "collect_covered_lines", lambda _path, _files: {2})
    monkeypatch.setattr(
        run_mutation,
        "test_mutation",
        lambda _path, mutation, _files: run_mutation.MutationResult(mutation, killed=True),
    )

    report = run_mutation.run_module(source, "composer.py")

    assert report.total == 1
    assert report.killed == 1
    assert report.uncovered == 1
