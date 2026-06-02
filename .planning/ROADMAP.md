---
milestone: v1.1
milestone_name: Hardening Release
created: 2026-06-02
total_phases: 7
total_requirements: 22
---

# Roadmap — sva2rtl

## Milestones

- ✅ **v1.0 MVP** — SVA→RTL Compiler — Phases 1-6 (shipped 2026-06-01) — see [.planning/milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- 📋 **v1.1 Hardening Release** (in progress) — 7 phases, 22 requirements

---

## v1.1 — Hardening Release

**Goal:** Close all carry-forward debt from v1.0, refactor Verilog-2001 template duplication at the root cause, add Verilator as a second simulation oracle, and ship `v1.1.0` as a publicly-tagged maintenance release.

**Ordering principle:** Establish baseline → expand validation infrastructure → fix at root cause → fix remaining HIGH defects → polish → release.

**Phase numbering:** Starts at Phase 1 (`--reset-phase-numbers` active; v1.0 phases archived to `.planning/milestones/v1.0-phases/`).

### Phase Overview

| Phase | Name | Requirements | Plan estimate |
|-------|------|-------------|---------------|
| 1 | Retroactive Nyquist Baseline | VALIDATE-01 | 2 |
| 2 | Verilator Parity + CI Expansion | VALIDATE-02, VALIDATE-03, VALIDATE-04 | 3 |
| 3 | V2001 Template Dedup + HARDEN-01 Root Fix | REFACTOR-01, REFACTOR-02, REFACTOR-03, HARDEN-01 | 4 |
| 4 | Phase 03 Remaining HIGH Fixes | HARDEN-02, HARDEN-03, HARDEN-04 | 3 |
| 5 | Phase 06 HIGH CLI Fixes | HARDEN-05, HARDEN-06, HARDEN-07, HARDEN-08 | 3 |
| 6 | MEDIUM/LOW Cleanup + Version Sync + Final Review | POLISH-01, POLISH-02, POLISH-03, POLISH-04 | 3 |
| 7 | Release — v1.1.0 Tag + Notes + Smoke | RELEASE-01, RELEASE-02, RELEASE-03 | 2 |

**Totals:** 7 phases · 22 requirements · ~20 plans (estimated; exact counts set at phase-plan time)

---

## Phase Details

---

### Phase 1 — Retroactive Nyquist Baseline

**Goal:** Generate Nyquist coverage `VALIDATION.md` reports retroactively for all 6 v1.0 phases. This is a read-only analysis pass — no production code is changed. Establishing documented coverage before any v1.1 edits land gives hardening phases a clear before/after reference and surfaces any operator edge-case gaps that should inform fix scope.

**Requirements:**
- **VALIDATE-01** — All 6 v1.0 phase directories under `.planning/milestones/v1.0-phases/` contain a `*-VALIDATION.md` Nyquist coverage report

**Success criteria:**
1. User reviewing `.planning/milestones/v1.0-phases/01-*/` through `06-*/` finds exactly one `*-VALIDATION.md` file in each of the six phase directories.
2. Each `VALIDATION.md` identifies: operators exercised, boundary/edge cases covered, explicit Nyquist gaps (documented even if gaps exist), and a pass/fail verdict.
3. Any gaps found during the sweep are captured as named findings in the Phase 1 completion summary, enabling downstream hardening phases to address them within scope.
4. All 736 existing regression tests pass unchanged at the end of this phase — no production code is touched.

---

### Phase 2 — Verilator Parity + CI Expansion

**Goal:** Install Verilator as a second simulation oracle alongside iverilog. Establish parity on the existing 65-test simulation suite, expand the CI matrix to a Verilator axis, and document the dual-oracle commitment. All hardening fixes in Phases 3–5 will then be automatically validated under both simulators without additional per-phase work.

**Requirements:**
- **VALIDATE-02** — Verilator produces the same 65 pass/fail outcomes as iverilog on the existing simulation oracle suite
- **VALIDATE-03** — CI matrix expands to `Ubuntu/macOS × Py 3.12/3.13 × {iverilog, Verilator}`; all 8 jobs green before merge
- **VALIDATE-04** — Dual-oracle commitment documented in README and enforced in CI

**Success criteria:**
1. User running `pytest -m simulation --simulator=verilator` sees the same 65 pass/fail outcomes as `pytest -m simulation --simulator=iverilog`.
2. CI matrix shows all 8 jobs (`2 OS × 2 Python × 2 simulators`) green on the main branch after this phase merges.
3. README install/usage section explicitly documents Verilator as a supported simulator alongside iverilog, including install instructions.
4. A property compiled and simulated after this phase is automatically verified under both simulators in CI without any extra user action.

---

### Phase 3 — V2001 Template Dedup + HARDEN-01 Root Fix

**Goal:** Extract the duplicated Verilog-2001 always-block bodies from all 11 templates into a shared Jinja2 macro, collapsing 22× duplication to 1. Apply the HARDEN-01 fix (`attempt_fired_q` not cleared by `disable_i`) once at the macro root so it covers both SV and V2001 output paths for all 11 templates automatically. Verify all 736 regression tests and golden parity are unbroken (byte-identical SV, behaviorally-equivalent V2001).

**Requirements:**
- **REFACTOR-01** — Every Jinja2 template's always-block body lives in exactly one macro; both SV and V2001 `verilog_mode` branches call it
- **REFACTOR-02** — HARDEN-01's fix is applied once at the macro root and verified to appear in both SV and V2001 emitted output
- **REFACTOR-03** — All 736 existing tests + golden parity pass after dedup (SV byte-identical; V2001 behaviorally equivalent)
- **HARDEN-01** — `attempt_fired_q` is correctly latched on every triggering attempt when `disable iff` is active; fix lives at macro root

**Success criteria:**
1. User running `grep -r "attempt_fired_q" src/sva2rtl/templates/` finds the fix in exactly one Jinja2 macro definition, not scattered across per-template branches.
2. User compiling a `disable iff` property with `--verilog` and simulating under `iverilog -g2001` observes `attempt_fired` going high on every triggered attempt, never cleared by the disable signal.
3. `git diff --stat` for this phase shows a net-negative line count in the `templates/` directory — duplication removed, not just moved.
4. All 736 regression tests pass with byte-identical SV golden output; V2001 output compiles clean under `iverilog -g2001` and passes simulation.
5. All 65 simulation oracle tests pass under both iverilog and Verilator (dual-oracle installed in Phase 2).

---

### Phase 4 — Phase 03 Remaining HIGH Fixes

**Goal:** Address the three Phase 03 carry-forward HIGH defects that do not depend on the template refactor: `_DECLARATIONS` global leaking between multi-assertion runs (HARDEN-02), `rep_consecutive` producing a silent miscompile on edge-case repetition bounds (HARDEN-03), and `_collect_signals` discarding user signal names in IR debug output (HARDEN-04).

**Requirements:**
- **HARDEN-02** — `_DECLARATIONS` global is reset between assertions; no cross-assertion declaration leak in multi-file or multi-property runs
- **HARDEN-03** — `rep_consecutive` with edge-case bounds (`[*0]`, `[*1]`, `[*0:0]`, etc.) produces either correct RTL or an explicit "unsupported bound" error — never a silent miscompile
- **HARDEN-04** — `_collect_signals` preserves the user-assigned `sig_name` in `--dump-ir` output

**Success criteria:**
1. User compiling a file containing two sequential assertions that share signal names gets correct, independent RTL output for each — no cross-contamination from the first assertion's declarations polluting the second.
2. User compiling `a [*0] |-> b`, `a [*1] |-> b`, and `a [*0:0] |-> b` gets either correct synthesizable monitors or an explicit exit-code-2 error with source location — no silent wrong output.
3. User running `sva2rtl --dump-ir foo.sv` on a property that references a signal named `my_ready` sees `my_ready` in the dump, not an auto-generated fallback name.
4. All 736 regression tests + 65 simulation oracle tests pass under both iverilog and Verilator after these fixes.

---

### Phase 5 — Phase 06 HIGH CLI Fixes

**Goal:** Fix the four Phase 06 carry-forward HIGH defects that affect CLI UX: `--dump-tree` silently dropping `unoptimized_checker` on multi-property files (HARDEN-05), `--property` failing silently on unlabeled assertions (HARDEN-06), `--output PATH` being ambiguous between file and directory modes (HARDEN-07), and `--verilog` being silently ignored when combined with `--dump-*` flags (HARDEN-08).

**Requirements:**
- **HARDEN-05** — `--dump-tree` on a multi-property file shows an `unoptimized_checker` block for every property, not just the first
- **HARDEN-06** — `--property` can match unlabeled assertions by source line number or anonymous index (does not silently fail)
- **HARDEN-07** — `--output PATH` is unambiguous: file path for single-property, directory path for multi-property; mismatched modes produce a clear error
- **HARDEN-08** — `--verilog` combined with `--dump-ast` / `--dump-ir` / `--dump-tree` either applies V2001 mode to the dump output or raises a visible "incompatible flags" error — no silent drop

**Success criteria:**
1. User running `sva2rtl --dump-tree multi.sv` on a file with N properties sees exactly N `unoptimized_checker:` blocks in the tree output.
2. User running `sva2rtl --property 3 multi.sv` (index) or `sva2rtl --property "@42" multi.sv` (source line) selects the correct unlabeled assertion; the tool does not silently compile a different property or produce no output.
3. User passing a bare file path to `--output` with a single-property input gets a file; with a multi-property input gets a clear error message instructing them to supply a directory. No ambiguous behavior.
4. User running `sva2rtl --verilog --dump-tree foo.sv` either sees a Verilog-2001-annotated dump or a visible `Error: --verilog and --dump-tree are incompatible` message — never silent `--verilog` suppression.
5. All 736 regression tests + 65 simulation oracle tests pass under both iverilog and Verilator after these CLI fixes.

---

### Phase 6 — MEDIUM/LOW Cleanup + Version Sync + Final Review

**Goal:** Synchronize `__init__.py` to `1.1.0` (POLISH-01); formally resolve all 10 Phase 06 MEDIUM and 9 Phase 06 LOW advisory findings as either closed or explicitly deferred with rationale logged in PROJECT.md (POLISH-02/03); perform a cross-phase code review of the complete v1.1 diff to confirm zero new HIGH-severity findings before the release tag is cut (POLISH-04).

**Requirements:**
- **POLISH-01** — `src/sva2rtl/__init__.py` `__version__` and `pyproject.toml` `version` both read `1.1.0`
- **POLISH-02** — All 10 Phase 06 MEDIUM advisory findings are closed (with commit SHA) or formally deferred (with reason in PROJECT.md "Out of Scope")
- **POLISH-03** — All 9 Phase 06 LOW advisory findings are closed or formally deferred; zero open HIGH or MEDIUM findings remain
- **POLISH-04** — A cross-phase code review of the v1.1 hardening diff produces zero new HIGH-severity findings

**Success criteria:**
1. User running `python -c "import sva2rtl; print(sva2rtl.__version__)"` and `pip show sva2rtl | grep Version` both print `1.1.0`.
2. A MEDIUM/LOW triage artifact (checklist or table) lists all 19 advisory findings with dispositions: `closed (SHA: …)` or `deferred (reason: …; PROJECT.md updated)`.
3. Zero open HIGH or MEDIUM findings remain in the v1.1 codebase at the end of this phase — confirmed by the triage artifact and the cross-phase review.
4. A code review artifact covering the full v1.1 diff (Phases 1–5 changes inclusive) explicitly states zero new HIGH-severity findings introduced during v1.1 hardening work.

---

### Phase 7 — Release: v1.1.0 Tag + Notes + Smoke

**Goal:** Cut the `v1.1.0` annotated tag, publish GitHub release notes summarizing all v1.1 changes in user-facing language, verify the artifact installs cleanly under both `pip install` and `uv pip install`, and confirm `pyproject.toml` version is `1.1.0` and README reflects the current feature set. This is the final phase of v1.1; no further production changes follow.

**Requirements:**
- **RELEASE-01** — Repository carries an annotated git tag `v1.1.0` on the final merged hardening commit
- **RELEASE-02** — GitHub release notes summarize: HARDEN-01..08 user impact, REFACTOR-01..03 (template dedup), VALIDATE-02..04 (Verilator parity), and POLISH-01 (version sync) — in user-facing language, not ticket IDs
- **RELEASE-03** — `pyproject.toml` version is `1.1.0`, README install/usage instructions are current, `pip install` and `uv pip install` smoke checks pass in a fresh virtual environment

**Success criteria:**
1. `git tag -v v1.1.0` succeeds and resolves to the final merged v1.1 commit on main.
2. GitHub Releases page for `sva2rtl` shows a `v1.1.0` entry whose notes cover (in user language): the `disable iff` latching fix, Verilog-2001 template dedup, Verilator as second oracle, CLI UX fixes (dump-tree, --property, --output, --verilog), and version sync.
3. `pip install sva2rtl==1.1.0` and `uv pip install sva2rtl==1.1.0` complete without errors in a fresh virtual environment on the CI-supported platforms.
4. After install, `sva2rtl --version` prints `1.1.0` and `sva2rtl --help` correctly reflects all v1.1 CLI flags.
5. Final CI run triggered by the `v1.1.0` tag shows all matrix jobs green: Ubuntu/macOS × Py 3.12/3.13 × {iverilog, Verilator}.

---

## Phase Rationale

### Phase 1 has only one requirement — is that intentional?

Yes. VALIDATE-01 covers six independent reports (one per v1.0 phase), each requiring structured operator-coverage analysis of a different phase's test suite. The single requirement maps to ~2 plans in execution and produces 6 VALIDATION.md artifacts. It was not bundled with Phase 2 because Nyquist analysis and Verilator infrastructure setup are orthogonal concerns — combining them would make Phase 2 harder to parallelise and harder to review.

### Why VALIDATE-01 (Nyquist sweep) lands first

The sweeps are read-only: no production code changes. Running them first before any v1.1 edits exist documents the baseline state of the v1.0 codebase. Any coverage gaps discovered flow into the scope definitions for Phases 3–5 as named findings. If the sweep ran after hardening, the baseline would be polluted by the fixes.

### Why VALIDATE-02/03/04 (Verilator) lands in Phase 2 — before hardening

Verilator infrastructure must exist before any hardening fix is validated, so every Phase 3–5 fix is automatically tested under both simulators. Installing Verilator after hardening would leave some fixes validated by only one oracle — a weaker guarantee than the dual-oracle contract the project commits to.

### Why REFACTOR-01..03 and HARDEN-01 are bundled in Phase 3

REFACTOR-02 explicitly states: "HARDEN-01's fix is applied once at the macro root." This means REFACTOR-01 (extract bodies into shared macros) is a hard prerequisite for HARDEN-01. The two are tightly coupled changes to the same template files; splitting them across phases would create a transient "macros extracted but HARDEN-01 not yet applied" state that breaks V2001 `disable iff` behavior between phases. Bundling them in Phase 3 with an internal plan ordering (REFACTOR-01 plan finishes before HARDEN-01 plan begins) satisfies the constraint cleanly.

### Why HARDEN-02..04 and HARDEN-05..08 are in separate phases

Phase 03 defects (HARDEN-02..04) live in compiler internals: global state management (`_DECLARATIONS`), IR signal collection (`_collect_signals`), and repetition FSM generation (`rep_consecutive`). Phase 06 defects (HARDEN-05..08) are entirely in the CLI layer: dump formatting, `--property` matching, `--output` routing, flag interaction. Separating them isolates blast radius — a data-path fix in Phase 4 cannot accidentally break CLI-path tests being developed in Phase 5, and vice versa.

### Why POLISH-04 (zero new HIGH review) is in Phase 6, not Phase 7

POLISH-04 is a gate condition: "the v1.1 hardening diff produces zero new HIGH findings." If any new HIGH issues are found, there must be a window to fix them before the release tag is cut. Placing POLISH-04 in Phase 6 (last pre-release phase) gives exactly that window — problems found in the review can be fixed within Phase 6 itself. Moving it to Phase 7 would require Phase 7 to potentially loop back and make production code changes, which defeats the purpose of a clean release phase.

---

## Requirement Coverage Matrix

| REQ-ID | Phase | Phase Name | Category |
|--------|-------|------------|----------|
| VALIDATE-01 | 1 | Retroactive Nyquist Baseline | Validate |
| VALIDATE-02 | 2 | Verilator Parity + CI Expansion | Validate |
| VALIDATE-03 | 2 | Verilator Parity + CI Expansion | Validate |
| VALIDATE-04 | 2 | Verilator Parity + CI Expansion | Validate |
| REFACTOR-01 | 3 | V2001 Template Dedup + HARDEN-01 Root Fix | Refactor |
| REFACTOR-02 | 3 | V2001 Template Dedup + HARDEN-01 Root Fix | Refactor |
| REFACTOR-03 | 3 | V2001 Template Dedup + HARDEN-01 Root Fix | Refactor |
| HARDEN-01 | 3 | V2001 Template Dedup + HARDEN-01 Root Fix | Harden |
| HARDEN-02 | 4 | Phase 03 Remaining HIGH Fixes | Harden |
| HARDEN-03 | 4 | Phase 03 Remaining HIGH Fixes | Harden |
| HARDEN-04 | 4 | Phase 03 Remaining HIGH Fixes | Harden |
| HARDEN-05 | 5 | Phase 06 HIGH CLI Fixes | Harden |
| HARDEN-06 | 5 | Phase 06 HIGH CLI Fixes | Harden |
| HARDEN-07 | 5 | Phase 06 HIGH CLI Fixes | Harden |
| HARDEN-08 | 5 | Phase 06 HIGH CLI Fixes | Harden |
| POLISH-01 | 6 | MEDIUM/LOW Cleanup + Version Sync + Final Review | Polish |
| POLISH-02 | 6 | MEDIUM/LOW Cleanup + Version Sync + Final Review | Polish |
| POLISH-03 | 6 | MEDIUM/LOW Cleanup + Version Sync + Final Review | Polish |
| POLISH-04 | 6 | MEDIUM/LOW Cleanup + Version Sync + Final Review | Polish |
| RELEASE-01 | 7 | Release — v1.1.0 Tag + Notes + Smoke | Release |
| RELEASE-02 | 7 | Release — v1.1.0 Tag + Notes + Smoke | Release |
| RELEASE-03 | 7 | Release — v1.1.0 Tag + Notes + Smoke | Release |

**Coverage verification:** 22/22 requirements mapped. Each requirement appears in exactly one phase. ✅

---

## Progress

| Phase | Name | Status | Plans |
|-------|------|--------|-------|
| 1 | Retroactive Nyquist Baseline | not started | — |
| 2 | Verilator Parity + CI Expansion | not started | — |
| 3 | V2001 Template Dedup + HARDEN-01 Root Fix | not started | — |
| 4 | Phase 03 Remaining HIGH Fixes | not started | — |
| 5 | Phase 06 HIGH CLI Fixes | not started | — |
| 6 | MEDIUM/LOW Cleanup + Version Sync + Final Review | not started | — |
| 7 | Release — v1.1.0 Tag + Notes + Smoke | not started | — |

---

*v1.0 archived: 2026-06-01 — see `.planning/MILESTONES.md` and `.planning/milestones/v1.0-*` for full historical detail.*

*ROADMAP.md updated: 2026-06-02 — v1.1 Hardening Release roadmap created (7 phases, 22 requirements).*
