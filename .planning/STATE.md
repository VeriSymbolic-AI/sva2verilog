---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: — Hardening Release
current_phase: 07
status: ready
last_updated: "2026-06-05T05:10:00.000Z"
last_activity: 2026-06-05 -- Phase 02 completed
progress:
  total_phases: 7
  completed_phases: 6
  total_plans: 10
  completed_plans: 10
  percent: 86
---

# Project State: sva2rtl

**Last updated:** 2026-06-04
**Current phase:** 02
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
| 1 | Retroactive Nyquist Baseline | ✅ complete | VALIDATE-01 |
| 2 | Verilator Parity + CI Expansion | ✅ complete | VALIDATE-02, VALIDATE-03, VALIDATE-04 |
| 3 | V2001 Template Dedup + HARDEN-01 Root Fix | ✅ complete | REFACTOR-01, REFACTOR-02, REFACTOR-03, HARDEN-01 |
| 4 | Remaining HIGH Fixes | ✅ complete | HARDEN-02, HARDEN-03, HARDEN-04 |
| 5 | Phase 06 HIGH CLI Fixes | ✅ complete | HARDEN-05, HARDEN-06, HARDEN-07, HARDEN-08 |
| 6 | Cleanup + Version Sync + Final Review | ✅ complete | POLISH-01, POLISH-02, POLISH-03, POLISH-04 |
| 7 | Release — v1.1.0 Tag + Notes + Smoke | not started | RELEASE-01, RELEASE-02, RELEASE-03 |

---

## Active Phase

**Phase 03: V2001 Template Dedup + HARDEN-01 Root Fix** — ready to start.

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

- **Total v1.1:** 34 (22 original + 12 Nyquist BLOCKING gaps)
- **Completed:** 4 (VALIDATE-01..04)
- **In progress:** 0
- **Not started:** 30

---

## Transition Log

| Date | Event |
|------|-------|
| 2026-06-02 | Milestone v1.1 started; REQUIREMENTS.md defined (22 requirements, 5 categories) |
| 2026-06-02 | ROADMAP.md created — 7 phases, 22/22 requirements mapped, phase numbering reset to Phase 1 |
| 2026-06-04 | Phase 01 completed — 2 plans executed, 6 VALIDATION.md files written, 12 NYQ-XX BLOCKING gaps identified |
| 2026-06-05 | Phase 02 completed — 5 plans executed, pytest --simulator infra + tb_generator refactor + CI 2×2×2 + CLAUDE.md dual-oracle |

---

## Current Position

Phase: 03 (v2001-template-dedup-harden-01-root-fix) — READY
Plan: not yet planned
Status: Phase 02 complete; Phase 03 next
Last activity: 2026-06-05 — Phase 02 completed

## Operator Next Steps

- Next: `/gsd:discuss-phase 3` or `/gsd:plan-phase 3`
- `/gsd:verify-work 2` — manual acceptance testing of Phase 02 artifacts
