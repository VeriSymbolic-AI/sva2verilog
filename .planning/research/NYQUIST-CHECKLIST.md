# NYQUIST-CHECKLIST — Per-Operator Boundary Coverage

**Purpose:** Static per-operator boundary checklist for the v1.1 Retroactive Nyquist Baseline audit.
**Consumed by:** Plan 02 audit tasks (one per v1.0 phase), which fill the Evidence column and derive BLOCKING/ADVISORY verdicts.
**Source of truth:** PITFALLS.md (mandatory floor) + D-04 static additions from 01-CONTEXT.md.

---

## Top-Level Rules

1. **Every PITFALLS.md row is a mandatory row** in the operator(s) it applies to. A pitfall row with no evidence citation IS a gap row — there is no "covered by analogy" exemption.
2. **Every static row that is uncovered in v1.0 is a candidate gap** — BLOCKING if a silent miscompile is possible; ADVISORY otherwise (D-03).
3. **Plan 02 audit tasks fill the Evidence column.** A blank Evidence cell = gap row. Plan 02 must cite a specific `tests/test_<file>.py::test_<function>` symbol per D-05.
4. **Tier 2 pitfalls P1.4 and P1.5 are out of v1.0 scope.** They appear in this file with the explicit annotation `Tier 2 — out of v1.0 scope, deferred` so their absence from Plan 02 grep coverage is auditable and intentional.
5. **Row IDs:** Pitfall-derived rows use `PITFALLS:Pn.x`; static rows use `STATIC:Sn.x` (sequential within each operator section).

---

## Operator-to-Phase Mapping

| Operator | Template File | v1.0 Phase | Plan 02 Audit Task |
|----------|--------------|-----------|-------------------|
| Boolean expr | `bool_expr.sv.j2` | Phase 01 | 2.1.1 |
| `##N` (fixed delay) | `concat_delay.sv.j2` | Phase 02 | 2.2.1 |
| `##[M:N]` (range delay) | `concat_delay.sv.j2` | Phase 02 | 2.2.1 |
| `\|->` (overlapping impl.) | `overlap_bitvec.sv.j2` | Phase 02/03 | 2.2.1 / 2.3.1 |
| `\|=>` (non-overlapping impl.) | `nonoverlap.sv.j2` | Phase 02/03 | 2.2.1 / 2.3.1 |
| `[*N]` / `[*M:N]` (consec. rep.) | `rep_consecutive.sv.j2` | Phase 03 | 2.3.1 |
| `$rose` / `$fell` / `$stable` | `rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2` | Phase 03 | 2.3.1 |
| `$past(sig, n)` | `past.sv.j2` | Phase 03 | 2.3.1 |
| `disable iff` | `disable_iff_top.sv.j2` | Phase 03 | 2.3.1 |
| Named sequences / properties | `seq_concat_top.sv.j2` | Phase 03 | 2.3.1 |

---

## 1. Boolean Expressions (`bool_expr`)

**Phase 01.** Template: `bool_expr.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Vacuous satisfaction — antecedent never fires, monitor reports pass | `PITFALLS:P1.1` | — | BLOCKING |
| Power-on reset: `rst_n` asserted at cycle 0, outputs deassert cleanly | `PITFALLS:P2.4` | — | BLOCKING |
| `attempt_fired` output goes high exactly on the first valid antecedent match | `PITFALLS:P3.5` | — | BLOCKING |
| Error message cites source SVA location (not generated RTL line) | `PITFALLS:P5.1` | — | BLOCKING |
| Slang AST `BooleanExpression` kind is visited; no unknown-kind fall-through | `PITFALLS:P8.1` | — | BLOCKING |
| Implicit clocking: no silent default-clock assumption | `PITFALLS:P8.4` | — | BLOCKING |
| Strong vs. weak: `strong()` must emit compile error, not silent liveness weakening | `PITFALLS:P1.8` | — | BLOCKING |
| Constant-true property: `1 |-> 1` — passes always, attempt_fired always high | `STATIC:S1.1` | — | ADVISORY |
| Constant-false property: `0 |-> 1` — vacuous, attempt_fired stays low | `STATIC:S1.2` | — | BLOCKING |
| Multi-bit boolean signal as condition (not just 1-bit) | `STATIC:S1.3` | — | ADVISORY |
| Named signal with `$rose`/`$fell` not in this phase (would be an IR error) | `STATIC:S1.4` | — | ADVISORY |

---

## 2. Fixed Delay (`##N`)

**Phase 02.** Template: `concat_delay.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Combinational loop via shift-register feedback | `PITFALLS:P2.1` | — | BLOCKING |
| Counter bit-width: `##0` — zero-cycle delay (degenerate identity case) | `PITFALLS:P2.3` | — | BLOCKING |
| Power-on reset: shift-register clears to all-zero at rst_n | `PITFALLS:P2.4` | — | BLOCKING |
| Boundary test: `##(N-1)` fails, `##N` passes, `##(N+1)` fails | `PITFALLS:P3.4` | — | BLOCKING |
| `attempt_fired` asserted in test | `PITFALLS:P3.5` | — | BLOCKING |
| NFA→DFA not used for `##N` (token-passing preserves NFA) | `PITFALLS:P4.1` | — | ADVISORY |
| `##0` — zero delay, input directly wired to output | `STATIC:S2.1` | — | BLOCKING |
| `##1` — single-cycle delay (canonical case) | `STATIC:S2.2` | — | BLOCKING |
| `##N` large (e.g. `##100`) — shift-register width sufficient | `STATIC:S2.3` | — | BLOCKING |
| `##N` where N exceeds counter bit-width allocation | `STATIC:S2.4` | — | BLOCKING |
| Multi-thread: antecedent fires every cycle for 2×N cycles | `PITFALLS:P3.1` | — | BLOCKING |

---

## 3. Range Delay (`##[M:N]`)

**Phase 02.** Template: `concat_delay.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Combinational loop via counter feedback | `PITFALLS:P2.1` | — | BLOCKING |
| Counter bit-width overflow for `##[0:100]` — needs ceil(log2(101))+1 bits | `PITFALLS:P2.3` | — | BLOCKING |
| Power-on reset: counter clears correctly | `PITFALLS:P2.4` | — | BLOCKING |
| Boundary test: M-1 (fail), M (pass), N (pass), N+1 (fail) | `PITFALLS:P3.4` | — | BLOCKING |
| `attempt_fired` asserted in test | `PITFALLS:P3.5` | — | BLOCKING |
| `##[0:0]` — degenerates to `##0` (identity) | `STATIC:S3.1` | — | BLOCKING |
| `##[M:M]` — degenerates to `##M` (fixed delay) | `STATIC:S3.2` | — | BLOCKING |
| `##[M:N]` with M>N — must be a hard compile-time error or IR-level normalization | `STATIC:S3.3` | — | BLOCKING |
| `##[0:N]` — lower bound zero, window starts immediately | `STATIC:S3.4` | — | BLOCKING |
| `##[N:N+1]` — minimal 2-value window | `STATIC:S3.5` | — | BLOCKING |
| Multi-thread: antecedent fires every cycle for 2×N cycles | `PITFALLS:P3.1` | — | BLOCKING |
| Counter encoding (not state expansion): `##[0:100]` should use 7-bit counter | `STATIC:S3.6` | — | BLOCKING |

---

## 4. Overlapping Implication (`|->`)

**Phase 02/03.** Template: `overlap_bitvec.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Vacuous satisfaction — antecedent never fires | `PITFALLS:P1.1` | — | BLOCKING |
| Same-cycle start: consequent starts cycle 0 (not cycle 1) | `PITFALLS:P1.2` | — | BLOCKING |
| Bit-vector overflow: antecedent fires every cycle for > bit-vector width | `PITFALLS:P1.3` | — | BLOCKING |
| Combinational loop via bit-vector feedback | `PITFALLS:P2.1` | — | BLOCKING |
| Power-on reset: bit-vector register clears | `PITFALLS:P2.4` | — | BLOCKING |
| Multi-thread concurrent-attempt stress test | `PITFALLS:P3.1` | — | BLOCKING |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | — | BLOCKING |
| NFA→DFA not applied to bit-vector method | `PITFALLS:P4.1` | — | ADVISORY |
| `|->` with trivially-true consequent — passes always, attempt_fired latches | `STATIC:S4.1` | — | ADVISORY |
| `|->` with `##N` consequent — same-cycle vs next-cycle offset | `STATIC:S4.2` | — | BLOCKING |
| Multi-thread bit-vector overflow: overflow_flag sticky output | `STATIC:S4.3` | — | BLOCKING |

---

## 5. Non-Overlapping Implication (`|=>`)

**Phase 02/03.** Template: `nonoverlap.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Vacuous satisfaction — antecedent never fires | `PITFALLS:P1.1` | — | BLOCKING |
| Next-cycle start: consequent starts cycle 1 not cycle 0 (off-by-one) | `PITFALLS:P1.2` | — | BLOCKING |
| Multi-thread concurrent-attempt stress test | `PITFALLS:P3.1` | — | BLOCKING |
| Boundary test: distinguish `|->` vs `|=>` by asserting differing result on same stimulus | `PITFALLS:P3.4` | — | BLOCKING |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | — | BLOCKING |
| Power-on reset: internal delay FF clears | `PITFALLS:P2.4` | — | BLOCKING |
| `|=>` with `##0` consequent body — next cycle then zero delay | `STATIC:S5.1` | — | BLOCKING |
| `|=>` with `##N` consequent — one-cycle head offset plus N additional | `STATIC:S5.2` | — | BLOCKING |

---

## 6. Consecutive Repetition (`[*N]` / `[*M:N]`)

**Phase 03.** Template: `rep_consecutive.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Combinational loop via FSM state feedback | `PITFALLS:P2.1` | — | BLOCKING |
| Counter bit-width overflow at `2^width` | `PITFALLS:P2.3` | — | BLOCKING |
| Power-on reset: FSM counter clears | `PITFALLS:P2.4` | — | BLOCKING |
| Boundary test: N-1 (fail), N (pass), N+1 (fail for exact) | `PITFALLS:P3.4` | — | BLOCKING |
| Single-thread testing only — must add multi-thread | `PITFALLS:P3.1` | — | BLOCKING |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | — | BLOCKING |
| Unbounded repetition `[*]` must be compile error | `PITFALLS:P4.2` | — | BLOCKING |
| `[*0]` — zero repetitions (match vacuously, immediately) | `STATIC:S6.1` | — | BLOCKING |
| `[*0:0]` — degenerates to zero-rep case | `STATIC:S6.2` | — | BLOCKING |
| `[*1]` — single repetition (canonical case) | `STATIC:S6.3` | — | BLOCKING |
| `[*N]` large N — counter width sufficient | `STATIC:S6.4` | — | BLOCKING |
| `[*M:N]` with M>N — must be hard error or IR normalization | `STATIC:S6.5` | — | BLOCKING |
| Counter overflow at `2^width` — overflow_flag sticky output | `STATIC:S6.6` | — | BLOCKING |
| Token duplication on parallel branches within repetition | `PITFALLS:P8.2` | — | BLOCKING |

---

## 7. `$rose` / `$fell` / `$stable`

**Phase 03.** Templates: `rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Power-on first-cycle: all edge-detect FFs in reset state | `PITFALLS:P2.4` | — | BLOCKING |
| `$rose` at cycle 0 (first posedge after reset) — should not false-fire | `STATIC:S7.1` | — | BLOCKING |
| `$fell` at cycle 0 (first posedge after reset) — should not false-fire | `STATIC:S7.2` | — | BLOCKING |
| `$stable` at cycle 0 (first posedge after reset) — behavior documented | `STATIC:S7.3` | — | ADVISORY |
| X-propagation at reset: input signal X in cycle 0 | `STATIC:S7.4` | — | ADVISORY |
| `$rose` on multi-bit signal — only bit 0 matters? Or any bit? Documented | `STATIC:S7.5` | — | BLOCKING |
| Vacuity tested (attempt_fired asserted in property context) | `PITFALLS:P3.5` | — | BLOCKING |
| Error cites SVA source location (not generated RTL) | `PITFALLS:P5.1` | — | BLOCKING |

---

## 8. `$past(sig, n)`

**Phase 03.** Template: `past.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Power-on reset: shift-register contents all-zero | `PITFALLS:P2.4` | — | BLOCKING |
| `$past(sig, 0)` — degenerate identity (returns current value) | `STATIC:S8.1` | — | BLOCKING |
| `$past(sig, 1)` — one-cycle delay (canonical case) | `STATIC:S8.2` | — | BLOCKING |
| `$past(sig, n)` with n >> pipeline depth — silent shift-register exhaustion | `STATIC:S8.3` | — | BLOCKING |
| `$past(sig, n)` with n=0 vs n=1 behavioral difference verified | `STATIC:S8.4` | — | BLOCKING |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | — | BLOCKING |
| Error cites SVA source location | `PITFALLS:P5.1` | — | BLOCKING |

---

## 9. `disable iff`

**Phase 03.** Template: `disable_iff_top.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| `disable iff` is asynchronous — must gate combinationally, not synchronous | `PITFALLS:P1.6` | — | BLOCKING |
| One-cycle spurious disable window (synchronous vs async clear race) | `STATIC:S9.1` | — | BLOCKING |
| `disable iff` interaction with `attempt_fired` latching — HARDEN-01 root cause | `STATIC:S9.2` | — | BLOCKING |
| `attempt_fired_q` cleared by `disable_i` incorrectly (H-03 defect) | `STATIC:S9.3` | — | BLOCKING |
| Power-on reset with disable active simultaneously | `PITFALLS:P2.4` | — | BLOCKING |
| Disable fires mid-sequence: pending threads cancelled cleanly | `STATIC:S9.4` | — | BLOCKING |
| Disable inactive whole sequence: normal pass/fail | `STATIC:S9.5` | — | BLOCKING |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | — | BLOCKING |

---

## 10. Named Sequences / Properties

**Phase 03.** Template: `seq_concat_top.sv.j2`.

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Severity if Uncovered |
|----------|--------|--------------------------------------|-----------------------|
| Token duplication at `or` branch within named sequence | `PITFALLS:P8.2` | — | BLOCKING |
| Slang AST named-sequence node kind correctly dispatched | `PITFALLS:P8.1` | — | BLOCKING |
| Argument substitution: named sequence with formal parameter | `STATIC:S10.1` | — | BLOCKING |
| Recursive instantiation: compiler must reject with error | `STATIC:S10.2` | — | BLOCKING |
| Hierarchical scope: named sequence defined in separate `sequence` block | `STATIC:S10.3` | — | ADVISORY |
| Named sequence inlined at call site (not emitted as separate module) | `STATIC:S10.4` | — | ADVISORY |
| Error cites SVA source location for unsupported construct in named seq | `PITFALLS:P5.1` | — | BLOCKING |
| Vacuity tested (attempt_fired asserted in outer property context) | `PITFALLS:P3.5` | — | BLOCKING |

---

## Tier 2 Pitfall Annotations (Out of v1.0 Scope)

The following pitfalls apply to Tier 2 operators (`throughout`, `intersect`) which are explicitly out of v1.0 scope per FEATURES.md §2.1. They appear here so their absence from Plan 02 per-phase grep coverage is auditable and intentional.

| Pitfall ID | Pitfall Title | Annotation |
|------------|--------------|------------|
| P1.4 | `throughout` every-tick semantics | Tier 2 — out of v1.0 scope, deferred |
| P1.5 | `intersect` same-start-AND-end | Tier 2 — out of v1.0 scope, deferred |

---

*Last updated: 2026-06-03*
*Source: PITFALLS.md + 01-CONTEXT.md D-04 static boundary enumeration*
