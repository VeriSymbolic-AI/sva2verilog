# Phase 1: Retroactive Nyquist Baseline - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-02
**Phase:** 1-retroactive-nyquist-baseline
**Areas discussed:** VALIDATION.md schema + verdict format, Nyquist boundary enumeration, Gap → hardening handoff, Plan granularity

---

## Pre-discussion routing

| Option | Description | Selected |
|--------|-------------|----------|
| Continue and replan after | Capture context now; replan to incorporate new decisions afterward | ✓ |
| View existing plans | Show the existing PLAN.md files first before deciding | ✓ (pre-step) |
| Cancel | Exit the discuss-phase workflow without changes | |

**User's choice:** Viewed the 5 archived v1.0 PLAN.md files first, then chose "Continue and replan after".

---

## Phase identity disambiguation

| Option | Description | Selected |
|--------|-------------|----------|
| v1.1 Phase 1 (Nyquist Baseline) | Active milestone phase — generate VALIDATION.md reports for all 6 v1.0 phases. No plans yet. | ✓ |
| v1.0 Phase 1 (archived) | Foundation IR + slang frontend + boolean assert SV monitor. Already shipped with 5 plans. | |

**User's choice:** v1.1 Phase 1 (Nyquist Baseline). The init had pointed at the archived v1.0 directory; corrected target before discussion.
**Notes:** The active milestone is v1.1 Hardening Release. Phase 1 within v1.1 is "Retroactive Nyquist Baseline" with one requirement (VALIDATE-01).

---

## VALIDATION.md schema + verdict format

### Sub-question 1/3 — Schema

| Option | Description | Selected |
|--------|-------------|----------|
| Strict template (front-matter + sections) | Fixed schema: front-matter, Operator Coverage Table, Narrative, Verdict, Gap List | |
| Loose narrative + required header | Free-form body; required verdict + gap list at top | |
| Match v1.0 VERIFICATION.md style | Reuse 06-VERIFICATION.md's verdict-first / evidence-by-must-have / file-by-file structure | ✓ |

**User's choice:** Match v1.0 VERIFICATION.md style.
**Notes:** Already proven shape; downstream agents already know how to parse it.

### Sub-question 2/3 — Verdict format

| Option | Description | Selected |
|--------|-------------|----------|
| PASS / FAIL (binary) | Any uncovered operator → FAIL | |
| PASS / PASS-WITH-GAPS / FAIL | Three tiers; PASS-WITH-GAPS for "operators exercised, edge cases missing" | ✓ |
| Numeric coverage score (0–10) | Score plus 1-line summary | |

**User's choice:** PASS / PASS-WITH-GAPS / FAIL.
**Notes:** Tiered verdict lets v1.1 ship a documented baseline without forcing every micro-gap into hardening scope. Numeric scores rejected as ambiguous for downstream gating.

### Sub-question 3/3 — Gap severity

| Option | Description | Selected |
|--------|-------------|----------|
| HIGH / MEDIUM / LOW | Mirrors review severity vocabulary | |
| BLOCKING / ADVISORY | Two tiers — fix in v1.1 or defer | ✓ |
| No severity — raw gap list | Let Phases 3–5 triage | |

**User's choice:** BLOCKING / ADVISORY.
**Notes:** v1.1 routing is binary (in-scope or deferred), so two tiers are sufficient and clearer than HIGH/MEDIUM/LOW.

---

## Nyquist boundary enumeration

### Sub-question 1/2 — Boundary source

| Option | Description | Selected |
|--------|-------------|----------|
| Static per-operator checklist | Build the checklist up-front; uniform application | |
| Derive from PITFALLS.md | Each pitfall = one Nyquist sample point | |
| PITFALLS.md + static checklist (hybrid) | PITFALLS.md is the floor; static checklist adds boundaries pitfalls don't cover | ✓ |
| Test-file naming as ground truth | Inspect tests/ for absent test names | |

**User's choice:** Hybrid (PITFALLS.md + static checklist).
**Notes:** PITFALLS.md already encodes "what could fail silently" — those ARE the Nyquist boundaries. Static checklist supplements with operator-edge values pitfalls don't enumerate (e.g., `##0` vs `##1` vs `##N`, repetition with `[*0]` / `[*0:0]`).

### Sub-question 2/2 — Evidence precision

| Option | Description | Selected |
|--------|-------------|----------|
| Cite test_file::test_function for each boundary | Highest evidence value | ✓ |
| Cite test file only | Lighter to author | |
| Narrative reference only | "Covered by repetition tests" | |

**User's choice:** Cite test_file::test_function for each boundary.
**Notes:** A row with no citation = a gap. Narrative-only references hide what's actually missing.

---

## Gap → hardening handoff

### Sub-question 1/2 — Routing

| Option | Description | Selected |
|--------|-------------|----------|
| Inline gaps per VALIDATION.md only | No central index | |
| Inline + cross-phase VALIDATION-INDEX.md | Aggregated index file | |
| Stable NYQ-XX IDs added to REQUIREMENTS.md | Same flow as HARDEN-XX/REFACTOR-XX | ✓ |

**User's choice:** Stable NYQ-XX IDs added to REQUIREMENTS.md.
**Notes:** Single source of truth; reuses the existing requirement-ID convention; mechanical traceability table append.

### Sub-question 2/2 — ADVISORY policy

| Option | Description | Selected |
|--------|-------------|----------|
| ADVISORY → PROJECT.md Out of Scope | Atomic loop closure | |
| ADVISORY stays in VALIDATION.md | Defer triage to v1.2 | ✓ |
| ADVISORY → backlog todos | Triaged at /gsd-review-backlog | |

**User's choice:** ADVISORY stays in VALIDATION.md.
**Notes:** v1.1 is hardening-only; ADVISORY gaps belong to v1.2 entry, not v1.1 PROJECT.md churn.

---

## Plan granularity

### Sub-question 1/2 — Plan count

| Option | Description | Selected |
|--------|-------------|----------|
| 2 plans (template + parallel writeup) | Plan 01 = template/checklist; Plan 02 = parallel writeup of 6 reports | ✓ |
| 6 plans (one per v1.0 phase) | Highest parallelism, redundant template work | |
| 1 + 6 + 1 (template, audit, aggregate) | 8 plans total — most parallel, most overhead | |
| 1 plan (one big task list) | Sequential, simplest review | |

**User's choice:** 2 plans (template + parallel writeup).
**Notes:** Matches the roadmap's ~2-plan estimate; wave-parallel writeup with a shared template/checklist artifact.

### Sub-question 2/2 — REQUIREMENTS.md update timing

| Option | Description | Selected |
|--------|-------------|----------|
| Same plan as audit (atomic) | Each phase's audit plan-task appends its own NYQ-XX rows in the same commit | ✓ |
| Dedicated aggregate plan at the end | Single deduped REQUIREMENTS.md edit | |
| Defer to Phases 3–5 | Phase 1 produces VALIDATION.md only | |

**User's choice:** Same plan as audit (atomic).
**Notes:** Avoids orphan-finding window; atomic commit preserves traceability.

---

## Claude's Discretion

- Filename pattern (`0N-VALIDATION.md` vs bare `VALIDATION.md`) — recommendation noted in CONTEXT.md; planner may mirror v1.0 phases 04/05's bare-name style if preferred.
- Front-matter field set beyond the minimal (`phase`, `phase_number`, `verifier`, `status`, `date`, `requirement_ids`).
- Boundary-checklist storage (Markdown vs YAML asset; inline vs `.planning/research/NYQUIST-CHECKLIST.md`).
- Audit harness implementation (Python script vs pytest collector).

## Deferred Ideas

- Numeric coverage score (0–10) as verdict format — rejected; tiered verdict is clearer for downstream gating.
- Cross-phase VALIDATION-INDEX.md — superseded by NYQ-XX IDs in REQUIREMENTS.md.
- PROJECT.md "Out of Scope" entries for ADVISORY gaps during v1.1 — out of scope per D-07; revisit at v1.2 entry.
- Test-file naming as ground-truth boundary source — rejected for biasing toward what was tested.
- 6-plan or 8-plan granularity — rejected as overhead vs the 2-plan split.
- Dedicated aggregate plan for REQUIREMENTS.md edits — rejected in favor of atomic per-phase appends.
- Re-running the v1.0 simulation oracle as part of the audit — Phase 1 cites existing test results, doesn't re-run.
