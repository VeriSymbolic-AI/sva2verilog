---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Hardening Release
current_phase: 01
status: executing
last_updated: "2026-06-03T11:57:55.754Z"
last_activity: 2026-06-03 -- Phase 01 execution started
progress:
  total_phases: 1
  completed_phases: 0
  total_plans: 2
  completed_plans: 1
  percent: 0
---

# Project State: sva2rtl

**Last updated:** 2026-06-02
**Current phase:** 01
**Mode:** hardening

---

## Current Status

| Item | State |
|------|-------|
| Roadmap | ✅ Created (7 phases, 22 requirements mapped) |
| Requirements | ✅ Defined (22 v1.1 requirements, traceability populated) |
| Research | ✅ Complete (v1.0 retrospective + audit as baseline) |
| Architecture | ✅ Unchanged from v1.0 — hardening only |
| Code | ✅ v1.0 shipped — hardening not yet started |
| Tests | ✅ 736 tests (736 pass, 17 skip); mypy --strict + ruff clean |
| CI | ✅ Ubuntu/macOS × Py 3.12/3.13 matrix (iverilog only; Verilator axis in Phase 2) |

---

## Phase Progress

| Phase | Name | Status | Requirements |
|-------|------|--------|-------------|
| 1 | Retroactive Nyquist Baseline | not started | VALIDATE-01 |
| 2 | Verilator Parity + CI Expansion | not started | VALIDATE-02, VALIDATE-03, VALIDATE-04 |
| 3 | V2001 Template Dedup + HARDEN-01 Root Fix | not started | REFACTOR-01, REFACTOR-02, REFACTOR-03, HARDEN-01 |
| 4 | Phase 03 Remaining HIGH Fixes | not started | HARDEN-02, HARDEN-03, HARDEN-04 |
| 5 | Phase 06 HIGH CLI Fixes | not started | HARDEN-05, HARDEN-06, HARDEN-07, HARDEN-08 |
| 6 | MEDIUM/LOW Cleanup + Version Sync + Final Review | not started | POLISH-01, POLISH-02, POLISH-03, POLISH-04 |
| 7 | Release — v1.1.0 Tag + Notes + Smoke | not started | RELEASE-01, RELEASE-02, RELEASE-03 |

---

## Active Phase

**None** — roadmap created, awaiting Phase 1 start.

---

## Key Decisions (Settled)

| Decision | Rationale |
|----------|-----------|
| Python 3.12+ with slang CLI (`--ast-json`) | Fastest iteration; JSON AST is stable; avoids C++ build complexity |
| Token-passing architecture (TIMA Lab) | Linear O(n) area, compositional, proven in academic literature |
| Bit-vector method for `|->` | Simple, hardware-efficient, handles 85%+ of real SVA |
| Counter encoding over state expansion | `##[0:100]` = 7-bit counter vs. 101 parallel paths — critical area |
| Frozen dataclasses for IR | Structural hashing for CSE; immutable for safe sharing across passes |
| `attempt_fired` first-class from Phase 1 | Prevents vacuous satisfaction going undetected; cannot be retrofitted |
| `SourceLoc` first-class on IR nodes | Prevents Phase 5 pitfall (source location not threaded through IR) |
| Normalization before Phase 4 operators | Phases 2–3 use direct wiring; Phase 4 installs proper composition engine |
| REFACTOR-01 before HARDEN-01 fix | HARDEN-01 fix must land at macro root; macro extraction is prerequisite |
| Verilator parity before hardening (Phase 2 before 3–5) | Every hardening fix validated under both simulators automatically |

---

## Risks Being Tracked

| Risk | Mitigation | Status |
|------|-----------|--------|
| HARDEN-01 fix duplicated in 22 template branches | REFACTOR-01 extracts macro root first; fix applied once in Phase 3 | Phase 3 mitigation |
| Verilator behavioral divergence from iverilog | Parity test suite in Phase 2; any divergence is a bug to fix before hardening | Phase 2 mitigation |
| MEDIUM/LOW findings contain hidden HIGH issues | Cross-phase review (POLISH-04) gated before release | Phase 6 mitigation |
| Version mismatch `__init__.py` vs `pyproject.toml` | POLISH-01 in Phase 6; single atomic commit synchronizes both | Phase 6 mitigation |

---

## Requirement Status Summary

- **Total v1.1:** 22
- **Completed:** 0
- **In progress:** 0
- **Not started:** 22

---

## Transition Log

| Date | Event |
|------|-------|
| 2026-06-02 | Milestone v1.1 started; REQUIREMENTS.md defined (22 requirements, 5 categories) |
| 2026-06-02 | ROADMAP.md created — 7 phases, 22/22 requirements mapped, phase numbering reset to Phase 1 |

---

## Current Position

Phase: 01 (retroactive-nyquist-baseline) — EXECUTING
Plan: 1 of 2
Status: Executing Phase 01
Last activity: 2026-06-03 -- Phase 01 execution started

## Operator Next Steps

- Start Phase 1 with `/gsd-execute-phase 1`
