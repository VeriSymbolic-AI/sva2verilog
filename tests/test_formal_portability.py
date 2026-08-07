"""Pinned formal-runtime and capability-report contracts."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sva2rtl.formal_doctor import main
from sva2rtl.formal_toolchain import validate_replay_contract

PROJECT_ROOT = Path(__file__).parent.parent


def _identity(role: str, available: bool = True) -> dict[str, object]:
    return {
        "role": role,
        "available": available,
        "version": f"{role} test",
        "sha256": "a" * 64 if available else "",
    }


def test_doctor_reports_safety_ready_but_missing_live_without_paths() -> None:
    toolchain = {
        role: _identity(role, available=role != "suprove")
        for role in (
            "sby",
            "slang",
            "solver",
            "suprove",
            "yosys",
            "yosys-smtbmc",
        )
    }
    with patch("sva2rtl.formal_doctor.probe_formal_toolchain", return_value=toolchain):
        result = CliRunner().invoke(main, ["--json-output"])
        required = CliRunner().invoke(main, ["--json-output", "--require-live"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["safety_ready"] is True
    assert payload["liveness_ready"] is False
    assert required.exit_code == 11
    assert "/Users/" not in result.output


def test_replay_contract_rejects_unbound_path_lookup() -> None:
    toolchain = {"sby": _identity("sby")}
    commands = [
        ["@tool:sby", "-f", "formal.sby"],
        ["@tool:sby", "-f", "formal_cover.sby"],
    ]
    assert validate_replay_contract(commands, toolchain, require_cover=True)

    try:
        validate_replay_contract([["sby", "-f", "formal.sby"]], toolchain, require_cover=False)
    except ValueError as error:
        assert "role-bound" in str(error)
    else:
        raise AssertionError("literal PATH-based replay command was accepted")


def test_portable_image_pins_base_and_both_tool_archives() -> None:
    dockerfile = (PROJECT_ROOT / "tools" / "formal" / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM debian:bookworm-slim@sha256:" in dockerfile
    assert "OSS_CAD_SUITE_RELEASE=2026-07-21" in dockerfile
    assert "6efd4012620df0c2305844dfdf9dab7a31763753b9792d6cbb1dcd8327e99d49" in dockerfile
    assert "cca0698fa42d70b895ae09b9fdce055e9ffd8186e204e2c313f6327c9bc59e79" in dockerfile
    assert "sha256sum --check --strict" in dockerfile
