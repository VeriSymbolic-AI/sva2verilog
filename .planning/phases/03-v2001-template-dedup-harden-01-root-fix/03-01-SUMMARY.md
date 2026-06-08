---
plan: 01
plan_name: Create Shared Macros + Migrate Simple Templates (Wave 1)
phase: 03
completed: 2026-06-08
status: complete
files_written:
  - templates/_macros.sv.j2 (new)
  - templates/_attempt_fired_macro.sv.j2 (new)
  - templates/bool_expr.sv.j2 (refactored)
  - templates/rose.sv.j2 (refactored)
  - templates/fell.sv.j2 (refactored)
  - templates/stable.sv.j2 (refactored)
  - templates/past.sv.j2 (refactored)
  - tests/test_emitter.py (test updated for new sticky pattern)
commits:
  - 68985a1 (feat(03-01): create shared macros + migrate 5 simple templates)
  - 93b5842 (feat(03-02): includes Wave 2 too)

# Plan 03-01 Summary

All 5 simple templates migrated. Macros created. Simulation tests pass.
