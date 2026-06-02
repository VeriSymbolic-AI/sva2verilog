---
phase: 06-cli-polish-verilog-2001-integration-testing
plan: 01
subsystem: cli
tags: [cli, click, multi-property, dump-ir, dump-ast, verilog-2001-flag, version, error-codes]

# Dependency graph
requires:
  - phase: 04-normalization-composition-engine
    provides: format_dump_tree() pattern in debug.py; normalize() pipeline stage
  - phase: 05-optimization-passes
    provides: --dump-tree / --no-optimize CLI flag patterns; CheckerNode hash map
provides:
  - import_all_assertions() — multi-property AST collector
  - format_dump_ir() — D-02 normalized IR dump with source locations
  - PropertyNotFound (SVA-E005) error class with available-labels listing
  - CLI flags: --dump-ast, --dump-ir, --property, --verilog, --version
  - Multi-property compilation pipeline (default: emit all assertions)
  - 13 unit tests in tests/test_cli_phase6.py (CliRunner + mocks, no slang dependency)
affects: [06-cli-polish-verilog-2001-integration-testing/02-PLAN, 06-cli-polish-verilog-2001-integration-testing/03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Click early-exit debug flag: print result + sys.exit(0)"
    - "Multi-assertion two-pass collection (declarations first, assertions second)"
    - "Recursive _find_all_assertions_in_members returning list (mirror of single-find)"
    - "PropertyNotFound exception → exit code 2 (user-input error, not compiler bug)"
    - "verilog_mode kwarg threaded through emit() / emit_all() into Jinja2 context"

key-files:
  created:
    - tests/test_cli_phase6.py
  modified:
    - src/sva2rtl/cli.py
    - src/sva2rtl/debug.py
    - src/sva2rtl/ast_importer.py
    - src/sva2rtl/errors.py
    - tests/test_cli.py

key-decisions:
  - "D-02: --dump-ir uses 2-space indent, named child labels (antecedent/consequent/body), source loc on every node line"
  - "D-03: --property is a filter (not a mode) — pipeline runs identically; no-match exits 2 listing available labels"
  - "import_assertion() preserved unchanged for backward compatibility; import_all_assertions() added as new public API"
  - "PropertyNotFound mapped to exit code 2 (same as UnsupportedConstruct — user input, not compiler bug)"
  - "--dump-ast exits BEFORE import_all_assertions; --dump-ir exits AFTER normalize, before compose"

patterns-established:
  - "Public dump_* function in debug.py wraps private _format_* with explicit show_loc kwarg"
  - "Error class with structured fields (property_name, available) + custom __str__ formatting SVA-Exxx code"
  - "Multi-property pipeline branches on len(assertions) == 1 vs > 1 to preserve single-property output behavior"

requirements-completed: [CLI-01, CLI-02, CLI-03]
requirements-partially:
  - "CLI-04: --dump-tree integration verified through new pipeline (already existed)"
  - "OUT-05: --verilog flag wiring complete; template Verilog-2001 conversion is Plan 6.2"

# Metrics
duration: implemented in commit 2cbfd99 (2026-05-28); SUMMARY created 2026-06-01
completed: 2026-06-01
---

# Phase 6 Plan 1: CLI Flags + Multi-Property Support + --dump-ir Summary

**All Phase 6 CLI flags shipped as a complete vertical slice — `--dump-ast`, `--dump-ir`, `--property` (with multi-property support), `--verilog` flag wiring, and `--version` — backed by 13 mock-based unit tests.**

## Performance

- **Tasks:** 5 (all green)
- **Files modified:** 5 (4 src + 1 test)
- **Tests added:** 13 (test_cli_phase6.py)
- **Mypy --strict:** ✅ Success: no issues found in 4 source files
- **Ruff check src/ tests/:** ✅ All checks passed
- **pytest tests/test_cli_phase6.py:** ✅ 13/13 passed

## Accomplishments

### Task 6.1.1 — `import_all_assertions()` in `ast_importer.py`
- New public function returning `list[tuple[SVANode, ClockSpec, str, str | None]]` — collects ALL ConcurrentAssertions in source order.
- New private `_find_all_assertions_in_members()` mirrors the single-find pattern but extends `results` instead of returning early.
- `import_assertion()` left unchanged (backwards compatible — still returns first only).
- Raises `SvaCompileError` when no assertions found.

### Task 6.1.2 — `format_dump_ir()` in `debug.py`
- New public function returning the D-02 formatted normalized-IR dump with `=== Normalized IR ===` header.
- Enhanced private `_format_ir()` with optional `show_loc: bool = False` parameter.
- When `show_loc=True`, every node line appends `, loc=<file>:<line>:<col>` from `node.source_loc`.
- Preserves named child labels (`antecedent:`, `consequent:`, `body:`) and 2-space indentation.

### Task 6.1.3 — `PropertyNotFound` (SVA-E005) error class
- Inherits from `SvaError` with two new fields: `property_name: str` and `available: list[str]` (default-factory).
- `__str__` produces `error SVA-E005: property '<name>' not found. Available: [<comma-separated labels>]`.
- Maps to CLI exit code 2 (user-input error class, not compiler bug class).

### Task 6.1.4 — All new CLI flags wired in `cli.py`
- `@click.version_option(package_name="sva2rtl", prog_name="sva2rtl")` — `--version` exits 0.
- `--dump-ast`: pretty-prints raw slang JSON via `json.dumps(ast, indent=2)`, exits 0 BEFORE `import_all_assertions`.
- `--dump-ir`: prints `format_dump_ir(node)`, exits 0 AFTER `normalize()`, BEFORE `compose()`.
- `--property <name>`: filters `import_all_assertions()` results by label; no-match raises `PropertyNotFound`.
- `--verilog`: bool flag threaded as `verilog_mode=True` keyword into `emit()` / `emit_all()`.
- Multi-property pipeline: default behaviour iterates all assertions; single-assertion branch preserved for unchanged single-property output.
- Exception handler chain: `SlangNotFound` → 3, `PropertyNotFound` → 2, `UnsupportedConstruct` → 2, `SvaError` → 1, generic → 1.

### Task 6.1.5 — Tests in `tests/test_cli_phase6.py`
- 13 tests covering: `--version`, `--dump-ast` (3 sub-tests: exit code, valid JSON, no RTL), `--dump-ir` (3 sub-tests: exit code, header, no compose), `--property` match, `--property` no-match (SVA-E005), `--verilog` flag threading, multi-property default emits all, `format_dump_ir` loc inclusion, `PropertyNotFound` format.
- All tests use `CliRunner` + `unittest.mock.patch` — zero slang binary dependency, fast (≈140 ms total).

## Task Commits

The implementation landed in earlier worktree commits (single feature commit + lint follow-up):

1. **Tasks 6.1.1 – 6.1.5 (combined feat commit)** — `2cbfd99` (`feat(cli): add --dump-ast, --dump-ir, --property, --verilog, --version flags + multi-property support`).
   - `src/sva2rtl/ast_importer.py` (+78): `import_all_assertions()`, `_find_all_assertions_in_members()`.
   - `src/sva2rtl/cli.py` (+195/-77): full pipeline rewrite, all new flags, exception chain.
   - `src/sva2rtl/debug.py` (+69): `format_dump_ir()`, `_format_ir(show_loc=...)`.
   - `src/sva2rtl/errors.py` (+20): `PropertyNotFound` (SVA-E005).
   - `tests/test_cli.py` (+73 modified): updated mocks to use `import_all_assertions`.
   - `tests/test_cli_phase6.py` (+270 new): 13 tests for all flags.
2. **Lint/CI follow-up** — `1c3204d` (release-prep commit; tightened ruff/mypy compliance across the same files).

The combined commit reflects the tight coupling between CLI plumbing, the new public APIs (`import_all_assertions`, `format_dump_ir`, `PropertyNotFound`), and their first consumers — splitting them would have introduced transient compile failures.

## Files Created/Modified

- **Created:** `tests/test_cli_phase6.py` (270 lines, 13 tests)
- **Modified:**
  - `src/sva2rtl/cli.py` (246 lines total) — full pipeline rewrite
  - `src/sva2rtl/debug.py` (219 lines total) — added `format_dump_ir` + `show_loc` plumbing
  - `src/sva2rtl/ast_importer.py` (+78 lines) — `import_all_assertions` + helper
  - `src/sva2rtl/errors.py` (105 lines total) — `PropertyNotFound` class
  - `tests/test_cli.py` — updated existing mocks to point at `import_all_assertions`

## Decisions Made

- **Combined tasks 6.1.1 – 6.1.5 into a single feat commit** — the new public APIs (`import_all_assertions`, `format_dump_ir`, `PropertyNotFound`) cannot be merged without their CLI consumer without leaving the tree in a broken state mid-commit; the test file in 6.1.5 exercises all three together.
- **`import_assertion()` left untouched** — preserves backwards compatibility for any direct importer (e.g., simulation tests, integration tests) until a deliberate migration phase.
- **Exit code 2 for `PropertyNotFound`** — matches `UnsupportedConstruct` semantics (user-input error vs. compiler-internal error). Exit code 1 reserved for genuine compile failures.
- **`--dump-ir` exits at the normalized IR boundary** (post-`normalize`, pre-`compose`) — gives users a stable debugging window into the canonicalized tree before composition mutates structure.

## Deviations from Plan

- None functional. The plan was executed exactly as specified.
- The plan called for "at least 9 test functions"; delivered 13 (the extras are tighter sub-assertions on `--dump-ast`, `--dump-ir`, and standalone `format_dump_ir` / `PropertyNotFound` invariant tests).

## Issues Encountered

- None during implementation.
- During SUMMARY-time verification, the worktree's `.venv` was incomplete and `uv sync` failed due to network unavailability for `hatchling`; mypy/pytest/ruff were re-run successfully via the project's parent `.venv` (which already has all deps cached). Result: all gates pass.

## User Setup Required

None.

## Next Phase Readiness

- `cli.py` is now the stable CLI surface for v1.0; downstream Plan 6.2 (Verilog-2001 template conversion) only needs to update Jinja2 templates — the `verilog_mode` flag is already threaded.
- `format_dump_ir()` is reusable by integration tests in Plan 6.3 for IR-shape regression assertions.
- `import_all_assertions()` unblocks Plan 6.3 multi-property end-to-end tests.
- 13 mock-based tests run in <200 ms with zero external dependencies — safe to run in CI matrix without slang/iverilog.

## Verification (gates run at SUMMARY time)

```text
$ mypy --strict src/sva2rtl/cli.py src/sva2rtl/debug.py src/sva2rtl/ast_importer.py src/sva2rtl/errors.py
Success: no issues found in 4 source files

$ pytest tests/test_cli_phase6.py -v
============================== 13 passed in 0.14s ==============================

$ ruff check src/ tests/
All checks passed!
```

---
*Phase: 06-cli-polish-verilog-2001-integration-testing*
*Plan: 01 — CLI Flags + Multi-Property Support + --dump-ir*
*Completed: 2026-06-01*
