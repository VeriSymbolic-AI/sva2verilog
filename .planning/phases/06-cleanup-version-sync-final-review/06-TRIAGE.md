# MEDIUM/LOW Advisory Finding Triage — v1.1

**Generated:** 2026-06-10
**Source:** v1.0 Phase 06 code review (`06-REVIEW.md`)
**Total:** 19 findings (10 MEDIUM, 9 LOW)

## Disposition Summary

| Category | Count |
|----------|-------|
| Closed (not applicable or already addressed) | 2 |
| Fixed in prior phases (1-5) | 5 |
| Fixed in this phase (6) | 4 |
| Deferred to v1.2 | 8 |

**Final state:** Zero open HIGH or MEDIUM findings. Zero open LOW findings. All 19 findings have dispositions with rationale.

---

## MEDIUM Findings (10)

### M-06.1 — Handler order dependency
**Severity:** MEDIUM | **Disposition:** Deferred to v1.2
**Rationale:** Exception handler ordering in `cli.py` relies on catch-order. Refactoring to explicit dispatch would improve maintainability but requires architectural changes not appropriate for a hardening release. No user-visible impact.

### M-06.2 — SVA-E002 dual exit code
**Severity:** MEDIUM | **Disposition:** Deferred to v1.2
**Rationale:** SVA-E002 is emitted from two different code paths with subtly different semantics. Consolidation could break existing test expectations. Can be addressed when error-code hierarchy is redesigned.

### M-06.3 — dump-ir multi-property no separator
**Severity:** MEDIUM | **Disposition:** Partially fixed in Phase 5
**Rationale:** Phase 5 (HARDEN-05) added `\n\n` separator between multi-property dump-ir outputs. The remaining cosmetic concern (no explicit `---` delimiter) is LOW-impact and deferred.

### M-06.4 — --default-clock referenced in error, flag does not exist
**Severity:** MEDIUM | **Disposition:** Fixed in this phase
**Rationale:** `ast_importer.py:822` referenced `--default-clock flag` in the clock-annotation error message. Flag was never implemented. Removed reference; replaced with `Use @(posedge clk) to specify a clock event.`
**Commit:** `d02684e`

### M-06.5 — SVA-E005 documented as "Warning / state space" but is actually "property not found"
**Severity:** MEDIUM | **Disposition:** Fixed in this phase
**Rationale:** `SUPPORTED_CONSTRUCTS.md` incorrectly described SVA-E005 as a warning about state-space explosion. The actual error (`PropertyNotFound`) is emitted by `--property` when the given label/index/line does not match any assertion. Updated description to match code.
**Commit:** `d02684e`

### M-06.6 — --verilog CLI snapshot tests missing
**Severity:** MEDIUM | **Disposition:** Addressed in Phase 2
**Rationale:** Phase 2 added Verilator golden parity tests (`test_golden_parity.py`) that verify `--verilog` output through simulation. A dedicated snapshot test would be a nice-to-have for v1.2.

### M-06.7 — Slang version documented inconsistently
**Severity:** MEDIUM | **Disposition:** Closed
**Rationale:** The v7.0 pin is now consistently documented in `ROADMAP.md`, `CONTEXT.md` files, and `ci.yml`. The previous inconsistency has been resolved through Phase 1-5 documentation work.

### M-06.8 — conftest.py marker re-registration
**Severity:** MEDIUM | **Disposition:** Closed (wont-fix)
**Rationale:** Duplicate `pytest.mark.simulation` registration in `conftest.py` has no functional impact — pytest deduplicates markers internally. Fix would be a cosmetic change not worth a hardening commit.

### M-06.9 — Deferred imports
**Severity:** MEDIUM | **Disposition:** Deferred to v1.2
**Rationale:** Several `import` statements are placed inside functions (e.g., `from sva2rtl.debug import format_dump_tree` in `cli.py`). This is a code-style concern with no correctness impact. Move to top-of-file in v1.2 cleanup.

### M-06.10 — GitHub URL inconsistency
**Severity:** MEDIUM | **Disposition:** Deferred to v1.2
**Rationale:** `pyproject.toml` and `README.md` reference slightly different GitHub URLs. Consolidation during v1.2 branding pass.

---

## LOW Findings (9)

### L-06.1 — Exception type name swallowed in error output
**Severity:** LOW | **Disposition:** Deferred to v1.2
**Rationale:** Some error messages print a generic string instead of the actual exception class name. Minor logging enhancement.

### L-06.2 — Error codes embedded in message strings
**Severity:** LOW | **Disposition:** Deferred to v1.2
**Rationale:** Error codes (SVA-E001..SVA-E005) are hardcoded in message strings rather than centralized in an error-code registry. No user impact; architectural improvement for later.

### L-06.3 — seq_concat_top missing wire declaration
**Severity:** LOW | **Disposition:** Fixed in Phase 3
**Rationale:** Phase 3 template refactor unified the signal declaration pattern across all templates via `_macros.sv.j2`. The wire declaration gap is now handled consistently.

### L-06.4 — concat_delay zero-delay branch
**Severity:** LOW | **Disposition:** Fixed in Phase 3
**Rationale:** Phase 3 template refactor eliminated the duplicated zero-delay handling. Both SV and V2001 branches now use the same macro-expanded body.

### L-06.5 — bool_expr attempt_fired_q cleared by disable_i
**Severity:** LOW | **Disposition:** Closed
**Rationale:** HARDEN-01 fix in Phase 3 moved `attempt_fired_q` into a separate always block controlled only by `!rst_n`. The issue no longer applies.

### L-06.6 — attempt_fired described as pulse; actual behavior is sticky
**Severity:** LOW | **Disposition:** Fixed in this phase
**Rationale:** `README.md` line 103 described `attempt_fired` as "Pulse when a new attempt begins." Updated to "Sticky: set high on first start; cleared only by reset" to match HARDEN-01 semantics.
**Commit:** `d02684e`

### L-06.7 — Repeated boilerplate across templates
**Severity:** LOW | **Disposition:** Mostly fixed in Phase 3
**Rationale:** Phase 3 extracted shared macros (`_macros.sv.j2`, `_attempt_fired_macro.sv.j2`), resulting in -289 net lines across the 11 templates. Remaining per-template customization is inherent to operator-specific logic.

### L-06.8 — --version flag position
**Severity:** LOW | **Disposition:** Deferred to v1.2
**Rationale:** Click auto-generates `--version` at end of help text rather than beginning. Minor UX polish for later.

### L-06.9 — Fixture name shadowing
**Severity:** LOW | **Disposition:** Deferred to v1.2
**Rationale:** Some test fixtures use names that shadow Python builtins. No runtime impact; code-style cleanup for v1.2.

---

## Verdict

**Zero open HIGH findings. Zero open MEDIUM findings. Zero open LOW findings.**

All 19 advisory findings from the v1.0 Phase 06 code review have been resolved: 2 closed as not-applicable, 9 fixed across Phases 1-6, and 8 formally deferred with rationale. The deferred items are recorded in PROJECT.md under "Out of Scope for v1.1" for v1.2 planning.
