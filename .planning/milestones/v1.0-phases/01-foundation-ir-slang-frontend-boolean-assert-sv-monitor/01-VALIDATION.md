---
phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor
phase_number: 01
phase_name: foundation-ir-slang-frontend-boolean-assert-sv-monitor
verifier: plan-02-audit (autonomous)
verified: 2026-06-04
status: failed
requirement_ids:
  - VALIDATE-01
verdict: FAIL
gap_count_blocking: 2
gap_count_advisory: 1
---

<!-- NYQ range: NYQ-01..NYQ-09 -->

# Phase 01 — Nyquist Validation Report

## Verdict: **FAIL**

Phase 01 ships boolean expression compilation, IR foundations (BoolExpr, ClockSpec, SourceLoc), slang AST import, and standard monitor port interface. Two BLOCKING gaps are identified: (1) no dedicated test verifies vacuous-satisfaction behavior — `attempt_fired` port exists but no test asserts `pass=0, fail=0` when `start` never fires; (2) `strong()` semantics remains uncovered — the code path appears to silently weaken liveness properties. One ADVISORY gap: multi-bit boolean signal handling lacks an explicit test. All other boundary rows are COVERED with `tests/test_*.py::test_*` citations.

---

## Per-Phase NYQ-XX Range Table

Fixed allocation — Plan 02 parallel audits use these ranges; they CANNOT collide.

| v1.0 Phase | NYQ Range      | Phase Slug |
|------------|----------------|------------|
| Phase 01   | NYQ-01..NYQ-09 | foundation-ir-slang-frontend-boolean-assert-sv-monitor |
| Phase 02   | NYQ-10..NYQ-19 | core-sequential-operators-n-m-n |
| Phase 03   | NYQ-20..NYQ-29 | remaining-tier-1-operators-named-sequences-simulation-valida |
| Phase 04   | NYQ-30..NYQ-39 | normalization-composition-engine |
| Phase 05   | NYQ-40..NYQ-49 | optimization-passes |
| Phase 06   | NYQ-50..NYQ-59 | cli-polish-verilog-2001-integration-testing |

> **ID allocation rule:** Each NYQ-XX ID is BLOCKING-gap-only. Assign IDs
> sequentially within the phase range, starting at the range minimum (e.g.,
> Phase 01 first BLOCKING gap → NYQ-01, second → NYQ-02, …). ADVISORY gaps
> do NOT receive NYQ-XX IDs (D-07).

---

## 1. Operators Exercised

| Operator | Template File (`templates/`) | IR Node Kind | Evidence Test File |
|----------|------------------------------|-------------|-------------------|
| Boolean expression | `bool_expr.sv.j2` | `BoolExpr` | `tests/test_ir.py`, `tests/test_composer.py` |
| Monitor port interface | `bool_expr.sv.j2` (port block) | n/a (emitter-level) | `tests/test_emitter.py` |
| `attempt_fired` first-class | `bool_expr.sv.j2` | `CheckerOutput` | `tests/test_integration.py` |
| slang AST → IR import | n/a (importer) | all IR nodes | `tests/test_ast_importer.py` |
| `SourceLoc` plumbing | n/a (IR field) | `SourceLoc` on `SVANode` | `tests/test_integration.py` |
| Default clocking | n/a (importer) | `ClockSpec` | `tests/test_ast_importer.py`, `tests/test_ir.py` |

---

## 2. Boundary / Edge-Case Coverage

### 2.1 Boolean Expression

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Vacuous satisfaction — antecedent never fires, monitor reports pass | `PITFALLS:P1.1` | — | GAP-BLOCKING |
| Power-on reset: `rst_n` asserted at cycle 0, outputs deassert cleanly | `PITFALLS:P2.4` | `tests/test_emitter.py::test_emit_contains_reset` | COVERED |
| `attempt_fired` output goes high exactly on the first valid antecedent match | `PITFALLS:P3.5` | `tests/test_integration.py::test_pipeline_standard_port_contract` | COVERED |
| Error message cites source SVA location (not generated RTL line) | `PITFALLS:P5.1` | `tests/test_integration.py::test_pipeline_source_loc_preserved` | COVERED |
| Slang AST `BooleanExpression` kind is visited; no unknown-kind fall-through | `PITFALLS:P8.1` | `tests/test_ast_importer.py::test_import_assertion_bool_simple_returns_bool_expr` | COVERED |
| Implicit clocking: no silent default-clock assumption | `PITFALLS:P8.4` | `tests/test_ast_importer.py::test_import_assertion_clock_extraction` | COVERED |
| Strong vs. weak: `strong()` must emit compile error, not silent liveness weakening | `PITFALLS:P1.8` | — | GAP-BLOCKING |
| Constant-true property: `1 \|-> 1` — passes always, attempt_fired always high | `STATIC:S1.1` | `tests/test_integration.py::test_pipeline_bool_simple` | COVERED |
| Constant-false property: `0 \|-> 1` — vacuous, attempt_fired stays low | `STATIC:S1.2` | `tests/test_integration.py::test_pipeline_bool_complex` | COVERED |
| Multi-bit boolean signal as condition (not just 1-bit) | `STATIC:S1.3` | — | GAP-ADVISORY |
| Named signal with `$rose`/`$fell` not in this phase (would be an IR error) | `STATIC:S1.4` | `tests/test_errors.py::test_unsupported_construct_format` | COVERED |
| Observable monitor state: `attempt_fired`, `pending_count`, `overflow_flag` exposed as debug outputs | `PITFALLS:P5.4` | `tests/test_emitter.py::test_emit_all_ports_present` | COVERED |

### 2.2 Monitor Port Interface

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Standard ports: clk, rst_n, start, pass, fail, active, attempt_fired | `STATIC:S1.0` | `tests/test_integration.py::test_pipeline_standard_port_contract` | COVERED |
| All outputs are registered (no combinational passthrough) | `PITFALLS:P2.2` | `tests/test_integration.py::test_pipeline_registered_outputs` | COVERED |
| `attempt_fired` is sticky (accumulates across multiple start pulses) | `STATIC:S1.0a` | `tests/test_emitter.py::test_emit_contains_attempt_fired_sticky` | COVERED |
| Source location threaded through IR → emitted as comment in generated RTL | `PITFALLS:P5.1` | `tests/test_integration.py::test_pipeline_source_loc_preserved` | COVERED |

---

## 3. Pitfall Coverage Cross-Reference

| Pitfall ID | Pitfall Title | §2 Sub-Table | Status |
|------------|--------------|--------------|--------|
| P1.1 | Vacuous satisfaction | §2.1 Boolean Expression | GAP-BLOCKING |
| P1.2 | Overlapping implication off-by-one | — | N/A — operator not in Phase 01 |
| P1.3 | Bit-vector overflow (multi-thread) | — | N/A — operator not in Phase 01 |
| P1.4 | `throughout` every-tick semantics | — | Tier 2 — out of v1.0 scope |
| P1.5 | `intersect` same-start-AND-end | — | Tier 2 — out of v1.0 scope |
| P1.6 | `disable iff` async semantics | — | N/A — operator not in Phase 01 |
| P1.8 | Strong vs. weak in hardware | §2.1 Boolean Expression | GAP-BLOCKING |
| P2.1 | Combinational loop in monitor | — | N/A — operator not in Phase 01 |
| P2.3 | Counter bit-width overflow | — | N/A — operator not in Phase 01 |
| P2.4 | Missing monitor reset | §2.1 Boolean Expression | COVERED |
| P3.1 | Single-thread testing only | — | N/A — operator not in Phase 01 |
| P3.4 | No boundary tests | — | N/A — operator not in Phase 01 |
| P3.5 | Vacuity not tested | §2.1 Boolean Expression | COVERED |
| P4.1 | NFA→DFA state explosion | — | N/A — architectural decision, not per-operator |
| P4.2 | Unbounded repetition | — | N/A — operator not in Phase 01 |
| P5.1 | Errors reference generated RTL | §2.1 Boolean Expression | COVERED |
| P5.4 | No observable monitor state | §2.1 Boolean Expression | COVERED |
| P8.1 | Slang AST node types differ | §2.1 Boolean Expression | COVERED |
| P8.2 | Token duplication on branches | — | N/A — operator not in Phase 01 |
| P8.4 | Implicit clocking uses wrong clock | §2.1 Boolean Expression | COVERED |

---

## 4. Gaps

### Blocking Gaps (must fix in v1.1 hardening)

- [BLOCKING] NYQ-01 — Phase 3 (templates) — No dedicated test verifies vacuous satisfaction: `attempt_fired` port exists but no test asserts `pass=0, fail=0` when `start` never fires (P1.1). Silent false-pass possible.
- [BLOCKING] NYQ-02 — Phase 4 (IR/codegen) — `strong()` semantics uncovered: no test verifies that `strong(property)` emits a compile error rather than silently weakening to safety semantics (P1.8). Silent liveness weakening possible.

### Advisory Gaps (defer to v1.2)

- [ADVISORY] Multi-bit boolean signal as condition lacks dedicated test (STATIC:S1.3). The `pipeline_bool_complex` test exercises multi-signal expressions but not specifically multi-bit signal semantics.

---

## 5. Verdict-Tier Derivation

| Condition | Verdict |
|-----------|---------|
| gap_count_blocking = 0 AND gap_count_advisory = 0 | `PASS` |
| gap_count_blocking = 0 AND gap_count_advisory >= 1 | `PASS-WITH-GAPS` |
| gap_count_blocking >= 1 OR any uncovered operator | `FAIL` |

**This phase:**
- `gap_count_blocking` = 2
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

*Phase 01 Nyquist validation completed: 2026-06-04*
*Validation artifact: `.planning/milestones/v1.0-phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-VALIDATION.md`*
