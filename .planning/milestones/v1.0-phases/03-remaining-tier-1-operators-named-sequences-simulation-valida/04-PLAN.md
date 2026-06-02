---
wave: 3
depends_on:
  - "01"
  - "02"
  - "03"
files_modified:
  - tests/simulation/__init__.py
  - tests/simulation/conftest.py
  - tests/simulation/test_sim_rose.py
  - tests/simulation/test_sim_fell.py
  - tests/simulation/test_sim_stable.py
  - tests/simulation/test_sim_past.py
  - tests/simulation/test_sim_repetition.py
  - tests/simulation/test_sim_disable_iff.py
  - tests/simulation/test_sim_delay.py
  - tests/simulation/test_sim_implication.py
  - tests/simulation/tb_generator.py
  - tests/conftest.py
  - src/sva2rtl/behavioral_oracle.py
autonomous: true
requirements:
  - TEST-03
  - TEST-04
---

# Plan 3.4: Simulation Validation Harness (TEST-03, TEST-04)

## Summary

Deliver the dual-layer simulation validation oracle: (1) Python behavioral model validates cycle-by-cycle semantics for all Tier 1 operators; (2) Icarus Verilog co-simulation cross-checks generated RTL against the Python oracle. Both layers use the same stimulus traces. Tests use `@pytest.mark.simulation` and gracefully skip when `iverilog` is not installed locally.

## Vertical Slice

For each Tier 1 operator: generate stimulus trace -> run Python oracle -> produce expected outputs -> compile generated RTL with iverilog -> simulate with vvp -> parse VCD/text output -> compare cycle-by-cycle with Python oracle results. Any mismatch = test failure with cycle-precise diff.

<threat_model>
- **Simulator divergence:** Python oracle might model different registered-output delay than RTL. Mitigated: oracle explicitly models the 1-cycle registration delay matching the `always_ff` pattern.
- **Testbench timing mismatch:** Sampling at wrong clock edge could shift outputs by 1 cycle. Mitigated: testbench uses `@(posedge clk)` synchronous sampling matching the monitor's clock.
- **Non-deterministic test failures:** Random Hypothesis traces could be flaky. Mitigated: seed is fixed per test; failures are reproducible.
- **iverilog version differences:** Different iverilog versions might parse SV differently. Mitigated: use `-g2012` flag; test fixtures use only basic SV constructs.
- **Severity:** All LOW. No high-severity threats. Simulation validation is a quality gate, not a security surface.
</threat_model>

## Tasks

<task id="3.4.1">
<title>Create simulation test infrastructure and conftest</title>
<read_first>
- tests/conftest.py
- src/sva2rtl/behavioral_oracle.py
- .planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-RESEARCH.md (Section 7)
</read_first>
<action>
1. Create `tests/simulation/` directory with `__init__.py`.
2. Create `tests/simulation/conftest.py`:
   - Register `simulation` pytest marker
   - Add `autouse` fixture `check_iverilog` that calls `shutil.which("iverilog")` — if None, `pytest.skip("iverilog not installed; install with: brew install icarus-verilog")`
   - Add shared fixtures: `tmp_sim_dir(tmp_path)` that returns a clean temp dir for simulation artifacts
3. Update `tests/conftest.py` (root):
   - Register the `simulation` marker in `pytest_configure` if not already done: `config.addinivalue_line("markers", "simulation: marks tests requiring iverilog (deselect with '-m not simulation'")`
4. Create `tests/simulation/tb_generator.py` — testbench generation utility:
   - `generate_testbench(monitor_sv: str, module_name: str, signals: list[tuple[str,str]], stimulus: list[dict[str, bool]], clock_signal: str = "clk") -> str`
   - Generates a Verilog testbench with: clock generation (`always #5 clk = ~clk`), reset sequence, signal driving from stimulus list, output capture via `$fdisplay` to `sim_output.txt`
   - Output format per cycle: `cycle_num pass fail active`
   - `parse_sim_output(path: Path) -> list[dict[str, bool]]` — reads `sim_output.txt` and returns list of dicts with keys pass/fail/active per cycle
   - `compile_and_run(monitor_files: list[Path], tb_file: Path, output_dir: Path) -> Path` — calls `iverilog -g2012 -o sim.vvp ...` then `vvp sim.vvp`, returns path to sim_output.txt
</action>
<acceptance_criteria>
- Directory `tests/simulation/` exists with `__init__.py` and `conftest.py`
- `conftest.py` skips tests when `iverilog` not found (verified by mock)
- `tb_generator.py` contains `generate_testbench`, `parse_sim_output`, `compile_and_run` functions
- `generate_testbench` produces valid Verilog with `module tb;`, clock, reset, stimulus, `$fopen`/`$fdisplay`
- `parse_sim_output` correctly parses "0 1 0 1
1 0 0 0
" format into list of dicts
- Root `conftest.py` registers `simulation` marker
- `mypy --strict tests/simulation/tb_generator.py` exits 0
</acceptance_criteria>
</task>

<task id="3.4.2">
<title>Create simulation tests for signal functions (rose, fell, stable, past)</title>
<read_first>
- tests/simulation/tb_generator.py
- tests/simulation/conftest.py
- src/sva2rtl/behavioral_oracle.py
- src/sva2rtl/composer.py
- src/sva2rtl/emitter.py
</read_first>
<action>
1. Create `tests/simulation/test_sim_rose.py`:
   - `@pytest.mark.simulation` on class
   - `test_rose_0_to_1()`: stimulus [0,1,1,0,1] -> Python oracle -> iverilog sim -> compare. Assert pass fires exactly on 0->1 transitions.
   - `test_rose_sustained_high()`: stimulus [1,1,1,1] -> no pass after first tick
   - `test_rose_random(hypothesis)`: random boolean trace, compare Python vs RTL

2. Create `tests/simulation/test_sim_fell.py`:
   - `test_fell_1_to_0()`: stimulus [1,0,0,1,0] -> pass on 1->0 transitions
   - `test_fell_sustained_low()`: stimulus [0,0,0,0] -> no pass
   - `test_fell_random(hypothesis)`: random trace comparison

3. Create `tests/simulation/test_sim_stable.py`:
   - `test_stable_no_change()`: stimulus [1,1,1] -> pass on ticks where value unchanged
   - `test_stable_change()`: stimulus [0,1,0] -> fail on change ticks
   - `test_stable_random(hypothesis)`: random trace comparison

4. Create `tests/simulation/test_sim_past.py`:
   - `test_past_depth_1()`: verify 1-cycle delay of signal
   - `test_past_depth_3()`: verify 3-cycle delay
   - `test_past_random(hypothesis)`: random trace, verify shifted output

Each test: (a) compile monitor via pipeline, (b) generate testbench with stimulus, (c) compile+run iverilog, (d) compare output with Python behavioral oracle.
</action>
<acceptance_criteria>
- `pytest tests/simulation/test_sim_rose.py tests/simulation/test_sim_fell.py tests/simulation/test_sim_stable.py tests/simulation/test_sim_past.py -v -m simulation` exits 0 (when iverilog available) or all skip gracefully (when not)
- At least 3 test functions per file (golden + random)
- Hypothesis tests use `@given(trace=st.lists(st.booleans(), min_size=5, max_size=30))` with `@settings(max_examples=50)`
- Tests use `tb_generator.compile_and_run` and `parse_sim_output` utilities
- `mypy --strict tests/simulation/test_sim_rose.py` exits 0
</acceptance_criteria>
</task>

<task id="3.4.3">
<title>Create simulation tests for consecutive repetition</title>
<read_first>
- tests/simulation/tb_generator.py
- src/sva2rtl/behavioral_oracle.py
- templates/rep_consecutive.sv.j2
</read_first>
<action>
Create `tests/simulation/test_sim_repetition.py`:
- `@pytest.mark.simulation` on class
- `test_rep_fixed_3_exact()`: signal true for exactly 3 cycles -> pass on cycle 3
- `test_rep_fixed_3_early_fail()`: signal true for 2 then false -> fail on cycle 3
- `test_rep_fixed_3_longer()`: signal true for 5 cycles -> pass on cycle 3 (and stays?)
- `test_rep_range_2_5_min()`: signal true for exactly 2 cycles -> pass
- `test_rep_range_2_5_max()`: signal true for exactly 5 cycles -> pass
- `test_rep_range_2_5_below()`: signal true for 1 cycle then false -> fail
- `test_rep_random(hypothesis)`: random boolean trace with random rep_min/rep_max params, compare Python oracle vs RTL

Each test generates the monitor via full pipeline (fixture -> import -> compose -> emit), generates testbench, compiles with iverilog, runs simulation, compares against Python behavioral oracle output.
</action>
<acceptance_criteria>
- `pytest tests/simulation/test_sim_repetition.py -v -m simulation` exits 0 (or all skip)
- At least 6 golden test functions + 1 hypothesis test
- Tests verify exact cycle where pass/fail fires (cycle-precise)
- Boundary tests at rep_min-1, rep_min, rep_max, rep_max+1 cycles
- `mypy --strict tests/simulation/test_sim_repetition.py` exits 0
</acceptance_criteria>
</task>

<task id="3.4.4">
<title>Create simulation tests for disable iff</title>
<read_first>
- tests/simulation/tb_generator.py
- src/sva2rtl/behavioral_oracle.py
- templates/disable_iff_top.sv.j2
</read_first>
<action>
Create `tests/simulation/test_sim_disable_iff.py`:
- `@pytest.mark.simulation` on class
- `test_disable_suppresses_fail()`: start a sequence, assert disable mid-sequence -> verify NO fail fires on the disable cycle or after
- `test_disable_before_start()`: disable is high before start -> verify no pass/fail/active while disabled
- `test_disable_clears_state()`: start sequence, assert disable, de-assert disable, restart sequence -> verify fresh evaluation (no stale state)
- `test_no_spurious_on_disable_edge()`: sequence would normally pass this cycle, but disable asserts same cycle -> verify pass=0 (combinational gating)
- `test_disabled_output_indicator()`: verify disabled_o matches the disable condition each cycle
- `test_disable_random(hypothesis)`: random trace with random disable assertions

**Critical test (from D-09):** The "no spurious failure" test must verify that when disable asserts on the SAME cycle as a would-be fail event, fail output is 0 (not 1 then 0 next cycle).
</action>
<acceptance_criteria>
- `pytest tests/simulation/test_sim_disable_iff.py -v -m simulation` exits 0 (or all skip)
- At least 5 golden test functions + 1 hypothesis test
- `test_no_spurious_on_disable_edge` explicitly verifies pass=0 AND fail=0 on the disable-assertion cycle
- `test_disable_clears_state` verifies all internal state resets (counter at 0 after disable cycle)
- `mypy --strict tests/simulation/test_sim_disable_iff.py` exits 0
</acceptance_criteria>
</task>

<task id="3.4.5">
<title>Create simulation tests for Phase 2 operators (delay, implication)</title>
<read_first>
- tests/simulation/tb_generator.py
- src/sva2rtl/behavioral_oracle.py
- templates/concat_delay.sv.j2
- templates/overlap_bitvec.sv.j2
</read_first>
<action>
Create `tests/simulation/test_sim_delay.py`:
- `test_delay_fixed_3()`: start pulse, verify pass fires exactly at cycle 3
- `test_delay_range_2_5()`: start pulse, verify pass fires at cycles 2 through 5
- `test_delay_zero()`: start pulse, verify immediate pass (##0 combinational)

Create `tests/simulation/test_sim_implication.py`:
- `test_overlap_simple()`: antecedent match -> consequent evaluated same cycle
- `test_nonoverlap_simple()`: antecedent match -> consequent evaluated next cycle
- `test_overlap_concurrent_threads()`: antecedent fires 3 consecutive cycles, verify all 3 threads tracked independently
- `test_overflow_detection()`: saturate bit-vector, verify overflow_flag latches

These tests validate that the UPDATED templates (with disable_i/disabled_o) still produce correct behavior when disable_i=1'b0.
</action>
<acceptance_criteria>
- `pytest tests/simulation/test_sim_delay.py tests/simulation/test_sim_implication.py -v -m simulation` exits 0 (or all skip)
- At least 3 tests per file
- Delay tests verify cycle-precise pass timing
- Implication tests verify concurrent thread tracking
- All use the updated templates (with disable_i port) and pass disable_i=1'b0
- `mypy --strict tests/simulation/test_sim_delay.py tests/simulation/test_sim_implication.py` exits 0
</acceptance_criteria>
</task>

<task id="3.4.6">
<title>Add behavioral oracle extensions for disable_iff and integrate</title>
<read_first>
- src/sva2rtl/behavioral_oracle.py
- tests/simulation/tb_generator.py
</read_first>
<action>
1. Extend `SVABehavioralSim` to support a `disable` input signal in the tick interface:
   - Add optional `"disable"` key to the signals dict in `tick()`
   - When `disable=True`: return `{"active": False, "pass": False, "fail": False, "overflow": False}` immediately (same-cycle suppression)
   - When `disable` transitions to True: reset all internal state (counter, running, bv, etc.) — models the `!rst_n | disable_i` behavior
2. All existing `_tick_*` methods check disable FIRST before normal logic.
3. Ensure backward compatibility: when `"disable"` key is absent from signals, behavior is identical to before (no disable).
4. Add to the oracle: ability to compose two oracle instances (e.g., implication = antecedent oracle + consequent oracle + thread tracker). This enables the simulation tests to use a single oracle call per cycle for compound operators.
</action>
<acceptance_criteria>
- `SVABehavioralSim("delay_fixed", {"delay_min": 3, "delay_max": 3}).tick({"start": True, "disable": True})` returns all-False outputs
- Existing tests that don't pass `"disable"` key still work (backward compatible)
- After `disable=True` tick, internal state is reset (next tick with `disable=False` starts fresh)
- `mypy --strict src/sva2rtl/behavioral_oracle.py` exits 0
- All existing behavioral oracle tests still pass
</acceptance_criteria>
</task>

## Verification

```bash
# Run simulation tests (skip gracefully if no iverilog)
pytest tests/simulation/ -v -m simulation

# Run non-simulation tests (always pass)
pytest tests/ -v -m "not simulation"

# Run everything
pytest tests/ -v

# Type checking
mypy --strict src/sva2rtl/behavioral_oracle.py tests/simulation/

# Linting
ruff check tests/simulation/
```

## must_haves

- [ ] `tests/simulation/` directory with infrastructure (conftest, tb_generator)
- [ ] Testbench generator produces valid Verilog compilable by iverilog
- [ ] Simulation tests for ALL Tier 1 operators: rose, fell, stable, past, rep, disable_iff, delay, implication
- [ ] Python behavioral oracle matches RTL simulation cycle-by-cycle for all test cases
- [ ] Tests gracefully skip when iverilog not available (no hard failure)
- [ ] Hypothesis property-based tests for random trace fuzzing
- [ ] disable_iff simulation verifies no-spurious-failure on disable cycle
- [ ] All non-simulation tests still pass (no regressions)
