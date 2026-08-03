#!/usr/bin/env python3
"""Fail release qualification on likely personal paths or committed secrets."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

_HOME_PATH = re.compile(r"(?:/Users/|/home/)([A-Za-z0-9._-]+)(?:/|\\)")
_WINDOWS_HOME = re.compile(r"[A-Za-z]:\\Users\\([A-Za-z0-9._-]+)\\")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_TOKEN = re.compile(r"\b(?:gh[opsu]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b")
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|password|secret|access[_-]?token)\b\s*[:=]\s*"
    r"['\"](?!\$|\{|<)([^'\"\s]{8,})['\"]"
)
_ALLOWED_HOME_NAMES = {"private", "user", "username", "runner", "example", "tmp"}
_ALLOWED_EMAIL_DOMAINS = {
    "example.com",
    "example.org",
    "users.noreply.github.com",
}


def _scan_text(name: str, text: str) -> list[str]:
    issues: list[str] = []
    for pattern in (_HOME_PATH, _WINDOWS_HOME):
        for match in pattern.finditer(text):
            if match.group(1).lower() not in _ALLOWED_HOME_NAMES:
                issues.append(f"{name}: personal home path")
    for match in _EMAIL.finditer(text):
        if match.group(1).lower() not in _ALLOWED_EMAIL_DOMAINS:
            issues.append(f"{name}: personal email address")
    if _PRIVATE_KEY.search(text):
        issues.append(f"{name}: private-key material")
    if _TOKEN.search(text):
        issues.append(f"{name}: credential-shaped token")
    if _SECRET_ASSIGNMENT.search(text):
        issues.append(f"{name}: literal secret assignment")
    return sorted(set(issues))


def _decode(data: bytes) -> str | None:
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _scan_file(path: Path) -> list[str]:
    if zipfile.is_zipfile(path):
        issues: list[str] = []
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or member.file_size > 5_000_000:
                    continue
                text = _decode(archive.read(member))
                if text is not None:
                    issues.extend(_scan_text(f"{path}:{member.filename}", text))
        return issues
    if tarfile.is_tarfile(path):
        issues = []
        with tarfile.open(path, "r:*") as archive:
            for member in archive.getmembers():
                if not member.isfile() or member.size > 5_000_000:
                    continue
                extracted = archive.extractfile(member)
                text = _decode(extracted.read()) if extracted is not None else None
                if text is not None:
                    issues.extend(_scan_text(f"{path}:{member.name}", text))
        return issues
    if path.stat().st_size > 5_000_000:
        return []
    text = _decode(path.read_bytes())
    return [] if text is None else _scan_text(str(path), text)


def _tracked_files() -> Iterable[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    for raw in completed.stdout.split(b"\x00"):
        if raw:
            yield Path(raw.decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or list(_tracked_files())
    issues: list[str] = []
    for path in paths:
        if path.is_file():
            issues.extend(_scan_file(path))
    if issues:
        for issue in sorted(set(issues)):
            print(issue, file=sys.stderr)
        print(f"privacy scan failed: {len(set(issues))} issue(s)", file=sys.stderr)
        return 1
    print(f"privacy scan passed: {len(paths)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
