---
plan: 01
plan_name: pytest --simulator infrastructure + C++ wrapper template
phase: 02
completed: 2026-06-05
status: complete
files_written:
  - tests/conftest.py (updated)
  - tests/simulation/conftest.py (updated)
  - tests/simulation/wrapper.cpp.j2 (new)
commits:
  - 917ac4d (feat(02-01): add --simulator pytest flag, dual-simulator conftest, and Verilator C++ wrapper template)
---

# Plan 02-01 Summary

All 3 tasks complete. `pytest --help` shows `--simulator` flag. `wrapper.cpp.j2` renders valid Verilator C++ code.
