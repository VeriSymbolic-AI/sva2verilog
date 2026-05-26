---
wave: 3
depends_on:
  - PLAN-2.1
  - PLAN-2.2
files_modified:
  - tests/test_sequential.py
  - tests/test_behavioral_oracle.py
  - tests/sv_fixtures/delay_fixed_1.sv
  - tests/sv_fixtures/delay_fixed_3.sv
  - tests/sv_fixtures/delay_fixed_8.sv
  - tests/sv_fixtures/delay_range_0_1.sv
  - tests/sv_fixtures/delay_range_2_5.sv
  - tests/sv_fixtures/delay_range_0_15.sv
  - tests/sv_fixtures/impl_overlap_simple.sv
  - tests/sv_fixtures/impl_nonoverlap_simple.sv
  - tests/sv_fixtures/impl_overlap_delay.sv
  - src/sva2rtl/behavioral_oracle.py
requirements:
  - TEST-02
  - TEST-05
  - TEST-06
autonomous: true
---

# Plan 2.3: Integration Tests, Golden File Harness, Concurrent-Attempt Stress Tests, Boundary Tests, and Behavioral Oracle

## Goal

Deliver comprehensive testing that proves Phase 2 operators work correctly end-to-end: golden file integration tests for deterministic codegen (TEST-02), concurrent-attempt stress tests that verify the bit-vector handles overlapping threads without false negatives/positives (TEST-05), boundary tests that verify exact cycle behavior at N-1, N, M, M+1 boundaries (TEST-06), and a behavioral reference oracle for semantic correctness validation. This plan also verifies `attempt_fired` and `overflow_flag` debug outputs (OUT-06) are exercised in every test scenario.

## Key Design Decisions

- **[REVIEW FIX] Behavioral reference oracle (HIGH concern #5):** A minimal Python `SVABehavioralSim` class (~150 lines) models `##N`, `##[M:N]`, `|->`, `|=>` semantics cycle-by-cycle. Used as test oracle to validate generated RTL monitors produce semantically correct pass/fail against IEEE 1800 definitions. This is NOT a full simulation — it is a pure-Python reference implementation that processes stimulus traces and produces expected pass/fail/active output for comparison.
- **[REVIEW FIX] Reset during active threads test (HIGH concern #6):** Explicit test case where `rst_n` asserts while threads are active in the bit-vector. Expected behavior: all state clears atomically in one cycle — bv_q goes to 0, overflow_flag clears, all outputs deassert. No residual thread state after reset.
- **[REVIEW FIX] Verilator lint gate (MEDIUM concern #8):** `verilator --lint-only output/*.sv` added as a required validation step. All generated RTL must pass Verilator lint with zero warnings. This catches undeclared wires, width mismatches, and undriven signals that iverilog may miss.

## Vertical Slice

Input: Real SVA source files for each operator variant
Pipeline: Full CLI invocation or programmatic `import_assertion -> compose -> emit_all`
Proof: Byte-for-byte golden match; stress test assertions on overflow_flag; boundary assertions on pass/fail cycle timing; behavioral oracle agreement

---

## Tasks

<task id="2.3.1">
<title>Create SVA source fixture files for all Phase 2 operator variants</title>
<read_first>
- tests/fixtures/bool_assert.sv (existing SVA fixture format)
- tests/fixtures/delay_assert.sv (existing delay fixture)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (full operator list)
</read_first>
<action>
Create `tests/sv_fixtures/` directory with real SVA source files (these are .sv files that slang can parse, unlike the JSON fixtures which are pre-parsed):

1. `tests/sv_fixtures/delay_fixed_1.sv`:
   ```
   module test_delay_1(input clk, a, b);
     assert property (@(posedge clk) a ##1 b);
   endmodule
   ```

2. `tests/sv_fixtures/delay_fixed_3.sv`:
   ```
   module test_delay_3(input clk, a, b);
     assert property (@(posedge clk) a ##3 b);
   endmodule
   ```

3. `tests/sv_fixtures/delay_fixed_8.sv`:
   ```
   module test_delay_8(input clk, a, b);
     assert property (@(posedge clk) a ##8 b);
   endmodule
   ```

4. `tests/sv_fixtures/delay_range_0_1.sv`: `a ##[0:1] b`
5. `tests/sv_fixtures/delay_range_2_5.sv`: `a ##[2:5] b`
6. `tests/sv_fixtures/delay_range_0_15.sv`: `a ##[0:15] b`
7. `tests/sv_fixtures/impl_overlap_simple.sv`: `a |-> b`
8. `tests/sv_fixtures/impl_nonoverlap_simple.sv`: `a |=> b`
9. `tests/sv_fixtures/impl_overlap_delay.sv`: `a |-> ##[2:5] b`

Each file is a minimal complete SV module with input ports and a single assert property statement.
</action>
<acceptance_criteria>
- Directory `tests/sv_fixtures/` exists
- All 9 .sv files exist and are syntactically valid SystemVerilog
- Each file contains exactly one `assert property` statement
- Each file declares a module with `input clk` and relevant signal ports
- Files `delay_fixed_1.sv`, `delay_fixed_3.sv`, `delay_fixed_8.sv` contain `##1`, `##3`, `##8` respectively
- Files `delay_range_0_1.sv`, `delay_range_2_5.sv`, `delay_range_0_15.sv` contain `##[0:1]`, `##[2:5]`, `##[0:15]` respectively
- File `impl_overlap_simple.sv` contains `|->`
- File `impl_nonoverlap_simple.sv` contains `|=>`
- File `impl_overlap_delay.sv` contains `|-> ##[2:5]`
</acceptance_criteria>
</task>

<task id="2.3.2">
<title>Create golden file integration test harness</title>
<read_first>
- tests/test_emitter.py (test_emit_golden_match pattern, lines 143-154)
- tests/test_integration.py (existing integration test patterns)
- tests/test_pipeline_e2e.py (existing end-to-end test patterns)
- src/sva2rtl/emitter.py (emit_all function from Plan 2.1)
- src/sva2rtl/ast_importer.py (import_assertion function)
- src/sva2rtl/composer.py (compose function)
</read_first>
<action>
Create `tests/test_sequential.py` with the golden file integration test harness for Phase 2:

1. Define helper function `_compile_fixture(fixture_json_path: Path) -> dict[str, str]`:
   - Loads JSON fixture, calls import_assertion -> compose -> emit_all
   - Returns dict of module_name -> sv_text

2. Define helper `_assert_golden_match(actual: str, golden_path: Path) -> None`:
   - Loads golden file, strips trailing whitespace per line, asserts line-by-line equality
   - On mismatch: shows first differing line number and content

3. TEST-02 Golden file tests (parametrized with pytest.mark.parametrize):
   - `test_golden_delay_fixed_3()`: compile delay_fixed.json, assert sva_delay_3_3 module matches golden
   - `test_golden_delay_range_2_5()`: compile delay_range.json, assert sva_delay_2_5 module matches golden
   - `test_golden_overlap_impl()`: compile implication_overlap.json, assert top module matches golden
   - `test_golden_nonoverlap_impl()`: compile implication_nonoverlap.json, assert top module matches golden

4. Determinism tests:
   - `test_codegen_deterministic_delay()`: compile same fixture 5 times, assert all outputs identical
   - `test_codegen_deterministic_implication()`: same for implication fixture

5. Debug output verification (OUT-06):
   - `test_attempt_fired_in_all_modules()`: for each compiled module, assert "attempt_fired" appears in output
   - `test_overflow_flag_in_implication_modules()`: for implication modules, assert "overflow_flag" appears
</action>
<acceptance_criteria>
- File `tests/test_sequential.py` exists
- `pytest tests/test_sequential.py -v` exits 0 with all tests passing
- Test `test_golden_delay_fixed_3` asserts byte-for-byte match against `tests/golden/sva_delay_3_3.sv`
- Test `test_golden_delay_range_2_5` asserts byte-for-byte match against `tests/golden/sva_delay_2_5.sv`
- Test `test_codegen_deterministic_delay` compiles the same fixture multiple times and asserts identical output
- Test `test_attempt_fired_in_all_modules` verifies "attempt_fired" string in every emitted module
- Test `test_overflow_flag_in_implication_modules` verifies "overflow_flag" in implication module output
- All tests use the `_assert_golden_match` helper for consistent diff reporting
</acceptance_criteria>
</task>

<task id="2.3.3">
<title>[REVIEW FIX] Concurrent-attempt stress tests including reset-during-active-threads</title>
<read_first>
- tests/test_sequential.py (after task 2.3.2)
- templates/overlap_bitvec.sv.j2 (after Plan 2.2)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-05, D-06, D-07)
- .planning/REQUIREMENTS.md (TEST-05 definition)
</read_first>
<action>
Add stress tests to `tests/test_sequential.py` (or create separate `tests/test_stress.py`):

1. `test_bv_width_sufficient_for_max_concurrent()`:
   - For `a |-> ##[2:5] b`: bv_width should be 6 (max_delay=5, width=5+1=6)
   - Compile fixture, assert int(params["bv_width"]) >= consequent max length + 1
   - Parametrize over multiple consequent patterns

2. `test_overflow_flag_not_set_within_capacity()`:
   - Construct a scenario: BV_WIDTH=6, antecedent fires 6 consecutive cycles
   - Verify structural correctness: the generated RTL has BV_WIDTH parameter >= 6
   - This is a compile-time structural test (runtime simulation deferred to Phase 3)

3. `test_overflow_flag_structure_present()`:
   - Compile `a |-> ##[2:5] b`
   - Assert the generated RTL contains: overflow detection conditional, halt state logic, sticky flag logic
   - Verify strings: "overflow_flag" appears, register reset includes overflow_flag, halt gating logic exists

4. `test_concurrent_threads_structural_capacity()`:
   - For `a |-> ##8 b`: bv_width should be >= 9 (max_delay=8, width=8+1=9)
   - For `a |-> ##1 b`: bv_width should be >= 2 (max_delay=1, width=1+1=2)
   - For `a |-> ##[0:15] b`: bv_width should be >= 16 (max_delay=15, width=15+1=16)
   - Parametrize over multiple delay configurations

5. `test_overflow_halt_prevents_output()`:
   - Verify the template contains logic that gates active/pass/fail to 0 when overflow_flag is set
   - String assertion: check for overflow_flag-conditioned output gating in emitted RTL

6. [REVIEW FIX] `test_reset_during_active_threads()` (HIGH concern #6):
   - Verify structural reset behavior: the generated RTL clears ALL state on rst_n
   - Assert the always_ff block contains: `bv_q <= '0` (or equivalent) in the rst_n branch
   - Assert `overflow_flag <= 1'b0` in the rst_n branch
   - Assert `ant_pass_delayed_q <= 1'b0` in the rst_n branch (for nonoverlap)
   - Document expected behavior: "rst_n asserts while threads active -> all state clears atomically in one cycle, no residual thread state"
   - Verify no conditional logic gates the reset (reset is unconditional on all registers)
</action>
<acceptance_criteria>
- Test `test_bv_width_sufficient_for_max_concurrent` passes: bv_width >= max_delay + 1
- Test `test_overflow_flag_structure_present` passes: emitted RTL contains overflow detection logic
- Test `test_concurrent_threads_structural_capacity` parametrized over [(8,9), (1,2), (15,16)] verifies bv_width >= each value
- Test `test_overflow_halt_prevents_output` passes: emitted RTL contains halt/gating logic
- [REVIEW FIX] Test `test_reset_during_active_threads` passes: rst_n branch clears bv_q, overflow_flag, and all state registers unconditionally
- All tests in `pytest tests/test_sequential.py` (or test_stress.py) exit 0
- Tests document TEST-05 requirement in docstrings
</acceptance_criteria>
</task>

<task id="2.3.4">
<title>Boundary tests for delay operators</title>
<read_first>
- tests/test_sequential.py (after tasks 2.3.2, 2.3.3)
- templates/concat_delay.sv.j2 (after Plan 2.1)
- .planning/REQUIREMENTS.md (TEST-06 definition: test at N-1, N, M, M+1)
</read_first>
<action>
Add boundary tests to `tests/test_sequential.py`:

1. `test_delay_cnt_width_boundary_values()`:
   - ##1: cnt_width=1 (ceil(log2(2))=1)
   - ##2: cnt_width=2 (ceil(log2(3))=2)
   - ##3: cnt_width=2 (ceil(log2(4))=2)
   - ##4: cnt_width=3 (ceil(log2(5))=3)
   - ##7: cnt_width=3 (ceil(log2(8))=3)
   - ##8: cnt_width=4 (ceil(log2(9))=4)
   - ##15: cnt_width=4 (ceil(log2(16))=4)
   - ##16: cnt_width=5 (ceil(log2(17))=5)
   - ##100: cnt_width=7 (ceil(log2(101))=7)
   - Parametrize with pytest.mark.parametrize over (delay, expected_width) tuples

2. `test_delay_window_comparator_boundaries()`:
   - For ##[2:5]: emitted RTL contains comparison against 2 and 5
   - For ##[0:1]: emitted RTL contains comparison against 0 and 1
   - For ##3 (as ##[3:3]): emitted RTL contains equality check (count_q >= 3) && (count_q <= 3)
   - Verify the actual parameter values in emitted template output

3. `test_delay_zero_special_case()`:
   - ##0 or ##[0:0]: delay_min=0 and delay_max=0
   - The template should handle this as combinational pass-through (pass on start cycle)
   - Verify emitted RTL contains `assign pass = start` (combinational, no counter)
   - Verify emitted RTL does NOT contain `always_ff` in the ##0 case (or if it does, counter logic is gated off)

4. `test_delay_single_cycle_fixed()`:
   - ##1: pass should be a single-cycle pulse (window width 1)
   - Verify delay_min == delay_max == 1 in params

5. `test_delay_range_window_width()`:
   - ##[2:5]: window width is 4 cycles (passes at cycles 2, 3, 4, 5)
   - Verify structural parameters: delay_min=2, delay_max=5
   - ##[0:15]: window width is 16 cycles
   - Verify structural parameters: delay_min=0, delay_max=15

6. `test_bv_width_boundary_for_implication()`:
   - `a |-> b` (single-cycle consequent): bv_width == 1
   - `a |-> ##1 b`: bv_width == 2
   - `a |-> ##[0:1] b`: bv_width == 2
   - `a |-> ##[2:5] b`: bv_width == 6
   - `a |-> ##[0:15] b`: bv_width == 16
</action>
<acceptance_criteria>
- All parametrized tests in `test_delay_cnt_width_boundary_values` pass for values: (1,1), (2,2), (3,2), (4,3), (7,3), (8,4), (15,4), (16,5), (100,7)
- Test `test_delay_window_comparator_boundaries` verifies window parameters appear in emitted RTL
- Test `test_delay_zero_special_case` handles ##0 correctly: contains `assign pass = start`
- Test `test_delay_range_window_width` verifies delay_min and delay_max params for range delays
- Test `test_bv_width_boundary_for_implication` verifies bv_width values per the formal algorithm
- All tests reference TEST-06 requirement in their docstrings
- `pytest tests/test_sequential.py` exits 0
</acceptance_criteria>
</task>

<task id="2.3.5">
<title>[REVIEW FIX] Create behavioral reference oracle for semantic validation</title>
<read_first>
- src/sva2rtl/ir.py (SVANode, SeqConcat, PropImplication, BoolExpr definitions)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-03, D-05)
- .planning/REQUIREMENTS.md (TEST-02, TEST-05, TEST-06)
</read_first>
<action>
[REVIEW FIX] Create `src/sva2rtl/behavioral_oracle.py` (HIGH concern #5):

A minimal Python class that models SVA sequential operator semantics cycle-by-cycle. Used as test oracle to validate that our generated RTL architecture would produce correct pass/fail outputs.

1. Create class `SVABehavioralSim`:
   - Constructor takes operator specification: `kind` (one of "delay_fixed", "delay_range", "implication_overlap", "implication_nonoverlap"), `params` dict (delay_min, delay_max, bv_width)
   - Method `reset()`: clear all internal state
   - Method `tick(signals: dict[str, bool]) -> dict[str, bool]`: advance one cycle
     - Input: signal values for this cycle (e.g., {"start": True, "con_pass": False})
     - Output: {"active": bool, "pass": bool, "fail": bool, "overflow": bool}
   - Maintains internal state: counter value, running flag, bit-vector (as Python int)

2. Implement `##N` / `##[M:N]` model:
   - State: `counter: int`, `running: bool`
   - On `start=True`: set counter=0, running=True
   - Each tick while running: counter += 1
   - `pass` = running AND (counter >= delay_min) AND (counter <= delay_max)
   - `active` = running AND (counter <= delay_max)
   - Special case ##0: `pass` = `start` (same cycle, combinational)

3. Implement `|->` model (overlapping):
   - State: `bv: int` (Python integer used as bit-vector), `overflow_flag: bool`
   - On `ant_pass=True` AND NOT overflow: insert bit at position 0 (bv |= 1)
   - Each tick: shift bv right by 1 (bv >>= 1, with new bit inserted before shift)
   - Actually: `bv = ((ant_pass & ~overflow) << 0) | (bv >> 1)` -- but track correctly
   - More precisely: `new_bv = (bv << 1) | (1 if ant_pass and not overflow else 0)` -- shift LEFT (age bits move to higher positions)
   - `pass` = bit at evaluation position is set AND con_pass
   - `fail` = bit at evaluation position is set AND NOT con_pass, OR overflow event
   - Overflow: ant_pass AND bv is full (all bv_width bits set)
   - On overflow: freeze state, gate outputs

4. Implement `|=>` model (non-overlapping):
   - Same as `|->` but antecedent pass is delayed by 1 cycle before insertion

5. Create `tests/test_behavioral_oracle.py`:
   - `test_oracle_delay_fixed_3()`: stimulus with start at cycle 0, verify pass at cycle 3
   - `test_oracle_delay_range_2_5()`: verify pass from cycle 2 through cycle 5
   - `test_oracle_delay_zero()`: verify pass on same cycle as start
   - `test_oracle_implication_overlap_simple()`: ant fires, verify consequent evaluated same cycle
   - `test_oracle_implication_nonoverlap_simple()`: ant fires, verify consequent evaluated next cycle
   - `test_oracle_overflow_halts()`: fill bit-vector, fire one more ant -> verify overflow, outputs frozen
   - [REVIEW FIX] `test_oracle_reset_clears_all_state()`: run some threads, call reset(), verify all state zeroed and no residual output
</action>
<acceptance_criteria>
- File `src/sva2rtl/behavioral_oracle.py` exists
- Class `SVABehavioralSim` is importable from `sva2rtl.behavioral_oracle`
- `SVABehavioralSim` has methods: `__init__`, `reset`, `tick`
- `tick()` returns dict with keys "active", "pass", "fail", "overflow"
- File `tests/test_behavioral_oracle.py` exists
- [REVIEW FIX] `test_oracle_delay_fixed_3` passes: start at cycle 0 -> pass at cycle 3 only
- [REVIEW FIX] `test_oracle_delay_range_2_5` passes: start at cycle 0 -> pass at cycles 2,3,4,5
- [REVIEW FIX] `test_oracle_delay_zero` passes: start and pass on same cycle
- [REVIEW FIX] `test_oracle_overflow_halts` passes: overflow -> all subsequent outputs gated
- [REVIEW FIX] `test_oracle_reset_clears_all_state` passes: reset -> zero state, no output
- `mypy --strict src/sva2rtl/behavioral_oracle.py` exits 0
- `pytest tests/test_behavioral_oracle.py` exits 0
</acceptance_criteria>
</task>

<task id="2.3.6">
<title>[REVIEW FIX] Full regression, integration validation, and Verilator lint gate</title>
<read_first>
- tests/test_sequential.py (after tasks 2.3.2-2.3.4)
- tests/test_integration.py (existing Phase 1 integration tests)
- tests/test_pipeline_e2e.py (existing Phase 1 end-to-end tests)
- tests/test_ast_importer.py (after Plans 2.1, 2.2)
- tests/test_composer.py (after Plans 2.1, 2.2)
- tests/test_emitter.py (after Plans 2.1, 2.2)
</read_first>
<action>
Final integration validation:

1. Add to `tests/test_sequential.py`:
   - `test_phase1_bool_still_works()`: compile bool_simple.json fixture -> assert returns BoolExpr, compose succeeds, emit produces valid SV with "module sva_"
   - `test_phase1_golden_unchanged()`: emit bool_labeled checker -> compare against golden/bool_labeled.sv (byte-for-byte unchanged)

2. Add end-to-end tests using programmatic pipeline:
   - `test_e2e_delay_fixed_compiles()`: load delay_fixed.json -> full pipeline -> verify all modules in emit_all output compile (contain "module" and "endmodule")
   - `test_e2e_implication_overlap_compiles()`: same for implication_overlap.json
   - `test_e2e_complex_impl_delay()`: test `a |-> ##[2:5] b` (PropImplication with SeqConcat consequent) — verify hierarchical module tree

3. Add structural soundness tests:
   - `test_all_modules_have_standard_ports()`: for each emitted module in a hierarchical output, verify strings "clk", "rst_n", "start", "active", "pass", "fail" appear
   - `test_all_modules_have_sync_reset()`: every module contains "if (!rst_n)"
   - `test_no_duplicate_module_names()`: emit_all keys are all unique

4. [REVIEW FIX] Verilator lint gate (MEDIUM concern #8):
   - Add test `test_verilator_lint_clean()` (marked with `@pytest.mark.skipif` if verilator not installed):
     - Compile each Phase 2 operator fixture through the full pipeline
     - Write output to a temp directory
     - Run `verilator --lint-only -Wall <output_dir>/*.sv`
     - Assert exit code 0 (no warnings, no errors)
   - Document in verification section: `verilator --lint-only output/*.sv` is a required CI step
   - This catches: undeclared signals, width mismatches, undriven nets, unused signals

5. Run full test suite command validation:
   - Document that `pytest tests/ -v` must exit 0
   - Document that `mypy --strict src/sva2rtl/` must exit 0
   - Document that `ruff check src/ tests/` must exit 0
</action>
<acceptance_criteria>
- `pytest tests/ -v` exits 0 with ALL tests passing (Phase 1 + Phase 2)
- `mypy --strict src/sva2rtl/` exits 0
- `ruff check src/ tests/` exits 0
- Test `test_phase1_golden_unchanged` confirms bool_labeled.sv golden is byte-for-byte identical
- Test `test_all_modules_have_standard_ports` passes for all emitted modules
- Test `test_all_modules_have_sync_reset` passes for all emitted modules
- Test `test_e2e_complex_impl_delay` successfully compiles `a |-> ##[2:5] b` through the full pipeline
- [REVIEW FIX] Test `test_verilator_lint_clean` exists and passes when verilator is available (skipped gracefully when not)
- No Phase 1 tests are broken or skipped
- Total test count increases from 131 (Phase 1) to at least 175 (Phase 2 adds 44+ tests including oracle tests)
</acceptance_criteria>
</task>

---

## Threat Model

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Golden files become stale after template changes (false test passes) | Medium | Golden files are regenerated from templates during task 2.1.6 and 2.2.5. Each test explicitly compares against the golden. CI would catch mismatches. |
| Stress tests only verify structure, not runtime behavior | Medium | [REVIEW FIX] Behavioral oracle (task 2.3.5) provides semantic correctness validation. Phase 3 adds Icarus Verilog simulation. Combined: structure + oracle + simulation = full coverage. |
| Boundary test misses an edge case (off-by-one) | Medium | Parametrized tests cover powers-of-2 boundaries (1,2,4,8,16) and adjacent values. Oracle validates exact cycle timing. Combined with Phase 3 simulation. |
| Regression in Phase 1 tests due to ast_importer changes | Low | Explicit regression test (test_phase1_golden_unchanged) ensures backward compatibility. |
| [REVIEW FIX] Generated RTL has lint warnings (synthesis tool rejects) | Medium | Verilator lint gate catches undeclared signals, width mismatches, undriven nets before they reach FPGA tools. |
| [REVIEW FIX] Reset during active threads leaves residual state | High | Explicit test verifies unconditional reset in always_ff block. Oracle validates reset behavior. Template design review ensures no conditional reset logic. |
</threat_model>

---

## Verification

```bash
# Full test suite
pytest tests/ -v --tb=short

# Type checking
mypy --strict src/sva2rtl/

# Lint
ruff check src/ tests/

# [REVIEW FIX] Verilator lint gate (CI step)
verilator --lint-only -Wall tests/golden/*.sv 2>&1 | grep -c "Error\|Warning" | xargs test 0 -eq

# Verify test count increased
pytest tests/ --co -q | tail -1
# Expected: "175+ tests collected"

# Verify Phase 1 regression
pytest tests/test_integration.py tests/test_pipeline_e2e.py -v

# [REVIEW FIX] Behavioral oracle validation
pytest tests/test_behavioral_oracle.py -v
```

---

## Must-Haves (Goal-Backward Verification)

- [ ] Golden file integration tests exist for all Phase 2 operators (TEST-02)
- [ ] Golden outputs are deterministic across repeated runs (TEST-02)
- [ ] Concurrent-attempt stress tests verify bv_width >= max_delay + 1 (TEST-05)
- [ ] Overflow detection structure is verified present in generated RTL (TEST-05)
- [ ] Boundary tests cover N-1, N, M, M+1 for counter widths (TEST-06)
- [ ] Boundary tests cover window comparator parameters (TEST-06)
- [ ] `attempt_fired` verified present in all generated modules (OUT-06)
- [ ] `overflow_flag` verified present in implication modules (OUT-06)
- [ ] All Phase 1 tests pass unchanged (no regression)
- [ ] mypy --strict and ruff check pass on entire codebase
- [ ] [REVIEW FIX] Behavioral oracle exists and validates ##N, ##[M:N], |-> , |=> semantics
- [ ] [REVIEW FIX] Oracle tests cover: fixed delay, range delay, zero delay, overlap, nonoverlap, overflow halt, reset
- [ ] [REVIEW FIX] Reset-during-active-threads test verifies atomic state clear
- [ ] [REVIEW FIX] Verilator lint gate passes on all generated RTL (zero warnings)
