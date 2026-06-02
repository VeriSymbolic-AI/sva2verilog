---
phase: 04-normalization-composition-engine
plan: 02
subsystem: compiler-pipeline
tags: [structural-hash, sha256, normalize, pipeline-integration, composition]

# Dependency graph
requires:
  - phase: 04-normalization-composition-engine
    plan: 01
    provides: normalizer.py — pure IR-to-IR normalization pass with normalize() function
provides:
  - structural_hash() — deterministic SHA-256 content hash for CheckerNode trees
  - compute_hash_map() — tree-wide module_name -> hash mapping for Phase 5 CSE
  - normalize() wired into CLI pipeline (cli.py) and integration tests
  - 8 new tests proving parity and hash correctness
affects: [04-normalization-composition-engine/03-PLAN, 05-optimization-passes]

# Tech tracking
tech-stack:
  added: []
  patterns: [SHA-256 structural hashing with volatile-param exclusion, normalize-before-compose pipeline pattern]

key-files:
  created: []
  modified:
    - src/sva2rtl/composer.py
    - src/sva2rtl/cli.py
    - tests/test_integration.py
    - tests/test_composer.py

key-decisions:
  - "_VOLATILE_PARAMS excludes module_name, source_loc, sva2rtl_version, original_text from hash"
  - "8-char hex prefix (32 bits) sufficient for display — collision negligible for <1000 nodes"
  - "compute_hash_map keyed by module_name (unique per tree) — returned externally, not stored on frozen node"

patterns-established:
  - "Pipeline pattern: import -> normalize -> compose -> emit (normalize always runs, transparent for canonical inputs)"
  - "Structural hash computed post-composition as external dict, not on frozen dataclass"

requirements-completed: [PIPE-02]

# Metrics
duration: 5min
completed: 2026-05-28
---

# Phase 4 Plan 2: Structural Hash + Pipeline Integration Summary

**SHA-256 structural hashing for CheckerNode trees + normalize() wired into CLI and test pipelines — 478 tests pass, zero golden file regressions**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-28T00:05:00Z
- **Completed:** 2026-05-28T00:10:00Z
- **Tasks:** 5
- **Files modified:** 4

## Accomplishments
- Added `structural_hash()` and `compute_hash_map()` to composer.py — deterministic SHA-256 content hashing that excludes volatile metadata (module_name, source_loc, sva2rtl_version, original_text)
- Wired `normalize()` into cli.py between import_assertion and compose — production pipeline now canonicalizes IR before composition
- Wired `normalize()` into test_integration.py `_run()` helper — integration tests mirror production path
- Added 8 new tests: 4 normalize->compose parity tests + 4 structural hash tests
- Verified all 478 tests pass (470 existing + 8 new), zero golden file regressions

## Task Commits

Each task was committed atomically:

1. **Task 4.2.1: Add structural_hash function to composer.py** - `55b5865` (feat)
2. **Task 4.2.2: Insert normalize() into cli.py pipeline** - `dcef323` (feat)
3. **Task 4.2.3: Insert normalize() into test_integration.py _run() helper** - `ff440ce` (feat)
4. **Task 4.2.4: Add normalize->compose parity tests to test_composer.py** - `f50737b` (test)
5. **Task 4.2.5: Run full existing test suite** - no commit (verification only, 0 failures)

## Files Created/Modified
- `src/sva2rtl/composer.py` - Added _VOLATILE_PARAMS, structural_hash(), compute_hash_map(), _collect_hashes()
- `src/sva2rtl/cli.py` - Added normalize import + call between import_assertion and compose
- `tests/test_integration.py` - Added normalize import + call in _run() helper
- `tests/test_composer.py` - Added 8 new tests (4 parity + 4 hash)

## Decisions Made
- Used 8-char hex prefix (not full 64-char SHA-256) for compact display in --dump-tree
- Hash excludes exactly 4 volatile params — all other params contribute to structural identity
- compute_hash_map returns external dict rather than modifying frozen CheckerNode (preserves immutability)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pipeline now runs normalize->compose for all inputs (CLI + tests)
- structural_hash ready for Phase 5 CSE candidate detection
- compute_hash_map ready for --dump-tree display (Plan 4.3)
- All golden files verified byte-for-byte parity — safe to proceed to Plan 4.3

---
*Phase: 04-normalization-composition-engine*
*Completed: 2026-05-28*
