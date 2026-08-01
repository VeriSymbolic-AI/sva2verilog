"""Keep release identity consistent across package, lock, docs, and license."""

from __future__ import annotations

import tomllib
from pathlib import Path

from sva2rtl import __version__

ROOT = Path(__file__).parents[1]


def test_release_identity_is_consistent() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    project_version = project["project"]["version"]
    locked_project = next(package for package in lock["package"] if package["name"] == "sva2rtl")
    supported = (ROOT / "SUPPORTED_CONSTRUCTS.md").read_text(encoding="utf-8")
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    project_status = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    support_matrix = (ROOT / "SUPPORT_MATRIX.md").read_text(encoding="utf-8")
    industrial_gaps = (ROOT / "INDUSTRIAL_VALIDATION_GAPS.md").read_text(
        encoding="utf-8"
    )

    assert __version__ == project_version
    assert locked_project["version"] == project_version
    assert f"sva2rtl v{project_version} current main" in supported
    assert f"Licensed Work:        sva2rtl {project_version}" in license_text
    assert f"> 当前版本：v{project_version}" in project_status
    assert f"Current v{project_version}" in support_matrix
    assert f"> Scope: v{project_version}" in industrial_gaps
