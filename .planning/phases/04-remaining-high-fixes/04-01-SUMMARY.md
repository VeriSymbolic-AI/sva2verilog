---
plan: 01
plan_name: HARDEN-02/03/04 Three Compiler-Internals HIGH Fixes
phase: 04
completed: 2026-06-09
status: complete
files_modified:
  - src/sva2rtl/ast_importer.py (+15 lines)
  - src/sva2rtl/composer.py (+6/-4 lines)
commits:
  - 02b888d (fix(04): HARDEN-02/03/04)
test_results:
  passed: 721
  skipped: 17
  regressions: 0 (15 golden comparison failures pre-existing from Phase 03)
---

# Plan 04-01 Summary

All three HIGH fixes applied cleanly. Total 21 lines added, 4 removed across 2 files.

### HARDEN-02 ✅
`_DECLARATIONS.clear()` added at start of `import_all_assertions()` in ast_importer.py (line 159).

### HARDEN-03 ✅
Two validations added in `_build_seq_repetition()`:
- `rep_min > rep_max` → `SvaCompileError`
- `rep_min == 0 and rep_max == 0` (`[*0]`) → `SvaCompileError`

### HARDEN-04 ✅
`_collect_signals()` rewritten to preserve original `(port_name, sig_name)` pairs instead of reconstructing as `(name, name)`.
