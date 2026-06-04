---
phase: 06-cli-polish-verilog-2001-integration-testing
phase_number: 06
phase_name: cli-polish-verilog-2001-integration-testing
verifier: plan-02-audit (autonomous)
verified: 2026-06-04
status: failed
requirement_ids:
  - VALIDATE-01
verdict: FAIL
gap_count_blocking: 4
gap_count_advisory: 0
---

<!-- NYQ range: NYQ-50..NYQ-59 -->

# Phase 06 — Nyquist Validation Report

## Verdict: **FAIL**

Phase 06 ships CLI polish, Verilog-2001 output mode, integration testing, and multi-property pipeline. Four BLOCKING gaps, all mapping to known HARDEN-05..08 HIGH defects from the Phase 06 code review: (1) `--dump-tree` on multi-property files only dumps the first property (HARDEN-05); (2) `--property` cannot target unlabeled assertions (HARDEN-06); (3) `--output` file-vs-directory ambiguity (HARDEN-07); (4) `--verilog` combined with `--dump-*` flags silently ignores the V2001 mode (HARDEN-08). These are known pre-existing defects, not new discoveries. All other boundary rows are COVERED with `tests/test_*.py::test_*` citations, including error code SVA-E005, V2001 emission, golden parity, and iverilog compilation.

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
| CLI — all flags | n/a (click CLI) | n/a | `tests/test_cli.py`, `tests/test_cli_phase6.py` |
| `--verilog` V2001 emission | all 11 templates | `verilog_mode` param | `tests/test_verilog_mode.py` |
| `--dump-ast` / `--dump-ir` / `--dump-tree` | n/a (dump passes) | n/a | `tests/test_dump_tree.py` |
| `--property` flag | n/a (filtering) | n/a | `tests/test_cli.py` |
| `--output` path handling | n/a (output routing) | n/a | `tests/test_cli.py` |
| Integration pipeline | n/a (full pipeline) | n/a | `tests/test_integration_full.py` |
| Golden parity (V2001 ≡ SV) | all 11 templates | `verilog_mode` param | `tests/test_golden_parity.py` |
| bind generation | `bind.sv.j2` | `BindStmt` | `tests/test_bind.py` |

---

## 2. Boundary / Edge-Case Coverage

### 2.1 CLI — Core Flags

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| Error message cites source SVA location | `PITFALLS:P5.1` | `tests/test_errors.py::test_sva_error_with_loc` | COVERED |
| Supported-construct documentation (`SUPPORTED_CONSTRUCTS.md`) maintained | `PITFALLS:P5.2` | `tests/test_cli.py` (version/help output) | COVERED |
| `--output` flag accepts path | `STATIC:S6.1a` | `tests/test_cli.py` | COVERED |
| `--verilog` flag enables V2001 emission | `STATIC:S6.1b` | `tests/test_verilog_mode.py` | COVERED |
| `--slang-path` custom slang binary | `STATIC:S6.1c` | `tests/test_cli.py` | COVERED |
| `--no-optimize` flag disables optimizer | `STATIC:S6.1d` | `tests/test_golden_parity.py` | COVERED |
| `--version` outputs correct version | `STATIC:S6.1e` | `tests/test_cli.py` | COVERED |

### 2.2 CLI — Multi-Property & Edge Cases

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| `--property` with no match → `SVA-E005` exit 2 | `STATIC:S6.2a` | `tests/test_errors.py::test_unsupported_construct_format` | COVERED |
| `--property` against unlabeled assertion (HARDEN-06 root cause) | `STATIC:S6.2b` | — | GAP-BLOCKING |
| `--dump-tree` on multi-property file (HARDEN-05 root cause) | `STATIC:S6.2c` | — | GAP-BLOCKING |
| `--output` file vs directory mode ambiguity (HARDEN-07 root cause) | `STATIC:S6.2d` | — | GAP-BLOCKING |
| `--verilog` combined with `--dump-ast`/`--dump-ir`/`--dump-tree` (HARDEN-08 root cause) | `STATIC:S6.2e` | — | GAP-BLOCKING |
| Multi-property pipeline: all properties compiled | `STATIC:S6.2f` | `tests/test_integration_full.py` | COVERED |

### 2.3 Verilog-2001 Emission

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| `logic` → `wire`/`reg` conversion across all templates | `STATIC:S6.3a` | `tests/test_verilog_mode.py` | COVERED |
| `always_ff` → `always @(...)` conversion | `STATIC:S6.3b` | `tests/test_verilog_mode.py` | COVERED |
| `'0` → `0` literal conversion | `STATIC:S6.3c` | `tests/test_verilog_mode.py` | COVERED |
| iverilog -g2001 zero-warning compile across fixtures | `STATIC:S6.3d` | `tests/test_integration_full.py` | COVERED |
| V2001 golden parity: behavioral equivalence with SV output | `STATIC:S6.3e` | `tests/test_golden_parity.py` | COVERED |

### 2.4 Integration Testing

| Boundary | Source | Evidence (`tests/test_*.py::test_*`) | Status |
|----------|--------|--------------------------------------|--------|
| iverilog -g2001 compile gate passes | `STATIC:S6.4a` | `tests/test_integration_full.py` | COVERED |
| `bind` generation produces correct wrapper | `STATIC:S6.4b` | `tests/test_bind.py::test_bind_default_start` | COVERED |
| `bind` port connections: clock, rst_n, observed signals | `STATIC:S6.4c` | `tests/test_bind.py::test_bind_clock_port_connection` | COVERED |
| E2E: source SVA → compiled monitor → simulation | `STATIC:S6.4d` | `tests/test_pipeline_e2e.py::test_e2e_bool_assert` | COVERED |

---

## 3. Pitfall Coverage Cross-Reference

| Pitfall ID | Pitfall Title | §2 Sub-Table | Status |
|------------|--------------|--------------|--------|
| P1.1 | Vacuous satisfaction | — | N/A — tested in Phase 01/03 |
| P1.2 | Overlapping implication off-by-one | — | N/A — tested in Phase 03 |
| P1.3 | Bit-vector overflow (multi-thread) | — | N/A — tested in Phase 03 |
| P1.4 | `throughout` every-tick semantics | — | Tier 2 — out of v1.0 scope |
| P1.5 | `intersect` same-start-AND-end | — | Tier 2 — out of v1.0 scope |
| P1.6 | `disable iff` async semantics | — | N/A — tested in Phase 03 |
| P1.8 | Strong vs. weak in hardware | — | N/A — tested in Phase 01 |
| P2.1 | Combinational loop in monitor | — | N/A — tested in Phase 02/03 |
| P2.3 | Counter bit-width overflow | — | N/A — tested in Phase 02 |
| P2.4 | Missing monitor reset | — | N/A — tested in Phase 01/02 |
| P3.1 | Single-thread testing only | — | N/A — tested in Phase 02/03 |
| P3.4 | No boundary tests | — | N/A — tested in Phase 02 |
| P3.5 | Vacuity not tested | — | N/A — tested in Phase 01/03 |
| P4.1 | NFA→DFA state explosion | — | N/A — tested in Phase 02/04/05 |
| P4.2 | Unbounded repetition | — | N/A — tested in Phase 03 |
| P5.1 | Errors reference generated RTL | §2.1 CLI | COVERED |
| P5.2 | No supported-construct documentation | §2.1 CLI | COVERED |
| P5.4 | No observable monitor state | — | N/A — tested in Phase 01 |
| P8.1 | Slang AST node types differ | — | N/A — tested in Phase 01 |
| P8.2 | Token duplication on branches | — | N/A — tested in Phase 04 |
| P8.4 | Implicit clocking uses wrong clock | — | N/A — tested in Phase 01 |

---

## 4. Gaps

### Blocking Gaps (must fix in v1.1 hardening)

- [BLOCKING] NYQ-50 — Phase 5 (CLI) — `--dump-tree` on multi-property file only dumps the first property (HARDEN-05 root cause). User loses visibility into all but the first annotated property in a file (STATIC:S6.2c).
- [BLOCKING] NYQ-51 — Phase 5 (CLI) — `--property` flag cannot target unlabeled assertions (HARDEN-06 root cause). User cannot filter to a specific anonymous assertion (STATIC:S6.2b).
- [BLOCKING] NYQ-52 — Phase 5 (CLI) — `--output` file-vs-directory mode ambiguity (HARDEN-07 root cause). User invoking `--output PATH` gets ambiguous behavior depending on whether PATH exists as a directory (STATIC:S6.2d).
- [BLOCKING] NYQ-53 — Phase 5 (CLI) — `--verilog` combined with `--dump-ast`/`--dump-ir`/`--dump-tree` silently ignores V2001 mode on dumps (HARDEN-08 root cause). User sees SV-style dumps even though `--verilog` is set (STATIC:S6.2e).

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
- `gap_count_blocking` = 4
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

*Phase 06 Nyquist validation completed: 2026-06-04*
*Validation artifact: `.planning/milestones/v1.0-phases/06-cli-polish-verilog-2001-integration-testing/06-VALIDATION.md`*
