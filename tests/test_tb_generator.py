"""Unit regressions for simulator-backend orchestration."""

from __future__ import annotations

import subprocess
from pathlib import Path

from pytest import MonkeyPatch

from tests.simulation import tb_generator


def test_repeated_verilator_runs_use_fresh_build_directories(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Fast Hypothesis examples must never reuse stale wrapper object files."""
    compile_directories: list[Path] = []

    monkeypatch.setattr(tb_generator.shutil, "which", lambda _name: "/fake/verilator")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "Verilator 5.028", "")
        if "--build" in command:
            compile_directories.append(Path(str(kwargs["cwd"])))
            assert "" not in command
            return subprocess.CompletedProcess(command, 0, "", "")
        return subprocess.CompletedProcess(command, 0, "0 0 0\n", "")

    monkeypatch.setattr(tb_generator.subprocess, "run", fake_run)

    for value in (False, True):
        result = tb_generator._run_simulation_verilator(
            "demo_checker",
            ["module demo_checker; endmodule"],
            "",
            work_dir=tmp_path,
            has_overflow_flag=False,
            stimulus=[{"start": value}],
            extra_inputs=["start"],
            clock_signal="clk",
        )
        assert result == [{"active": False, "pass": False, "fail": False}]

    assert len(compile_directories) == 2
    assert compile_directories[0] != compile_directories[1]
    assert all(directory.parent == tmp_path for directory in compile_directories)
    assert all((directory / "wrapper.cpp").is_file() for directory in compile_directories)
