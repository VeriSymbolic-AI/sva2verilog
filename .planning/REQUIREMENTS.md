---
milestone: v1.1
milestone_name: Hardening Release
version: 1.1
status: defined
last_updated: 2026-06-02
---

# Milestone v1.1 — Hardening Release Requirements

**Goal:** Close all carry-forward debt from v1.0, refactor Verilog-2001 template duplication at the root cause, add Verilator as a second simulation oracle, and ship `v1.1.0` as a publicly-tagged maintenance release.

**Validation strategy:** Co-sim only — every fix must pass both iverilog and Verilator on the existing 65-test simulation oracle plus the full 736-test regression suite. No new formal/equivalence-checking tooling.

---

## v1.1 Requirements

### Hardening — Phase 03 HIGH defect fixes (carry-forward)

- [ ] **HARDEN-01**: User can compile any SVA property using `disable iff` and have `attempt_fired` correctly latched on every triggering attempt — fix `attempt_fired_q` being cleared by `disable_i` (H-03), at the template-macro root, not per template instance
- [ ] **HARDEN-02**: User can compile multiple files in one run without one assertion's parser declarations leaking into the next — fix `_DECLARATIONS` global not reset between assertions (H-01)
- [ ] **HARDEN-03**: User receives an error or correct compile (never a silent miscompile) for `[*N]` repetition with edge-case bounds — fix `rep_consecutive` silent miss (H-02)
- [ ] **HARDEN-04**: User-named signals in IR debug dumps (`--dump-ir`) match the source — fix `_collect_signals` discarding `sig_name` (H-04)

### Hardening — Phase 06 HIGH defect fixes (carry-forward)

- [ ] **HARDEN-05**: User running `--dump-tree` on a multi-property file sees an `unoptimized_checker` block for every property, not just the first
- [ ] **HARDEN-06**: User can target an unlabeled assertion via `--property` (e.g. by source line or anonymous index) instead of the flag silently failing
- [ ] **HARDEN-07**: User invoking `--output PATH` gets unambiguous behavior — `PATH` is interpreted as a file when single-property, directory when multi-property; mismatched modes produce a clear error
- [ ] **HARDEN-08**: User combining `--verilog` with `--dump-ast` / `--dump-ir` / `--dump-tree` either applies the V2001 mode to dumps or receives an explicit "incompatible flags" error — no silent ignoring

### Refactor — Verilog-2001 template deduplication

- [ ] **REFACTOR-01**: Every Jinja2 template's always-block body lives in exactly one place, called from both SV and V2001 `verilog_mode` branches via macro extraction (22× duplication → 1)
- [ ] **REFACTOR-02**: HARDEN-01's fix is applied once at the macro root and verified to land in both SV and V2001 output (no per-instance re-application needed)
- [ ] **REFACTOR-03**: All 736 existing tests + golden parity continue to pass byte-identical SV output and behaviorally-equivalent V2001 output after dedup

### Validate — Retroactive Nyquist sweeps + Verilator parity

- [ ] **VALIDATE-01**: User reviewing `.planning/milestones/v1.0-phases/0N-*/` finds a `*-VALIDATION.md` Nyquist coverage report for every v1.0 phase (Phases 1–6) — generated retroactively at the start of v1.1
- [ ] **VALIDATE-02**: User running the simulation oracle suite under Verilator gets the same 65 pass/fail outcomes as iverilog (parity established on existing tests)
- [ ] **VALIDATE-03**: CI matrix expands to include a Verilator axis — Ubuntu/macOS × Py 3.12/3.13 × {iverilog, Verilator} — and all jobs are green before merge
- [ ] **VALIDATE-04**: User compiling any SVA property and simulating the result has confidence the monitor passes both iverilog and Verilator (documented in README and verified in CI)

### Polish — MEDIUM / LOW advisory cleanup + version sync

- [ ] **POLISH-01**: User running `python -c "import sva2rtl; print(sva2rtl.__version__)"` sees the same version string as `pip show sva2rtl` (i.e. `__init__.py` and `pyproject.toml` agree)
- [ ] **POLISH-02**: All 10 Phase 06 MEDIUM advisory findings are either closed (with code change) or formally deferred (with reason logged in PROJECT.md "Out of Scope")
- [ ] **POLISH-03**: All 9 Phase 06 LOW advisory findings are either closed or formally deferred — review board reaches zero open HIGH/MEDIUM
- [ ] **POLISH-04**: Cross-phase code review of the v1.1 hardening diff produces zero new HIGH-severity findings

### Release — Public v1.1.0 tag

- [ ] **RELEASE-01**: Repository carries an annotated git tag `v1.1.0` pointing at the merged hardening release
- [ ] **RELEASE-02**: GitHub release notes summarize: hardening fixes (HARDEN-01..08), V2001 dedup (REFACTOR-01..03), Verilator parity (VALIDATE-02..04), and version sync (POLISH-01) — in user-facing language
- [ ] **RELEASE-03**: Final `pyproject.toml` version is `1.1.0`, README install/usage instructions are current, and the published artifact installs cleanly under `pip install` and `uv pip install` smoke checks

---

## Future Requirements (deferred to v1.2+)

Tier 2 SVA operators — pushed from v1.1 to keep this release narrowly scoped:

- Goto repetition `[->N]` and non-consecutive repetition `[=N]`
- `$changed`
- `throughout`, `within`, `intersect`, `first_match`
- Sequence `and` / `or` composition
- Implementation choice: NFA-based composition vs token-passing extension — re-evaluate at v1.2 plan time

Other deferred items:

- Formal equivalence checking via yosys/sby/symbiyosys (between `--no-optimize` and optimized output)
- C++ rewrite for v2 performance (still on the table; not for v1.x)
- Local variables in sequences (data-path synthesis required) — reserved for v2
- Multi-clock assertions — reserved for v2

---

## Out of Scope (v1.1)

Explicit exclusions, with reasoning:

- **No new SVA operators.** v1.1 is hardening-only. Any user discovering Tier 2 gaps gets a clear "unsupported operator" error with source location (existing exit code 2 path).
- **No new IR features.** The frozen-dataclass IR is frozen for v1.1 — no new node kinds, no schema changes. All fixes operate within the existing IR.
- **No formal/equivalence-checking tooling.** Co-sim with iverilog + Verilator is the validation contract for v1.1. yosys/sby integration deferred.
- **No GUI or IDE integration.** CLI-first remains the v1 architectural commitment.
- **No FPGA toolchain integration.** Downstream user concern; not in sva2rtl's scope.
- **No performance optimization beyond current optimizer.** v1.1 must not regress optimizer output; no new optimization passes.
- **No breaking CLI changes.** `--output` semantics are clarified (HARDEN-07), not redesigned. Every v1.0 invocation must still work.

---

## Traceability

| REQ-ID | Phase | Plan | Status |
|--------|-------|------|--------|
| VALIDATE-01 | 1 | TBD | not started |
| VALIDATE-02 | 2 | TBD | not started |
| VALIDATE-03 | 2 | TBD | not started |
| VALIDATE-04 | 2 | TBD | not started |
| REFACTOR-01 | 3 | TBD | not started |
| REFACTOR-02 | 3 | TBD | not started |
| REFACTOR-03 | 3 | TBD | not started |
| HARDEN-01 | 3 | TBD | not started |
| HARDEN-02 | 4 | TBD | not started |
| HARDEN-03 | 4 | TBD | not started |
| HARDEN-04 | 4 | TBD | not started |
| HARDEN-05 | 5 | TBD | not started |
| HARDEN-06 | 5 | TBD | not started |
| HARDEN-07 | 5 | TBD | not started |
| HARDEN-08 | 5 | TBD | not started |
| POLISH-01 | 6 | TBD | not started |
| POLISH-02 | 6 | TBD | not started |
| POLISH-03 | 6 | TBD | not started |
| POLISH-04 | 6 | TBD | not started |
| RELEASE-01 | 7 | TBD | not started |
| RELEASE-02 | 7 | TBD | not started |
| RELEASE-03 | 7 | TBD | not started |

**Total:** 22 v1.1 requirements across 5 categories. Coverage: 22/22 mapped to phases 1–7. ✅

---

*REQUIREMENTS.md created: 2026-06-02 — milestone v1.1 Hardening Release.*
*Traceability table populated: 2026-06-02 — roadmap created (7 phases, reset numbering from Phase 1).*
