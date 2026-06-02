---
phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor
plan: "04"
subsystem: cli
tags: [click, cli, error-handling, exit-codes, systemverilog, sva]

# Dependency graph
requires:
  - phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor plan 01
    provides: ir.py (BoolExpr, CheckerNode, SourceLoc), errors.py (SvaError hierarchy)
  - phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor plan 02
    provides: frontend.py (invoke_slang), ast_importer.py (import_assertion)
  - phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor plan 03
    provides: composer.py (compose), emitter.py (emit, write_output), bool_expr template
provides:
  - cli.py: click-based CLI entry point wiring the full compiler pipeline
  - exit code contract: 0=success, 1=compile error, 2=unsupported construct, 3=slang not found
  - tests/fixtures/bool_assert.sv: labeled boolean assertion fixture for integration tests
  - tests/fixtures/delay_assert.sv: ##1 sequence fixture for testing rejection (exit 2)
  - tests/test_cli.py: 9 unit tests covering all exit code paths and pipeline order
affects: [plan-05-unit-tests, phase-02-core-operators, phase-06-cli-polish]

# Tech tracking
tech-stack:
  added: [click>=8.0 (already in deps)]
  patterns:
    - click @command/@argument/@option decorators for CLI definition
    - sys.exit() within click command for precise exit code control
    - click.echo(err=True) for stderr output in compiler diagnostics
    - CliRunner + unittest.mock.patch for isolated CLI unit testing

key-files:
  created:
    - src/sva2rtl/cli.py
    - tests/test_cli.py
    - tests/fixtures/bool_assert.sv
    - tests/fixtures/delay_assert.sv
  modified: []

key-decisions:
  - "Used sys.exit() inside click command (not raise SystemExit) for deterministic exit code mapping"
  - "Broad except Exception catches unexpected errors with 'internal error:' prefix to distinguish from SvaError hierarchy"
  - "CliRunner(mix_stderr not supported in click 8.4.x) — result.output contains both stdout and stderr"

patterns-established:
  - "All CLI tests use CliRunner (not subprocess) for deterministic, fast isolation"
  - "Each pipeline stage is mocked independently with unittest.mock.patch for precise fault injection"

requirements-completed: [CLI-05, CLI-06]

# Metrics
duration: 12min
completed: 2026-05-25
---

# Phase 1 Plan 04: CLI Entry Point + Error Handling Summary

**click-based `sva2rtl` CLI wiring invoke_slang→import_assertion→compose→emit→write_output with precise exit codes (0/1/2/3) for success, compile error, unsupported construct, and slang-not-found**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-25T12:15:00Z
- **Completed:** 2026-05-25T12:27:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Created `src/sva2rtl/cli.py` with full pipeline orchestration and exit code mapping satisfying CLI-05/CLI-06
- Created `tests/fixtures/bool_assert.sv` (labeled boolean assertion) and `delay_assert.sv` (##1 unsupported) as real SV test inputs
- Created `tests/test_cli.py` with 9 tests covering all exit code paths, pipeline order verification, and both stdout/file output modes
- All tests pass, mypy --strict reports zero errors, ruff reports zero violations
- `uv run sva2rtl --help` exits 0; `--slang-path /nonexistent/...` exits 3

## Task Commits

Each task was committed atomically:

1. **Task 1: cli.py click entry point** - `af6dd50` (feat(01-04))
2. **Task 2: SV fixture files** - `ff00de5` (test(01-04))
3. **Task 3: CLI unit tests** - `0f79349` (test(01-04))

## Files Created/Modified

- `src/sva2rtl/cli.py` — click @command wiring full pipeline, exception→exit code mapping
- `tests/fixtures/bool_assert.sv` — `my_check: assert property (@(posedge clk) a && b)` in module test_bool
- `tests/fixtures/delay_assert.sv` — `assert property (@(posedge clk) a ##1 b)` for Phase 2+ rejection testing
- `tests/test_cli.py` — 9 test functions using CliRunner + patch: help, missing input, SlangNotFound (exit 3), UnsupportedConstruct/SVA-E002 (exit 2), SvaCompileError (exit 1), success stdout (exit 0), success --output file, internal error, pipeline call order

## Decisions Made

- Used `sys.exit()` inside the click command body rather than relying on click's built-in exception handling — this gives exact control over exit codes and prevents click from adding unwanted error formatting
- Broad `except Exception` clause logs `internal error:` prefix to distinguish from intentional `SvaError` subclass messages (prevents silent swallowing of bugs)
- `CliRunner` in click 8.4.x doesn't support `mix_stderr=False` — removed that parameter; stdout+stderr are combined in `result.output`, which is fine for these assertion-style tests

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] click.testing.CliRunner has no mix_stderr parameter in click 8.4.x**
- **Found during:** Task 3 (CLI unit tests) — first pytest run
- **Issue:** `CliRunner(mix_stderr=False)` raises `TypeError: CliRunner.__init__() got an unexpected keyword argument 'mix_stderr'` in click 8.4.1
- **Fix:** Removed `mix_stderr=False`; updated assertions to use `result.output` (which captures both stdout and stderr in this version)
- **Files modified:** tests/test_cli.py
- **Verification:** `uv run pytest tests/test_cli.py -v` → 9 passed
- **Committed in:** `0f79349` (Task 3 commit — fix was applied before committing)

---

**Total deviations:** 1 auto-fixed (1 Rule 1 - click API version mismatch)
**Impact on plan:** Minimal — test assertions are equivalent in correctness; stderr content is still validated, just via `result.output`.

## Issues Encountered

None beyond the click version deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 1.4 (CLI) is complete — `sva2rtl` CLI is the primary user interface and is fully functional for boolean assertions
- Plan 1.5 (Unit test framework + Phase 1 tests) is the final plan in Phase 1; test infrastructure is already in place, 113 total tests pass (104 from Plans 1.1–1.3 + 9 new)
- No blockers for Plan 1.5

---
*Phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor*
*Completed: 2026-05-25*
