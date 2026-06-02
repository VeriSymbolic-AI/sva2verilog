# Phase 1: Retroactive Nyquist Baseline - Context

**Gathered:** 2026-06-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Read-only analysis pass that produces exactly one `*-VALIDATION.md` Nyquist coverage report per shipped v1.0 phase directory under `.planning/milestones/v1.0-phases/0N-*/`. Six reports total, one per v1.0 phase (1–6). No production code, IR schema, templates, or test files are modified. Findings are routed into Phases 3–5 hardening scope via stable `NYQ-XX` requirement IDs appended to `REQUIREMENTS.md`. ADVISORY findings remain in their VALIDATION.md only and are deferred to v1.2 triage. The 736-test regression suite must remain green at end of phase (read-only contract).

Single requirement: **VALIDATE-01**.

</domain>

<decisions>
## Implementation Decisions

### VALIDATION.md schema + verdict format
- **D-01:** Each `*-VALIDATION.md` follows the v1.0 `06-VERIFICATION.md` style — front-matter (phase, phase_number, requirements, verifier, status, date), verdict-first, evidence-by-must-have sections, file-by-file evidence, and a final Gaps section. Downstream agents already know this shape.
- **D-02:** Verdict is one of three tiers — `PASS` (full coverage), `PASS-WITH-GAPS` (operators exercised, edge cases missing), `FAIL` (operator entirely uncovered). Lets v1.1 ship a documented baseline without forcing every micro-gap into hardening scope.
- **D-03:** Each gap inside a VALIDATION.md is classified `BLOCKING` (silent miscompile possible / real correctness gap → must fix in v1.1) or `ADVISORY` (defer to v1.2). Two-tier severity is sufficient because v1.1 routing is binary: in-scope or deferred.

### Nyquist boundary enumeration
- **D-04:** Boundary cases come from a **hybrid source-of-truth**: (a) every pitfall in `.planning/research/PITFALLS.md` is a mandatory Nyquist sample point — every pitfall MUST appear as a row in the relevant operator's coverage table; (b) a static per-operator boundary checklist (defined in Plan 01) covers boundaries pitfalls don't list — for example `##0` / `##1` / `##N`, `##[0:0]` / `##[M:M]` / `##[M:N]` with `M>N`, `[*0]` / `[*0:0]` / `[*N]` / `[*M:N]` overflow, `$past(sig, 0)` vs large `n`, `disable iff` vs `attempt_fired` interaction, multi-thread overlapping implication bit-vector overflow.
- **D-05:** Every boundary row in a coverage table cites a specific `tests/test_<file>.py::test_<function>` evidence line. Rows with no citation are gaps (no narrative-only "covered by repetition tests" entries — that hides what's actually missing).

### Gap → hardening handoff
- **D-06:** BLOCKING gaps receive stable IDs of the form `NYQ-XX` (sequential, two-digit, scoped to v1.1). Each NYQ-XX is appended to `.planning/REQUIREMENTS.md` under a new "Validate — Nyquist gap remediation" subsection AND added to the traceability table with target Phase = 3, 4, or 5 chosen by which compiler layer the gap lives in (templates → 3, IR/codegen → 4, CLI → 5). Same precedent as `HARDEN-XX` and `REFACTOR-XX`.
- **D-07:** ADVISORY gaps stay in their VALIDATION.md only — no PROJECT.md "Out of Scope" churn during v1.1, no backlog todos. Triaged at v1.2 entry.
- **D-08:** REQUIREMENTS.md updates are **atomic with the audit plan that produced them**: the same plan-task that writes `0N-VALIDATION.md` for v1.0 Phase N also appends that phase's NYQ-XX rows to REQUIREMENTS.md and the traceability table in the same commit. No separate aggregate plan; no orphan windows.

### Plan granularity
- **D-09:** Phase 1 is split into **2 plans** (matches roadmap estimate):
  - **Plan 01 — Template + boundary checklist:** authors `templates/VALIDATION.md.template` (or in-repo equivalent), the static per-operator boundary checklist, the PITFALLS.md → boundary mapping rule, the `NYQ-XX` ID allocation rule, and a tiny audit harness (script that walks `.planning/milestones/v1.0-phases/` and stubs out empty VALIDATION.md skeletons keyed on phase number).
  - **Plan 02 — Parallel writeup of all 6 VALIDATION.md files:** consumes the template + checklist; writes the six VALIDATION.md files; appends NYQ-XX rows to REQUIREMENTS.md atomically per phase audited; verifies the 736-test regression suite still passes (read-only contract). Wave-parallelizable across the six v1.0 phases.

### Claude's Discretion
- Exact filename pattern (`0N-VALIDATION.md` vs `VALIDATION.md` — note v1.0 phases 04 and 05 use bare `VERIFICATION.md` while phases 01/02/03/06 use the prefixed form). Recommendation: prefer `0N-VALIDATION.md` (`01-VALIDATION.md` … `06-VALIDATION.md`) for consistency with the prefixed phases; bare `VALIDATION.md` is acceptable in 04 and 05 if the planner prefers to mirror their existing VERIFICATION.md naming.
- Front-matter field set beyond `{phase, phase_number, verifier, status, date, requirement_ids}` — researcher / planner may add fields if the audit harness benefits.
- Boundary-checklist storage location (`.planning/research/NYQUIST-CHECKLIST.md` vs inline in Plan 01 task vs a YAML asset).
- Whether the audit harness is a one-off Python script or a `pytest` collector — both satisfy the read-only contract.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope (locks what Phase 1 must produce)
- `.planning/ROADMAP.md` §"Phase 1 — Retroactive Nyquist Baseline" — phase goal, success criteria, plan estimate (2 plans).
- `.planning/REQUIREMENTS.md` §"Validate — Retroactive Nyquist sweeps + Verilator parity" — VALIDATE-01 requirement text and acceptance criteria.
- `.planning/PROJECT.md` §"Current Milestone: v1.1 Hardening Release" + §"Known Issues / Tech Debt" — lists the v1.0 carry-forward defects that downstream NYQ-XX gaps may overlap with.

### Schema reference (template the new VALIDATION.md files must match)
- `.planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md` — canonical structural model: front-matter, verdict-first, requirement cross-reference table, must-have evidence, file-by-file evidence.

### Boundary-case source of truth
- `.planning/research/PITFALLS.md` — every pitfall row is a mandatory Nyquist sample point (D-04). Floor coverage for the static checklist.
- `.planning/research/FEATURES.md` — operator inventory (Tier 1 set shipped in v1.0); used to build the per-operator boundary checklist.
- `.planning/research/SUMMARY.md` — confirms the dominant risk class is "silent semantic incorrectness"; informs why BLOCKING vs ADVISORY severity matters.

### v1.0 phase artifacts being audited (input to Plan 02)
- `.planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/` — Phase 1 (boolean assert SV monitor)
- `.planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/` — Phase 2 (`##N`, `##[M:N]`)
- `.planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/` — Phase 3 (`|->`, `|=>`, `[*N]`, `$rose`, `$fell`, `$stable`, `$past`, `disable iff`, named sequences)
- `.planning/milestones/v1.0-phases/04-normalization-composition-engine/` — Phase 4 (normalize + composition)
- `.planning/milestones/v1.0-phases/05-optimization-passes/` — Phase 5 (CSE, constant folding, counter encoding)
- `.planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/` — Phase 6 (CLI surface, `--verilog`, integration tests)

### Existing review artifacts (cross-reference for known HIGH defects, do not re-discover)
- `.planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/02-REVIEWS.md`
- `.planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-REVIEW.md`
- `.planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-REVIEW.md`

### Test corpus (evidence source for D-05 citations)
- `tests/` directory — 736 tests; every boundary citation must point at a real `tests/test_<file>.py::test_<function>` symbol.
- `tests/simulation/` — iverilog co-sim oracle (65 tests) — primary evidence for behavioral correctness boundaries.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **v1.0 06-VERIFICATION.md as schema model** — already proven, mypy-strict-clean front-matter style; copy its structure verbatim.
- **PITFALLS.md as boundary catalog** — every pitfall row already encodes a "what could fail silently" Nyquist sample; no need to re-derive.
- **Test naming convention** — `tests/test_<module>.py::test_<scenario>` is uniform across the corpus, so citation links are stable and greppable.

### Established Patterns
- **Stable XX-prefixed requirement IDs** (`HARDEN-01..08`, `REFACTOR-01..03`, `VALIDATE-01..04`, `POLISH-01..04`, `RELEASE-01..03`) — `NYQ-XX` follows the same convention; traceability table append is mechanical.
- **Read-only analysis phase** — Phase 1 is the only v1.1 phase that writes ONLY to `.planning/` and never to `src/` or `tests/`; the test-suite-green gate is a hard contract.
- **Phase number reset** — v1.1 phase numbering restarts at 1 (per ROADMAP); v1.0 phase directories live under `.planning/milestones/v1.0-phases/` and are the audit targets, not the audit context.

### Integration Points
- Phase 1 output (`*-VALIDATION.md` × 6 + `NYQ-XX` rows in REQUIREMENTS.md) feeds directly into Phases 3, 4, 5 PLAN.md files — those plans MUST `<read_first>` the relevant VALIDATION.md when scoping their fixes.
- Phase 1 does NOT touch Phase 2 (Verilator parity) — Phase 2's CI matrix change is independent. Both phases can run in parallel if branching policy allows.

</code_context>

<specifics>
## Specific Ideas

- "Every pitfall is a Nyquist sample point" — derived from the project's stated dominant risk class (silent semantic incorrectness). This makes PITFALLS.md the canonical floor for boundary coverage; the static checklist only adds boundaries pitfalls don't list.
- The audit is a **paper exercise on the shipped v1.0 codebase, not a re-validation of the v1.1 hardening fixes**. Hardening lands later; Phase 1 documents the as-shipped state.
- v1.0 phases 04 and 05 use `VERIFICATION.md` (no phase prefix) — the writeup plan should normalize to `0N-VALIDATION.md` for consistency unless a strong reason emerges to mirror existing names.
- The tiered verdict (PASS / PASS-WITH-GAPS / FAIL) maps mechanically to gap counts: zero gaps → PASS; only ADVISORY gaps → PASS-WITH-GAPS; any BLOCKING gap or any uncovered operator → FAIL. The verdict logic should be deterministic from the gap list, not author-chosen.

</specifics>

<deferred>
## Deferred Ideas

- **Numeric coverage score (0–10)** — considered as a verdict format; rejected because tiered verdicts give clearer downstream gating (Phases 3–5 can branch on verdict directly, no threshold debate).
- **Cross-phase VALIDATION-INDEX.md** — considered as a one-stop file aggregating all BLOCKING gaps; rejected in favor of `NYQ-XX` IDs in REQUIREMENTS.md (single source of truth, same pattern as other v1.1 IDs).
- **PROJECT.md "Out of Scope" entries for ADVISORY gaps** — considered to atomically close the loop; rejected because v1.1 is hardening-only; ADVISORY gaps belong to v1.2 triage entry, not v1.1 scope.
- **Test-file naming as ground truth** — considered as the boundary-enumeration mechanism; rejected because it biases toward what was tested (misses unknown-unknowns); pitfall-first hybrid is stricter.
- **6 separate plans (one per audited phase)** — considered for max parallelism; rejected as overhead; the 2-plan split (template, then parallel writeup) gets the same wave-parallel writeup with one shared template/checklist artifact.
- **Dedicated aggregate plan** — considered for centralized REQUIREMENTS.md editing; rejected; per-phase atomic appends are simpler and avoid one merge-window for all 6 audits.
- **Findings entering PROJECT.md `Out of Scope`** during v1.1 — explicitly out of scope per D-07.
- **Re-running the v1.0 simulation oracle as part of the audit** — Phase 1 cites existing test results, doesn't re-run them; the regression-suite-green gate is the only test execution Phase 1 owns.

</deferred>

---

*Phase: 1-retroactive-nyquist-baseline*
*Context gathered: 2026-06-02*
