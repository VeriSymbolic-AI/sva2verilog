---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Open Formal Verification
status: ready_to_plan
last_updated: "2026-08-03T17:29:27Z"
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 6
  completed_plans: 6
  percent: 50
---

# Project State: sva2rtl v2.0

## Current Position

Phase: 22 (Open Liveness Backend) — READY TO PLAN
Plan: Not yet planned
Phases 19 through 21 are complete. Phase 22 is next.

## Verified v2.0 Evidence

- Dedicated user-DUT open-formal command with source-isolated evidence bundles.
- Correct real DUT: PROVEN; buggy real DUT: FAILED with trace; BMC PASS: UNKNOWN.
- Unbounded always uses direct invariant safety with no finite PASS monitor.
- Nexttime uses an exact fixed-delay property rewrite.
- Structured Boolean semantics retain width/signedness and support reductions
  plus relational comparisons through generated and direct-formal ports.

- Bare temporal sequences reject after a real false-PROVEN regression was found.
- Goto/nonconsecutive occurrence obligations classify as liveness and do not
  enter the safety backend.
- Symbolic-witness safety handles bounded implications beyond monitor K/T
  budgets and matches exhaustive small-trace attempt semantics.
- Proof PASS is retained only when a separate critical-cover task is REACHED;
  vacuous antecedents downgrade the result to UNKNOWN.
- Logical slice manifests and input-bound decomposition proof certificates are
  hashed into replayable evidence.

## Latest Local Qualification

- Phase 21 focused formal/evidence suite: 66 passed.
- Complete pytest baseline before Phase 21: 1643 passed, 1 skipped, 1 xfailed.
- Verilator simulation: 174 passed, 2 reviewed skips.
- Full Formal: 126 passed, 1 expected xfail.
- Yosys synthesis gates: 80 passed.
- Ruff and mypy: passed.

## Evidence Boundary

- True liveness and fairness remain Phase 22 work.
- Remote same-commit CI/nightly/Full Formal evidence is not yet recorded for
  the v2.0 commits.

## Next Work

Plan Phase 22 requirements LIVE-01 through LIVE-03: open live-engine discovery,
strong-until obligation splitting, and hashed fairness assumptions.

## Performance Metrics

| Phase | Plan | Result |
|---|---|---|
| 19 | 19-01 | Complete |
| 19 | 19-02 | Complete |
| 20 | 20-01 | Complete |
| 20 | 20-02 | Complete |
| 21 | 21-01 | Complete |
| 21 | 21-02 | Complete |
