---
phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor
plan: "05"
subsystem: test-infrastructure
tags: [pytest, mypy, ruff, golden-files, integration-tests, e2e-tests, conftest]

# Dependency graph
requires:
  - phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor plan 01
    provides: ir.py (BoolExpr, CheckerNode, SourceLoc, ClockSpec), errors.py (SvaError hierarchy)
  - phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor plan 02
    provides: frontend.py (invoke_slang), ast_importer.py (import_assertion)
  - phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor plan 03
    provides: composer.py (compose), emitter.py (emit, write_output), bool_expr template
  - phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor plan 04
    provides: cli.py (main), SV fixture files (bool_assert.sv, delay_assert.sv)
provides:
  - tests/conftest.py: shared fixtures, requires_slang skip marker, assert_golden helper
  - tests/test_integration.py: 12 pipeline tests from JSON fixture to emitted SV (no slang required)
  - tests/test_pipeline_e2e.py: 6 CLI e2e tests (5 @requires_slang, 1 unconditional)
  - golden file fixes: bool_labeled.sv and bool_simple.sv source locs synced to JSON fixtures
  - test_emitter.py update: _labeled_checker() source loc matched to bool_labeled.json
  - complete Phase 1 validation: 126 pass, 5 skip, mypy --strict clean, ruff clean
affects: [all-future-phases (test infrastructure is shared)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - conftest.py with requires_slang marker using shutil.which("slang") for conditional skipping
    - assert_golden() using difflib.unified_diff for readable golden file mismatch diffs
    - cast(dict[str, object], json.loads(...)) for mypy-clean JSON fixture loading
    - CliRunner() (no mix_stderr param — not supported in click 8.4.x)
    - @pytest.fixture() for path fixtures (fixtures_dir, golden_dir) and IR object fixtures

key-files:
  created:
    - tests/conftest.py
    - tests/test_integration.py
    - tests/test_pipeline_e2e.py
    - .planning/phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/05-SUMMARY.md
  modified:
    - tests/golden/bool_labeled.sv (source loc: test.sv:3:5 → test_labeled.sv:2:14)
    - tests/golden/bool_simple.sv (source loc: test.sv:3:5 → test_bool.sv:2:3)
    - tests/test_emitter.py (_labeled_checker() loc → test_labeled.sv:2:14; assertion updated)
    - tests/test_integration.py (cast import; type: ignore removed)
    - tests/test_pipeline_e2e.py (mix_stderr=False removed)
    - tests/test_frontend.py (mock_open typed assignment, type: ignore removed)

key-decisions:
  - "Golden files updated to match actual pipeline output from JSON fixtures — not the old hardcoded emitter test params"
  - "cast(dict[str, object], json.loads(...)) chosen over type: ignore for mypy strict compliance"
  - "mix_stderr=False removed from CliRunner — not a valid parameter in click 8.4.x"
  - "conftest.py assert_golden uses rstrip() per line for whitespace-insensitive comparison"
  - "test_pipeline_e2e.py test 2 checks result.output (combined stdout+stderr) for SVA-E002 / 'unsupported'"

patterns-established:
  - "All fixture-based integration tests use _load(name) + _run(name) helpers — DRY pipeline invocation"
  - "requires_slang = pytest.mark.skipif(not has_slang, ...) imported in test files from conftest"
  - "Golden file tests use assert_golden() from conftest — not inline difflib calls"

requirements-completed: [TEST-01, PARSE-05, OUT-02, OUT-03]

# Metrics
duration: 28min
completed: 2026-05-25
---

# Phase 1 Plan 05: Unit Test Framework + Phase 1 Tests Summary

**Complete test infrastructure (pytest + mypy --strict + ruff) with 131 tests: 12 integration tests from JSON fixtures, 6 CLI e2e tests, shared conftest fixtures, and golden file regression locks on the bool_expr emitter**

## Performance

- **Duration:** ~28 min
- **Started:** 2026-05-25T12:30:00Z
- **Completed:** 2026-05-25T13:00:00Z
- **Tasks:** 4
- **Files modified:** 9 (3 created, 6 modified)

## Accomplishments

- Created `tests/conftest.py` with 5 fixtures (`fixtures_dir`, `golden_dir`, `sample_source_loc`, `sample_clock`, `sample_bool_expr`), `requires_slang` skip marker, and `assert_golden` helper using `difflib.unified_diff`
- Created `tests/test_integration.py` with 12 tests covering the full `import_assertion → compose → emit` pipeline from pre-captured JSON fixtures (no slang required):
  - `test_pipeline_bool_simple`, `test_pipeline_bool_simple_golden` (golden comparison)
  - `test_pipeline_bool_labeled`, `test_pipeline_bool_labeled_golden` (golden comparison)
  - `test_pipeline_source_loc_preserved` (PARSE-05: source location threaded JSON → comment)
  - `test_pipeline_registered_outputs` (OUT-02: no combinational outputs, all `_q` registers)
  - `test_pipeline_sync_reset` (OUT-03: `if (!rst_n)`, ≥4 `<= 1'b0` assignments)
  - `test_pipeline_unsupported_raises` (SVA-E002, non-None source_loc on UnsupportedConstruct)
  - `test_pipeline_bool_complex`, `test_pipeline_header_comments`
  - `test_pipeline_standard_port_contract`, `test_pipeline_observed_signals_as_ports`
- Created `tests/test_pipeline_e2e.py` with 6 CLI tests via `click.testing.CliRunner`:
  - 5 tests decorated `@requires_slang` (skip on machines without slang binary)
  - 1 test unconditional (`test_e2e_nonexistent_input`)
  - Test 3 additionally skips when iverilog absent
- Fixed golden files to match actual pipeline source locations from JSON fixtures
- Achieved: 126 passed, 5 skipped, `mypy --strict` zero errors, `ruff` zero violations

## Task Commits

Each task was committed atomically:

1. **Task 1: conftest.py + golden file fixes + test_emitter.py sync** — `(feat/test(01-05))`
2. **Task 2: test_integration.py** — `(test(01-05))`
3. **Task 3: test_pipeline_e2e.py** — `(test(01-05))`
4. **Task 4: mypy/ruff fixes (cast, mix_stderr removal)** — `(fix(01-05))`

## Files Created/Modified

- `tests/conftest.py` — shared fixtures, `requires_slang`, `assert_golden`
- `tests/test_integration.py` — 12 pipeline integration tests (no slang)
- `tests/test_pipeline_e2e.py` — 6 CLI e2e tests (5 slang-gated, 1 unconditional)
- `tests/golden/bool_labeled.sv` — source loc updated to `test_labeled.sv:2:14`
- `tests/golden/bool_simple.sv` — source loc updated to `test_bool.sv:2:3`
- `tests/test_emitter.py` — `_labeled_checker()` source loc synced; assertion updated
- `tests/test_integration.py` — `cast()` import; `type: ignore` removed
- `tests/test_pipeline_e2e.py` — `mix_stderr=False` removed from `CliRunner()`
- `tests/test_frontend.py` — `mock_open` typed assignment; `type: ignore` removed

## Decisions Made

- **Golden file source locs**: The emitter unit test (`_labeled_checker()`) used hardcoded params that differed from the actual pipeline output when run on `bool_labeled.json`. Resolved by: updating golden files to match pipeline output, and syncing `_labeled_checker()` to use the same source loc as the JSON fixture (`test_labeled.sv:2:14`). This ensures the integration golden test and the emitter unit test both validate the same reference file.
- **`cast()` over `type: ignore`**: `json.loads()` returns `Any` in mypy; using `cast(dict[str, object], ...)` is semantically honest and avoids the `no-any-return` error without suppressing type checking.
- **`CliRunner()` without `mix_stderr`**: click 8.4.x does not support `mix_stderr` as a parameter (documented in Plan 1.4 decisions). Tests check `result.output` which combines stdout+stderr for assertion purposes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Consistency] Golden file source locs differed between emitter unit tests and pipeline integration tests**
- **Found during:** Task 2 (test_integration.py) — golden comparison failed
- **Issue:** `bool_labeled.sv` golden file had `// Source: test.sv:3:5` (emitter unit test params) but pipeline-from-JSON produces `// Source: test_labeled.sv:2:14`
- **Fix:** Updated golden files to match actual pipeline output; updated `_labeled_checker()` in `test_emitter.py` to use `SourceLoc("test_labeled.sv", 2, 14)` so both tests validate the same reference
- **Files modified:** `tests/golden/bool_labeled.sv`, `tests/golden/bool_simple.sv`, `tests/test_emitter.py`
- **Committed in:** Task 1 commit

**2. [Rule 2 - mypy] `type: ignore[return-value]` used with wrong/unnecessary error codes**
- **Found during:** Task 4 (mypy validation) — `uv run mypy tests/ --strict` reported 4 errors
- **Issue 1:** `test_integration.py:37`: `json.loads()` returns `Any`; function typed `dict[str, object]` → `no-any-return`; wrong suppression code used
- **Issue 2:** `test_pipeline_e2e.py:69`: `CliRunner(mix_stderr=False)` — `mix_stderr` not in type stubs
- **Issue 3:** `test_frontend.py:141`: unused `type: ignore[return-value]` on `mock_open()` return
- **Fix:** Used `cast(dict[str, object], json.loads(...))` in test_integration.py; removed `mix_stderr=False` from CliRunner; used typed assignment `result: MagicMock = mock_open(...)` in test_frontend.py
- **Committed in:** Task 4 commit

---

**Total deviations:** 2 auto-fixed (1 golden file consistency, 1 mypy strict compliance)
**Impact on plan:** None — all acceptance criteria fully met

## Issues Encountered

None beyond the deviations described above.

## User Setup Required

None — no external service or binary configuration required for the 126 non-skipped tests.

## Phase 1 Complete

All 5 Phase 1 plans are now complete:

| Plan | Title | Status |
|------|-------|--------|
| 1.1 | Project skeleton + SVA IR | ✅ 2026-05-25 |
| 1.2 | Slang frontend + AST importer | ✅ 2026-05-25 |
| 1.3 | Template emitter + bool_expr template | ✅ 2026-05-25 |
| 1.4 | CLI entry point + error handling | ✅ 2026-05-25 |
| 1.5 | Unit test framework + Phase 1 tests | ✅ 2026-05-25 |

**Requirements satisfied this plan:** TEST-01, PARSE-05, OUT-02, OUT-03

**Phase 1 requirements fully satisfied:** PARSE-01, PARSE-02, PARSE-04, PARSE-05, OUT-01, OUT-02, OUT-03, OUT-07, OUT-08, CLI-05, CLI-06, TEST-01

**Total tests:** 131 collected (126 passed, 5 skipped — all skips are slang-gated e2e tests)

---
*Phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor*
*Completed: 2026-05-25*
