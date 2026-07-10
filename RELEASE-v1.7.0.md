# sva2rtl v1.7.0 Release Notes

**Release date:** 2026-07-10
**Type:** Language surface closure — ##0 rewrite/reject + NFA rejection path elimination

v1.7.0 closes the last known behavioral gaps in the supported SVA subset: `##0`
fusion is now semantically correct via auto-rewrite, and all previously-rejected
NFA operand shapes (SeqOr, ranged delays, ranged repetition, goto/nonconsecutive
repetition) are now supported via the NFA composition engine.

## Summary

| Area | Change |
|------|--------|
| `##0` fusion | BoolExpr `a ##0 b` → auto-rewritten to `(a) && (b)`; non-BoolExpr `##0` → rejected |
| NFA SeqOr | Union construction via `_lift_to_nfa`; `(a or b) intersect c` now compiles |
| NFA ranged delays | `##[M:N]` non-deterministic delay expansion in NFA engine |
| NFA ranged repetition | `[*M:N]` multi-accept NFA states |
| NFA goto repetition | `[->N]` self-loop counting NFA |
| NFA nonconsecutive repetition | `[=N]` relaxed-tail NFA |
| Slang convention fix | Dual-convention delay parsing (old elem[i] + new v11 elem[i+1]) |
| Oracle fallback fix | `_tick_bool_expr_semantic` fallback corrected (default True → signal eval) |
| Differential tests | pre-existing failure fixed (slang convention + oracle fallback root causes) |

## ##0 Fusion Rewrite/Reject (LANG-01)

**Before:** `a ##0 b` emitted RTL with +1 cycle separation (known non-standard behavior)
with a compile-time warning.

**After:**
- `a ##0 b` where both operands are BoolExpr → auto-rewritten to `(a) && (b)` in the
  normalizer, producing a single merged `bool_expr` module
- `a ##0 <complex>` or `<complex> ##0 b` → `SvaCompileError` raised, suggesting
  `a && b` for boolean operands

**Implementation:** `src/sva2rtl/normalizer.py` — `_handle_fusion_delay` replaces
the deprecated `_warn_fusion_delay`.

## NFA Rejection Path Elimination (LANG-02..04)

### SeqOr Union Construction (LANG-02)

`_is_nfa_liftable` now accepts `SeqOr` with liftable children. Union NFA merges
left and right sub-NFAs with a shared start state and total state budget ≤ 32.

### Ranged Delays and Repetition (LANG-03)

`_is_nfa_liftable` now accepts `SeqConcat` with ranged delays and `SeqRepetition`
with ranged counts. The NFA expands delay windows via non-deterministic exit
transitions and repetition windows via multi-accept states.

### Goto and Nonconsecutive Repetition (LANG-04)

`_is_nfa_liftable` now accepts `SeqGotoRep` and `SeqNonconsecRep` with fixed
counts. NFAs use guard/neg-guard self-loop patterns for occurrence counting,
with nonconsecutive tail via always-true self-loops on the accept state.

## Bug Fixes

### Slang Delay Convention (P0)

slang v11+ stores inter-element delay on element i+1 (prefix convention), while
old slang and JSON fixtures store it on element i (suffix convention). The
importer (`_build_seq_concat`) now auto-detects the convention by checking
whether element[1] has non-zero min/max.

This fix resolved a long-standing differential test failure where `a ##1 b` was
parsed as `delays=((0,0),)` and incorrectly merged by the ##0 rewrite.

### Oracle Boolean Fallback

`_tick_bool_expr_semantic` defaulted `truth=True` when structured semantic
payload was absent. Fixed to fall back to observed-signal evaluation (AND of
all watched signals).

## Test Status

- Fast suite: 905 passed, 6 skipped, 0 failed
- Differential tests: 2 passed, 1 skipped (slow sweep)
- ruff: 0 errors repo-wide
- mypy --strict: 0 errors

## Known Limitations (carried forward)

- K-state budget (>32) is the only remaining NFA rejection path
- CDC/metastability proof permanently excluded
- Unbounded liveness not synthesizable
- Multi-thread local variables: demand-pulled future work

## Files Changed

- `src/sva2rtl/normalizer.py` — `_handle_fusion_delay` (##0 rewrite/reject)
- `src/sva2rtl/composer.py` — `_is_nfa_liftable`, `_lift_to_nfa`, `_try_lift_operand` (NFA expansion)
- `src/sva2rtl/ast_importer.py` — `_build_seq_concat` dual-convention fix
- `src/sva2rtl/behavioral_oracle.py` — oracle boolean fallback fix
- `tests/test_v15_g2a_reject.py` — rejection → acceptance tests
- `tests/test_composer.py`, `tests/test_sequential.py` — updated rejection tests
- `tests/test_v151_p2_implication_nfa.py` — acceptance tests
- `tests/test_emitter.py` — normalize integration, golden file updates
- `tests/golden/*.sv` — all regenerated
- `SUPPORT_MATRIX.md` — updated NFA operand rows
- `PROJECT_STATUS.md` — removed obsolete limitations
