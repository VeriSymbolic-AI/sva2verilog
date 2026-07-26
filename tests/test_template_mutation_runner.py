"""Regression tests for the targeted RTL-template mutation gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.mutation import run_template_mutation


def test_all_template_mutation_sites_are_exact_and_unique() -> None:
    for mutation in run_template_mutation.MUTATIONS:
        assert run_template_mutation.validate_mutation(mutation).is_file()


@pytest.mark.parametrize(
    ("total", "killed", "expected"),
    [(0, 0, 1), (11, 10, 1), (11, 11, 0)],
)
def test_template_mutation_gate_requires_every_mutant_killed(
    total: int,
    killed: int,
    expected: int,
) -> None:
    assert run_template_mutation.mutation_exit_code(total, killed) == expected


def test_template_is_restored_when_test_execution_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template = tmp_path / "test.sv.j2"
    template.write_text("wire result = left | right;\n", encoding="utf-8")
    mutation = run_template_mutation.TemplateMutation(
        name="restore-on-error",
        template="test.sv.j2",
        original="left | right",
        replacement="left & right",
        pytest_args=("tests/test_placeholder.py",),
    )
    monkeypatch.setattr(run_template_mutation, "ROOT", tmp_path)

    def raise_during_tests(_args: tuple[str, ...]) -> bool:
        raise RuntimeError("synthetic test failure")

    monkeypatch.setattr(run_template_mutation, "_run_tests", raise_during_tests)
    with pytest.raises(RuntimeError, match="synthetic test failure"):
        run_template_mutation.run_mutation(mutation)

    assert template.read_text(encoding="utf-8") == "wire result = left | right;\n"
