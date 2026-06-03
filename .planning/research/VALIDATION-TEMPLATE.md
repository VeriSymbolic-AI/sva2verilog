---
phase: <phase_slug>
phase_number: <phase_number>
phase_name: <phase_name>
verifier: plan-02-audit (autonomous)
verified: <YYYY-MM-DD>
status: <passed | passed-with-gaps | failed>
requirement_ids:
  - VALIDATE-01
  # NYQ-XX rows appended here by Plan 02 for each BLOCKING gap found in this phase
verdict: <PASS | PASS-WITH-GAPS | FAIL>
gap_count_blocking: <int>
gap_count_advisory: <int>
---

<!-- NYQ range: NYQ-XX..NYQ-YY -->

# Phase <phase_number> — Nyquist Validation Report

## Verdict: **<PASS | PASS-WITH-GAPS | FAIL>**

<!-- One-paragraph justification for the verdict tier.
     PASS: All Tier-1 operators exercised by this phase have full Nyquist boundary
           coverage — every pitfall row and every static-checklist row has a
           `tests/test_*.py::test_*` citation; gap_count_blocking = 0.
     PASS-WITH-GAPS: All operators exercised; every BLOCKING boundary row has
           evidence; one or more ADVISORY rows are uncovered. No silent miscompile
           possible with the current implementation.
     FAIL: At least one Tier-1 operator shipped in this phase is entirely
           uncovered OR at least one BLOCKING boundary row has no evidence. A
           silent miscompile is possible in the as-shipped v1.0 codebase.
-->

---

## Per-Phase NYQ-XX Range Table

Fixed allocation — Plan 02 parallel audits use these ranges; they CANNOT collide.

| v1.0 Phase | NYQ Range      | Phase Slug |
|------------|----------------|------------|
| Phase 01   | NYQ-01..NYQ-09 | foundation-ir-slang-frontend-boolean-assert-sv-monitor |
| Phase 02   | NYQ-10..NYQ-19 | core-sequential-operators-n-m-n |
| Phase 03   | NYQ-20..NYQ-29 | remaining-tier-1-operators-named-sequences-simulation-valida |
| Phase 04   | NYQ-30..NYQ-39 | normalization-composition-engine |
| Phase 05   | NYQ-40..NYQ-49 | optimization-passes |
| Phase 06   | NYQ-50..NYQ-59 | cli-polish-verilog-2001-integration-testing |

> **ID allocation rule:** Each NYQ-XX ID is BLOCKING-gap-only. Assign IDs
> sequentially within the phase range, starting at the range minimum (e.g.,
> Phase 01 first BLOCKING gap → NYQ-01, second → NYQ-02, …). ADVISORY gaps
> do NOT receive NYQ-XX IDs (D-07). IDs that are unused within a range are
> simply skipped — no padding required.

---

## 1. Operators Exercised

> One row per Tier-1 operator shipped in this v1.0 phase. Operators NOT shipped
> in this phase are omitted here (they appear in their respective phase's report).

| Operator | Template File (`templates/`) | IR Node Kind | Evidence Test File |
|----------|------------------------------|-------------|-------------------|
| `<operator>` | `<template_file>.sv.j2` | `<IRNodeKind>` | `tests/test_<file>.py` |

---

## 2. Boundary / Edge-Case Coverage

> One sub-table per operator exercised in this phase. Rows come from two sources:
> (a) PITFALLS.md — every applicable pitfall is a **mandatory** row (D-04 floor);
> (b) NYQUIST-CHECKLIST.md static rows for boundaries pitfalls don't list.
>
> Evidence column MUST cite a specific `tests/test_<file>.py::test_<function>`
> symbol (D-05). "Covered by repetition tests" or similar narrative citations are
> NOT acceptable — a missing citation IS a gap row.

### 2.1 `<Operator>`

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| <boundary description> | `PITFALLS:P1.1` | `tests/test_<file>.py::test_<function>` | COVERED |
| <boundary description> | `STATIC:S1.1` | `tests/test_<file>.py::test_<function>` | COVERED |
| <boundary description> | `PITFALLS:P2.3` | — | GAP-BLOCKING |
| <boundary description> | `STATIC:S1.4` | — | GAP-ADVISORY |

> **Status values:**
> - `COVERED` — citation present and test exists in `tests/`
> - `GAP-BLOCKING` — no evidence; silent miscompile possible (BLOCKING per D-03)
> - `GAP-ADVISORY` — no evidence; correctness gap is advisory-only (ADVISORY per D-03)

---

## 3. Pitfall Coverage Cross-Reference

> Every PITFALLS.md row that applies to THIS phase must appear at least once in
> §2. The table below maps each applicable pitfall ID to the §2 sub-table row
> where it appears. A pitfall listed as "N/A — operator not in this phase" means
> it is out of scope for this specific phase's report (Plan 02 will cover it in
> the relevant phase's report).

| Pitfall ID | Pitfall Title | §2 Sub-Table | Status |
|------------|--------------|--------------|--------|
| P1.1 | Vacuous satisfaction | §2.X `<operator>` | COVERED / GAP-BLOCKING / GAP-ADVISORY / N/A |
| P1.2 | Overlapping implication off-by-one | §2.X | … |
| P1.3 | Bit-vector overflow (multi-thread) | §2.X | … |
| P1.4 | `throughout` every-tick semantics | — | Tier 2 — out of v1.0 scope |
| P1.5 | `intersect` same-start-AND-end | — | Tier 2 — out of v1.0 scope |
| P1.6 | `disable iff` async semantics | §2.X | … |
| P1.8 | Strong vs. weak in hardware | §2.X | … |
| P2.1 | Combinational loop in monitor | §2.X | … |
| P2.3 | Counter bit-width overflow | §2.X | … |
| P2.4 | Missing monitor reset | §2.X | … |
| P3.1 | Single-thread testing only | §2.X | … |
| P3.4 | No boundary tests | §2.X | … |
| P3.5 | Vacuity not tested | §2.X | … |
| P4.1 | NFA→DFA state explosion | §2.X | … |
| P4.2 | Unbounded repetition | §2.X | … |
| P5.1 | Errors reference generated RTL | §2.X | … |
| P8.1 | Slang AST node types differ | §2.X | … |
| P8.2 | Token duplication on branches | §2.X | … |
| P8.4 | Implicit clocking uses wrong clock | §2.X | … |

---

## 4. Gaps

> Every uncovered boundary row from §2 is listed here with its severity tier.
>
> **Gap-row syntax (mandatory — grep-stable):**
> - BLOCKING gaps: `- [BLOCKING] NYQ-XX — <target phase> — <one-line justification>`
> - ADVISORY gaps: `- [ADVISORY] <one-line description>`
>
> Verdict↔gap-count cross-check: `grep -c '^\- \[BLOCKING\]'` must equal
> `gap_count_blocking`; `grep -c '^\- \[ADVISORY\]'` must equal
> `gap_count_advisory`.

### Blocking Gaps (must fix in v1.1 hardening)

- [BLOCKING] NYQ-XX — Phase 3 (templates) — <one-line justification of silent miscompile risk>

### Advisory Gaps (defer to v1.2)

- [ADVISORY] <one-line description of uncovered boundary — no NYQ-XX ID>

> If gap_count_blocking = 0 AND gap_count_advisory = 0, replace both sub-sections
> with: "None — full Nyquist coverage achieved for all operators in this phase."

---

## 5. Verdict-Tier Derivation

> Deterministic mapping from gap counts (D-02). Do NOT choose verdict subjectively —
> compute it from the gap list above.

| Condition | Verdict |
|-----------|---------|
| gap_count_blocking = 0 AND gap_count_advisory = 0 | `PASS` |
| gap_count_blocking = 0 AND gap_count_advisory >= 1 | `PASS-WITH-GAPS` |
| gap_count_blocking >= 1 OR any uncovered operator | `FAIL` |

**This phase:**
- `gap_count_blocking` = <int>
- `gap_count_advisory` = <int>
- Verdict = **<PASS | PASS-WITH-GAPS | FAIL>**

---

## 6. Read-Only Contract Attestation

> Plan 01 (and Plan 02 audit tasks) are read-only with respect to `src/` and
> `tests/`. The excerpt below confirms zero changes attributable to this audit.

```text
$ git diff --stat src/ tests/
(no output — zero changes)
```

All 736 v1.0 regression tests remain green at audit time:

```text
$ pytest tests/ --timeout=120 -q -m "not simulation"
658 passed, 17 skipped, <N> deselected
```

---

*Phase <phase_number> Nyquist validation completed: <YYYY-MM-DD>*
*Validation artifact: `.planning/milestones/v1.0-phases/<phase_slug>/<phase_number>-VALIDATION.md`*
