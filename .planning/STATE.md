---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Open Formal Verification
current_phase: 24
current_phase_name: Evidence Closure and Release Qualification
status: ready_to_plan
last_updated: "2026-08-04T00:00:00Z"
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 10
  completed_plans: 10
  percent: 83
---

# Project State: sva2rtl v2.0

## Current Position

Phase: 24 (Evidence Closure and Release Qualification) — READY TO PLAN
Plan: Not yet planned
Phases 19 through 23 are complete. Phase 24 is next.

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

- Selected Boolean unbounded eventual and strong-until shapes route to an open
  SBY live backend without entering monitor synthesis.

- Strong until splits safety from eventual discharge; explicit fairness is
  identifier-restricted, replayable, and hashed.

- Missing Super Prove yields actionable UNKNOWN while the AIG preparation and
  separate cover path remain testable.
- Multi-clock and X/Z-dependent formal inputs produce sanitized, hashed
  UNSUPPORTED evidence without entering Yosys.
- One automatic scalar local-capture shape uses private per-attempt symbolic
  witness state; good/bad/changing-value solver cases distinguish outcomes.

## Latest Local Qualification

- Phase 23 focused boundary/formal/document suite: 117 passed, 2 conditional skips.
- Complete pytest baseline before Phase 21: 1643 passed, 1 skipped, 1 xfailed.
- Verilator simulation: 174 passed, 2 reviewed skips.
- Full Formal: 126 passed, 1 expected xfail.
- Yosys synthesis gates: 80 passed.
- Ruff and mypy: passed.

## Evidence Boundary

- Real live good/bad solver qualification remains conditional because local
  macOS ARM has no Super Prove executable.

- Remote same-commit CI/nightly/Full Formal evidence is not yet recorded for
  the v2.0 commits.

## Next Work

Plan Phase 24 requirements EVID-01 through EVID-05: corpus/status closure,
formal-vs-monitor matrix, complete local qualification, package/privacy gates,
and exact-commit remote evidence.

## Performance Metrics

| Phase | Plan | Result |
|---|---|---|
| 19 | 19-01 | Complete |
| 19 | 19-02 | Complete |
| 20 | 20-01 | Complete |
| 20 | 20-02 | Complete |
| 21 | 21-01 | Complete |
| 21 | 21-02 | Complete |
| 22 | 22-01 | Complete |
| 22 | 22-02 | Complete |
| 23 | 23-01 | Complete |
| 23 | 23-02 | Complete |
