---
phase: 05-optimization-passes
plan: 01
subsystem: compiler-pipeline
tags: [optimizer, constant-fold, concat-merge, cli, pytest, mypy, ruff]

# Dependency graph
requires:
  - phase: 04-normalization-composition-engine
    provides: structural_hash, compute_hash_map, CheckerNode tree, composer.compose(), normalizer.normalize()

provides:
  - optimizer.py with optimize(), constant_fold(), concat_merge(), cse/counter_merge/dead_node stubs
  - _walk_bottom_up() bottom-up tree traversal helper
  - --no-optimize CLI flag skipping all optimization passes
  - 22 unit tests covering constant_fold, concat_merge, idempotency, integration

affects: [05-optimization-passes/02, 05-optimization-passes/03, 06-cli-polish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "optimizer.py mirrors normalizer.py: pure tree transform, idempotent, bottom-up traversal"
    - "dataclasses.replace() for creating mutated CheckerNode copies (frozen dataclass)"
    - "_walk_bottom_up() helper: generic recursive bottom-up transform pattern"
    - "structural_hash() before/after comparison for early-exit convergence detection"

key-files:
  created:
    - src/sva2rtl/optimizer.py
    - tests/test_optimizer.py
  modified:
    - src/sva2rtl/cli.py
    - tests/test_cli.py

key-decisions:
  - "concat_merge operates on CheckerNode tree (post-compose), not SVA IR level — matches plan spec"
  - "optimize() loops max 2 iterations using structural_hash comparison for fixed-point detection"
  - "constant_fold tags nodes with _const_true/_const_false params for downstream dead_node pass"
  - "three consecutive delays need 2 concat_merge passes; optimize() 2-iteration loop handles this"
  - "mock sva2rtl.cli.optimize in CLI tests (not the real optimize) to keep unit test isolation"

patterns-established:
  - "Optimizer pass: def pass_name(root: CheckerNode) -> CheckerNode"
  - "All optimizer files use from __future__ import annotations + mypy --strict compatible"
  - "New CLI stages must be mocked in test_cli.py pipeline tests"

requirements-completed:
  - PIPE-03
  - PIPE-04
  - PIPE-05

# Metrics
duration: 35min
completed: 2026-05-28
---

# Phase 5.1: Optimizer Framework + Constant Folding + Concat Merging Summary

**Optimizer pass pipeline (constant_fold + concat_merge) wired into CLI with --no-optimize flag; adjacent delays ##3 ##2 → ##5; 524 tests pass, mypy --strict + ruff clean**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-05-28T09:15:00Z
- **Completed:** 2026-05-28T09:50:00Z
- **Tasks:** 5
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments
- Created `src/sva2rtl/optimizer.py` with full pass orchestration (`optimize()`), `constant_fold`, `concat_merge`, and stubs for `cse`, `counter_merge`, `dead_node`
- `--no-optimize` CLI flag wired; pipeline docstring updated to include `optimize` step
- 22 unit tests covering all acceptance criteria: identity, constant fold rules, concat merge rules, idempotency, integration
- Regression: 524 tests pass (up from 502), 15 skipped; no golden file changes

## Task Commits

Each task was committed atomically:

1. **Task 5.1.1: optimizer.py with pass orchestration + constant_fold** - `e9f7a26` (feat)
2. **Task 5.1.2: concat_merge pass (marker commit, already in 5.1.1)** - `af466c1` (feat)
3. **Task 5.1.3: --no-optimize CLI flag** - `db8e995` (feat)
4. **Task 5.1.4: unit tests (22 tests)** - `050001a` (test)
5. **Task 5.1.5: regression fix (CLI test mocks + E501 fix)** - `3a794e6` (fix)

## Files Created/Modified
- `src/sva2rtl/optimizer.py` — Full optimizer module: optimize(), constant_fold(), concat_merge(), cse/counter_merge/dead_node stubs, _walk_bottom_up() helper
- `src/sva2rtl/cli.py` — Added `from sva2rtl.optimizer import optimize`, `--no-optimize` flag, optimize() call in pipeline
- `tests/test_optimizer.py` — 22 unit tests covering all optimizer passes
- `tests/test_cli.py` — Added optimize mock to 3 tests; updated pipeline call order expectation

## Decisions Made
- `concat_merge` operates on the CheckerNode tree (post-compose) using `template_name == "concat_delay"` detection — matches plan D-03 / 05-CONTEXT.md spec
- `optimize()` uses structural_hash for fixed-point detection (max 2 iterations) — three consecutive delays need 2 passes, converge in second iteration
- CLI tests mock `sva2rtl.cli.optimize` (not the real function) to maintain unit test isolation — avoids MagicMock TypeError in structural_hash()

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] CLI test MagicMock TypeError in structural_hash()**
- **Found during:** Task 5.1.5 (regression validation)
- **Issue:** Three CLI tests mock `compose` to return MagicMock; when `optimize(checker_node)` was added to pipeline, `structural_hash(mock)` failed because `mock.template_name.encode()` returns MagicMock (not bytes)
- **Fix:** Added `patch("sva2rtl.cli.optimize", return_value=mock_checker)` to the three affected tests; updated pipeline call order assertion to include "optimize"
- **Files modified:** `tests/test_cli.py`
- **Verification:** All 9 CLI tests pass; `ruff check tests/test_cli.py` clean
- **Committed in:** `3a794e6` (Task 5.1.5 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking — CLI test isolation)
**Impact on plan:** Auto-fix necessary for correctness. No scope creep.

## Issues Encountered
- Initial commits accidentally went to the main branch (`/Users/allenenli/Documents/formal_sva_rtl/`) instead of the worktree because `cd /path/to/main/repo` was prepended to git commands. Fixed by resetting main branch with `git reset --hard HEAD~1` and rewriting all files to the worktree path. All subsequent work used the worktree CWD exclusively.

## Next Phase Readiness
- Phase 5.2 (CSE deduplication + counter merging) can proceed immediately
- `cse()` and `counter_merge()` stubs in optimizer.py are ready to be filled in
- `structural_hash()` from composer.py is already imported in optimizer.py for CSE use
- Test pattern in `test_optimizer.py` provides factory helpers reusable by Plan 5.2

---
*Phase: 05-optimization-passes*
*Completed: 2026-05-28*
