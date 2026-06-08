---
plan: 02
plan_name: Migrate Complex Templates (Wave 2)
phase: 03
completed: 2026-06-08
status: complete
files_written:
  - templates/concat_delay.sv.j2 (refactored)
  - templates/overlap_bitvec.sv.j2 (refactored)
  - templates/nonoverlap.sv.j2 (refactored)
  - templates/rep_consecutive.sv.j2 (refactored)
  - templates/disable_iff_top.sv.j2 (refactored)
  - templates/seq_concat_top.sv.j2 (refactored)
commits:
  - 93b5842 (feat(03-02): migrate all 11 templates — macros + HARDEN-01 fix complete)

# Plan 03-02 Summary

All 11 templates migrated. Net -289 lines in templates/. 643 non-simulation + 78 simulation tests pass.
