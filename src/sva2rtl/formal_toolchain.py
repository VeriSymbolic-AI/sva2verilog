"""Privacy-safe tool identity and replay contracts for formal evidence."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolIdentity:
    """One executable identity without recording a host-specific absolute path."""

    role: str
    available: bool
    version: str
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "available": self.available,
            "version": self.version,
            "sha256": self.sha256,
        }


_VERSION_ARGS: dict[str, tuple[str, ...]] = {
    "slang": ("--version",),
    "sby": ("--version",),
    "suprove": ("--version",),
    "yosys": ("-V",),
    "yosys-smtbmc": ("--version",),
    "solver": ("--version",),
}


def solver_executable(solver: str) -> str:
    """Map an SBY solver token to the executable it actually launches."""
    return {"yices": "yices-smt2"}.get(solver, solver)


def _resolved_executable(requested: str) -> Path | None:
    candidate = shutil.which(requested)
    if candidate is None and ("/" in requested or "\\" in requested):
        raw = Path(requested).expanduser()
        if raw.is_file():
            candidate = str(raw)
    if candidate is None:
        return None
    resolved = Path(candidate).resolve()
    return resolved if resolved.is_file() else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sanitized_version(command: Sequence[str]) -> str:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    combined = (completed.stdout + "\n" + completed.stderr).strip()
    if not combined:
        return "unknown"
    first_line = combined.splitlines()[0].strip()
    home = str(Path.home())
    if home:
        first_line = first_line.replace(home, "<home>")
    return first_line[:500] or "unknown"


def probe_tool(role: str, requested: str) -> ToolIdentity:
    """Resolve and fingerprint a configured executable without persisting its path."""
    resolved = _resolved_executable(requested)
    if resolved is None:
        return ToolIdentity(role=role, available=False, version="missing", sha256="")
    version_args = _VERSION_ARGS.get(role, ("--version",))
    return ToolIdentity(
        role=role,
        available=True,
        version=_sanitized_version((str(resolved), *version_args)),
        sha256=_file_sha256(resolved),
    )


def probe_formal_toolchain(
    *,
    slang_path: str,
    sby_path: str,
    suprove_path: str,
    solver_path: str,
) -> dict[str, dict[str, object]]:
    """Return deterministic role-keyed identities for all formal executables."""
    requested = {
        "slang": slang_path,
        "sby": sby_path,
        "suprove": suprove_path,
        "yosys": "yosys",
        "yosys-smtbmc": "yosys-smtbmc",
        "solver": solver_path,
    }
    return {
        role: probe_tool(role, executable).to_dict()
        for role, executable in sorted(requested.items())
    }


def tool_versions(toolchain: Mapping[str, Mapping[str, object]]) -> dict[str, str]:
    """Project the richer tool identity into the legacy version summary."""
    return {
        role: str(identity.get("version", "unknown"))
        for role, identity in sorted(toolchain.items())
    }


def role_command(role: str, *arguments: str) -> tuple[str, ...]:
    """Build a relocatable replay command whose executable is a manifest role."""
    return (f"@tool:{role}", *arguments)


def validate_replay_contract(
    replay_commands: object,
    toolchain: object,
    *,
    require_cover: bool,
    require_live: bool = False,
) -> tuple[tuple[str, ...], ...]:
    """Validate role-based replay commands without trusting host PATH strings."""
    if not isinstance(toolchain, dict):
        raise ValueError("formal evidence is missing its toolchain identity")
    sby = toolchain.get("sby")
    if not isinstance(sby, dict) or sby.get("role") != "sby":
        raise ValueError("formal evidence has an invalid sby tool identity")
    if not isinstance(sby.get("available"), bool):
        raise ValueError("formal evidence has an invalid sby availability flag")
    sha256 = sby.get("sha256")
    if sby["available"] and (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(char not in "0123456789abcdef" for char in sha256)
    ):
        raise ValueError("formal evidence has an invalid sby executable fingerprint")

    primary = ["@tool:sby", "-f", "formal.sby"]
    if require_live:
        suprove = toolchain.get("suprove")
        if not isinstance(suprove, dict) or suprove.get("role") != "suprove":
            raise ValueError("formal evidence has an invalid suprove tool identity")
        primary.extend(("--suprove", "@tool:suprove"))
    expected = [
        primary,
        *([["@tool:sby", "-f", "formal_cover.sby"]] if require_cover else []),
    ]
    if replay_commands != expected:
        raise ValueError("formal evidence does not declare role-bound replay commands")
    return tuple(tuple(str(token) for token in command) for command in expected)


def toolchain_matches(
    recorded: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    roles: Sequence[str],
) -> bool:
    """Return whether selected executable roles still match their recorded identities."""
    return all(recorded.get(role) == current.get(role) for role in roles)
