"""Release privacy scanner regressions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCANNER = ROOT / "tools" / "ci" / "check_release_privacy.py"


def _run(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_privacy_scanner_allows_documented_placeholders(tmp_path: Path) -> None:
    source = tmp_path / "clean.txt"
    source.write_text(
        "/Users/" + "private/token\nbot@users.noreply.github.com\n",
        encoding="utf-8",
    )
    result = _run(source)
    assert result.returncode == 0, result.stderr
    assert "privacy scan passed" in result.stdout


def test_privacy_scanner_rejects_personal_identifiers_without_echoing_secret(
    tmp_path: Path,
) -> None:
    source = tmp_path / "bad.txt"
    source.write_text(
        "/Users/" + "named-person/project\n"
        + "person@"
        + "gmail.com\n"
        + "api_key = \""
        + "do-not-print-this-value"
        + "\"\n",
        encoding="utf-8",
    )
    result = _run(source)
    assert result.returncode == 1
    assert "personal home path" in result.stderr
    assert "personal email address" in result.stderr
    assert "literal secret assignment" in result.stderr
    assert "do-not-print-this-value" not in result.stderr
