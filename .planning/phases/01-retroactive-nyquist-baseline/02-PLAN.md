---
wave: 2
depends_on: [01]
files_modified:
  - .planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-VALIDATION.md
  - .planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/02-VALIDATION.md
  - .planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-VALIDATION.md
  - .planning/milestones/v1.0-phases/04-normalization-composition-engine/04-VALIDATION.md
  - .planning/milestones/v1.0-phases/05-optimization-passes/05-VALIDATION.md
  - .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VALIDATION.md
  - .planning/REQUIREMENTS.md
autonomous: true
requirements: [VALIDATE-01]
---

# Plan 02: Parallel Retroactive Nyquist Audits — All Six v1.0 Phase VALIDATION.md Files

## Goal

Consume the template (`.planning/research/VALIDATION-TEMPLATE.md`), the per-operator boundary checklist (`.planning/research/NYQUIST-CHECKLIST.md`), and the audit harness (`tools/audit/seed_validation_skeletons.py`) shipped by Plan 01. Produce exactly one `0N-VALIDATION.md` Nyquist coverage report per v1.0 phase directory under `.planning/milestones/v1.0-phases/`. Each per-phase audit task is wave-parallelizable: it owns its own input directory, its own output file, its own NYQ-XX range, and its own append rows in `.planning/REQUIREMENTS.md` (atomic per D-08).

The plan is read-only with respect to `src/` and `tests/`. The 736-test regression suite is verified green at the end of the plan as the closing gate.

## Requirements

- **VALIDATE-01** — Every v1.0 phase directory contains exactly one `*-VALIDATION.md` Nyquist coverage report; gaps are routed to Phase 3/4/5 hardening scope as `NYQ-XX` requirement IDs in `REQUIREMENTS.md`'s traceability table.

## Threat Model

<threat_model>
- **Cross-task NYQ-XX collisions** — Mitigated by Plan 01's fixed per-phase NYQ-XX range table (Phase 1 → NYQ-01..09, …, Phase 6 → NYQ-50..59). Each audit task is restricted to its own range; impossible to collide.
- **Cross-task REQUIREMENTS.md merge conflicts** — Mitigated by D-08: each per-phase audit appends only its own NYQ-XX rows in one atomic commit before the next audit runs. Tasks are wave-parallel only at edit-text time; commits land sequentially. Each task limits its diff to a contiguous block in REQUIREMENTS.md (its own range subsection + its own traceability rows).

<sequencing>
**Wave-parallelism vs commit-order constraint (INFO 3 from plan-checker):**

Per-phase audit tasks 2.1.1–2.1.6 are **wave-parallelizable for VALIDATION.md authoring** — six independent files in six independent v1.0 phase directories. Each task can author its `0N-VALIDATION.md` concurrently with the others; there is no shared-file write contention on the VALIDATION.md side.

However, **commits to `.planning/REQUIREMENTS.md` MUST land sequentially in `01 → 02 → 03 → 04 → 05 → 06` order.** All six tasks append rows to the same traceability table; concurrent commits would produce merge conflicts. Two equivalent encodings of this constraint are acceptable to the executor:

1. **Serialize the commit step:** All six tasks may author their VALIDATION.md in parallel, but the per-task `git commit` step (or its equivalent atomic-edit dispatch on REQUIREMENTS.md per D-08) is gated to run in 01 → 02 → … → 06 order — that is, task 2.1.K's REQUIREMENTS.md append waits for task 2.1.(K-1)'s commit to land before invoking its own append.
2. **Strict serial execution:** Run tasks 2.1.1 → 2.1.2 → … → 2.1.6 strictly in order with no parallelism. Slower but trivially conflict-free.

Either encoding satisfies D-08. The executor MUST NOT issue six concurrent appends to `.planning/REQUIREMENTS.md`.
</sequencing>
- **Read-only contract violation via accidental `src/` or `tests/` edit** — Mitigated by the final gate task asserting `git diff --stat src/ tests/` is empty after the audit. Per-task acceptance criteria also assert this.
- **Subjective verdict drift** — Mitigated by D-02 deterministic mapping from gap counts to verdict tier; per-task acceptance criteria grep for the exact mapping signature in each VALIDATION.md.
- **Missing pitfall coverage rows** — Mitigated by per-task acceptance criteria grep'ing every relevant PITFALLS.md ID into the operator's coverage table for that phase's operators.
- **Citation-free coverage rows** — Mitigated by D-05; per-task acceptance criteria grep for `tests/test_.*\.py::test_` patterns in every coverage table row claimed COVERED.
- **Regression suite breaks because audit harness side-effected something** — Mitigated by the final gate task (`pytest tests/` exits 0 with corpus count 736 in stdout).
</threat_model>

## Tasks

<task id="2.1.1">
<title>Audit v1.0 Phase 01 — Foundation IR + slang frontend + boolean assert SV monitor</title>
<read_first>
- .planning/research/VALIDATION-TEMPLATE.md (Plan 01 output — copy structure verbatim)
- .planning/research/NYQUIST-CHECKLIST.md (Plan 01 output — operator section: bool, IR foundations, slang frontend, default monitor port interface)
- .planning/research/PITFALLS.md (P1.1 vacuous satisfaction, P2.4 missing reset, P5.1 source location, P8.1 slang AST node types, P8.4 implicit clocking — mandatory rows for this phase)
- .planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-PLAN.md (phase scope: IR shape, slang importer, bool_expr template, monitor port interface)
- .planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-VERIFICATION.md (existing per-plan evidence — citation source for D-05)
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md (structural model — front-matter, verdict-first, file-by-file evidence ordering)
- .planning/REQUIREMENTS.md (current traceability table format; will be appended)
- templates/bool_expr.sv.j2 (operator under audit)
- tests/ directory listing — find tests covering boolean property compilation, default port interface, source-location threading, slang AST kinds, clock specification
</read_first>
<action>
Run `python tools/audit/seed_validation_skeletons.py` first if no skeletons exist; this writes `01-VALIDATION.md` with placeholders. Then fill the skeleton:

- Front-matter: `phase_number: 01`, `phase_name: foundation-ir-slang-frontend-boolean-assert-sv-monitor`, `verifier: phase-validate (autonomous)`, `verified: 2026-06-02`, `requirement_ids: [VALIDATE-01]` plus any NYQ-XX rows produced (range NYQ-01..NYQ-09).
- Operators exercised: bool_expr (combinational), monitor port interface (clk/rst_n/start/pass/fail/active), `attempt_fired` first-class, slang AST → IR import, `SourceLoc` plumbing, default clocking.
- Boundary table per operator with rows from NYQUIST-CHECKLIST.md. Cite `tests/test_<file>.py::test_<function>` for every COVERED row (D-05 mandate). Mark missing rows GAP-BLOCKING or GAP-ADVISORY per D-03.
- Pitfall coverage cross-reference: P1.1 vacuous satisfaction, P2.4 missing reset, P5.1 source location, P8.1 slang AST node kinds, P8.4 implicit clocking — every pitfall referenced into the table.
- Gaps: each BLOCKING gap gets the next NYQ-XX from the NYQ-01..09 range. Target hardening Phase per D-06 (templates → 3, IR/codegen → 4, CLI → 5).
- Verdict tier: deterministic per D-02 (zero gaps → PASS, only ADVISORY → PASS-WITH-GAPS, any BLOCKING or any uncovered operator → FAIL). Show the count → tier mapping at the bottom of the file.
- Read-only contract attestation section.

Atomically (D-08), in the same edit, append to `.planning/REQUIREMENTS.md`:
- A new subsection "Validate — Nyquist gap remediation (Phase 1 audit, v1.0 Phase 01)" listing every NYQ-XX BLOCKING row with one-line user-facing requirement text.
- Traceability table rows (one per NYQ-XX) with target Phase = 3, 4, or 5 and `Status = not started`.

Only NYQ-01..NYQ-09 are within this task's allocated range — never use NYQ-10 or higher.

Final task action: assert read-only contract via `git diff --stat src/ tests/` produces zero output.
</action>
<acceptance_criteria>
- `find .planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/ -name '*-VALIDATION.md' | wc -l` outputs `1`.
- `grep -qE '^verdict: (PASS|PASS-WITH-GAPS|FAIL)$' .planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-VALIDATION.md` succeeds.
- **Verdict↔gap-count determinism (D-02 cross-check):** the following deterministic shell sequence exits 0 — `B=$(grep -c '^- \[BLOCKING\]' .../01-VALIDATION.md || echo 0); A=$(grep -c '^- \[ADVISORY\]' .../01-VALIDATION.md || echo 0); V=$(grep -E '^verdict:' .../01-VALIDATION.md | awk '{print $2}'); case "$V" in PASS) test "$B" -eq 0 && test "$A" -eq 0 ;; PASS-WITH-GAPS) test "$B" -eq 0 && test "$A" -gt 0 ;; FAIL) test "$B" -gt 0 ;; *) false ;; esac` — using whatever per-row gap-marker syntax the VALIDATION-TEMPLATE.md actually emits (Plan 01 fixes the template's gap-row prefix; this acceptance check uses that prefix verbatim).
- `grep -qE 'tests/test_[a-zA-Z_]+\.py::test_' .planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-VALIDATION.md` succeeds (at least one D-05 evidence citation).
- `grep -q 'P1.1' .planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-VALIDATION.md` AND `grep -q 'P2.4' .../01-VALIDATION.md` AND `grep -q 'P5.1' .../01-VALIDATION.md` AND `grep -q 'P8.1' .../01-VALIDATION.md` AND `grep -q 'P8.4' .../01-VALIDATION.md` AND `grep -q 'P1.8' .../01-VALIDATION.md` all succeed (mandatory pitfalls cited per D-04; P1.8 strong/weak is the Phase 1 architectural-boundary pitfall).
- For every BLOCKING gap line: it carries an `NYQ-0[1-9]` ID — concrete shell check: `test $(grep -c '^- \[BLOCKING\]' .../01-VALIDATION.md) -eq $(grep -cE 'NYQ-0[1-9]\b' .../01-VALIDATION.md)` exits 0.
- No NYQ ID outside the NYQ-01..NYQ-09 range is used: `grep -E 'NYQ-[1-9][0-9]' .../01-VALIDATION.md` returns no matches.
- `grep -q 'NYQ-' .planning/REQUIREMENTS.md` succeeds AND every NYQ-XX added by this task appears in the REQUIREMENTS.md traceability table with target Phase ∈ {3, 4, 5}.
- `git diff --stat src/ tests/` produces zero output (read-only contract per the phase contract).
- Front-matter `requirement_ids` field includes `VALIDATE-01` and every NYQ-XX produced by this task.
</acceptance_criteria>
</task>

<task id="2.1.2">
<title>Audit v1.0 Phase 02 — Core sequential operators (##N, ##[M:N])</title>
<read_first>
- .planning/research/VALIDATION-TEMPLATE.md
- .planning/research/NYQUIST-CHECKLIST.md (operator sections: `##N`, `##[M:N]`)
- .planning/research/PITFALLS.md (P2.3 counter bit-width, P3.4 boundary tests, P4.1 NFA-DFA blowup — mandatory)
- .planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/02-PLAN.md
- .planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/02-VERIFICATION.md
- .planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/02-REVIEWS.md (already-known HIGH defects — cross-reference, do not re-discover)
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md (structural model)
- templates/concat_delay.sv.j2 and templates/seq_concat_top.sv.j2 (operators under audit)
- tests/ directory — tests/test_concat_delay*.py and similar (citation source for D-05)
</read_first>
<action>
Run the audit harness if no skeleton exists, then fill `02-VALIDATION.md` with operators `##N` (fixed delay), `##[M:N]` (range delay), counter encoding boundaries.

Boundary table must enumerate (NYQUIST-CHECKLIST.md static rows + pitfalls):
- `##0`, `##1`, `##N` large; `##[0:0]`, `##[M:M]`, `##[0:N]`, `##[N:N+1]`, `##[M:N]` with `M>N` (must error or normalize, not silent miscompile).
- P2.3 counter bit-width: `width = ceil(log2(N+1)) + 1`; assert at boundary and one above.
- P3.4 boundary tests: at N-1 (fail), N (pass), M (pass), M+1 (fail) per range delay.
- P4.1 NFA→DFA: confirmed token-passing avoids determinization for these operators.

Each row cites `tests/test_<file>.py::test_<function>` per D-05. Cross-reference 02-REVIEWS.md HIGH findings — if a HIGH defect overlaps with a NYQ-XX, note it in the gap row but allocate a fresh NYQ ID (don't recycle HARDEN-XX IDs).

NYQ allocation: NYQ-10..NYQ-19. Atomically append to REQUIREMENTS.md (D-08).
</action>
<acceptance_criteria>
- `find .planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/ -name '*-VALIDATION.md' | wc -l` outputs `1`.
- `grep -qE '^verdict: (PASS|PASS-WITH-GAPS|FAIL)$' .planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/02-VALIDATION.md` succeeds.
- **Verdict↔gap-count determinism (D-02 cross-check):** the deterministic shell sequence `B=$(grep -c '^- \[BLOCKING\]' .../02-VALIDATION.md || echo 0); A=$(grep -c '^- \[ADVISORY\]' .../02-VALIDATION.md || echo 0); V=$(grep -E '^verdict:' .../02-VALIDATION.md | awk '{print $2}'); case "$V" in PASS) test "$B" -eq 0 && test "$A" -eq 0 ;; PASS-WITH-GAPS) test "$B" -eq 0 && test "$A" -gt 0 ;; FAIL) test "$B" -gt 0 ;; *) false ;; esac` exits 0.
- `grep -q 'P2.1' .../02-VALIDATION.md` AND `grep -q 'P2.3' .../02-VALIDATION.md` AND `grep -q 'P3.4' .../02-VALIDATION.md` AND `grep -q 'P4.1' .../02-VALIDATION.md` all succeed (P2.1 combinational-loop is mandatory for the multi-cycle sequential operators introduced in Phase 02).
- `grep -q 'M>N' .../02-VALIDATION.md` succeeds (range-bound boundary present).
- `grep -qE 'tests/test_[a-zA-Z_]+\.py::test_' .../02-VALIDATION.md` succeeds.
- BLOCKING-row → NYQ-ID 1:1 match: `test $(grep -c '^- \[BLOCKING\]' .../02-VALIDATION.md) -eq $(grep -cE 'NYQ-1[0-9]\b' .../02-VALIDATION.md)` exits 0.
- `grep -E 'NYQ-' .../02-VALIDATION.md` only ever matches `NYQ-1[0-9]` (range scope) — `grep -E 'NYQ-(0[1-9]|[2-9][0-9])' .../02-VALIDATION.md` returns no matches.
- Every NYQ-XX in `.../02-VALIDATION.md` appears in `.planning/REQUIREMENTS.md` traceability table with target Phase ∈ {3, 4, 5}.
- `git diff --stat src/ tests/` produces zero output.
</acceptance_criteria>
</task>

<task id="2.1.3">
<title>Audit v1.0 Phase 03 — Remaining Tier 1 operators (|->, |=>, [*N], $rose, $fell, $stable, $past, disable iff, named sequences)</title>
<read_first>
- .planning/research/VALIDATION-TEMPLATE.md
- .planning/research/NYQUIST-CHECKLIST.md (operator sections: `|->`, `|=>`, `[*N]`/`[*M:N]`, `$rose`/`$fell`/`$stable`, `$past`, `disable iff`, named sequences)
- .planning/research/PITFALLS.md (P1.1 vacuity, P1.2 implication off-by-one, P1.3 bit-vector overflow, P1.6 disable iff async, P3.1 single-thread, P3.5 vacuity not tested — mandatory)
- .planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-PLAN.md
- .planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-VERIFICATION.md
- .planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-REVIEW.md (HIGH findings: HARDEN-01 disable iff/attempt_fired, HARDEN-02 _DECLARATIONS leak, HARDEN-03 rep_consecutive edge cases, HARDEN-04 _collect_signals naming — every HIGH must be traced into a corresponding NYQ-XX gap row even though it has its own HARDEN-XX ID, since this audit documents Nyquist coverage of the as-shipped state)
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md (structural model)
- templates/overlap_bitvec.sv.j2, templates/nonoverlap.sv.j2, templates/rep_consecutive.sv.j2, templates/rose.sv.j2, templates/fell.sv.j2, templates/stable.sv.j2, templates/past.sv.j2, templates/disable_iff_top.sv.j2 (operators under audit)
- tests/test_overlap_bitvec*.py, tests/test_nonoverlap*.py, tests/test_rep_consecutive*.py, tests/test_rose*.py, tests/test_fell*.py, tests/test_stable*.py, tests/test_past*.py, tests/test_disable_iff*.py, tests/simulation/ (citation source for D-05)
</read_first>
<action>
Run the audit harness if no skeleton exists. This is the most operator-dense phase — coverage table will have a sub-table per operator.

Operator boundary tables must include (per NYQUIST-CHECKLIST.md):
- `|->` overlapping: P1.2 same-cycle start, vacuous antecedent (P1.1), bit-vector overflow (P1.3) — multi-thread.
- `|=>` non-overlapping: same plus next-cycle off-by-one differentiator.
- `[*N]` / `[*M:N]`: `[*0]`, `[*0:0]`, `[*1]`, `[*N]` large, `[*M:N]` with `M>N`, counter overflow at `2^width` — link to HARDEN-03 root cause.
- `$rose`/`$fell`/`$stable`: power-on first-cycle, X-propagation at reset, reset-to-active-edge.
- `$past(sig, n)`: `n=0`, `n=1`, `n` ≫ pipeline depth.
- `disable iff`: P1.6 async semantics, interaction with `attempt_fired` latching (HARDEN-01 root cause — must appear as NYQ-XX gap referencing the as-shipped buggy behavior, even though HARDEN-01 covers the fix).
- Named sequences: argument substitution, hierarchical scope, recursive instantiation rejection, `_DECLARATIONS` global leak (HARDEN-02 root cause — must appear as NYQ-XX gap).

D-05 evidence citations mandatory per row. Anything uncovered or with a known HIGH defect → BLOCKING gap with NYQ-XX from NYQ-20..NYQ-29 range. Cite which HARDEN-XX requirement (if any) addresses the same root cause; that does NOT replace the NYQ-XX — Nyquist documents what coverage exists today, separately from what will be hardened.

Atomically append to REQUIREMENTS.md (D-08): NYQ subsection rows + traceability table rows with target Phase = 4 (HARDEN-02/03/04 territory) or 3 (HARDEN-01 territory).
</action>
<acceptance_criteria>
- `find .planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/ -name '*-VALIDATION.md' | wc -l` outputs `1`.
- `grep -qE '^verdict: (PASS|PASS-WITH-GAPS|FAIL)$' .planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-VALIDATION.md` succeeds.
- **Verdict↔gap-count determinism (D-02 cross-check):** the deterministic shell sequence `B=$(grep -c '^- \[BLOCKING\]' .../03-VALIDATION.md || echo 0); A=$(grep -c '^- \[ADVISORY\]' .../03-VALIDATION.md || echo 0); V=$(grep -E '^verdict:' .../03-VALIDATION.md | awk '{print $2}'); case "$V" in PASS) test "$B" -eq 0 && test "$A" -eq 0 ;; PASS-WITH-GAPS) test "$B" -eq 0 && test "$A" -gt 0 ;; FAIL) test "$B" -gt 0 ;; *) false ;; esac` exits 0.
- `grep -q 'P1.1' .../03-VALIDATION.md` AND `grep -q 'P1.2' .../03-VALIDATION.md` AND `grep -q 'P1.3' .../03-VALIDATION.md` AND `grep -q 'P1.6' .../03-VALIDATION.md` AND `grep -q 'P3.1' .../03-VALIDATION.md` AND `grep -q 'P3.5' .../03-VALIDATION.md` all succeed (P1.4 `throughout` and P1.5 `intersect` are Tier-2 operators NOT shipped in v1.0 per FEATURES.md — their omission here is intentional and is annotated in `.planning/research/NYQUIST-CHECKLIST.md` as deferred).
- `grep -q 'attempt_fired' .../03-VALIDATION.md` AND `grep -q 'HARDEN-01' .../03-VALIDATION.md` succeed (HARDEN-01 root cause traced).
- `grep -q 'HARDEN-03' .../03-VALIDATION.md` succeeds (rep_consecutive edge case traced).
- `grep -qE 'tests/test_[a-zA-Z_]+\.py::test_' .../03-VALIDATION.md` succeeds.
- BLOCKING-row → NYQ-ID 1:1 match: `test $(grep -c '^- \[BLOCKING\]' .../03-VALIDATION.md) -eq $(grep -cE 'NYQ-2[0-9]\b' .../03-VALIDATION.md)` exits 0.
- `grep -E 'NYQ-' .../03-VALIDATION.md` only ever matches `NYQ-2[0-9]` — `grep -E 'NYQ-(0[1-9]|1[0-9]|[3-9][0-9])' .../03-VALIDATION.md` returns no matches.
- Every NYQ-XX in `.../03-VALIDATION.md` appears in `.planning/REQUIREMENTS.md` traceability table.
- `git diff --stat src/ tests/` produces zero output.
</acceptance_criteria>
</task>

<task id="2.1.4">
<title>Audit v1.0 Phase 04 — Normalization + composition engine</title>
<read_first>
- .planning/research/VALIDATION-TEMPLATE.md
- .planning/research/NYQUIST-CHECKLIST.md (composition + normalization sections)
- .planning/research/PITFALLS.md (P8.2 token duplication, P4.1 NFA-DFA blowup, P4.2 unbounded repetition — mandatory for composition)
- .planning/milestones/v1.0-phases/04-normalization-composition-engine/VERIFICATION.md (note: bare `VERIFICATION.md` here, not prefixed — output filename normalizes to `04-VALIDATION.md` per D-09 specifics)
- .planning/milestones/v1.0-phases/04-normalization-composition-engine/ (all PLAN.md and SUMMARY.md files in this directory — pass-by-pass scope)
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md (structural model)
- src/sva2rtl/normalize.py and src/sva2rtl/compose.py paths exist (referenced as audit subjects, NOT modified — read-only)
- tests/test_normalize*.py, tests/test_compose*.py, tests/test_token*.py (citation source for D-05)
</read_first>
<action>
Run the audit harness; output filename is `04-VALIDATION.md` (per D-09 specifics, normalize to `0N-VALIDATION.md` even though the existing artifact is bare `VERIFICATION.md`).

Operators / passes under audit:
- IR normalization (`##0` collapse, `[*1]` collapse, identity simplifications, range-delay validation `M ≤ N`).
- Token-passing composition engine (P8.2 duplication on parallel branches — every `or` node MUST duplicate, every `and` node MUST gate).
- CheckerNode tree shape — antecedent / consequent wiring, clock thread, reset thread, `attempt_fired` thread.

Boundary cases (per NYQUIST-CHECKLIST.md):
- `##0` normalization vs `[*0]` normalization vs identity prop — ensure not conflated.
- `M>N` range-delay error path (P4.2 unbounded repetition — error path coverage).
- Token-count invariant on `or` node (must be 2 outgoing tokens for 1 incoming).
- Composition of named sequence with substituted arguments — token-count preservation.

Each row cites `tests/test_*.py::test_*` per D-05. NYQ allocation: NYQ-30..NYQ-39. Atomically append to REQUIREMENTS.md.
</action>
<acceptance_criteria>
- `find .planning/milestones/v1.0-phases/04-normalization-composition-engine/ -name '*-VALIDATION.md' | wc -l` outputs `1` (and the file is named `04-VALIDATION.md`, not bare `VALIDATION.md`).
- `test -f .planning/milestones/v1.0-phases/04-normalization-composition-engine/04-VALIDATION.md` succeeds.
- `grep -qE '^verdict: (PASS|PASS-WITH-GAPS|FAIL)$' .../04-VALIDATION.md` succeeds.
- **Verdict↔gap-count determinism (D-02 cross-check):** the deterministic shell sequence `B=$(grep -c '^- \[BLOCKING\]' .../04-VALIDATION.md || echo 0); A=$(grep -c '^- \[ADVISORY\]' .../04-VALIDATION.md || echo 0); V=$(grep -E '^verdict:' .../04-VALIDATION.md | awk '{print $2}'); case "$V" in PASS) test "$B" -eq 0 && test "$A" -eq 0 ;; PASS-WITH-GAPS) test "$B" -eq 0 && test "$A" -gt 0 ;; FAIL) test "$B" -gt 0 ;; *) false ;; esac` exits 0.
- `grep -q 'P8.2' .../04-VALIDATION.md` AND `grep -q 'P4.1' .../04-VALIDATION.md` AND `grep -q 'P4.2' .../04-VALIDATION.md` all succeed.
- `grep -qE 'tests/test_[a-zA-Z_]+\.py::test_' .../04-VALIDATION.md` succeeds.
- BLOCKING-row → NYQ-ID 1:1 match: `test $(grep -c '^- \[BLOCKING\]' .../04-VALIDATION.md) -eq $(grep -cE 'NYQ-3[0-9]\b' .../04-VALIDATION.md)` exits 0.
- `grep -E 'NYQ-' .../04-VALIDATION.md` only ever matches `NYQ-3[0-9]` — `grep -E 'NYQ-(0[1-9]|[12][0-9]|[4-9][0-9])' .../04-VALIDATION.md` returns no matches.
- Every NYQ-XX in `.../04-VALIDATION.md` appears in `.planning/REQUIREMENTS.md` traceability table with target Phase ∈ {3, 4, 5}.
- `git diff --stat src/ tests/` produces zero output.
</acceptance_criteria>
</task>

<task id="2.1.5">
<title>Audit v1.0 Phase 05 — Optimization passes (CSE, constant folding, counter encoding)</title>
<read_first>
- .planning/research/VALIDATION-TEMPLATE.md
- .planning/research/NYQUIST-CHECKLIST.md (optimization-pass sections — counter encoding, CSE, constant folding, dead-state)
- .planning/research/PITFALLS.md (P2.3 counter bit-width, P4.1 NFA-DFA blowup, P5.4 observable monitor state — mandatory; also "correctness-sacrificing optimization" anti-feature from FEATURES.md)
- .planning/milestones/v1.0-phases/05-optimization-passes/VERIFICATION.md (note: bare `VERIFICATION.md` — output normalizes to `05-VALIDATION.md`)
- .planning/milestones/v1.0-phases/05-optimization-passes/ (all PLAN.md and SUMMARY.md files — pass-by-pass scope)
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md (structural model)
- tests/test_optimize*.py, tests/test_golden_parity.py (citation source for D-05 — golden parity ensures optimizer is correctness-preserving)
</read_first>
<action>
Run the audit harness; output filename is `05-VALIDATION.md`.

Optimization passes under audit (per FEATURES.md §2.2 and `.planning/milestones/v1.0-phases/05-optimization-passes/`):
- Constant folding (boolean simplification at IR level).
- Common sub-expression elimination (CSE) via structural hashing.
- Counter encoding for range delays / repetition (counter width = `ceil(log2(N+1)) + 1` per P2.3).
- Dead-state pruning (if applicable to v1.0; mark as not-applicable if not shipped).

Boundary cases:
- Optimizer correctness invariant: `--no-optimize` and optimized output behaviorally equivalent on golden parity (`tests/test_golden_parity.py`).
- Counter width at `N=0`, `N=1`, `N=2^k`, `N=2^k - 1`, `N=2^k + 1` — width must not regress.
- CSE on duplicate antecedent across multiple properties — single shared logic emitted.
- Constant folding does not eliminate `attempt_fired` (vacuity must remain observable — P5.4 observable monitor state).

NYQ allocation: NYQ-40..NYQ-49. Most NYQ rows here will be ADVISORY (optimizer correctness is gated by golden-parity tests; gaps are typically about under-optimization, not miscompiles), but flag any "constant folds away `attempt_fired`" or "counter width too narrow at boundary" finding as BLOCKING. Atomically append to REQUIREMENTS.md.
</action>
<acceptance_criteria>
- `find .planning/milestones/v1.0-phases/05-optimization-passes/ -name '*-VALIDATION.md' | wc -l` outputs `1` (named `05-VALIDATION.md`).
- `test -f .planning/milestones/v1.0-phases/05-optimization-passes/05-VALIDATION.md` succeeds.
- `grep -qE '^verdict: (PASS|PASS-WITH-GAPS|FAIL)$' .../05-VALIDATION.md` succeeds.
- **Verdict↔gap-count determinism (D-02 cross-check):** the deterministic shell sequence `B=$(grep -c '^- \[BLOCKING\]' .../05-VALIDATION.md || echo 0); A=$(grep -c '^- \[ADVISORY\]' .../05-VALIDATION.md || echo 0); V=$(grep -E '^verdict:' .../05-VALIDATION.md | awk '{print $2}'); case "$V" in PASS) test "$B" -eq 0 && test "$A" -eq 0 ;; PASS-WITH-GAPS) test "$B" -eq 0 && test "$A" -gt 0 ;; FAIL) test "$B" -gt 0 ;; *) false ;; esac` exits 0.
- `grep -q 'P2.3' .../05-VALIDATION.md` AND `grep -q 'P4.1' .../05-VALIDATION.md` AND `grep -q 'P5.4' .../05-VALIDATION.md` succeed (P5.4 observable monitor state — `attempt_fired` must not be optimized away).
- `grep -q 'golden_parity' .../05-VALIDATION.md` succeeds (correctness-preservation invariant cited).
- `grep -qE 'tests/test_[a-zA-Z_]+\.py::test_' .../05-VALIDATION.md` succeeds.
- BLOCKING-row → NYQ-ID 1:1 match: `test $(grep -c '^- \[BLOCKING\]' .../05-VALIDATION.md) -eq $(grep -cE 'NYQ-4[0-9]\b' .../05-VALIDATION.md)` exits 0.
- `grep -E 'NYQ-' .../05-VALIDATION.md` only ever matches `NYQ-4[0-9]` — `grep -E 'NYQ-(0[1-9]|[1-3][0-9]|[5-9][0-9])' .../05-VALIDATION.md` returns no matches.
- Every NYQ-XX in `.../05-VALIDATION.md` appears in `.planning/REQUIREMENTS.md` traceability table.
- `git diff --stat src/ tests/` produces zero output.
</acceptance_criteria>
</task>

<task id="2.1.6">
<title>Audit v1.0 Phase 06 — CLI polish + Verilog-2001 + integration testing</title>
<read_first>
- .planning/research/VALIDATION-TEMPLATE.md
- .planning/research/NYQUIST-CHECKLIST.md (CLI surface + Verilog-2001 emission sections)
- .planning/research/PITFALLS.md (P5.1 source location in errors, P5.2 supported-construct documentation — mandatory; CLI usability gaps)
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-PLAN.md (if exists) and 01-PLAN.md, 02-PLAN.md, 03-PLAN.md
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md (structural model AND existing per-plan evidence)
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-REVIEW.md (HIGH findings: HARDEN-05 dump-tree multi-property, HARDEN-06 unlabeled property, HARDEN-07 output ambiguity, HARDEN-08 verilog vs dump conflict — must appear as NYQ-XX gaps)
- tests/test_cli_phase6.py, tests/test_verilog_mode.py, tests/test_integration_full.py (citation source for D-05)
- tests/test_golden_parity.py (V2001 byte-equivalence)
</read_first>
<action>
Run the audit harness; output filename is `06-VALIDATION.md`.

Surface under audit:
- All Phase 6 CLI flags: `--output`, `--property`, `--verilog`, `--slang-path`, `--dump-ast`, `--dump-ir`, `--dump-tree`, `--no-optimize`, `--version`.
- Verilog-2001 emission: `logic→wire/reg`, `always_ff→always @(...)`, `'0→0` across all 11 templates.
- Integration: iverilog -g2001 compile gate, golden parity, `bind` generation.
- Multi-property pipeline.

Boundary cases:
- `--property` with no match → `SVA-E005` exit 2.
- `--property` against unlabeled assertion (HARDEN-06 root cause — must produce NYQ-XX gap).
- `--dump-tree` on multi-property file (HARDEN-05 root cause — dump only first vs all).
- `--output` file vs directory mode (HARDEN-07 root cause).
- `--verilog` combined with `--dump-ast`/`--dump-ir`/`--dump-tree` (HARDEN-08 root cause — silent ignore).
- iverilog -g2001 zero-warning compile across 9 fixtures.
- P5.1 source location in error messages.

NYQ allocation: NYQ-50..NYQ-59. Most BLOCKING gaps here map to Phase 5 (CLI fixes). Atomically append to REQUIREMENTS.md.
</action>
<acceptance_criteria>
- `find .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/ -name '*-VALIDATION.md' | wc -l` outputs `1`.
- `test -f .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VALIDATION.md` succeeds.
- `grep -qE '^verdict: (PASS|PASS-WITH-GAPS|FAIL)$' .../06-VALIDATION.md` succeeds.
- **Verdict↔gap-count determinism (D-02 cross-check):** the deterministic shell sequence `B=$(grep -c '^- \[BLOCKING\]' .../06-VALIDATION.md || echo 0); A=$(grep -c '^- \[ADVISORY\]' .../06-VALIDATION.md || echo 0); V=$(grep -E '^verdict:' .../06-VALIDATION.md | awk '{print $2}'); case "$V" in PASS) test "$B" -eq 0 && test "$A" -eq 0 ;; PASS-WITH-GAPS) test "$B" -eq 0 && test "$A" -gt 0 ;; FAIL) test "$B" -gt 0 ;; *) false ;; esac` exits 0.
- `grep -q 'P5.1' .../06-VALIDATION.md` AND `grep -q 'P5.2' .../06-VALIDATION.md` succeed.
- `grep -q 'HARDEN-05' .../06-VALIDATION.md` AND `grep -q 'HARDEN-06' .../06-VALIDATION.md` AND `grep -q 'HARDEN-07' .../06-VALIDATION.md` AND `grep -q 'HARDEN-08' .../06-VALIDATION.md` all succeed (CLI HIGH defects traced).
- `grep -qE 'tests/test_[a-zA-Z_]+\.py::test_' .../06-VALIDATION.md` succeeds.
- BLOCKING-row → NYQ-ID 1:1 match: `test $(grep -c '^- \[BLOCKING\]' .../06-VALIDATION.md) -eq $(grep -cE 'NYQ-5[0-9]\b' .../06-VALIDATION.md)` exits 0.
- `grep -E 'NYQ-' .../06-VALIDATION.md` only ever matches `NYQ-5[0-9]` — `grep -E 'NYQ-(0[1-9]|[1-4][0-9]|[6-9][0-9])' .../06-VALIDATION.md` returns no matches.
- Every NYQ-XX in `.../06-VALIDATION.md` appears in `.planning/REQUIREMENTS.md` traceability table with target Phase ∈ {3, 4, 5}.
- `git diff --stat src/ tests/` produces zero output.
</acceptance_criteria>
</task>

<task id="2.1.7">
<title>Final gate — regression suite green + read-only contract attestation + harness --check</title>
<read_first>
- All six `0N-VALIDATION.md` files written by tasks 2.1.1–2.1.6 (verify presence count = 6)
- .planning/REQUIREMENTS.md (verify NYQ-XX rows added by previous tasks land correctly in traceability table)
- tools/audit/seed_validation_skeletons.py (use --check mode for gate)
- .planning/phases/01-retroactive-nyquist-baseline/01-CONTEXT.md (read-only contract per phase contract; 736-test gate)
</read_first>
<action>
This task is the close-out gate. It does not edit content. It verifies:

1. Run `python tools/audit/seed_validation_skeletons.py --check` — exit 0 means all six `0N-VALIDATION.md` files exist.
2. Run `find .planning/milestones/v1.0-phases/ -maxdepth 2 -name '*-VALIDATION.md' | wc -l` — must output `6` (no duplicates, no misses).
3. Run `grep -E 'NYQ-[0-9]+' .planning/REQUIREMENTS.md | wc -l` — must be ≥ 1 (audit produced at least one NYQ-XX row, otherwise the audit produced no findings — also acceptable if all six audits returned PASS verdict, but cross-check by greping each VALIDATION.md for `verdict: PASS` and counting six PASS verdicts).
4. Run the full regression suite: `pytest tests/ --timeout=120` — must exit 0 with stdout containing the substring `736 passed`.
5. Run `git diff --stat src/ tests/` — must produce zero output (read-only contract).
6. Run `mypy --strict src/` and `ruff check src/ tests/` — both must exit 0 (no production code touched ⇒ both must remain clean).

If any of the above fails, stop and surface the failure. The task does not write any files; it is a pure verification gate.
</action>
<acceptance_criteria>
- `python tools/audit/seed_validation_skeletons.py --check` exits 0.
- `find .planning/milestones/v1.0-phases/ -maxdepth 2 -name '*-VALIDATION.md' | wc -l` outputs `6`.
- `pytest tests/ --timeout=120` exits 0 AND stdout contains the substring `736 passed`.
- `git diff --stat src/ tests/` produces zero output.
- `mypy --strict src/` exits 0.
- `ruff check src/ tests/` exits 0.
- For each `0N` ∈ {01, 02, 03, 04, 05, 06}: `grep -qE '^verdict: (PASS|PASS-WITH-GAPS|FAIL)$'` on the corresponding `0N-VALIDATION.md` succeeds.
- The `.planning/REQUIREMENTS.md` traceability table is internally consistent: every NYQ-XX row mentioned in any VALIDATION.md appears in the table with target Phase ∈ {3, 4, 5} (cross-checked by grep of NYQ-XX IDs from each VALIDATION.md against the REQUIREMENTS.md traceability table).
</acceptance_criteria>
</task>

## Verification

```bash
python tools/audit/seed_validation_skeletons.py --check
find .planning/milestones/v1.0-phases/ -maxdepth 2 -name '*-VALIDATION.md' | wc -l   # expects 6
pytest tests/ --timeout=120                                                          # expects 736 passed
git diff --stat src/ tests/                                                          # expects empty
mypy --strict src/
ruff check src/ tests/
```

## must_haves

- All six `0N-VALIDATION.md` files exist (one per v1.0 phase directory) — covers success criterion 1.
- Each VALIDATION.md identifies operators exercised, boundary/edge cases, gaps, and a deterministic verdict tier (PASS / PASS-WITH-GAPS / FAIL) — covers success criterion 2.
- All BLOCKING gaps carry `NYQ-XX` IDs from the per-phase ranges (Phase 1 → 01..09, …, Phase 6 → 50..59) and are appended atomically to `REQUIREMENTS.md` with target Phase ∈ {3, 4, 5} — covers success criterion 3.
- All 736 regression tests pass at the close of Plan 02; no production code modified — covers success criterion 4 and the read-only contract.
- Read-only contract enforced via `git diff --stat src/ tests/` produces zero output across every per-phase task and the final gate.
- Each per-phase audit task is self-contained (own input dir, own output file, own NYQ-XX range, own REQUIREMENTS.md append) — wave-parallelizable as a sub-wave per the phase requirements.
