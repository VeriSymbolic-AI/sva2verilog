---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Open Formal Verification
status: executing
last_updated: "2026-08-04"
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 12
  completed_plans: 11
  percent: 83
---

# Project State: sva2rtl v2.0

## Current Position

Phase: 24 — EXECUTING
Plan: 2 of 2
Phases 19 through 23 and Phase 24 Plan 01 are complete. Plan 02 remote
qualification is executing.

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

- Complete Icarus/default suite: 1722 passed, 3 conditional skips, 1 expected
  dynamically classified k-induction xfail.
- Verilator simulation/fast differential selection: 174 passed, 1 selected-out
  skip; explicit fixed-seed fast differential: 16 passed per backend.
- Rotating-seed slow differential: 1 passed per backend.
- Full Formal selection: 212 passed, 2 conditional live-solver skips, 1 expected
  k-induction xfail; generated RTL synthesis/lint: 133 passed.
- Critical mutation modules: bool semantics 25/25, behavioral oracle 135/135,
  composer 51/51, AST importer 124/124; RTL template mutations 12/12.
- Aggregate branch coverage: 86.89%; formal CLI/flow/lowering are independently
  gated at 85%/80%/75% minimums.
- Python 3.14 semantic axis: 1321 passed; wheel/sdist external-install smoke and
  source/archive privacy scans passed.
- Ruff, strict mypy, lock check, shell syntax, and diff check passed.

## Evidence Boundary

- Real live good/bad solver qualification remains conditional because local
  macOS ARM has no Super Prove executable.

- Remote same-commit CI/nightly/Full Formal evidence is not yet recorded for
  the v2.0 commits.

## Next Work

Commit and push the final anonymous main candidate, then require exact-head success for push
CI, nightly differential/mutation, and all eight Full Formal shards. Linux must
run both real live good/bad cases with no skip before EVID-05 can close.

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
| 24 | 24-01 | Complete |
| 24 | 24-02 | Executing |
