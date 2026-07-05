#!/usr/bin/env python3
"""seed_validation_skeletons.py — v1.1 Phase 1 Audit Harness

Walks the six v1.0 phase directories under
  .planning/milestones/v1.0-phases/0N-*/
and seeds one empty VALIDATION.md skeleton per phase directory, keyed on the
leading two-digit phase number from the directory name.

Usage
-----
  python tools/audit/seed_validation_skeletons.py [--dry-run] [--check]

Flags
-----
  --dry-run   List targets but do NOT write any files.  Exits 0 and prints
              exactly six "would-write ..." lines on stdout.
  --check     Verify existence only.  Exits 0 if all six 0N-VALIDATION.md
              files already exist; exits 1 otherwise (used as Plan 02 gate).
  (no flag)   Write skeleton files, skipping any that already exist (idempotent).

Safety contract
---------------
* Refuses to write outside .planning/milestones/v1.0-phases/.
* Does NOT import from src/ or touch tests/.
* Skips (does not overwrite) any 0N-VALIDATION.md that already exists.
* Stdlib-only — no click, jinja2, pyslang, or sva2rtl imports.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REPO_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_PHASES_DIR: Path = _REPO_ROOT / ".planning" / "milestones" / "v1.0-phases"
_TEMPLATE_PATH: Path = _REPO_ROOT / ".planning" / "research" / "VALIDATION-TEMPLATE.md"

# Fixed per-phase NYQ range table (matches VALIDATION-TEMPLATE.md).
_NYQ_RANGES: dict[str, str] = {
    "01": "NYQ-01..NYQ-09",
    "02": "NYQ-10..NYQ-19",
    "03": "NYQ-20..NYQ-29",
    "04": "NYQ-30..NYQ-39",
    "05": "NYQ-40..NYQ-49",
    "06": "NYQ-50..NYQ-59",
}

_EXPECTED_PHASE_NUMBERS: frozenset[str] = frozenset(_NYQ_RANGES.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_within_phases_dir(target: Path) -> None:
    """Raise RuntimeError if *target* escapes the allowed subtree."""
    try:
        target.resolve().relative_to(_PHASES_DIR.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"Write target {target!r} is outside the allowed subtree "
            f"{_PHASES_DIR!r}.  Refusing to write."
        ) from exc


def _discover_phase_dirs() -> list[tuple[str, Path]]:
    """Return a sorted list of (phase_number, phase_dir) pairs.

    Scans *_PHASES_DIR* for directories whose names begin with a two-digit
    decimal prefix matching exactly the six expected phase numbers (01-06).
    Raises SystemExit if the count is not exactly six.
    """
    if not _PHASES_DIR.is_dir():
        sys.exit(
            f"ERROR: phases directory not found: {_PHASES_DIR}\n"
            "Run this script from the repository root."
        )

    prefix_re = re.compile(r"^(\d{2})-")
    found: list[tuple[str, Path]] = []

    for entry in sorted(_PHASES_DIR.iterdir()):
        if not entry.is_dir():
            continue
        m = prefix_re.match(entry.name)
        if m and m.group(1) in _EXPECTED_PHASE_NUMBERS:
            found.append((m.group(1), entry))

    if len(found) != len(_EXPECTED_PHASE_NUMBERS):
        sys.exit(
            f"ERROR: expected exactly {len(_EXPECTED_PHASE_NUMBERS)} phase "
            f"directories under {_PHASES_DIR}; found {len(found)}:\n"
            + "\n".join(f"  {p}" for _, p in found)
        )

    return found


def _phase_name_from_dir(phase_dir: Path) -> str:
    """Strip the leading '0N-' prefix to get the human-readable phase name."""
    return re.sub(r"^\d{2}-", "", phase_dir.name)


def _load_template() -> str:
    """Read the VALIDATION-TEMPLATE.md content from disk."""
    if not _TEMPLATE_PATH.is_file():
        sys.exit(
            f"ERROR: template not found at {_TEMPLATE_PATH}.\n"
            "Run task 1.1.1 first to create VALIDATION-TEMPLATE.md."
        )
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _fill_skeleton(template: str, phase_number: str, phase_name: str) -> str:
    """Substitute per-phase placeholders in the template body."""
    nyq_range = _NYQ_RANGES[phase_number]
    result = template
    result = result.replace("<phase_number>", phase_number)
    result = result.replace("<phase_name>", phase_name)
    result = result.replace("<phase_slug>", f"{phase_number}-{phase_name}")
    # Replace the generic NYQ range comment placeholder
    result = result.replace(
        "<!-- NYQ range: NYQ-XX..NYQ-YY -->",
        f"<!-- NYQ range: {nyq_range} -->",
    )
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and drive skeleton generation.

    Returns 0 on success, 1 on failure.
    """
    parser = argparse.ArgumentParser(
        prog="seed_validation_skeletons.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List targets without writing any files.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Verify all six 0N-VALIDATION.md files exist. "
            "Exit 0 if all present, exit 1 otherwise."
        ),
    )
    args = parser.parse_args(argv)

    phase_dirs = _discover_phase_dirs()

    # --check mode: verify existence only
    if args.check:
        missing: list[str] = []
        for phase_number, phase_dir in phase_dirs:
            target = phase_dir / f"{phase_number}-VALIDATION.md"
            if not target.is_file():
                missing.append(str(target))
        if missing:
            print("MISSING (not yet seeded):")
            for p in missing:
                print(f"  {p}")
            return 1
        print("OK: all six 0N-VALIDATION.md skeletons exist.")
        return 0

    # Load template once (needed for both dry-run listing and real writes)
    template = _load_template()

    wrote = 0
    skipped = 0

    for phase_number, phase_dir in phase_dirs:
        phase_name = _phase_name_from_dir(phase_dir)
        target = phase_dir / f"{phase_number}-VALIDATION.md"

        if args.dry_run:
            print(f"would-write {target}")
            continue

        # Safety: refuse to write outside allowed subtree
        _assert_within_phases_dir(target)

        if target.exists():
            print(f"skip (already exists): {target}")
            skipped += 1
            continue

        skeleton = _fill_skeleton(template, phase_number, phase_name)
        target.write_text(skeleton, encoding="utf-8")
        print(f"wrote: {target}")
        wrote += 1

    if not args.dry_run:
        print(f"\nDone: {wrote} written, {skipped} skipped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
