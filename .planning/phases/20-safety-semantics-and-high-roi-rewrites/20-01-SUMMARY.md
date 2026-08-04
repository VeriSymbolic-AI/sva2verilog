---
phase: 20-safety-semantics-and-high-roi-rewrites
plan: 01
status: complete
completed: 2026-08-04
requirements-completed: [SAFE-03, SAFE-04]
commit: 741f948
---

# Phase 20 Plan 01 Summary

- Added formal-only `PropAlways` and fixed-delay `PropNexttime` IR.
- Imported verified slang v11 `Always`, `SAlways`, `NextTime`, and `SNextTime` AST shapes.
- Normalized nexttime to the existing exact-delay sequence kernel.
- Added `direct-invariant-safety`, which emits no finite-PASS monitor RTL.
- Real SBY good/bad DUT tests distinguish PROVEN from FAILED for both routes.
- Preserved monitor CLI fail-closed behavior for unbounded always.
- Fixed partial always-range ASTs so they reject instead of masquerading as unbounded syntax.

## Verification

- Phase-targeted safety/import/normalizer tests: 130 passed before the boundary fix.
- Partial-range regression plus affected suites: 79 passed after the fix.
- Ruff and mypy passed for the implementation slice.
- Full suite exposed exactly one partial-range regression; the corrected case is now green and will be rechecked in the Phase 20 final full run.
