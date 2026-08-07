"""Validate the focused machine-readable support evidence ledger."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[2]
LEDGER = ROOT / "support_evidence.json"
ALLOWED_STATUS = {
    "bounded_evidence",
    "conditional_formal_evidence",
    "trusted_boundary",
    "unsupported",
    "fully_supported",
}
QUALIFICATION_STATES = {
    "pending-exact-sha-remote-gates",
    "qualified-exact-sha",
}
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
RUN_ID_PATTERN = re.compile(r"[1-9][0-9]*\Z")


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def validate_payload(payload: dict[str, Any], *, root: Path = ROOT) -> int:
    if payload.get("schema_version") != 1:
        raise RuntimeError("unsupported support evidence schema")
    qualification = payload.get("current_worktree_qualification")
    if qualification not in QUALIFICATION_STATES:
        raise RuntimeError(f"invalid exact-SHA qualification state: {qualification!r}")

    baseline = _require_mapping(payload.get("qualified_baseline"), "qualified_baseline")
    executable_sha = baseline.get("executable_sha")
    if not isinstance(executable_sha, str) or SHA_PATTERN.fullmatch(executable_sha) is None:
        raise RuntimeError("qualified_baseline.executable_sha must be 40 lowercase hex digits")
    for field in ("ci_run", "differential_run", "full_formal_run"):
        run_id = baseline.get(field)
        if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
            raise RuntimeError(f"qualified_baseline.{field} must be a positive decimal run ID")

    capabilities = _require_mapping(payload.get("capabilities"), "capabilities")
    if not capabilities:
        raise RuntimeError("support evidence requires at least one capability")

    for capability, raw in capabilities.items():
        entry = _require_mapping(raw, capability)
        status = entry.get("status")
        if status not in ALLOWED_STATUS:
            raise RuntimeError(f"{capability} has invalid status: {status!r}")
        if status == "fully_supported" and qualification != "qualified-exact-sha":
            raise RuntimeError(
                f"{capability} cannot be fully supported before exact-SHA qualification"
            )
        evidence = _require_mapping(entry.get("evidence"), f"{capability}.evidence")
        if not evidence:
            raise RuntimeError(f"{capability} has no evidence dimensions")
        for dimension, paths in evidence.items():
            if not isinstance(paths, list) or not paths:
                raise RuntimeError(f"{capability}.{dimension} requires evidence paths")
            for relative in paths:
                if not isinstance(relative, str) or relative.startswith("/"):
                    raise RuntimeError(f"unsafe evidence path: {relative!r}")
                path = (root / relative).resolve()
                try:
                    path.relative_to(root.resolve())
                except ValueError as exc:
                    raise RuntimeError(f"evidence path escapes repository: {relative}") from exc
                if not path.is_file():
                    raise RuntimeError(f"missing evidence path: {relative}")
        blockers = entry.get("blockers")
        if status != "fully_supported" and (not isinstance(blockers, list) or not blockers):
            raise RuntimeError(f"{capability} must name promotion blockers")
    return len(capabilities)


def main() -> int:
    payload = _require_mapping(json.loads(LEDGER.read_text(encoding="utf-8")), "support evidence")
    capability_count = validate_payload(payload)

    print(f"support evidence valid: {capability_count} capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
