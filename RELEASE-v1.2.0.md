# sva2rtl v1.2.0 — Quality-First Hardening Release

**Released:** June 2026
**Tag:** `v1.2.0` (not available — see note below)
**Milestone:** v1.2 Quality-First Hardening

> **Tag note (2026-07-11):** The `v1.2.0` Git tag is missing. The repository
> was published as an orphan branch (history starts at v1.5.2 initial release).
> The original v1.2.0 commit is not in the current history and cannot be
> safely tagged without external backup confirmation. If the original repo
> still exists, run `git tag v1.2.0 <commit-sha>` from the original history.

This release establishes formal equivalence verification for the optimizer pipeline, closes all 6 remaining Nyquist coverage gaps, hardens input handling against silent failures, extends the behavioral oracle to composed checker hierarchies, and upgrades slang compatibility to v11.0.

---

## FORMAL VERIFICATION

### `sva2rtl --verify` — yosys Equivalence Checking

A new `--verify` CLI flag runs formal equivalence checking between unoptimized and optimized RTL via yosys `equiv_make` + `equiv_induct`. The pipeline compiles without optimization, compiles with full optimization, then proves equivalence for all possible inputs.

```bash
sva2rtl --verify my_property.sv
# PASS: Formal equivalence check — optimized RTL is equivalent.
```

Implementation details:
- `src/sva2rtl/formal.py` (333 lines) — yosys subprocess integration
- Module names are suffixed (`_gold` / `_gate`) to avoid collisions
- Submodule hierarchies are flattened before equivalence checking
- 18 mock tests for Tcl script generation and error handling

### Per-pass Formal Equivalence Tests (Plan 1-2)

9 of 11 formal equivalence tests pass for individual optimizer passes. 2 xfail: 1 due to yosys 0.66 SAT model limit (CSE shared delay nodes), 1 due to `|->` construct not supported via slang frontend (needs fixture-based test). Previously, 5 tests failed due to a `dead_node` pass bug that incorrectly removed `_const_false` children from `seq_concat_top` — now fixed.

### Template-level Formal Verification (Plan 1-3 — FORMAL-03)

18 template-level formal equivalence tests verify that all 11 checker templates produce equivalent RTL with and without optimization. Tests use fixture JSON files compiled through the full pipeline (import → normalize → compose → optimize) and checked via yosys `equiv_make` + `equiv_induct`. 17 of 18 pass; 1 xfail (implication_bitvec — yosys SAT model limit).

### CI Formal Verification Job (Plan 1-4 — FORMAL-04)

A new `formal` CI job runs on `ubuntu-latest` with yosys installed, executing both per-pass and template-level formal equivalence tests with a 10-minute timeout.

---

## NYQUIST GAP REMEDIATION

All 6 remaining Nyquist BLOCKING gaps are now closed (11 tests):

| Gap | Description |
|-----|-------------|
| NYQ-01 | Vacuous satisfaction IR structure verified |
| NYQ-02 | `strong()` produces clear `UnsupportedConstruct` error with source location |
| NYQ-10 | `##[M:N]` with M>N produces clear `SvaCompileError` |
| NYQ-11 | Concurrent attempt stress — BV_WIDTH sufficiency verified |
| NYQ-22 | `$past(sig, n)` with n>100 emits warning |
| NYQ-30 | Token-count invariant — element/delay chain preservation verified |

---

## INPUT HARDENING

Three silent failure points eliminated:

- **HARDEN-09**: `_extract_clock` raises `SvaCompileError` on missing or invalid edge field (previously silently defaulted to "posedge")
- **HARDEN-10**: `_build_seq_repetition` raises `SvaCompileError` on empty expression (previously emitted `<expr>` placeholder into RTL)
- **HARDEN-11**: `_compose_repetition` raises `SvaCompileError` on non-BoolExpr sub-expressions (previously used silent `<expr>` fallback)

---

## BEHAVIORAL ORACLE — Composed Hierarchy Support

`SVABehavioralSim` now supports composed checker tree simulation via `simulate_checker_hierarchy()`:

- `seq_concat_top` — token-passing chain with interleaved elements and delays
- `disable_iff_top` — conditional disable gating over wrapped body
- `overlap_bitvec` / `nonoverlap` — implication with antecedent/consequent child wiring

`concat_delay` has been added to the oracle's leaf template set, enabling correct multi-stage delay pipeline simulation. All 9 simulation test files now include oracle cross-check tests: 5 with cycle-by-cycle comparison (signal function templates) and 4 with event-pattern comparison (delay, implication, disable_iff, named_seq).

---

## SLANG v11.0 COMPATIBILITY

The slang v11.0 AST JSON format differs from v7.0 in several ways. All differences now handled:

- `ProceduralBlock` nests `ConcurrentAssertion` inside `Block` (was direct in v7.0)
- Assertion labels use `StatementBlock.name` (was `Block.block` with `ADDRESS` prefix in v7.0)
- Clock events appear as `Clocking` directly (was `PropertySpec` in v7.0)
- Edge field values use lowercase normalization (`PosEdge` → `posedge`)
- Source location fields use `source_file` (was `source_file_start` in v7.0)
- Boolean properties wrapped in `Simple` expression nodes

---

## DEBT CLEANUP

- **DEBT-09**: Removed unreachable dead-code branch in `normalizer._flatten_concat` where both sides of an if/else performed the identical operation
- **DEBT-01..08**: Assessed and deferred to future milestones (all are v1.1 pre-existing MEDIUM/LOW items)

---

## TEST COVERAGE

- **816 tests pass** (was 736 in v1.1.0)
- 5 skipped (iverilog/Verilator simulation tests)
- 5 xfail (1 implication_bitvec yosys limit, 1 CSE yosys SAT limit, 1 |-> unsupported construct, 2 oracle known limitations)
- All 11 Nyquist gap tests pass
- 18 template-level formal equivalence tests (17 pass, 1 xfail)
- 24 behavioral oracle tests pass (including 2 hierarchical tests)
- 9 oracle cross-check tests across all simulation test files
- All golden files regenerated to match current codebase

---

## CHANGES SINCE v1.1.0

### New files
- `src/sva2rtl/formal.py` — yosys equivalence checking integration
- `tests/test_formal.py` — 18 formal verification mock tests
- `tests/test_formal_passes.py` — 11 per-pass formal tests
- `tests/test_formal_templates.py` — 18 template-level formal tests

### Modified files
- `src/sva2rtl/optimizer.py` — dead_node pass preserves _const_false in seq_concat_top (BUG-01 fix)
- `src/sva2rtl/composer.py` — Added missing SvaCompileError import
- `src/sva2rtl/ast_importer.py` — slang v11.0 compatibility + HARDEN-09/10
- `src/sva2rtl/behavioral_oracle.py` — hierarchical oracle + concat_delay leaf fix
- `src/sva2rtl/cli.py` — `--verify` flag support
- `src/sva2rtl/composer.py` — HARDEN-11 hardening
- `src/sva2rtl/normalizer.py` — DEBT-09 dead code removal
- `.github/workflows/ci.yml` — formal verification CI job
- `tests/simulation/test_sim_delay.py` — oracle cross-check tests
- `tests/simulation/test_sim_implication.py` — oracle cross-check tests
- `tests/simulation/test_sim_disable_iff.py` — oracle cross-check tests + syntax fixes
- `tests/simulation/test_sim_named_seq.py` — oracle cross-check tests
- `tests/test_nyquist_gaps.py` — NYQ-01/11 tests (3 added)
- `tests/test_behavioral_oracle.py` — hierarchical oracle tests (2 added)
- `tests/test_integration.py` — reset pattern matching fix
- `tests/test_pipeline_e2e.py` — SequenceConcat now supported
