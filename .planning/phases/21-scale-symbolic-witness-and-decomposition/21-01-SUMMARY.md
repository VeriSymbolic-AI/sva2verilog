---
phase: 21-scale-symbolic-witness-and-decomposition
plan: 01
status: complete
requirements: [SCALE-01, SCALE-03]
requirements-completed: [SCALE-01, SCALE-03]
---

# Plan 21-01 Summary

Implemented a formal-only symbolic-witness backend for bounded implications.
It recognizes Boolean, exact/ranged delay, `nexttime[N]`, and consecutive
bounded consequent shapes while preserving overlap offsets and typed observed
signals. `auto`, `monitor`, and `symbolic-witness` attempt modes are exposed by
the formal CLI.

The emitted harness uses an unconstrained witness selector, so proof is
universal over every selectable antecedent attempt without allocating a fixed
hardware thread per overlap. Exhaustive small-trace reference comparisons and
real SymbiYosys good/bad DUT tests, including delay 64, passed.

Verification: 57 focused tests passed; Ruff, mypy, and `git diff --check`
passed.
