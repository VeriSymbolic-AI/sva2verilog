"""Validate the focused machine-readable support evidence ledger."""

from __future__ import annotations

import json
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


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def main() -> int:
    payload = _require_mapping(json.loads(LEDGER.read_text(encoding="utf-8")), "support evidence")
    if payload.get("schema_version") != 1:
        raise RuntimeError("unsupported support evidence schema")
    qualification = payload.get("current_worktree_qualification")
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
                path = (ROOT / relative).resolve()
                try:
                    path.relative_to(ROOT.resolve())
                except ValueError as exc:
                    raise RuntimeError(f"evidence path escapes repository: {relative}") from exc
                if not path.is_file():
                    raise RuntimeError(f"missing evidence path: {relative}")
        blockers = entry.get("blockers")
        if status != "fully_supported" and (not isinstance(blockers, list) or not blockers):
            raise RuntimeError(f"{capability} must name promotion blockers")

    print(f"support evidence valid: {len(capabilities)} capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
