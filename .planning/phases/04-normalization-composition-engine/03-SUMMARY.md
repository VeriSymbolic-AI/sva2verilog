---
phase: 04-normalization-composition-engine
plan: 03
subsystem: compiler-pipeline
tags: [dump-tree, golden-parity, regression, cli, debug, integration]

# Dependency graph
requires:
  - phase: 04-normalization-composition-engine
    plan: 01
    provides: normalizer.py — pure IR-to-IR normalization pass with normalize() function
  - phase: 04-normalization-composition-engine
    plan: 02
    provides: structural_hash() + compute_hash_map() + normalize in pipeline
provides:
  - debug.py — format_dump_tree() for structured --dump-tree output
  - --dump-tree CLI flag (prints IR + CheckerNode tree with hashes, exits 0)
  - 16 golden parity regression tests (byte-for-byte proof of pipeline transparency)
  - 11 dump-tree tests (8 unit + 3 CLI integration)
  - 2 E2E dump-tree tests in test_pipeline_e2e.py
affects: [05-optimization-passes]

# Tech tracking
tech-stack:
  added: []
  patterns: [--dump-tree debug flag pattern, parametrized golden parity regression, format_dump_tree two-section output]

key-files:
  created:
    - src/sva2rtl/debug.py
    - tests/test_dump_tree.py
    - tests/test_golden_parity.py
  modified:
    - src/sva2rtl/cli.py
    - tests/test_pipeline_e2e.py

key-decisions:
  - "--dump-tree saves raw_node before normalize() to show pre-normalization state"
  - "format_dump_tree outputs two sections: Pre-normalized IR + Composition Tree"
  - "Golden parity test parametrized over all 29 golden files via fixture->golden mapping"
  - "CheckerNode display excludes module_name, source_loc, sva2rtl_version, original_text"

patterns-established:
  - "Debug flag pattern: compute result, format, echo, exit 0 (no side effects)"
  - "Golden parity as parametrized pytest covering all output permutations"

requirements-completed: [PIPE-01, PIPE-02]

# Metrics
duration: 8min
completed: 2026-05-28
---

# Phase 4 Plan 3: Integration + Regression Validation Summary

**--dump-tree CLI flag, golden parity regression suite, full validation — 502 tests pass, zero regressions, Phase 4 complete**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-28T00:10:00Z
- **Completed:** 2026-05-28T00:18:00Z
- **Tasks:** 6
- **Files created:** 3
- **Files modified:** 2

## Accomplishments
- Created `debug.py` — `format_dump_tree()` renders two-section structured text (IR tree + CheckerNode tree with hashes)
- Added `--dump-tree` CLI flag — prints composition tree and exits 0, no RTL emitted
- Created `test_dump_tree.py` — 11 tests (8 unit + 3 CLI integration)
- Added 2 E2E tests to `test_pipeline_e2e.py` for --dump-tree
- Created `test_golden_parity.py` — 16 parametrized tests proving byte-for-byte parity for all 29 golden files through normalize->compose->emit
- Full validation: 502 tests pass, 15 skipped (slang-dependent), mypy --strict clean, ruff clean

## Task Commits

Each task committed atomically:

1. **Task 4.3.1: Create debug.py with format_dump_tree** - `b5c74ba` (feat)
2. **Task 4.3.2: Add --dump-tree flag to cli.py** - `2f075e7` (feat)
3. **Task 4.3.3: Create test_dump_tree.py** - `2b51567` (test)
4. **Task 4.3.4: Add E2E dump-tree tests to test_pipeline_e2e.py** - `85ceb79` (test)
5. **Task 4.3.5: Create golden parity regression test** - `df5df7d` (test)
6. **Task 4.3.6: Full validation + lint fix** - `8f2316a` (fix)

## Files Created/Modified
- `src/sva2rtl/debug.py` — format_dump_tree with _format_ir and _format_checker helpers (149 lines)
- `src/sva2rtl/cli.py` — --dump-tree option + raw_node save + conditional exit
- `tests/test_dump_tree.py` — 11 tests for dump-tree (170 lines)
- `tests/test_pipeline_e2e.py` — 2 new E2E dump-tree tests
- `tests/test_golden_parity.py` — 16 parametrized golden parity tests (175 lines)

## Decisions Made
- `format_dump_tree` excludes volatile params (module_name, source_loc, sva2rtl_version, original_text) from CheckerNode display — matches structural_hash exclusion
- Golden parity test maps fixtures to golden files explicitly (not by module_name discovery) to handle renamed golden files (overlap_impl.sv, nonoverlap_impl.sv)
- `raw_node = node` saved before normalize() to provide authentic pre-normalization state to --dump-tree

## Deviations from Plan

- Plan specified `test_golden_file_count_minimum asserting >= 29` — implemented as written
- Plan mentioned "simulation oracle re-run" as explicit test — simulation tests already run as part of `pytest tests/` (43 simulation tests pass via iverilog); no separate re-run test needed since they're already in the suite

## Issues Encountered
- `implication_bitvec.json` produces a `sva_delay_2_5` module that has different source_loc from the standalone `delay_range.json`-produced golden — the golden file was committed from `delay_range.json`, so the parity test correctly uses only the top-level `sva_bitvec_impl.sv` golden for that fixture

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- Phase 4 is COMPLETE (3/3 plans done)
- Pipeline: import -> normalize -> compose -> emit (production + tests)
- Structural hash ready for Phase 5 CSE optimization
- --dump-tree available for developer debugging of complex compositions
- All golden files verified byte-for-byte — safe to proceed to Phase 5

---
*Phase: 04-normalization-composition-engine*
*Completed: 2026-05-28*
