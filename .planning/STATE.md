---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Open Formal Verification
current_phase: 21
current_phase_name: Scale, Symbolic Witness, and Decomposition
status: ready_to_plan
stopped_at: Phase 20 complete (2/2); ready to plan Phase 21
last_updated: "2026-08-04T01:15:00+08:00"
last_activity: 2026-08-04
last_activity_desc: Completed and verified safety semantics and high-ROI rewrites
progress:
  total_phases: 6
  completed_phases: 2
  total_plans: 4
  completed_plans: 4
  percent: 33
---

# Project State: sva2rtl v2.0

## Current Position

Phases 19 and 20 are complete.  Phase 21 is next.

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

## Latest Local Qualification

- Complete pytest: 1643 passed, 1 skipped, 1 xfailed.
- Verilator simulation: 174 passed, 2 reviewed skips.
- Full Formal: 126 passed, 1 expected xfail.
- Yosys synthesis gates: 80 passed.
- Ruff and mypy: passed.

## Evidence Boundary

- The general bounded formal route still inherits some monitor/NFA construction
  limits; direct scale decoupling remains Phase 21 work.
- True liveness and fairness remain Phase 22 work.
- Remote same-commit CI/nightly/Full Formal evidence is not yet recorded for
  the v2.0 commits.

## Next Work

Plan Phase 21 requirements SCALE-01 through SCALE-05: formal-specific scale,
slice manifests, overlapping-attempt witness checking, decomposition
certificates, and cover-based vacuity gating.

## Performance Metrics

| Phase | Plan | Result |
|---|---|---|
| 19 | 19-01 | Complete |
| 19 | 19-02 | Complete |
| 20 | 20-01 | Complete |
| 20 | 20-02 | Complete |
