"""Keep release and license identity consistent across public artifacts."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from sva2rtl import __version__

ROOT = Path(__file__).parents[1]
OFFICIAL_APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def test_release_identity_is_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    project_version = project["project"]["version"]
    locked_project = next(package for package in lock["package"] if package["name"] == "sva2rtl")
    supported = (ROOT / "SUPPORTED_CONSTRUCTS.md").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    project_status = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    support_matrix = (ROOT / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")
    industrial_gaps = (ROOT / "INDUSTRIAL_VALIDATION_GAPS.md").read_text(encoding="utf-8")

    assert __version__ == project_version
    assert locked_project["version"] == project_version
    assert f"sva2rtl v{project_version} current main" in supported
    assert project["project"]["license"] == "Apache-2.0"
    assert project["project"]["license-files"] == ["LICENSE"]
    assert hashlib.sha256(license_text.encode()).hexdigest() == OFFICIAL_APACHE_2_SHA256
    assert "Apache License, Version 2.0" in readme
    assert "SPDX: `Apache-2.0`" in agents
    assert "Business Source License" not in readme
    assert "BSL-1.1" not in readme
    assert f"> 当前版本：v{project_version}" in project_status
    assert f"Current v{project_version}" in support_matrix
    assert f"> Scope: v{project_version}" in industrial_gaps
