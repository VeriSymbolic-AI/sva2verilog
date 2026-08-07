"""Regression tests for distribution package data."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from sva2rtl import emitter

PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "templates"


def test_wheel_force_includes_complete_template_tree() -> None:
    """The wheel must install every renderer template inside ``sva2rtl``."""
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    wheel_config = config["tool"]["hatch"]["build"]["targets"]["wheel"]

    assert wheel_config["force-include"] == {"templates": "sva2rtl/templates"}


def test_distribution_exposes_monitor_and_formal_entry_points() -> None:
    """Both backends must be callable after installing a wheel or sdist."""
    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["scripts"] == {
        "sva2rtl": "sva2rtl.cli:main",
        "sva2rtl-formal": "sva2rtl.formal_cli:main",
        "sva2rtl-formal-doctor": "sva2rtl.formal_doctor:main",
    }


def test_sdist_excludes_development_only_surfaces() -> None:
    """Published source archives contain build inputs, not audit/test history."""

    config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    include = set(config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"])

    assert include == {
        "/src",
        "/templates",
        "/LICENSE",
        "/README.md",
        "/FORMAL_VERIFICATION.md",
        "/SUPPORTED_CONSTRUCTS.md",
        "/SUPPORT_MATRIX.md",
        "/INDUSTRIAL_VALIDATION_GAPS.md",
        "/support_evidence.json",
        "/tools/formal",
        "/PROJECT_STATUS.md",
        "/PROJECT_ANALYSIS_2026-07-11.md",
        "/pyproject.toml",
    }


def test_installed_layout_resolves_every_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The emitter fallback must load the complete installed template tree."""
    package_dir = tmp_path / "site-packages" / "sva2rtl"
    shutil.copytree(TEMPLATE_ROOT, package_dir / "templates")
    monkeypatch.setattr(emitter, "__file__", str(package_dir / "emitter.py"))

    installed_templates = emitter._make_env().list_templates()
    source_templates = [
        path.relative_to(TEMPLATE_ROOT).as_posix()
        for path in TEMPLATE_ROOT.rglob("*")
        if path.is_file()
    ]

    assert sorted(installed_templates) == sorted(source_templates)
