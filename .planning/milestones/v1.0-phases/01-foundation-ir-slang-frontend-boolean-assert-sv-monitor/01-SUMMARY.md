---
phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor
plan: "01"
subsystem: ir
tags: [python, dataclasses, ir, errors, pytest, mypy, ruff, uv, hatchling]

# Dependency graph
requires: []
provides:
  - "Frozen-dataclass SVA IR: SourceLoc, SVANode, BoolExpr, SeqConcat, PropImplication, ClockSpec, CheckerNode"
  - "Error class hierarchy: SvaError, SlangNotFound, SvaCompileError, UnsupportedConstruct, InternalError"
  - "Installable sva2rtl Python package via uv + hatchling (src/ layout)"
  - "31 passing unit tests covering all IR and error classes"
affects: [02-slang-frontend, 03-emitter, 04-cli, all-subsequent-plans]

# Tech tracking
tech-stack:
  added: [uv, hatchling, click>=8.0, jinja2>=3.1.6, pytest>=9.0, hypothesis>=6.100, mypy>=1.10, ruff>=0.4]
  patterns:
    - "Frozen dataclasses (frozen=True) for all IR nodes — enables structural hashing for CSE"
    - "SourceLoc first-class on every SVANode — prevents pitfall P5.1 (source location loss)"
    - "Explicit __hash__/__eq__ on CheckerNode to handle dict[str,str] params field"
    - "TYPE_CHECKING guard for SourceLoc import in errors.py — avoids circular deps at runtime"
    - "Dataclass (not frozen) for exceptions — exceptions need mutability"

key-files:
  created:
    - pyproject.toml
    - .python-version
    - src/sva2rtl/__init__.py
    - src/sva2rtl/py.typed
    - src/sva2rtl/ir.py
    - src/sva2rtl/errors.py
    - tests/__init__.py
    - tests/test_ir.py
    - tests/test_errors.py
    - uv.lock
  modified: []

key-decisions:
  - "hatchling over uv_build as build backend — plan spec; hatchling is more widely supported"
  - "N818 added to ruff ignore — SlangNotFound/UnsupportedConstruct names are mandated by plan API contract, renaming would break all downstream code"
  - "ANN101/ANN102 in ignore list — deprecated rules, harmless warnings, kept per plan spec"
  - "TYPE_CHECKING import for SourceLoc in errors.py — prevents circular import (errors.py imports from ir.py) while satisfying mypy --strict"
  - "attempt_fired first-class in CheckerNode port contract — prevents vacuous satisfaction P1.1; non-negotiable from Phase 1"

patterns-established:
  - "Frozen IR pattern: all SVA nodes use @dataclass(frozen=True) for safe sharing and structural hashing"
  - "SourceLoc threading: every IR node and error carries source location from day one"
  - "Explicit hash/eq for dict-containing frozen dataclasses: use frozenset(params.items())"
  - "Error hierarchy: SvaError base → SlangNotFound(3) / SvaCompileError(1) / UnsupportedConstruct(2) / InternalError(1)"

requirements-completed: [PARSE-05, OUT-01, OUT-07]

# Metrics
duration: 18min
completed: 2026-05-25
---

# Phase 1 Plan 01: Project Skeleton + SVA IR Summary

**Frozen-dataclass SVA IR (SourceLoc, BoolExpr, SeqConcat, PropImplication, ClockSpec, CheckerNode) + SvaError hierarchy bootstrapped as installable uv/hatchling package with 31 passing tests, mypy strict, ruff clean**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-05-25T00:00:00Z
- **Completed:** 2026-05-25T00:18:00Z
- **Tasks:** 4 completed
- **Files modified:** 10

## Accomplishments

- Bootstrapped `sva2rtl` as an installable Python package with `uv + hatchling` (src/ layout, PEP 561 py.typed marker, `[project.scripts]` CLI entry point)
- Implemented all 7 frozen IR dataclasses: `SourceLoc`, `SVANode`, `BoolExpr`, `SeqConcat`, `PropImplication`, `ClockSpec`, `CheckerNode` — all hashable; `CheckerNode` has explicit `__hash__`/`__eq__` to handle `dict[str,str]` params field
- Implemented full error hierarchy: `SvaError`, `SlangNotFound` (exit 3), `SvaCompileError` (exit 1), `UnsupportedConstruct` with SVA-E002 error code format (exit 2), `InternalError` (exit 1)
- 31 unit tests pass; `mypy --strict` reports zero errors; `ruff check` clean

## Task Commits

Each task was committed atomically:

1. **Task 1: Initialize project skeleton** — `1f2e91f` (feat)
2. **Task 2: Implement ir.py** — `542b39c` (feat)
3. **Task 3: Implement errors.py** — `0e9ff18` (feat)
4. **Task 4: Unit tests** — `af27be2` (test)

## Files Created/Modified

- `pyproject.toml` — Project metadata, hatchling build, ruff/mypy/pytest config, dependency groups
- `.python-version` — Python 3.12 pin
- `src/sva2rtl/__init__.py` — Package init with `__version__ = "0.1.0"`
- `src/sva2rtl/py.typed` — PEP 561 marker
- `src/sva2rtl/ir.py` — All SVA IR frozen dataclasses
- `src/sva2rtl/errors.py` — Error class hierarchy
- `tests/__init__.py` — Test package marker
- `tests/test_ir.py` — 16 IR unit tests
- `tests/test_errors.py` — 15 error unit tests
- `uv.lock` — Locked dependency manifest

## Decisions Made

- **hatchling over uv_build**: Plan spec requires hatchling; broader ecosystem compatibility.
- **N818 added to ruff ignore**: `SlangNotFound` and `UnsupportedConstruct` are mandated names in the plan's API contract. Renaming to add `Error` suffix would break all downstream code referencing the public API.
- **TYPE_CHECKING guard for SourceLoc in errors.py**: `errors.py` imports `SourceLoc` from `ir.py`. Using `TYPE_CHECKING` guard prevents circular imports at runtime while keeping `mypy --strict` satisfied.
- **`attempt_fired` first-class in CheckerNode**: Non-negotiable per architecture spec — prevents vacuous-satisfaction pitfall P1.1. Must be present from Phase 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed deprecated ANN101/ANN102 from ruff effectively; added N818**
- **Found during:** Task 4 (running ruff check)
- **Issue:** ruff warning "ANN101/ANN102 have been removed"; N818 fired on SlangNotFound/UnsupportedConstruct
- **Fix:** Added N818 to ignore list (class names are mandated by plan); ANN101/ANN102 left per plan spec (harmless, just deprecated)
- **Files modified:** pyproject.toml
- **Verification:** `ruff check src/ tests/` → "All checks passed!"
- **Committed in:** af27be2

**2. [Rule 1 - Bug] Import ordering fix in test files**
- **Found during:** Task 4 (ruff check I001)
- **Issue:** `from dataclasses import FrozenInstanceError` appeared after `import pytest` in test_ir.py
- **Fix:** `ruff check --fix` auto-sorted imports: stdlib before third-party before local
- **Files modified:** tests/test_ir.py, tests/test_errors.py
- **Verification:** `ruff check src/ tests/` → "All checks passed!"
- **Committed in:** af27be2

---

**Total deviations:** 2 auto-fixed (2 bug fixes)
**Impact on plan:** Both auto-fixes were minor tooling issues; no scope change. All acceptance criteria met.

## Issues Encountered

None — all acceptance criteria met on first attempt after auto-fixes.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- IR types and error classes are stable and ready for Plan 02 (slang frontend + AST importer) to consume
- `pyproject.toml` is configured to accept new `src/sva2rtl/` modules without any further changes
- All tests pass; mypy strict is clean; linter is green — clean baseline for incremental development

---
*Phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor*
*Completed: 2026-05-25*

## Self-Check: PASSED

| Criterion | Result |
|-----------|--------|
| `pyproject.toml` exists with `name = "sva2rtl"` and `version = "0.1.0"` | ✅ PASS |
| `[project.scripts]` contains `sva2rtl = "sva2rtl.cli:main"` | ✅ PASS |
| `.python-version` contains `3.12` | ✅ PASS |
| `src/sva2rtl/__init__.py` contains `__version__ = "0.1.0"` | ✅ PASS |
| `src/sva2rtl/py.typed` exists | ✅ PASS |
| `uv sync` completes without errors | ✅ PASS |
| `uv run python -c "import sva2rtl; print(sva2rtl.__version__)"` → `0.1.0` | ✅ PASS |
| `ir.py` defines exactly: SourceLoc, SVANode, BoolExpr, SeqConcat, PropImplication, ClockSpec, CheckerNode | ✅ PASS |
| All classes use `@dataclass(frozen=True)` | ✅ PASS |
| `SourceLoc("test.sv", 3, 5).__str__()` returns `"test.sv:3:5"` | ✅ PASS |
| `BoolExpr` is hashable | ✅ PASS |
| `CheckerNode` is hashable via explicit `__hash__` | ✅ PASS |
| `BoolExpr` inherits from `SVANode` | ✅ PASS |
| `uv run mypy src/sva2rtl/ir.py --strict` → zero errors | ✅ PASS |
| `errors.py` defines: SvaError, SlangNotFound, SvaCompileError, UnsupportedConstruct, InternalError | ✅ PASS |
| All inherit from Exception (via SvaError) | ✅ PASS |
| `str(UnsupportedConstruct(...))` contains "f.sv:3:5", "SVA-E002", "##N" | ✅ PASS |
| `str(SlangNotFound(message="not found"))` contains "not found" | ✅ PASS |
| `isinstance(SlangNotFound(message="x"), SvaError)` is True | ✅ PASS |
| `uv run mypy src/sva2rtl/errors.py --strict` → zero errors | ✅ PASS |
| `tests/test_ir.py` has ≥6 test functions (has 16) | ✅ PASS |
| `tests/test_errors.py` has ≥5 test functions (has 15) | ✅ PASS |
| `uv run pytest tests/test_ir.py tests/test_errors.py -v` → all 31 pass | ✅ PASS |
| `uv run ruff check tests/` → zero violations | ✅ PASS |
