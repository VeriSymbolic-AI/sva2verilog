---
phase: 05-optimization-passes
plan: 02
subsystem: compiler-pipeline
tags: [optimizer, cse, counter-merge, templates, golden-files, pytest, mypy, ruff]

# Dependency graph
requires:
  - phase: 05-optimization-passes
    plan: 01
    provides: optimizer.py with cse/counter_merge stubs, _walk_bottom_up(), concat_merge, constant_fold

provides:
  - cse() pass: structural_hash-based deduplication with Python id() identity sharing
  - counter_merge() pass: safety-net for same-hash concat_delay nodes CSE might miss
  - _build_hash_groups(), _cse_canonical_name(), _rebuild_with_cse(), _collect_by_template() helpers
  - seq_concat_top.sv.j2 indexed instance names: u_{{ module_name }}_{{ loop.index0 }}
  - 16 new unit tests (38 total) covering cse, counter_merge, integration
  - 4 updated golden files (sva_prop_81cf66e0, sva_prop_e9edaa37, sva_prop_75080d6b, sva_prop_5c9caf75)

affects: [05-optimization-passes/03, 06-cli-polish]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_build_hash_groups: recursive walk returns dict[structural_hash → list[CheckerNode]]"
    - "_rebuild_with_cse: top-down rebuild with rebuilt_canonical cache for Python id() identity"
    - "Root node protection: check h == root_hash first; rebuild children but never rename root"
    - "counter_merge is a safety-net no-op after CSE for single-property trees"
    - "seq_concat_top.sv.j2: loop.index0 suffix on instance names prevents SV collision with CSE"
    - "Golden file regen: uv run python script calling emit_all() on fixtures"

key-files:
  modified:
    - src/sva2rtl/optimizer.py
    - templates/seq_concat_top.sv.j2
    - tests/test_optimizer.py
    - tests/golden/sva_prop_81cf66e0.sv
    - tests/golden/sva_prop_e9edaa37.sv
    - tests/golden/sva_prop_75080d6b.sv
    - tests/golden/sva_prop_5c9caf75.sv

key-decisions:
  - "cse() builds hash groups bottom-up then rebuilds top-down; avoids double-visit via rebuilt_canonical cache"
  - "Root node protected by h == root_hash check; root's children are still rebuilt (CSE children of root)"
  - "counter_merge conservative: only merges same-structural-hash concat_delay nodes with different module_names"
  - "Instance name indexing: u_{{ child.module_name }}_{{ loop.index0 }} — loop.index0 is unique per position"
  - "Golden files regenerated via pipeline (import_assertion + compose + emit_all), not manually patched"
  - "test_optimize_pipeline_deduplicates_identical_delays uses non-adjacent delays — concat_merge runs first and merges adjacent ones, leaving none for CSE"

patterns-established:
  - "CSE helper pattern: _build_hash_groups + _rebuild_with_cse(rebuilt_canonical dict) for sharing"
  - "Golden file regeneration: small Python script using emit_all() is more robust than manual sed"

requirements-completed:
  - PIPE-03
  - PIPE-04
  - PIPE-05

# Metrics
duration: 30min
completed: 2026-05-28
---

# Phase 5.2: CSE Deduplication + Counter Merging Summary

**CSE and counter_merge passes implemented; seq_concat_top indexed instance names prevent SV collisions; 540 tests pass (up from 524), mypy --strict + ruff clean**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-28T10:20:00Z
- **Completed:** 2026-05-28T10:50:00Z
- **Tasks:** 5 (5.2.1 through 5.2.5)
- **Files modified:** 7 (1 core, 1 template, 1 test file, 4 golden files)

## Accomplishments

- Replaced `cse()` stub with full implementation: structural_hash grouping, canonical naming (`sva_cse_concat_delay_{min}_{max}`), top-down rebuild with `rebuilt_canonical` cache for Python `id()` identity sharing
- Replaced `counter_merge()` stub with implementation: collects `concat_delay` nodes, groups by structural hash, assigns `sva_cse_counter_{min}_{max}` for same-hash nodes with different module names; effectively a safe no-op after CSE in single-property trees
- Added `import logging` + `_LOG.warning()` for cse_origin sanity check (D-05)
- New helpers: `_build_hash_groups`, `_cse_canonical_name`, `_rebuild_with_cse`, `_collect_by_template`
- Fixed instance name collision in `seq_concat_top.sv.j2`: `u_{{ child.module_name }}` → `u_{{ child.module_name }}_{{ loop.index0 }}`
- Regenerated 4 golden files with indexed instance names
- Added 16 new tests (38 total in test_optimizer.py): CSE identity, deduplication, canonical naming, Python id() sharing, root protection, deep tree, counter_merge identity/merge/no-merge/after-cse, pipeline integration

## Task Commits

1. **Task 5.2.1+5.2.2: CSE + counter_merge implementation** — `fdadc4d` (feat)
2. **Task 5.2.3: seq_concat_top template + golden file update** — `6c87b28` (fix)
3. **Task 5.2.4: 16 new unit tests** — `c09b541` (test)

(Tasks 5.2.5 golden file validation included in commit `6c87b28`; all 13 golden match tests pass)

## Files Created/Modified

- `src/sva2rtl/optimizer.py` — Full cse() + counter_merge() + 4 helpers; 275 net new lines
- `templates/seq_concat_top.sv.j2` — Instance name now `u_{{ child.module_name }}_{{ loop.index0 }}`
- `tests/test_optimizer.py` — 16 new tests; import line updated to include `counter_merge, cse`
- `tests/golden/sva_prop_81cf66e0.sv` — `u_sva_prop_81cf66e0_e0` → `u_sva_prop_81cf66e0_e0_0`, etc.
- `tests/golden/sva_prop_e9edaa37.sv` — Same pattern for e9edaa37 fixture
- `tests/golden/sva_prop_75080d6b.sv` — Same pattern for 75080d6b fixture
- `tests/golden/sva_prop_5c9caf75.sv` — Same pattern for 5c9caf75 fixture (5 children → indices 0-4)

## Decisions Made

- **Root protection via hash check**: `_rebuild_with_cse` checks `h == root_hash` first; never renames root but still rebuilds its children recursively — so CSE applies to all descendants
- **counter_merge as safety net**: After CSE, same-hash nodes already share module_name; `len(module_names) == 1` guard makes counter_merge a no-op. Useful for future cross-property sharing (D-11)
- **Instance name indexing with loop.index0**: Simpler than alternative approaches (UUID, hash suffix); always unique within a single `seq_concat_top` instantiation; backwards-compatible with non-CSE trees
- **Golden file regen via Python script**: More reliable than manual sed; ensures exact emitter output including whitespace

## Deviations from Plan

### Auto-fixed Issues

**1. [Non-blocking] test_optimize_pipeline_deduplicates_identical_delays wrong assumption**
- **Found during:** Task 5.2.4 test run
- **Issue:** Test built `[delay(3,3), delay(3,3)]` and expected CSE to deduplicate them, but `concat_merge` runs first and merges adjacent identical delays into `delay(6,6)` — nothing left for CSE
- **Fix:** Changed test to use `[delay(3,3), bool_expr, delay(3,3)]` — delays are non-adjacent so concat_merge skips them; CSE then deduplicates correctly
- **Verification:** Test passes; assertion updated to check `delay_children[0].module_name == delay_children[1].module_name`

---

**Total deviations:** 1 auto-fixed (non-blocking test logic issue)
**Impact on plan:** No scope change.

## Regression

- **Before:** 524 tests pass, 15 skipped
- **After:** 540 tests pass, 15 skipped (+16 new tests, all green)
- **mypy --strict src/sva2rtl/optimizer.py:** 0 issues
- **ruff check src/sva2rtl/ tests/:** 0 issues (warnings only for removed rules ANN101/ANN102)

## Next Phase Readiness

- Phase 5.3 (dead_node elimination) can proceed: `dead_node()` stub is in optimizer.py, `_const_false` tags from `constant_fold()` are ready to be consumed
- CSE canonical naming convention established; emitter's existing `module_name not in results` dedup correctly handles shared nodes
- All 540 tests pass; golden files current; no technical debt

---
*Phase: 05-optimization-passes*
*Plan: 02*
*Completed: 2026-05-28*
