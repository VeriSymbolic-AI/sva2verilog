---
wave: 1
depends_on: []
files_modified:
  - .planning/research/VALIDATION-TEMPLATE.md
  - .planning/research/NYQUIST-CHECKLIST.md
  - tools/audit/seed_validation_skeletons.py
  - tools/audit/README.md
autonomous: true
requirements: [VALIDATE-01]
---

# Plan 01: Nyquist VALIDATION.md Template + Per-Operator Boundary Checklist + Audit Harness

## Goal

Author the shared artifacts that Plan 02 consumes to produce the six v1.0 phase Nyquist coverage reports:

1. A canonical `VALIDATION.md` template that mirrors `06-VERIFICATION.md`'s structure (front-matter, verdict-first, must-have evidence, file-by-file evidence, Gaps section).
2. A static per-operator boundary checklist seeded from `PITFALLS.md` (mandatory rows, per D-04) plus the Tier-1 operator inventory in `FEATURES.md`.
3. A read-only audit harness script that walks `.planning/milestones/v1.0-phases/0N-*/` and stubs out exactly one empty `0N-VALIDATION.md` skeleton per phase directory, keyed on phase number.
4. The `NYQ-XX` ID allocation rule (per-phase range table, sequential within range).

This plan writes ONLY to `.planning/research/` and `tools/audit/` — no production code, no v1.0 phase artifact directories, no REQUIREMENTS.md edits. Plan 02 does the consuming work.

## Requirements

- **VALIDATE-01** — All 6 v1.0 phase directories under `.planning/milestones/v1.0-phases/` will contain a `*-VALIDATION.md` Nyquist coverage report. Plan 01 ships the template, the boundary checklist, and the harness that Plan 02 needs to satisfy this requirement.

## Threat Model

<threat_model>
- **Harness silently overwrites a real VALIDATION.md** — Mitigated by skeleton script refusing to write when target file already exists (idempotent / safe re-run).
- **Boundary checklist drifts from PITFALLS.md** — Mitigated by checklist citing every pitfall ID by name in a dedicated section, and Plan 02 grep-asserting every PITFALLS.md ID appears in the relevant operator's coverage table.
- **Template drift from `06-VERIFICATION.md`** — Mitigated by template's front-matter field set being the exact superset of `06-VERIFICATION.md`'s plus `verdict` and `gap_count` for deterministic verdict tier classification (D-02).
- **NYQ-XX ID collisions across parallel Plan 02 tasks** — Mitigated by Plan 01 publishing a fixed per-phase NYQ range table (Phase 1 → NYQ-01..09, Phase 2 → NYQ-10..19, etc.); each Plan 02 task owns its own 10-ID range and cannot collide.
- **Read-only contract violated by harness side effects** — Harness writes only to phase directories under `.planning/milestones/v1.0-phases/0N-*/` and never touches `src/` or `tests/`; Plan 02 final task verifies via `git diff --stat src/ tests/`. Plan 01 itself only exercises the harness via `--dry-run` (no skeleton files created during Plan 01) so its own scope contract (writes ONLY to `.planning/research/` and `tools/audit/`) is preserved.
</threat_model>

## Tasks

<task id="1.1.1">
<title>Author VALIDATION.md template at .planning/research/VALIDATION-TEMPLATE.md</title>
<read_first>
- .planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VERIFICATION.md (canonical structural model — copy section ordering verbatim)
- .planning/phases/01-retroactive-nyquist-baseline/01-CONTEXT.md (D-01 schema, D-02 verdict tiers, D-03 gap classification, D-08 atomic-append rule)
- .planning/REQUIREMENTS.md (front-matter `requirements` field convention; traceability table format)
</read_first>
<action>
Create `.planning/research/VALIDATION-TEMPLATE.md`. Front-matter fields (mandatory): `phase`, `phase_number`, `phase_name`, `verifier`, `verified` (date), `status` (mirrors verdict — `passed` / `passed-with-gaps` / `failed`), `requirement_ids` (list — `[VALIDATE-01]` plus any NYQ-XX rows the audit produces), `verdict` (one of `PASS` / `PASS-WITH-GAPS` / `FAIL` per D-02), `gap_count_blocking` (int), `gap_count_advisory` (int).

Body sections (in order, mirroring `06-VERIFICATION.md`):
1. Verdict-first headline (one of three tiers, with a one-paragraph justification).
2. Operators exercised (table: operator, source location in templates/, IR node kind, evidence test file).
3. Boundary / edge-case coverage table — one sub-table per operator. Columns: `Boundary`, `Source` (PITFALLS pitfall ID OR static-checklist row ID), `Evidence` (`tests/test_<file>.py::test_<function>` — D-05 mandate), `Status` (COVERED / GAP-BLOCKING / GAP-ADVISORY).
4. Pitfall coverage cross-reference (every PITFALLS.md row that applies to this phase appears at least once in §3).
5. Gaps — itemized list. Gap-row syntax is fixed: each gap row begins exactly with the literal prefix `- [BLOCKING]` or `- [ADVISORY]` at the start of its line. Every BLOCKING gap row carries an `NYQ-XX` ID (D-06) immediately after the marker, then a target hardening phase (3 → templates, 4 → IR/codegen, 5 → CLI), and a one-line justification. ADVISORY gaps stay here only (D-07) and do NOT carry NYQ-XX IDs. This row format is what Plan 02's verdict↔gap-count cross-check greps for.
6. Verdict-tier derivation — show the gap counts and the deterministic mapping (0 gaps → PASS; only ADVISORY → PASS-WITH-GAPS; any BLOCKING or any uncovered operator → FAIL).
7. Read-only contract attestation — `git diff --stat src/ tests/` excerpt confirming zero changes attributable to this audit.

Include a placeholder for the per-phase NYQ-XX range (`<!-- NYQ range: NYQ-XX..NYQ-YY -->`) so Plan 02's harness can substitute the right range per phase.

Also include a section labeled "## Per-Phase NYQ-XX Range Table" containing this fixed allocation:
- v1.0 Phase 01 → NYQ-01..NYQ-09
- v1.0 Phase 02 → NYQ-10..NYQ-19
- v1.0 Phase 03 → NYQ-20..NYQ-29
- v1.0 Phase 04 → NYQ-30..NYQ-39
- v1.0 Phase 05 → NYQ-40..NYQ-49
- v1.0 Phase 06 → NYQ-50..NYQ-59

Do not include full Markdown bodies for fenced code blocks of generated content here — the template itself is the only fenced output, lives in the file at the path above, and is referenced by `<read_first>` in Plan 02 tasks.
</action>
<acceptance_criteria>
- `test -f .planning/research/VALIDATION-TEMPLATE.md` succeeds (exit 0).
- `grep -q '^phase_number:' .planning/research/VALIDATION-TEMPLATE.md` succeeds.
- `grep -q '^verdict:' .planning/research/VALIDATION-TEMPLATE.md` succeeds.
- `grep -q '^requirement_ids:' .planning/research/VALIDATION-TEMPLATE.md` succeeds.
- `grep -qE '(PASS|PASS-WITH-GAPS|FAIL)' .planning/research/VALIDATION-TEMPLATE.md` succeeds.
- `grep -q 'NYQ-01..NYQ-09' .planning/research/VALIDATION-TEMPLATE.md` succeeds (range table present).
- `grep -q 'NYQ-50..NYQ-59' .planning/research/VALIDATION-TEMPLATE.md` succeeds.
- `grep -q 'BLOCKING' .planning/research/VALIDATION-TEMPLATE.md` AND `grep -q 'ADVISORY' .planning/research/VALIDATION-TEMPLATE.md` both succeed (D-03 severity tiers documented).
- `grep -q '\- \[BLOCKING\]' .planning/research/VALIDATION-TEMPLATE.md` AND `grep -q '\- \[ADVISORY\]' .planning/research/VALIDATION-TEMPLATE.md` both succeed (gap-row marker syntax — `- [BLOCKING]` / `- [ADVISORY]` — is documented in the template, so Plan 02's verdict↔gap-count cross-check has a stable substring to match).
- `grep -qi 'tests/test_' .planning/research/VALIDATION-TEMPLATE.md` succeeds (D-05 evidence-citation requirement is documented in the boundary table).
- Section headings include all of: "Operators exercised", "Boundary", "Pitfall coverage", "Gaps", "Verdict", "Read-only contract" (verified via `grep -c` ≥ 6 distinct heading hits).
</acceptance_criteria>
</task>

<task id="1.1.2">
<title>Author per-operator boundary checklist at .planning/research/NYQUIST-CHECKLIST.md</title>
<read_first>
- .planning/research/PITFALLS.md (every pitfall row is a mandatory Nyquist sample point per D-04 — checklist must enumerate each by ID)
- .planning/research/FEATURES.md (Tier 1 operator inventory shipped in v1.0 — one checklist section per operator; §2.1 lists Tier 2 operators including `throughout` and `intersect`, which are out of v1.0 scope)
- .planning/phases/01-retroactive-nyquist-baseline/01-CONTEXT.md (D-04 enumerates the static-checklist boundaries the planner must add beyond pitfalls — `##0`/`##1`/`##N`, `##[0:0]`/`##[M:M]`/`##[M:N]` with `M>N`, `[*0]`/`[*0:0]`/`[*N]`/`[*M:N]` overflow, `$past(sig, 0)` vs large `n`, `disable iff` vs `attempt_fired` interaction, multi-thread overlapping implication bit-vector overflow)
- templates/ directory listing (operator → template file mapping: bool_expr, concat_delay, rep_consecutive, overlap_bitvec, nonoverlap, disable_iff_top, rose, fell, stable, past, seq_concat_top, bind)
</read_first>
<action>
Create `.planning/research/NYQUIST-CHECKLIST.md` with a top-level table listing each Tier-1 v1.0 operator (from FEATURES.md §1.1) mapped to the relevant template file under `templates/` and the relevant Phase under `.planning/milestones/v1.0-phases/`. For each operator, provide a sub-section with a static boundary checklist following these rules:

- "Pitfall-derived rows" — one row per applicable PITFALLS.md pitfall ID (P1.1 through P8.5), referencing the pitfall by ID and one-line summary.
- "Static rows" — boundaries pitfalls don't list, drawn from D-04 verbatim (the boundary list above) plus per-operator specifics:
  - `##N` / `##[M:N]`: `##0`, `##1`, `##N` (large), `##[0:0]`, `##[M:M]`, `##[M:N]` with `M>N` (must be a hard error or normalized at IR level), `##[0:N]`, `##[N:N+1]`.
  - `[*N]` / `[*M:N]`: `[*0]`, `[*0:0]`, `[*1]`, `[*N]` (large), `[*M:N]` with `M>N` (error path), counter overflow at `2^width`.
  - `$past(sig, n)`: `n=0` (degenerate identity), `n=1`, `n` ≫ pipeline depth (silent shift-register exhaustion).
  - `|->` / `|=>`: same-cycle vs next-cycle start-off-by-one (P1.2), multi-thread bit-vector overflow (P1.3), vacuous antecedent (P1.1).
  - `$rose` / `$fell` / `$stable`: power-on first-cycle behavior, X-propagation at reset.
  - `disable iff`: async semantics (P1.6), interaction with `attempt_fired` latching (HARDEN-01 root cause), one-cycle disable spurious window.
  - Named sequences / properties: argument substitution, recursive instantiation rejection, hierarchical scope.

Each row carries: `Boundary` description, `Source` (`PITFALLS:Pn.x` or `STATIC:Sn.x`), and a placeholder `Evidence` column (Plan 02 fills the `tests/test_*.py::test_*` citation per D-05).

Add a top-of-file rule block:
- "Every PITFALLS.md row is a mandatory row in the operator(s) it applies to."
- "Every static row that is uncovered in v1.0 is a candidate gap (BLOCKING if silent miscompile possible, ADVISORY otherwise per D-03)."
- "Plan 02 audit tasks fill the Evidence column; missing evidence = gap row."
- "Pitfalls P1.4 (`throughout` every-tick semantics) and P1.5 (`intersect` same-start-AND-end) apply only to Tier 2 operators per FEATURES.md §2.1 and are out of v1.0 scope. Each MUST appear in this file with the explicit annotation `Tier 2 — out of v1.0 scope, deferred` so the omission from Plan 02's per-phase grep coverage is auditable."

Map each operator to its target Plan 02 audit task by listing the v1.0 phase number that ships it, so Plan 02 tasks know which checklist sub-section is theirs.
</action>
<acceptance_criteria>
- `test -f .planning/research/NYQUIST-CHECKLIST.md` succeeds.
- For every pitfall ID `P1.1`, `P1.2`, `P1.3`, `P1.4`, `P1.5`, `P1.6`, `P1.8`, `P2.1`, `P2.3`, `P2.4`, `P3.1`, `P3.4`, `P3.5`, `P4.1`, `P4.2`, `P5.1`, `P5.4`, `P8.1`, `P8.2`, `P8.4` — `grep -q '<id>' .planning/research/NYQUIST-CHECKLIST.md` succeeds (every PITFALLS.md row appears).
- `grep -c '^## ' .planning/research/NYQUIST-CHECKLIST.md` returns ≥ 9 (one section per Tier-1 operator: bool, `##N`, `##[M:N]`, `[*N]`, `$rose`/`$fell`/`$stable` (counted once), `$past`, `|->`, `|=>`, `disable iff`, named sequences/properties).
- `grep -q 'STATIC:' .planning/research/NYQUIST-CHECKLIST.md` succeeds (static-checklist rows are tagged).
- `grep -q 'PITFALLS:' .planning/research/NYQUIST-CHECKLIST.md` succeeds.
- `grep -q 'attempt_fired' .planning/research/NYQUIST-CHECKLIST.md` succeeds (HARDEN-01 root-cause row present).
- `grep -q 'M>N' .planning/research/NYQUIST-CHECKLIST.md` succeeds (range-bound static row present).
- `grep -q 'Tier 2' .planning/research/NYQUIST-CHECKLIST.md` succeeds AND each of `grep -q 'P1.4' ...` and `grep -q 'P1.5' ...` co-occur in lines containing `Tier 2 — out of v1.0 scope, deferred` (verified by `grep -B0 -A0 'P1.4' .../NYQUIST-CHECKLIST.md | grep -q 'Tier 2'` and same for P1.5) — Tier 2 deferral is explicit and auditable.
</acceptance_criteria>
</task>

<task id="1.1.3">
<title>Author audit harness at tools/audit/seed_validation_skeletons.py</title>
<read_first>
- .planning/research/VALIDATION-TEMPLATE.md (template authored by task 1.1.1 — script copies its body, substitutes `<phase_number>`, `<phase_name>`, `<NYQ range>` placeholders)
- .planning/phases/01-retroactive-nyquist-baseline/01-CONTEXT.md (D-09 plan split, output filename convention `0N-VALIDATION.md`)
- existing v1.0 phase directory names under `.planning/milestones/v1.0-phases/` (six directories — script must walk them and pull phase number from the leading `0N-` prefix)
</read_first>
<action>
Create `tools/audit/seed_validation_skeletons.py` (and a one-line `tools/audit/README.md` describing it as the v1.1 Phase 1 audit harness). The script:

1. Walks `.planning/milestones/v1.0-phases/0N-*/` (exactly six directories expected).
2. For each phase dir, computes the target filename `0N-VALIDATION.md` (uses the leading two-digit prefix from the directory name).
3. Refuses to write if `0N-VALIDATION.md` already exists in that phase dir (idempotent — exits 0 with a "skip" message; does not overwrite).
4. Reads `.planning/research/VALIDATION-TEMPLATE.md` and substitutes per-phase placeholders: `<phase_number>` ← `0N`, `<phase_name>` ← directory name's tail (after the `0N-` prefix), `<NYQ range>` ← per-phase range from the table baked into the template.
5. Writes the filled skeleton to `0N-VALIDATION.md` in the phase directory.
6. Refuses (non-zero exit) to write to anything outside `.planning/milestones/v1.0-phases/`. Read-only with respect to `src/` and `tests/` — the script must NOT import from `src/` and must NOT touch `tests/`.

Add a `--dry-run` flag that lists the targets but does not write. Add a `--check` flag that just verifies existence (exit 0 if all six phase dirs have a `0N-VALIDATION.md`, exit non-zero otherwise — useful for Plan 02's gate).

Script must be runnable as `python tools/audit/seed_validation_skeletons.py --dry-run` and produce six `would-write` lines on stdout. Script must be standalone (stdlib only — no `pyslang`, no `click`, no `jinja2` import — keeps the audit harness independent of the production toolchain per the read-only contract).

Add a CLI usage doc-string. Include type hints. Pass `mypy --strict tools/audit/seed_validation_skeletons.py`.

Plan 01's scope writes ONLY to `.planning/research/` and `tools/audit/`. The side-effecting harness execution that creates the six skeleton files is performed by Plan 02 task 2.1.1's preamble, NOT by Plan 01. This task's acceptance therefore exercises only the read-only paths (`--dry-run`, `--check`).
</action>
<acceptance_criteria>
- `test -f tools/audit/seed_validation_skeletons.py` succeeds.
- `test -f tools/audit/README.md` succeeds.
- `python tools/audit/seed_validation_skeletons.py --dry-run` exits 0 and stdout contains six lines matching `would-write .*0[1-6]-VALIDATION.md`.
- `python tools/audit/seed_validation_skeletons.py --check` exits non-zero before Plan 02 has run (zero of six skeletons exist) — verified at Plan 01 close-out time.
- Script imports only stdlib modules (`grep -E '^import (click|jinja2|pyslang|sva2rtl)' tools/audit/seed_validation_skeletons.py` returns no matches).
- `mypy --strict tools/audit/seed_validation_skeletons.py` exits 0.
- `ruff check tools/audit/seed_validation_skeletons.py` exits 0.
- `--dry-run` smoke test (read-only) confirms scope contract: `python tools/audit/seed_validation_skeletons.py --dry-run` exits 0, prints exactly six "would-write" lines on stdout, AND `git status --porcelain .planning/milestones/v1.0-phases/` reports zero untracked or modified files (Plan 01's scope is `.planning/research/` and `tools/audit/` only — no v1.0 phase artifact directories may be touched here).
- `git diff --stat src/ tests/` after the `--dry-run` invocation produces zero output (read-only contract).
- Idempotency contract documented in the script: when invoked without `--dry-run` against a tree where one or more skeletons already exist, the script skips existing files (does not overwrite). This contract is exercised and verified by Plan 02 task 2.1.1's preamble; Plan 01 verifies only the dry-run path.
</acceptance_criteria>
</task>

## Verification

```bash
test -f .planning/research/VALIDATION-TEMPLATE.md
test -f .planning/research/NYQUIST-CHECKLIST.md
test -f tools/audit/seed_validation_skeletons.py
python tools/audit/seed_validation_skeletons.py --dry-run
git status --porcelain .planning/milestones/v1.0-phases/    # must be empty
mypy --strict tools/audit/seed_validation_skeletons.py
ruff check tools/audit/seed_validation_skeletons.py
git diff --stat src/ tests/  # must show zero changes
```

## must_haves

- Template at `.planning/research/VALIDATION-TEMPLATE.md` mirrors `06-VERIFICATION.md` structure with verdict-first, operator inventory, boundary tables, gaps section, and verdict-tier derivation (success criterion 2).
- Per-operator boundary checklist at `.planning/research/NYQUIST-CHECKLIST.md` cites every PITFALLS.md row by ID (D-04 floor) and adds the static-row boundaries from D-04 (success criterion 2). Tier 2 pitfalls (P1.4, P1.5) carry an explicit "Tier 2 — out of v1.0 scope, deferred" annotation so their absence from Plan 02 grep coverage is auditable.
- Per-phase NYQ-XX range table is fixed and documented (Phase 1 → NYQ-01..09, …, Phase 6 → NYQ-50..59) so Plan 02 parallel audits cannot collide on IDs (success criterion 3).
- Audit harness `tools/audit/seed_validation_skeletons.py` walks the six v1.0 phase dirs and seeds skeletons keyed on phase number, idempotent and `src/`/`tests/`-read-only (success criterion 4). Plan 01 exercises only the harness's `--dry-run` and `--check` paths; the side-effecting skeleton-creation invocation lives in Plan 02 task 2.1.1's preamble, preserving Plan 01's scope contract.
- Plan 02 has all artifacts it needs to write the six VALIDATION.md files in parallel without further Plan 01 inputs.
