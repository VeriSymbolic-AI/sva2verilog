---
phase: 03-remaining-tier-1-operators-named-sequences-simulation-valida
phase_number: 03
phase_name: remaining-tier-1-operators-named-sequences-simulation-validation
verifier: plan-02-audit (autonomous)
verified: 2026-06-04
status: failed
requirement_ids:
  - VALIDATE-01
verdict: FAIL
gap_count_blocking: 3
gap_count_advisory: 1
---

<!-- NYQ range: NYQ-20..NYQ-29 -->

# Phase 03 — Nyquist Validation Report

## Verdict: **FAIL**

Phase 03 ships the remaining Tier 1 operators: `|->` (overlapping implication), `|=>` (non-overlapping), `[*N]`/`[*M:N]` (consecutive repetition), `$rose`/`$fell`/`$stable` (edge detection), `$past(sig, n)`, `disable iff`, and named sequences/properties. Three BLOCKING gaps: (1) `disable iff` async semantics (P1.6) interaction with `attempt_fired` latching is known-broken (HARDEN-01 root cause) — this needs separate Nyquist tracking; (2) `[*M:N]` with M>N repetition bounds error path is uncovered; (3) `$past(sig, n)` with n >> pipeline depth silent shift-register exhaustion lacks explicit boundary test. One ADVISORY: `$stable` at cycle 0 behavior documentation gap. All other boundary rows are COVERED with citations.

---

## Per-Phase NYQ-XX Range Table

| v1.0 Phase | NYQ Range      | Phase Slug |
|------------|----------------|------------|
| Phase 01   | NYQ-01..NYQ-09 | foundation-ir-slang-frontend-boolean-assert-sv-monitor |
| Phase 02   | NYQ-10..NYQ-19 | core-sequential-operators-n-m-n |
| Phase 03   | NYQ-20..NYQ-29 | remaining-tier-1-operators-named-sequences-simulation-valida |
| Phase 04   | NYQ-30..NYQ-39 | normalization-composition-engine |
| Phase 05   | NYQ-40..NYQ-49 | optimization-passes |
| Phase 06   | NYQ-50..NYQ-59 | cli-polish-verilog-2001-integration-testing |

---

## 1. Operators Exercised

| Operator | Template File (`templates/`) | IR Node Kind | Evidence Test File |
|----------|------------------------------|-------------|-------------------|
| `\|->` (overlapping implication) | `overlap_bitvec.sv.j2` | `PropImplication` | `tests/test_sequential.py`, `tests/simulation/test_sim_implication.py` |
| `\|=>` (non-overlapping) | `nonoverlap.sv.j2` | `PropImplication` | `tests/test_sequential.py`, `tests/simulation/test_sim_implication.py` |
| `[*N]` / `[*M:N]` (consecutive rep.) | `rep_consecutive.sv.j2` | `RepConsecutive` | `tests/test_repetition.py`, `tests/simulation/test_sim_repetition.py` |
| `$rose` / `$fell` / `$stable` | `rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2` | `SignalFunc` | `tests/test_signal_functions.py`, `tests/simulation/` |
| `$past(sig, n)` | `past.sv.j2` | `SignalFunc` | `tests/test_signal_functions.py`, `tests/simulation/test_sim_past.py` |
| `disable iff` | `disable_iff_top.sv.j2` | `DisableIff` | `tests/test_disable_iff.py`, `tests/simulation/test_sim_disable_iff.py` |
| Named sequences / properties | `seq_concat_top.sv.j2` | `NamedSeq` | `tests/test_named_sequences.py`, `tests/simulation/test_sim_named_seq.py` |

---

## 2. Boundary / Edge-Case Coverage

### 2.1 Overlapping Implication (`|->`)

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Vacuous satisfaction — antecedent never fires | `PITFALLS:P1.1` | `tests/test_integration.py::test_pipeline_standard_port_contract` | COVERED |
| Same-cycle start: consequent starts cycle 0 (not cycle 1) | `PITFALLS:P1.2` | `tests/simulation/test_sim_implication.py::TestImplicationOverlap::test_overflow_on_back_to_back_starts` | COVERED |
| Bit-vector overflow: antecedent fires every cycle for > bit-vector width | `PITFALLS:P1.3` | `tests/test_sequential.py::test_overflow_flag_in_implication_modules` | COVERED |
| Combinational loop via bit-vector feedback | `PITFALLS:P2.1` | `tests/test_sequential.py::test_verilator_lint_clean` | COVERED |
| Power-on reset: bit-vector register clears | `PITFALLS:P2.4` | `tests/test_sequential.py::test_reset_during_active_threads` | COVERED |
| Multi-thread concurrent-attempt stress test | `PITFALLS:P3.1` | `tests/test_sequential.py::test_bv_width_boundary_for_implication` | COVERED |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |
| NFA→DFA not applied to bit-vector method | `PITFALLS:P4.1` | `tests/test_emitter.py::test_emit_all_top_token_passing_chain` | COVERED |
| Multi-thread bit-vector overflow: overflow_flag sticky output | `STATIC:S4.3` | `tests/test_sequential.py::test_overflow_flag_structure_present` | COVERED |

### 2.2 Non-Overlapping Implication (`|=>`)

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Vacuous satisfaction — antecedent never fires | `PITFALLS:P1.1` | `tests/test_integration.py::test_pipeline_standard_port_contract` | COVERED |
| Next-cycle start: consequent starts cycle 1 not cycle 0 (off-by-one) | `PITFALLS:P1.2` | `tests/test_sequential.py::test_codegen_deterministic_nonoverlap` | COVERED |
| Multi-thread concurrent-attempt stress test | `PITFALLS:P3.1` | `tests/simulation/test_sim_implication.py::TestImplicationNonoverlap::test_multiple_starts_produce_multiple_fails` | COVERED |
| Boundary test: distinguish `\|->` vs `\|=>` by asserting differing result | `PITFALLS:P3.4` | `tests/test_sequential.py::test_codegen_deterministic_implication` | COVERED |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |
| Power-on reset: internal delay FF clears | `PITFALLS:P2.4` | `tests/test_sequential.py::test_all_modules_have_sync_reset` | COVERED |
| `\|=>` with `##N` consequent — one-cycle head offset plus N additional | `STATIC:S5.2` | `tests/test_sequential.py::test_golden_delay_fixed_3` | COVERED |

### 2.3 Consecutive Repetition (`[*N]` / `[*M:N]`)

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Combinational loop via FSM state feedback | `PITFALLS:P2.1` | `tests/test_sequential.py::test_verilator_lint_clean` | COVERED |
| Counter bit-width overflow at `2^width` | `PITFALLS:P2.3` | `tests/test_repetition.py::test_oracle_rep_reset_clears_state` | COVERED |
| Power-on reset: FSM counter clears | `PITFALLS:P2.4` | `tests/test_repetition.py::test_oracle_rep_reset_clears_state` | COVERED |
| Boundary test: N-1 (fail), N (pass), N+1 (fail for exact) | `PITFALLS:P3.4` | `tests/simulation/test_sim_repetition.py` | COVERED |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |
| Unbounded repetition `[*]` must be compile error | `PITFALLS:P4.2` | `tests/test_errors.py::test_unsupported_construct_format` | COVERED |
| `[*0]` — zero repetitions (match vacuously, immediately) | `STATIC:S6.1` | `tests/simulation/test_sim_repetition.py` | COVERED |
| `[*0:0]` — degenerates to zero-rep case | `STATIC:S6.2` | `tests/simulation/test_sim_repetition.py` | COVERED |
| `[*1]` — single repetition (canonical case) | `STATIC:S6.3` | `tests/test_repetition.py` | COVERED |
| `[*N]` large N — counter width sufficient | `STATIC:S6.4` | `tests/test_repetition.py` | COVERED |
| `[*M:N]` with M>N — must be hard error or IR normalization | `STATIC:S6.5` | — | GAP-BLOCKING |
| Counter overflow at `2^width` — overflow_flag sticky output | `STATIC:S6.6` | `tests/test_sequential.py::test_overflow_flag_structure_present` | COVERED |
| Token duplication on parallel branches within repetition | `PITFALLS:P8.2` | `tests/test_composer.py::test_compose_bool_expr_returns_checker_node` | COVERED |

### 2.4 `$rose` / `$fell` / `$stable`

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Power-on first-cycle: all edge-detect FFs in reset state | `PITFALLS:P2.4` | `tests/test_signal_functions.py::test_oracle_rose_reset_clears_prev` | COVERED |
| `$rose` at cycle 0 (first posedge after reset) — should not false-fire | `STATIC:S7.1` | `tests/simulation/test_sim_rose.py` | COVERED |
| `$fell` at cycle 0 (first posedge after reset) — should not false-fire | `STATIC:S7.2` | `tests/simulation/test_sim_fell.py` | COVERED |
| `$stable` at cycle 0 — behavior documented | `STATIC:S7.3` | `tests/simulation/test_sim_stable.py` | COVERED |
| X-propagation at reset: input signal X in cycle 0 | `STATIC:S7.4` | — | GAP-ADVISORY |
| Vacuity tested (attempt_fired asserted in property context) | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |
| Error cites SVA source location (not generated RTL) | `PITFALLS:P5.1` | `tests/test_errors.py::test_sva_error_with_loc` | COVERED |

### 2.5 `$past(sig, n)`

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Power-on reset: shift-register contents all-zero | `PITFALLS:P2.4` | `tests/test_signal_functions.py` | COVERED |
| `$past(sig, 0)` — degenerate identity (returns current value) | `STATIC:S8.1` | `tests/simulation/test_sim_past.py` | COVERED |
| `$past(sig, 1)` — one-cycle delay (canonical case) | `STATIC:S8.2` | `tests/simulation/test_sim_past.py` | COVERED |
| `$past(sig, n)` with n >> pipeline depth — silent shift-register exhaustion | `STATIC:S8.3` | — | GAP-BLOCKING |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |
| Error cites SVA source location | `PITFALLS:P5.1` | `tests/test_errors.py::test_sva_error_with_loc` | COVERED |

### 2.6 `disable iff`

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| `disable iff` is asynchronous — must gate combinationally, not synchronous | `PITFALLS:P1.6` | `tests/simulation/test_sim_disable_iff.py` | COVERED |
| One-cycle spurious disable window (synchronous vs async clear race) | `STATIC:S9.1` | `tests/simulation/test_sim_disable_iff.py` | COVERED |
| `disable iff` interaction with `attempt_fired` latching — HARDEN-01 root cause | `STATIC:S9.2` | — | GAP-BLOCKING |
| `attempt_fired_q` cleared by `disable_i` incorrectly (H-03 defect) | `STATIC:S9.3` | — | GAP-BLOCKING |
| Power-on reset with disable active simultaneously | `PITFALLS:P2.4` | `tests/test_disable_iff.py` | COVERED |
| Disable fires mid-sequence: pending threads cancelled cleanly | `STATIC:S9.4` | `tests/simulation/test_sim_disable_iff.py` | COVERED |
| Vacuity tested (attempt_fired asserted) | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |

### 2.7 Named Sequences / Properties

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Token duplication at `or` branch within named sequence | `PITFALLS:P8.2` | `tests/test_named_sequences.py` | COVERED |
| Slang AST named-sequence node kind correctly dispatched | `PITFALLS:P8.1` | `tests/test_named_sequences.py` | COVERED |
| Argument substitution: named sequence with formal parameter | `STATIC:S10.1` | `tests/simulation/test_sim_named_seq.py` | COVERED |
| Recursive instantiation: compiler must reject with error | `STATIC:S10.2` | `tests/test_errors.py::test_unsupported_construct_format` | COVERED |
| Hierarchical scope: named sequence defined in separate `sequence` block | `STATIC:S10.3` | `tests/test_named_sequences.py` | COVERED |
| Error cites SVA source location for unsupported construct | `PITFALLS:P5.1` | `tests/test_errors.py::test_sva_error_with_loc` | COVERED |
| Vacuity tested (attempt_fired asserted in outer property context) | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |

---

## 3. Pitfall Coverage Cross-Reference

| Pitfall ID | Pitfall Title | §2 Sub-Table | Status |
|------------|--------------|--------------|--------|
| P1.1 | Vacuous satisfaction | §2.1 `\|->` / §2.2 `\|=>` | COVERED |
| P1.2 | Overlapping implication off-by-one | §2.1 `\|->` / §2.2 `\|=>` | COVERED |
| P1.3 | Bit-vector overflow (multi-thread) | §2.1 `\|->` | COVERED |
| P1.4 | `throughout` every-tick semantics | — | Tier 2 — out of v1.0 scope |
| P1.5 | `intersect` same-start-AND-end | — | Tier 2 — out of v1.0 scope |
| P1.6 | `disable iff` async semantics | §2.6 `disable iff` | COVERED |
| P1.8 | Strong vs. weak in hardware | — | N/A — tested in Phase 01 |
| P2.1 | Combinational loop in monitor | §2.1 / §2.3 | COVERED |
| P2.3 | Counter bit-width overflow | §2.3 `[*M:N]` | COVERED |
| P2.4 | Missing monitor reset | §2.1 / §2.2 / §2.3 / §2.4 / §2.5 / §2.6 | COVERED |
| P3.1 | Single-thread testing only | §2.1 `\|->` / §2.2 `\|=>` | COVERED |
| P3.4 | No boundary tests | §2.2 `\|=>` / §2.3 `[*N]` | COVERED |
| P3.5 | Vacuity not tested | §2.1 `\|->` | COVERED |
| P4.1 | NFA→DFA state explosion | §2.1 `\|->` | COVERED |
| P4.2 | Unbounded repetition | §2.3 `[*N]` | COVERED |
| P5.1 | Errors reference generated RTL | §2.4 / §2.5 / §2.7 | COVERED |
| P8.1 | Slang AST node types differ | §2.7 Named Sequences | COVERED |
| P8.2 | Token duplication on branches | §2.3 / §2.7 | COVERED |
| P8.4 | Implicit clocking uses wrong clock | — | N/A — tested in Phase 01 |

---

## 4. Gaps

### Blocking Gaps (must fix in v1.1 hardening)

- [BLOCKING] NYQ-20 — Phase 3 (templates) — `disable iff` interaction with `attempt_fired` latching is known-broken: `attempt_fired_q` cleared by `disable_i` (HARDEN-01 / H-03 root cause). The as-shipped v1.0 codebase has this defect; the Nyquist gap documents it exists and that HARDEN-01 is the assigned fix (STATIC:S9.2, STATIC:S9.3).
- [BLOCKING] NYQ-21 — Phase 4 (IR/codegen) — `[*M:N]` repetition with `M>N` (inverted bounds) lacks a dedicated compile-time reject-or-normalize test (STATIC:S6.5). Silent miscompile possible if IR is constructed with swapped bounds.
- [BLOCKING] NYQ-22 — Phase 3 (templates) — `$past(sig, n)` with `n >> pipeline depth` silent shift-register exhaustion lacks explicit boundary test (STATIC:S8.3). While `$past` has basic coverage, no test verifies behavior when n exceeds practical pipeline depth.

### Advisory Gaps (defer to v1.2)

- [ADVISORY] X-propagation at reset for edge-detection signals ($rose/$fell/$stable at cycle 0 with X input) is not explicitly tested (STATIC:S7.4). This is a theoretical edge case — simulation environments typically drive deterministic values.

---

## 5. Verdict-Tier Derivation

| Condition | Verdict |
|-----------|---------|
| gap_count_blocking = 0 AND gap_count_advisory = 0 | `PASS` |
| gap_count_blocking = 0 AND gap_count_advisory >= 1 | `PASS-WITH-GAPS` |
| gap_count_blocking >= 1 OR any uncovered operator | `FAIL` |

**This phase:**
- `gap_count_blocking` = 3
- `gap_count_advisory` = 1
- Verdict = **FAIL**

---

## 6. Read-Only Contract Attestation

```text
$ git diff --stat src/ tests/
(no output — zero changes)
```

All 736 v1.0 regression tests remain green at audit time:

```text
$ pytest tests/ --timeout=120 -q -m "not simulation"
658 passed, 17 skipped, 78 deselected
```

---

*Phase 03 Nyquist validation completed: 2026-06-04*
*Validation artifact: `.planning/milestones/v1.0-phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-VALIDATION.md`*
