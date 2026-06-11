# sva2rtl v1.1.0 — Hardening Release

**Released:** June 2026
**Tag:** `v1.1.0`
**Milestone:** v1.1 Hardening

This release hardens the v1.0 foundation with fixes for edge-case correctness issues, Verilog-2001 template deduplication, Verilator as a second simulation oracle, CLI UX improvements, and comprehensive retroactive test coverage analysis. No API changes — drop-in replacement for v1.0.

---

## HARDENING Fixes

### HARDEN-01: attempt_fired correctly latches under disable iff

When a property uses `disable iff`, the `attempt_fired` output signal now correctly latches high on every triggering attempt and is never spuriously cleared by the disable condition. Previously, `attempt_fired` could be reset mid-evaluation, making it unreliable as an attempt counter.

### HARDEN-02: Multi-assertion declaration isolation

Compiling multiple assertions from the same source file no longer leaks named sequence/property declarations between compilation units. A defensive state reset ensures each assertion starts with a clean declaration table.

### HARDEN-03: Invalid repetition bounds rejected

Properties with `[*0]` (zero-length match) or `[*M:N]` where `M > N` (inverted range) now produce clear compile errors instead of silently generating incorrect RTL.

### HARDEN-04: Signal name preservation in bind statements

The `_collect_signals` function now preserves the original user-provided signal names rather than discarding them in favor of auto-generated port names. This affects `--dump-tree` output and bind statement signal references.

### HARDEN-05: dump-tree handles multi-property files

`--dump-tree` on a file with multiple assertions now shows the optimized vs unoptimized checker comparison for every property, not just the first one. The `--dump-ir` flag similarly outputs all properties with proper separators.

### HARDEN-06: --property supports index and line-number matching

The `--property` flag now accepts three match modes:
- Label name: `--property my_check`
- 1-based index: `--property 3` (selects the 3rd assertion)
- Source line: `--property @42` (selects the assertion at line 42)

### HARDEN-07: --output mode detection

`--output` now detects whether the target path is a file (has a `.sv`/`.v` extension) or a directory (ends with `/`). Combining a file path with multi-property input produces a clear error instead of ambiguous behavior.

### HARDEN-08: --verilog and --dump-* are mutually exclusive

Combining `--verilog` with `--dump-ast`, `--dump-ir`, or `--dump-tree` now produces an explicit error. Previously, `--verilog` was silently ignored on dump output. Run `--verilog` separately for V2001-style RTL emission.

---

## TEMPLATE REFACTORING

### Shared Jinja2 Macros

All 11 RTL templates now use shared Jinja2 macros (`_macros.sv.j2`) for type and keyword differences between SystemVerilog and Verilog-2001. This eliminates the duplicated SV/V2001 always-block bodies that previously existed in every template.

Net result: **289 fewer lines** in the templates directory. Generated RTL output is byte-identical to v1.0 for SystemVerilog mode and behaviorally equivalent for Verilog-2001 mode.

### HARDEN-01 Fix at Macro Root

The `attempt_fired` latching fix lives in exactly one macro definition (`_attempt_fired_macro.sv.j2`). All 11 templates inherit the fix automatically. No per-template duplication.

---

## VERILATOR PARITY + CI

### Verilator as Second Simulation Oracle

The 65-test simulation oracle suite now passes under both iverilog and Verilator. A Verilator C++ wrapper (`tests/simulation/wrapper.cpp.j2`) drives the same per-cycle stimulus and checks that iverilog uses, establishing dual-oracle confidence in generated RTL correctness.

### CI Matrix Expansion

The CI pipeline now runs 8 parallel jobs: Ubuntu and macOS × Python 3.12 and 3.13 × iverilog and Verilator. The iverilog axis runs the full 736-test suite; the Verilator axis runs the 65 simulation oracle tests. All 8 jobs must be green before merge.

### Dual-Oracle Commitment

The dual-oracle contract is documented in `CLAUDE.md`: a test passing under iverilog but failing under Verilator is a defect that must be fixed — never waived or marked as xfail.

---

## POLISH

### Version Sync

`__init__.py` and `pyproject.toml` now agree on version `1.1.0`. `sva2rtl --version` prints `1.1.0`.

### Code Review Findings Resolved

All 10 MEDIUM-severity and 9 LOW-severity advisory findings from the v1.0 Phase 06 code review are resolved: 2 closed as not-applicable, 9 fixed across Phases 1-6, and 8 formally deferred to v1.2 with rationale in `PROJECT.md`.

### Cross-Phase Code Review

A code review of the complete v1.1 hardening diff (Phases 1-5 changes) confirms **zero new HIGH-severity findings** introduced during hardening work.

---

## Nyquist Coverage Baseline

Retroactive Nyquist test-coverage reports were generated for all 6 v1.0 phases, identifying 12 BLOCKING coverage gaps (NYQ-01 through NYQ-53). These gaps are tracked in `REQUIREMENTS.md` for future hardening milestones.

Coverage reports: `.planning/milestones/v1.0-phases/0N-*/0N-VALIDATION.md`

---

## Upgrading from v1.0

- Version string: `1.0.0` → `1.1.0`
- No API changes — all existing compilation workflows continue to work
- CLI changes are additive (new `--property` modes, better error messages)
- Template refactoring produces byte-identical SystemVerilog output
- Drop-in replacement

---

## Full Changelog

See `.planning/phases/0[1-6]-*/0*-SUMMARY.md` for per-phase execution summaries and commit-level detail.
