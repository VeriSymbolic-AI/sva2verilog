---
phase: 04-normalization-composition-engine
plan: 01
subsystem: compiler-pipeline
tags: [normalization, ir, dataclass, match-case, bottom-up-traversal]

# Dependency graph
requires:
  - phase: 03-remaining-tier-1-operators-named-sequences-simulation-valida
    provides: Frozen dataclass IR hierarchy (SVANode, SeqConcat, SeqRepetition, SignalFunc, PropImplication, DisableIff)
provides:
  - normalizer.py — pure IR-to-IR normalization pass with [*1] removal and SeqConcat flattening
  - 17 unit tests proving idempotency, identity preservation, and rule correctness
affects: [04-normalization-composition-engine/02-PLAN, 04-normalization-composition-engine/03-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns: [bottom-up single-pass IR normalization, match/case dispatch for IR rewrites]

key-files:
  created:
    - src/sva2rtl/normalizer.py
    - tests/test_normalizer.py
  modified: []

key-decisions:
  - "PropImplication(overlapping=False) is NOT desugared by normalizer (D-05 golden parity)"
  - "Bottom-up single-pass traversal — no fixed-point iteration needed"
  - "Normalizer is idempotent by design: normalize(normalize(x)) == normalize(x)"

patterns-established:
  - "Pure IR-to-IR transform as standalone module with single public function"
  - "Bottom-up traversal: normalize children first, then apply rule to parent"

requirements-completed: [PIPE-01]

# Metrics
duration: 5min
completed: 2026-05-28
---

# Phase 4 Plan 1: IR Normalization Pass Summary

**Bottom-up IR normalizer with [*1] identity removal, SeqConcat flattening, and idempotency guarantee — 17 tests, mypy --strict clean**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-28T00:00:00Z
- **Completed:** 2026-05-28T00:05:00Z
- **Tasks:** 5
- **Files modified:** 2

## Accomplishments
- Created `normalizer.py` — pure IR-to-IR preprocessing pass with bottom-up single-pass traversal
- Implemented `[*1]` identity removal (trivial repetition node becomes inner expression)
- Implemented SeqConcat flattening (nested concats spliced into parent, handles 3+ levels)
- Preserved PropImplication(overlapping=False) unchanged per D-05 (golden file parity)
- Full test coverage: 17 tests covering identity, rules, idempotency, and edge cases

## Task Commits

Each task was committed atomically:

1. **Task 4.1.1: Create normalizer.py with bottom-up traversal skeleton** - `1e455a2` (feat)
2. **Tasks 4.1.2-4.1.4: [*1] removal, SeqConcat flatten, PropImplication preservation** - included in `1e455a2` (rules were integral to the skeleton's `_normalize_node` dispatch)
3. **Task 4.1.5: Comprehensive unit tests for normalizer** - `d71b318` (test)

## Files Created/Modified
- `src/sva2rtl/normalizer.py` - Pure IR normalization pass (180 lines)
- `tests/test_normalizer.py` - 17 unit tests (250 lines)

## Decisions Made
- Combined tasks 4.1.1-4.1.4 into a single implementation commit since the normalization rules are each 2-3 lines within `_normalize_node` and cannot meaningfully exist without the traversal skeleton
- Used inline `SeqConcat`/`SeqRepetition`/etc. construction in match cases to avoid mypy variable type narrowing issues

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `normalizer.py` is ready for Plan 4.2 integration (wire into CLI pipeline + structural hash)
- All 470 existing tests continue to pass (no regressions)
- `normalize()` API matches the interface expected by Plan 4.2: `compose(normalize(ir_root), ...)`

---
*Phase: 04-normalization-composition-engine*
*Completed: 2026-05-28*
