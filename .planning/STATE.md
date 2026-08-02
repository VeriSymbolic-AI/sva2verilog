---
gsd_state_version: 1.0
milestone: v1.7
milestone_name: Language Surface Closure
current_phase: 18
current_phase_name: complete
status: apache-2.0-remote-qualified
stopped_at: Apache-2.0, README, formal/advanced-SVA guide, and exact-commit c957bdf remote qualification complete
last_updated: "2026-08-02T17:31:08.000+08:00"
last_activity: 2026-08-02
last_activity_desc: Relicensed to Apache-2.0, corrected public claims, added formal and advanced-SVA guidance, and qualified exact commit c957bdf remotely
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 5
  completed_plans: 5
  percent: 100
---

# Project State: sva2rtl v1.7

## Current Position

Phase: v1.7 language milestone complete; Apache-2.0 public documentation and formal guidance qualified
Status: local and exact-commit remote evidence green at executable commit `c957bdf`
Last activity: 2026-08-02 — relicensed the current distribution, corrected README scope, documented formal verification and advanced-SVA alternatives, and completed same-commit remote qualification

## Project Reference

See: `.planning/PROJECT.md`

**Core value:** Turn any supported SVA property into a correct, area-efficient synthesizable hardware monitor with evidence strong enough that unsupported or insufficiently verified forms are rejected or downgraded rather than silently miscompiled.

**Current focus:** address the remaining industrial corpus, per-construct
evidence, uncovered mutation candidates, and CDC protocol gaps without
overstating the current Apache-2.0 release evidence.

## Baseline

- Version state: v1.7 (current main).
- Tests: the complete Icarus/default axis records 1553 passed, 1 skipped,
  0 failed, and 1 xfailed.
- Simulation: pinned Verilator 5.028 records 174 passed / 2 reviewed skips; Icarus is
  included in the complete green suite.
- Formal: the current Full Formal selection records 126 passed / 1
  bounded-eventually k-induction xfail.
- Generated RTL: Yosys synthesis + strict Verilator lint records 133 passed.
- Nightly: fixed-seed slow differential passes 64 generated examples on each
  Icarus and Verilator; mutation scores are bool 16/16, oracle 135/138,
  composer 47/51, importer 97/111, with invalid and uncovered candidates
  excluded and reported separately; template mutation is 12/12.
- Packaging: 35/35/35 runtime templates in source/wheel/sdist; isolated installs verified.
- Quality: ruff 0 errors; mypy --strict 0 errors; branch coverage 87.19% with
  aggregate and critical-module floors passing even in the CI-minimal tool set.
- P1 credibility: independent source-reference differential, 126 formal passes,
  all mutation modules above individual thresholds, and RTL template mutations
  12/12. Exact-commit CI 13/13, nightly 3/3, and Full Formal 6/6 are green.

## v1.7 Language Surface Closure

Committed scope (all delivered):
- LANG-01: `##0` rewrite/reject — rewrite BoolExpr `##0` to `&&`, reject complex forms
- LANG-02: NFA SeqOr through union construction
- LANG-03: NFA ranged delay and ranged repetition operands
- LANG-04: NFA goto and nonconsecutive repetition operands

## v1.7 Phase Progress

| Phase | Name | Status |
|-------|------|--------|
| 14 | Zero-Delay Fusion Rewrite/Reject | Complete |
| 15 | NFA SeqOr Union Construction | Complete |
| 16 | NFA Ranged Delay/Repetition Operands | Complete |
| 17 | NFA Goto/Nonconsecutive Operands | Complete |
| 18 | Evidence Chain Closure & Release | Complete |

## Deferred Scope (Future Milestones)

- Single-thread local variables.
- Multi-clock x NFA.
- FPGA prototype (FUT-03).
- C++ rewrite v2 (FUT-04).

## Notes

- `.planning/` and `.gsd/` are gitignored local artifacts.
- `PLAN-nfa-rejection-elimination.md` contains the full NFA expansion design.

### Quick Tasks Completed

| # | Description | Date | Commit | Status | Directory |
|---|-------------|------|--------|--------|-----------|
| 260711-qbb | Current project progress, problem, risk, and future-roadmap analysis | 2026-07-11 | ed170cc | Verified | [260711-qbb-current-project-analysis](./quick/260711-qbb-current-project-analysis/) |
| 260722-nx5 | P1 semantic credibility hardening | 2026-07-22 | 27ebefb | Verified | [260722-nx5-p1-semantic-credibility-hardening-indepe](./quick/260722-nx5-p1-semantic-credibility-hardening-indepe/) |
| 260802-mhy | Relicense to Apache-2.0, correct README, and document formal/advanced-SVA verification | 2026-08-02 | c957bdf | Verified | [260802-mhy-relicense-sva2rtl-to-apache-2-0-correct-](./quick/260802-mhy-relicense-sva2rtl-to-apache-2-0-correct-/) |

## Session

**Last session:** 2026-08-02
**Stopped at:** Apache-2.0 executable commit `c957bdf` is pushed and qualified by
CI, nightly, and Full Formal; the follow-up commit records evidence only and must
not be treated as a new executable proof object
