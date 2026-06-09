---
plan: 01
phase: 05
completed: 2026-06-09
status: complete
files_modified:
  - src/sva2rtl/cli.py (+100/-19)
commits:
  - 79e75d6 (fix(05): HARDEN-05/06/07/08)
test_results:
  passed: 721
  skipped: 17
  regressions: 0
---

# Plan 05-01 Summary

All four CLI fixes applied. Net +81 lines in cli.py.

- **HARDEN-05**: Per-assertion unoptimized_checker + dump-ir multi-prop fix
- **HARDEN-06**: Three-mode matching (label → index → @line)
- **HARDEN-07**: _resolve_output_mode helper with file-extension detection
- **HARDEN-08**: --verilog + --dump-* hard reject
