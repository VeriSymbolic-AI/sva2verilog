# sva2rtl v1.3.1 Release Notes

**Release date:** 2026-06-28
**Type:** Maintenance / hardening release (debt cleanup + verification honesty)

v1.3.1 is a focused maintenance release on top of v1.3.0. It contains no new
SVA operators. Its purpose is to pay down identified technical debt, fix a
conservative sizing issue, harden the behavioral oracle's disable handling, and
— most importantly — establish an **independent verification baseline** for the
composed operators `intersect` / `within` / `throughout` that honestly records a
known semantic boundary instead of hiding it.

## Summary

| Area | Change |
|------|--------|
| Version | Synced `pyproject.toml` and `__init__.py` to `1.3.1` (was out of sync at 1.2.0) |
| RISK-01 | Added independent, hand-derived golden-vector baseline tests for intersect/within/throughout |
| RISK-03 | Explicit `disable` handling added to intersect/within/throughout behavioral oracle ticks |
| RISK-04 | `_compute_bv_width` for goto/non-consecutive repetition now sizes from `rep_max` (was hardcoded 8) with overflow-flag safety note |
| Cleanup | Removed 26 temporary debug scripts from `tools/`; planning/dev-tooling dirs excluded from publication |
| Tests | 794 pass, 5 skipped, 5 xfailed (2 new xfails honestly record the RISK-02 oracle boundary) |

## Details

### RISK-01 — Independent verification baseline (the headline change)

Background: the behavioral oracle models `intersect` / `within` / `throughout`
with the same boolean composition the RTL templates use (e.g. intersect =
`left_pass & right_pass`). Because the two are structurally isomorphic, an
oracle-vs-RTL cross-check is not an independent test for these operators — both
could "agree while both being wrong."

This release adds `tests/test_v13_independent_baseline.py`: a set of golden
reference vectors whose expected per-cycle outputs are hand-derived directly
from IEEE 1800 semantics (by human reasoning, not by running the implementation),
covering the single-completion-time sub-sequence case that v1.3 claims to
support.

Running these vectors immediately surfaced a concrete, previously-masked gap:
because the boolean-expression oracle is modelled as "always pass / always
active" (RISK-02), `intersect` and `within` ignore their boolean operands
entirely (e.g. `a intersect b` emits pass on every start cycle regardless of `a`
and `b`). These two cases are now marked `xfail(strict=True)` to record the
boundary honestly. The correct fix is the unified "timing + data value" oracle
planned for the v1.5 NFA composition engine rewrite; it is intentionally NOT
attempted here (changing the oracle core is high-risk). `throughout` already
evaluates its real boolean condition (via the v1.3.0 `_eval_cond_expr` patch)
and therefore passes the baseline.

### RISK-03 — Explicit disable handling for composed operators

`intersect` / `within` / `throughout` oracle tick functions now return all-zero
on `disable` and still tick both children to keep their state reset, matching
`prop_and`'s behavior and making the composed-operator disable semantics
unambiguous.

### RISK-04 — Bit-vector width for occurrence-based repetition

`SeqGotoRep` / `SeqNonconsecRep` previously returned a hardcoded width of 8 from
`_compute_bv_width`. Occurrence-based repetition has an unbounded cycle window,
so an exact static width is not computable; the width is now sized to a
conservative lower bound `max(rep_max + 1, 8)`. Any runtime overrun continues to
be caught explicitly by the generated `overflow_flag` (never silently
truncated), preserving the "never fail silently" contract.

### Cleanup and publication hygiene

Removed 26 temporary debug scripts from `tools/` (dbg*, chk*, debug_sim*,
fix_*, test_x_fix*, tdebug, check_*, wire_simulator). Retained `tools/audit/`
(documented validation tooling) and the golden-regeneration scripts.
Development-process directories (`.planning/`, `.claude/`,
`.understand-anything/`) and process artifacts (`research_report_*.md`) are
excluded from the published repository via `.gitignore`.

## Known limitations carried forward

- `intersect` / `within` with boolean operands: oracle does not evaluate operand
  values (RISK-02) — recorded as strict xfail; fixed by v1.5.
- Nested multi-path operators: single-level only; deferred to v1.5 NFA engine.
- Multi-clock properties: planned for v1.4 (see
  `SUPPORTED_CONSTRUCTS.md` multi-clock section).
- Tier 3 temporal operators (`nexttime`/`always`/`eventually`/`until`): planned
  for v1.4 (bounded forms only).

## Test status

794 passed, 5 skipped (verilator not installed), 5 xfailed, in the non-simulation
suite. No new lint or type errors introduced by this release's changes.
