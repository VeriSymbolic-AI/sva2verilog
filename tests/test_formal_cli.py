"""CLI contract tests for the installed ``sva2rtl-formal`` command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sva2rtl.formal_cli import main
from sva2rtl.formal_flow import AttemptMode, FormalMode, FormalResult, FormalStatus


@pytest.fixture()
def sources(tmp_path: Path) -> tuple[Path, Path]:
    dut = tmp_path / "dut.sv"
    prop = tmp_path / "property.sv"
    dut.write_text("module dut(input clk, rst_n, req, ack); endmodule\n", encoding="utf-8")
    prop.write_text(
        "module spec(input clk, rst_n, req, ack);\n"
        "p: assert property (@(posedge clk) req |-> ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return dut, prop


def _args(tmp_path: Path, sources: tuple[Path, Path]) -> list[str]:
    dut, prop = sources
    return [
        "--dut",
        str(dut),
        "--property-file",
        str(prop),
        "--property",
        "p",
        "--top",
        "dut",
        "--output",
        str(tmp_path / "evidence"),
    ]


def _result(status: FormalStatus, mode: FormalMode = FormalMode.PROVE) -> FormalResult:
    return FormalResult(
        status=status,
        mode=mode,
        message=f"status {status.value}",
        returncode=0,
        duration_seconds=0.1,
        tool_versions={"sby": "test"},
        log_path="sby.log",
    )


def test_help_lists_formal_inputs() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for option in (
        "--dut",
        "--property-file",
        "--property",
        "--top",
        "--clock",
        "--reset",
        "--mode",
        "--attempt-mode",
        "--depth",
        "--timeout",
        "--engine",
        "--solver",
        "--logic-semantics",
        "--suprove-path",
        "--fairness",
        "--decomposition-certificate",
        "--compile-only",
    ):
        assert option in result.output


def test_compile_only_builds_without_running(
    tmp_path: Path, sources: tuple[Path, Path]
) -> None:
    evidence = MagicMock()
    evidence.bundle_dir = tmp_path / "evidence"
    with patch("sva2rtl.formal_cli.build_formal_bundle", return_value=evidence) as build:
        with patch("sva2rtl.formal_cli.run_formal_bundle") as run:
            result = CliRunner().invoke(main, [*_args(tmp_path, sources), "--compile-only"])
    assert result.exit_code == 0
    assert "compiled" in result.output.lower()
    assert "result.json" in result.output
    build.assert_called_once()
    run.assert_not_called()


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    [
        (FormalStatus.PROVEN, 0),
        (FormalStatus.FAILED, 10),
        (FormalStatus.UNKNOWN, 11),
        (FormalStatus.UNSUPPORTED, 12),
        (FormalStatus.TIMEOUT, 13),
        (FormalStatus.ERROR, 1),
    ],
)
def test_result_status_has_stable_exit_code(
    tmp_path: Path,
    sources: tuple[Path, Path],
    status: FormalStatus,
    expected_exit: int,
) -> None:
    evidence = MagicMock()
    evidence.bundle_dir = tmp_path / "evidence"
    with patch("sva2rtl.formal_cli.build_formal_bundle", return_value=evidence):
        with patch("sva2rtl.formal_cli.run_formal_bundle", return_value=_result(status)):
            result = CliRunner().invoke(main, _args(tmp_path, sources))
    assert result.exit_code == expected_exit
    assert status.value in result.output
    assert "result.json" in result.output


def test_options_map_to_typed_config(tmp_path: Path, sources: tuple[Path, Path]) -> None:
    evidence = MagicMock()
    evidence.bundle_dir = tmp_path / "evidence"
    args = [
        *_args(tmp_path, sources),
        "--mode",
        "bmc",
        "--attempt-mode",
        "symbolic-witness",
        "--depth",
        "42",
        "--timeout",
        "17",
        "--engine",
        "smtbmc",
        "--solver",
        "z3",
        "--suprove-path",
        "custom-suprove",
        "--fairness",
        "ready",
        "--fairness",
        "grant",
        "--force",
        "--compile-only",
    ]
    with patch("sva2rtl.formal_cli.build_formal_bundle", return_value=evidence) as build:
        result = CliRunner().invoke(main, args)
    assert result.exit_code == 0
    config = build.call_args.args[0]
    assert config.mode is FormalMode.BMC
    assert config.attempt_mode is AttemptMode.SYMBOLIC_WITNESS
    assert config.depth == 42
    assert config.timeout_seconds == 17
    assert config.engine == "smtbmc"
    assert config.solver == "z3"
    assert config.suprove_path == "custom-suprove"
    assert config.fairness_signals == ("ready", "grant")
    assert config.force is True


def test_invalid_identifier_is_usage_error(
    tmp_path: Path, sources: tuple[Path, Path]
) -> None:
    args = _args(tmp_path, sources)
    top_index = args.index("--top") + 1
    args[top_index] = "bad;top"
    result = CliRunner().invoke(main, args)
    assert result.exit_code == 2
    assert "invalid top identifier" in result.output
