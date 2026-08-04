---
phase: 23-semantic-boundaries
plan: 01
status: complete
completed: 2026-08-04
commit: c6cbfe9
requirements: [BOUND-01, BOUND-02]
requirements-completed: [BOUND-01, BOUND-02]
---

# Plan 23-01 Summary

Added a hashed two-state/single-clock semantic profile and sanitized
machine-readable `UNSUPPORTED` bundles. Real multi-clock properties cannot
collapse onto one clock, and real X/Z literals cannot enter the two-state
solver. Unsupported bundles contain no Yosys inputs or SBY project.

Evidence is in `tests/test_formal_boundaries.py`.
