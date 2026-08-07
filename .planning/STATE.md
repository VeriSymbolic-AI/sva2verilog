---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Open Formal Verification
status: complete
last_updated: "2026-08-07"
progress:
  total_phases: 6
  completed_phases: 6
  total_plans: 12
  completed_plans: 12
  percent: 100
---

# Project State: sva2rtl v2.0

## Current Position

Phase: 24 — COMPLETE
Plan: 2 of 2
Phases 19 through 24 and all twelve v2.0 plans are complete. The milestone
audit cross-references requirement checkboxes, plan summaries, phase
verifications, end-to-end flows, and exact-commit remote evidence.

## Verified v2.0 Evidence

- Dedicated user-DUT open-formal command with source-isolated evidence bundles.
- Correct real DUT: PROVEN; buggy real DUT: FAILED with trace; BMC PASS: UNKNOWN.
- Unbounded always uses direct invariant safety with no finite PASS monitor.
- Nexttime uses an exact fixed-delay property rewrite.
- Structured Boolean semantics retain width/signedness and support reductions
  plus relational comparisons through generated and direct-formal ports.
- Typed observations accept only a complete scalar or one-dimensional packed
  grammar; multi-dimensional/complex signal types reject before they can create
  a truncated false proof model. Type checking is scoped to the actual formal
  interface so unrelated complex DUT signals do not widen the property contract.

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

- Complete Icarus/default suite: 1752 passed, 3 conditional skips, 1 expected
  dynamically classified k-induction xfail.
- Verilator simulation selection: 174 passed, 1 reviewed skip; explicit
  fixed-seed fast differential: 16 passed per backend.
- Rotating-seed slow differential: 1 passed per backend.
- Full Formal selection: 222 passed, 2 conditional live-solver skips, 1 expected
  k-induction xfail; generated RTL synthesis/lint: 133 passed.
- Critical mutation modules: bool semantics 25/25, behavioral oracle 135/135,
  composer 51/51, AST importer 123/123; RTL template mutations 12/12. Across
  the four Python surfaces, 334/334 covered mutants were killed and 56
  uncovered candidates remain outside the score.
- Aggregate branch coverage: 87.03%; formal CLI/flow/lowering are independently
  gated at 85%/80%/75% minimums.
- Python 3.14 semantic axis: 1330 passed; wheel/sdist external-install smoke and
  source/archive privacy scans passed.
- Ruff, strict mypy, lock check, shell syntax, and diff check passed.
- The first exact-SHA remote attempt exposed a stale Icarus skip budget and a
  Python matrix environment-selection defect. Both CI contracts were corrected
  and regression-tested.
- Exact baseline `d7ffe10f9294424482dd7a869a2867d3aee61e6e`: CI run
  `30910167848` passed 13/13 jobs, nightly run `30910169662` passed 3/3 jobs,
  and Full Formal run `30910169857` passed 8/8 shards.
- Trust-hardening executable `5ad7e2f04c65348a709728447c64ff46acea1986`:
  CI run `31167742453` passed 13/13 jobs, nightly run `31167748554` passed
  3/3 jobs, and Full Formal run `31167747619` passed 8/8 shards. The first
  remote attempt exposed a stale Icarus skip ceiling; the exact three new
  formal-stack skips were admitted without weakening the reason whitelist.
- The Linux open-liveness shard executed 17/17 tests with no skip using Super
  Prove; the open-user-DUT shard executed 75/75 tests with no skip.

## Evidence Boundary

- Local macOS ARM still has no Super Prove executable, so local live tests skip.
  This is not counted as local pass evidence; the exact-commit Linux Full
  Formal shard above supplies the qualified real good/bad live evidence.
- Zero construct rows are promoted to Fully supported. Workflow qualification
  does not close row-specific independent-reference, proof-depth, CDC, or
  industrial-corpus gaps.
- The 2026-08-07 trust-hardening executable is exact-SHA remotely qualified.
  Its OpenTitan slice remains bounded external-source evidence, not OpenTitan,
  CDC, metastability, or industrial sign-off.

## Next Work

Use the closed v2.0 evidence as the baseline for a narrow next milestone. Any
executable, formal semantic, or workflow change must receive fresh exact-commit
CI, nightly, and Full Formal qualification before support claims move.

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
| 24 | 24-02 | Complete |
