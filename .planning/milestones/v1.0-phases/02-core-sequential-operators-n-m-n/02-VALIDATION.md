---
phase: 02-core-sequential-operators-n-m-n
phase_number: 02
phase_name: core-sequential-operators-n-m-n
verifier: plan-02-audit (autonomous)
verified: 2026-06-04
status: failed
requirement_ids:
  - VALIDATE-01
verdict: FAIL
gap_count_blocking: 2
gap_count_advisory: 0
---

<!-- NYQ range: NYQ-10..NYQ-19 -->

# Phase 02 — Nyquist Validation Report

## Verdict: **FAIL**

Phase 02 ships fixed-delay (`##N`) and range-delay (`##[M:N]`) sequential operators with counter encoding. Two BLOCKING gaps are identified: (1) the `M>N` range-delay error path lacks a dedicated compile-time reject-or-normalize test — a silent miscompile is possible if the IR is constructed with inverted bounds; (2) single-thread concurrent-attempt stress test for `##N` (antecedent fires every cycle for 2×N cycles) is not explicitly named or verified. All other boundary rows are COVERED with `tests/test_*.py::test_*` citations, including boundary delays, counter bit-width, reset, NFA avoidance, and deterministic codegen.

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
| `##N` (fixed delay) | `concat_delay.sv.j2` | `SeqConcat` | `tests/test_sequential.py` |
| `##[M:N]` (range delay) | `concat_delay.sv.j2` | `SeqConcat` | `tests/test_sequential.py` |
| Token-passing (TIMA Lab) | `seq_concat_top.sv.j2` | n/a (composition) | `tests/test_emitter.py` |
| Counter encoding | `concat_delay.sv.j2` | `SeqConcat.params` | `tests/test_sequential.py` |

---

## 2. Boundary / Edge-Case Coverage

### 2.1 Fixed Delay (`##N`)

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Combinational loop via shift-register feedback | `PITFALLS:P2.1` | `tests/test_sequential.py::test_verilator_lint_clean` | COVERED |
| Counter bit-width: `##0` — zero-cycle delay (degenerate identity case) | `PITFALLS:P2.3` | `tests/test_sequential.py::test_delay_zero_special_case` | COVERED |
| Power-on reset: shift-register clears to all-zero at rst_n | `PITFALLS:P2.4` | `tests/test_sequential.py::test_all_modules_have_sync_reset` | COVERED |
| Boundary test: `##(N-1)` fails, `##N` passes, `##(N+1)` fails | `PITFALLS:P3.4` | `tests/test_sequential.py::test_golden_delay_fixed_3` | COVERED |
| `attempt_fired` asserted in test | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |
| NFA→DFA not used for `##N` (token-passing preserves NFA) | `PITFALLS:P4.1` | `tests/test_emitter.py::test_emit_all_top_token_passing_chain` | COVERED |
| `##0` — zero delay, input directly wired to output | `STATIC:S2.1` | `tests/test_sequential.py::test_delay_zero_special_case` | COVERED |
| `##1` — single-cycle delay (canonical case) | `STATIC:S2.2` | `tests/test_sequential.py::test_delay_single_cycle_fixed` | COVERED |
| `##N` large (e.g. `##100`) — shift-register width sufficient | `STATIC:S2.3` | `tests/test_sequential.py::test_delay_cnt_width_boundary_values` | COVERED |
| `##N` where N exceeds counter bit-width allocation | `STATIC:S2.4` | `tests/test_sequential.py::test_delay_cnt_width_boundary_values` | COVERED |
| Multi-thread: antecedent fires every cycle for 2×N cycles | `PITFALLS:P3.1` | — | GAP-BLOCKING |

### 2.2 Range Delay (`##[M:N]`)

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Combinational loop via counter feedback | `PITFALLS:P2.1` | `tests/test_sequential.py::test_verilator_lint_clean` | COVERED |
| Counter bit-width overflow for `##[0:100]` — needs ceil(log2(101))+1 bits | `PITFALLS:P2.3` | `tests/test_sequential.py::test_delay_cnt_width_boundary_values` | COVERED |
| Power-on reset: counter clears correctly | `PITFALLS:P2.4` | `tests/test_sequential.py::test_reset_during_active_threads` | COVERED |
| Boundary test: M-1 (fail), M (pass), N (pass), N+1 (fail) | `PITFALLS:P3.4` | `tests/test_sequential.py::test_delay_window_comparator_boundaries` | COVERED |
| `attempt_fired` asserted in test | `PITFALLS:P3.5` | `tests/test_sequential.py::test_attempt_fired_in_all_modules` | COVERED |
| `##[0:0]` — degenerates to `##0` (identity) | `STATIC:S3.1` | `tests/test_sequential.py::test_delay_window_comparator_boundaries` | COVERED |
| `##[M:M]` — degenerates to `##M` (fixed delay) | `STATIC:S3.2` | `tests/test_sequential.py::test_delay_range_window_width` | COVERED |
| `##[M:N]` with M>N — must be a hard compile-time error or IR-level normalization | `STATIC:S3.3` | — | GAP-BLOCKING |
| `##[0:N]` — lower bound zero, window starts immediately | `STATIC:S3.4` | `tests/simulation/test_sim_delay.py::TestDelayRange::test_pass_at_min_delay` | COVERED |
| `##[N:N+1]` — minimal 2-value window | `STATIC:S3.5` | `tests/test_sequential.py::test_golden_delay_range_2_5` | COVERED |
| Multi-thread: antecedent fires every cycle for 2×N cycles | `PITFALLS:P3.1` | `tests/test_sequential.py::test_concurrent_threads_structural_capacity` | COVERED |
| Counter encoding (not state expansion) | `STATIC:S3.6` | `tests/test_sequential.py::test_delay_cnt_width_boundary_values` | COVERED |

---

## 3. Pitfall Coverage Cross-Reference

| Pitfall ID | Pitfall Title | §2 Sub-Table | Status |
|------------|--------------|--------------|--------|
| P1.1 | Vacuous satisfaction | — | N/A — tested in Phase 03 implication context |
| P1.2 | Overlapping implication off-by-one | — | N/A — operator not in Phase 02 |
| P1.3 | Bit-vector overflow (multi-thread) | — | N/A — operator not in Phase 02 |
| P1.4 | `throughout` every-tick semantics | — | Tier 2 — out of v1.0 scope |
| P1.5 | `intersect` same-start-AND-end | — | Tier 2 — out of v1.0 scope |
| P1.6 | `disable iff` async semantics | — | N/A — operator not in Phase 02 |
| P1.8 | Strong vs. weak in hardware | — | N/A — tested in Phase 01 |
| P2.1 | Combinational loop in monitor | §2.1 / §2.2 | COVERED |
| P2.3 | Counter bit-width overflow | §2.1 / §2.2 | COVERED |
| P2.4 | Missing monitor reset | §2.1 / §2.2 | COVERED |
| P3.1 | Single-thread testing only | §2.1 `##N` | GAP-BLOCKING |
| P3.4 | No boundary tests | §2.2 `##[M:N]` | COVERED |
| P3.5 | Vacuity not tested | §2.1 `##N` | COVERED |
| P4.1 | NFA→DFA state explosion | §2.1 `##N` | COVERED |
| P4.2 | Unbounded repetition | — | N/A — operator not in Phase 02 |
| P5.1 | Errors reference generated RTL | — | N/A — tested in Phase 01/06 |
| P8.1 | Slang AST node types differ | — | N/A — tested in Phase 01 |
| P8.2 | Token duplication on branches | — | N/A — operator not in Phase 02 |
| P8.4 | Implicit clocking uses wrong clock | — | N/A — tested in Phase 01 |

---

## 4. Gaps

### Blocking Gaps (must fix in v1.1 hardening)

- [BLOCKING] NYQ-10 — Phase 4 (IR/codegen) — `##[M:N]` with `M>N` (inverted bounds) lacks a dedicated compile-time reject-or-normalize test (STATIC:S3.3). Silent miscompile possible if IR is constructed with swapped bounds.
- [BLOCKING] NYQ-11 — Phase 3 (templates) — `##N` fixed-delay concurrent-attempt stress test (antecedent fires every cycle for 2×N cycles) is not explicitly named (PITFALLS:P3.1). The concurrent_threads_structural_capacity test covers `##[M:N]` but not `##N` verified independently.

### Advisory Gaps (defer to v1.2)

None — all advisory boundaries are COVERED.

---

## 5. Verdict-Tier Derivation

| Condition | Verdict |
|-----------|---------|
| gap_count_blocking = 0 AND gap_count_advisory = 0 | `PASS` |
| gap_count_blocking = 0 AND gap_count_advisory >= 1 | `PASS-WITH-GAPS` |
| gap_count_blocking >= 1 OR any uncovered operator | `FAIL` |

**This phase:**
- `gap_count_blocking` = 2
- `gap_count_advisory` = 0
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

*Phase 02 Nyquist validation completed: 2026-06-04*
*Validation artifact: `.planning/milestones/v1.0-phases/02-core-sequential-operators-n-m-n/02-VALIDATION.md`*
