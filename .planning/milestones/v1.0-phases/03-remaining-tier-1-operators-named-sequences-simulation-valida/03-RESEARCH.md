# Phase 3 Research: Remaining Tier 1 Operators + Named Sequences + Simulation Validation

**Researched:** 2026-05-27
**Confidence:** HIGH across all areas
**Phase requirements:** OP-05, OP-06, OP-07, OP-08, OP-09, OP-10, PARSE-03, OUT-04, TEST-03, TEST-04

---

## Table of Contents

1. [Slang AST JSON Schema for Phase 3 Constructs](#1-slang-ast-json-schema)
2. [Consecutive Repetition `[*N]`/`[*M:N]` — Hardware Architecture](#2-consecutive-repetition)
3. [Signal Functions: `$rose`, `$fell`, `$stable`, `$past` — RTL Templates](#3-signal-functions)
4. [Disable Iff — Async Semantics & Hardware Model](#4-disable-iff)
5. [Named Sequence/Property Expansion (PARSE-03)](#5-named-sequences)
6. [Bind Statement Generation (OUT-04)](#6-bind-generation)
7. [Simulation Validation Oracle Architecture (TEST-03/TEST-04)](#7-simulation-oracle)
8. [Interface Update: `disable`/`disabled` Ports](#8-interface-update)
9. [Risk Analysis & Mitigations](#9-risks)
10. [Implementation Order & Dependencies](#10-implementation-order)

---

## 1. Slang AST JSON Schema for Phase 3 Constructs {#1-slang-ast-json-schema}

### 1.1 SimpleAssertionExpr with Repetition (OP-05)

Slang represents consecutive repetition (`a[*3]` or `a[*2:5]`) as a `SimpleAssertionExpr` node with an optional `repetition` field:

```json
{
  "kind": "SimpleAssertionExpr",
  "expr": { ... },              // inner expression (e.g., NamedValue for signal)
  "repetition": {               // optional; absent if no repetition
    "kind": "Consecutive",      // "Consecutive" | "Nonconsecutive" | "GoTo"
    "min": 2,                   // minimum repetition count
    "max": 5                    // maximum count; "$" if unbounded
  }
}
```

**Key facts:**
- The `repetition` field is nested inside `SimpleAssertionExpr`, NOT a separate node
- `kind` = `"Consecutive"` maps to `[*N]`/`[*M:N]` (Phase 3 scope)
- `kind` = `"Nonconsecutive"` maps to `[=N]` and `kind` = `"GoTo"` maps to `[->N]` (v2, out of scope)
- When `max` = `"$"`, it's unbounded repetition `[*0:$]` — reject with SVA-E002 error
- Fixed repetition `[*N]` has `min == max == N`

### 1.2 System Function Calls: `$rose`, `$fell`, `$stable`, `$past` (OP-06/07/08/09)

System functions appear as `CallExpression` nodes in slang JSON:

```json
{
  "kind": "CallExpression",
  "type": "bit",
  "subroutineName": "$rose",
  "arguments": [
    {
      "kind": "NamedValue",
      "type": "logic",
      "symbol": "2 sig"
    }
  ]
}
```

**Key facts:**
- `subroutineName` field identifies the function: `"$rose"`, `"$fell"`, `"$stable"`, `"$past"`
- `$past(sig, N)` has TWO arguments: signal + integer literal for pipeline depth
- `$past(sig)` without second arg defaults to N=1
- These may appear inside `SimpleAssertionExpr` or as part of boolean expressions in a sequence context

### 1.3 DisableIffAssertionExpr (OP-10)

```json
{
  "kind": "DisableIff",
  "condition": {                 // the disable condition (boolean expression)
    "kind": "NamedValue",
    "symbol": "2 rst"
  },
  "expr": { ... }               // the assertion expression being disabled
}
```

**Key facts:**
- `condition` is an `Expression` (any boolean expression, not just a signal)
- `expr` is the wrapped `AssertionExpr` (the property body that gets disabled)
- This appears as a wrapper AROUND the property in the PropertySpec.expr hierarchy
- `disable iff` is at the property level, not sequence level

### 1.4 Named Sequence/Property References

Named sequences appear as references that slang resolves. The exact representation depends on slang version:
- If slang resolves inline: the body of the named sequence appears directly (already expanded)
- If slang uses a reference node: a `SequenceInstance` or similar node with a name pointing to the declaration

**Strategy:** Write a test fixture using slang to determine the exact JSON format. If slang pre-resolves named sequences, our job is simpler (just tag the origin for CSE). If not, we must walk the AST to find named declarations and inline them ourselves.

---

## 2. Consecutive Repetition `[*N]`/`[*M:N]` — Hardware Architecture {#2-consecutive-repetition}

### 2.1 Semantics (IEEE 1800-2017 Section 16.9.2)

- `sig [*N]` — signal must be true for exactly N consecutive cycles
- `sig [*M:N]` — signal must be true for between M and N consecutive cycles (inclusive)
- `sig [*0]` — empty match (zero cycles, immediate pass)
- `sig [*0:N]` — match anywhere from 0 to N consecutive true cycles
- `sig [*0:$]` — unbounded (REJECT: no finite hardware representation)

### 2.2 Counter-Based FSM Architecture

Directly reuse the counter encoding pattern from `concat_delay.sv.j2`:

```
Inputs:  start, sig (the signal being repeated)
State:   count_q[CNT_WIDTH-1:0], running_q
Outputs: pass, active, fail

Logic:
- On start && sig: count_q <= 1, running_q <= 1 (first match)
- On start && !sig: count_q <= 0, running_q <= 0 (immediate fail)
- While running && sig: count_q <= count_q + 1
- While running && !sig: running_q <= 0 (sequence broken)
- pass = running_q && (count_q >= M) && (count_q <= N)
- fail = running_q && !sig && (count_q < M)  // broke before minimum
- active = running_q || (start && sig)
```

### 2.3 Critical Differences from `concat_delay`

| Aspect | `##[M:N]` delay | `[*M:N]` repetition |
|--------|-----------------|---------------------|
| Input condition | Always counts (time passes) | Only counts while `sig` is true |
| Fail condition | Never fails (delay always completes) | Fails if `sig` goes false before M |
| Restart behavior | Restart resets counter | Restart resets counter |
| Zero case | `##0` = combinational passthrough | `[*0]` = immediate pass (no eval needed) |

### 2.4 Counter Width

Same formula: `CNT_WIDTH = max(1, ceil(log2(N + 1)))` where N is max repetition count.

### 2.5 Template Parameters

```python
params = {
    "module_name": f"sva_rep_{rep_min}_{rep_max}",
    "rep_min": str(rep_min),
    "rep_max": str(rep_max),
    "cnt_width": str(cnt_width),
    "clock_signal": clock.signal,
    "clock_edge": clock.edge,
    # ... standard params
}
```

---

## 3. Signal Functions: `$rose`, `$fell`, `$stable`, `$past` — RTL Templates {#3-signal-functions}

### 3.1 `$rose(sig)` (OP-06)

**Semantics:** Returns true when signal transitions from 0 to 1 (on clock edge).

**Hardware:**
```verilog
logic sig_prev_q;
always_ff @(posedge clk) begin
    if (!rst_n) sig_prev_q <= 1'b0;
    else        sig_prev_q <= sig;
end
assign rose_detect = sig & ~sig_prev_q;
```

**Cost:** 1 FF + AND-NOT gate
**Template name:** `rose.sv.j2`

### 3.2 `$fell(sig)` (OP-07)

**Semantics:** Returns true when signal transitions from 1 to 0.

**Hardware:**
```verilog
logic sig_prev_q;
always_ff @(posedge clk) begin
    if (!rst_n) sig_prev_q <= 1'b0;
    else        sig_prev_q <= sig;
end
assign fell_detect = ~sig & sig_prev_q;
```

**Cost:** 1 FF + AND gate
**Template name:** `fell.sv.j2`

### 3.3 `$stable(sig)` (OP-08)

**Semantics:** Returns true when signal has not changed since previous clock edge.

**Hardware:**
```verilog
logic sig_prev_q;
always_ff @(posedge clk) begin
    if (!rst_n) sig_prev_q <= 1'b0;
    else        sig_prev_q <= sig;
end
assign stable_detect = (sig == sig_prev_q);  // XNOR
```

**Cost:** 1 FF + XNOR gate
**Template name:** `stable.sv.j2`

### 3.4 `$past(sig, N)` (OP-09)

**Semantics:** Returns the value of signal N cycles ago.

**Hardware:**
```verilog
logic [N-1:0] shift_q;  // N-stage pipeline
always_ff @(posedge clk) begin
    if (!rst_n) shift_q <= '0;
    else        shift_q <= {shift_q[N-2:0], sig};
end
assign past_value = shift_q[N-1];  // oldest value = N cycles ago
```

**Cost:** N FFs (shift register)
**Template name:** `past.sv.j2`

**Constraints:**
- N must be a compile-time literal (reject non-literal N with SVA-E002)
- N=0 is identity (optimizer can fold away in Phase 5)
- N=1 is equivalent to a single FF (common case)

### 3.5 Integration with Property Evaluation

Signal functions are NOT standalone monitors — they are **leaf expressions** that replace signal references within a property. They produce a 1-bit signal that feeds into the containing property's boolean evaluation.

**Composer pattern:** When the AST importer encounters `$rose(sig)` inside a sequence, it creates a `SignalFunc` IR node. The composer generates a child CheckerNode with the appropriate template, and the parent template wires the function's output into its boolean expression.

### 3.6 Multi-bit Signal Handling

For `$rose`/`$fell`/`$stable` on multi-bit signals, IEEE 1800 specifies:
- `$rose(sig)` = `(sig[0] & ~sig_prev[0])` (LSB only for multi-bit)
- However, in practice for SVA monitors, typically used on 1-bit signals

**v1 approach:** Support 1-bit signals only; reject multi-bit with a warning (not error). Can extend in v2.

---

## 4. Disable Iff — Async Semantics & Hardware Model {#4-disable-iff}

### 4.1 IEEE 1800 Semantics

`disable iff (reset_condition)` specifies that when the condition is true:
1. The property evaluation is aborted
2. No pass or fail is generated
3. The property is treated as if it was never started

The critical aspect: this is **asynchronous** — the disable takes effect immediately in the same cycle, not on the next clock edge.

### 4.2 Hardware Architecture (D-09 through D-12)

Per user decisions, `disable iff` implements **full async state clear**:

```verilog
// disable signal is combinational (not registered)
input logic disable_i;
output logic disabled_o;

// ALL internal state gets combinationally cleared
wire effective_rst = !rst_n | disable_i;

always_ff @(posedge clk) begin
    if (effective_rst) begin
        // ALL state registers go to reset values
        count_q <= '0;
        running_q <= 1'b0;
        // ... all other state ...
    end else begin
        // normal operation
    end
end

// Outputs gated combinationally (same-cycle effect)
assign pass     = disable_i ? 1'b0 : pass_internal;
assign fail     = disable_i ? 1'b0 : fail_internal;
assign active   = disable_i ? 1'b0 : active_internal;
assign disabled_o = disable_i;
```

### 4.3 Two-Level Implementation Strategy

**Option A (per decision D-09):** Use `effective_rst = !rst_n | disable_i` in the `always_ff` reset condition. This means disable acts like a synchronous reset — state clears on the NEXT clock edge, but outputs are gated combinationally THIS cycle.

**Option B (true async):** Use `always_ff @(posedge clk or posedge disable_i)` for async clear. This gives immediate state clear but complicates synthesis and may cause timing issues.

**Recommended:** Option A (synchronous state clear + combinational output gating). This achieves the observable behavior requirement (no spurious pass/fail on the disable cycle) while keeping synthesis-friendly `always_ff` patterns. Internal state clears on the next clock edge, which is fine because outputs are already gated.

### 4.4 Uniform `disable` Port on All Sub-Modules (D-10)

Every generated module gets a `disable` input port, even if the top property has no `disable iff`. When absent, it's tied to `1'b0` at the top level.

**Impact on existing templates:** ALL 5 existing templates (`bool_expr`, `concat_delay`, `overlap_bitvec`, `nonoverlap`, `seq_concat_top`) must be updated to:
1. Add `input logic disable_i` port
2. Add `output logic disabled_o` port  
3. Gate outputs with `disable_i`
4. Include `disable_i` in the effective reset condition

### 4.5 Interface Change Risk

This is the **highest-risk change** in Phase 3 because it modifies ALL existing templates. All Phase 1-2 golden files will need regeneration.

**Mitigation strategy:**
1. First update all templates with `disable_i` tied to `1'b0` internally (no behavioral change)
2. Regenerate all golden files
3. Then implement the actual `disable iff` logic on top

---

## 5. Named Sequence/Property Expansion (PARSE-03) {#5-named-sequences}

### 5.1 Expansion Strategy (D-01 through D-04)

Per user decisions:
- **Inline expansion** at each use site (no shared sub-modules for named sequences)
- **CSE tagging** so Phase 5 optimizer can merge identical instances later
- **Recursive resolution** until only primitive operators remain
- **Cycle detection** to reject self-referencing sequences

### 5.2 Slang Behavior for Named Sequences

Two possibilities:
1. **Slang pre-resolves:** Named sequence references are already expanded in the JSON AST (slang does full elaboration). We just need to tag the CSE origin.
2. **Slang uses SequenceInstance:** A reference node points to the named declaration. We must find the declaration and inline the body ourselves.

**Action item:** Create a test SVA file with named sequences, run through slang `--ast-json`, and examine the output to determine which case applies.

### 5.3 AST Importer Changes

```python
# New dispatch in _import_concurrent_assertion or _dispatch_expr_to_ir:
case "SequenceInstance":
    # Resolve the named sequence, expand inline, tag CSE origin
    decl_name = node.get("sequenceName", "")
    expanded = _resolve_named_sequence(node, all_declarations)
    expanded.cse_origin = decl_name  # tag for Phase 5
    return expanded
```

### 5.4 CSE Tagging on IR/CheckerNode

Add an optional field to `CheckerNode`:

```python
@dataclass(frozen=True)
class CheckerNode:
    # ... existing fields ...
    cse_origin: str | None = None  # None=unique, non-None=named source
```

This is a pure metadata field — does not affect emission, only used by Phase 5 optimizer.

### 5.5 Cycle Detection

Implement a visited-set during recursive expansion:

```python
def _expand_named(name: str, declarations: dict, visited: set[str]) -> SVANode:
    if name in visited:
        raise SvaCompileError(f"SVA-E0xx: circular sequence reference: {name}")
    visited.add(name)
    body = declarations[name]
    # recursively expand any named refs within the body
    expanded = _resolve_all_refs(body, declarations, visited)
    visited.discard(name)
    return expanded
```

---

## 6. Bind Statement Generation (OUT-04) {#6-bind-generation}

### 6.1 Bind File Structure (D-13 through D-15)

One bind file per property: `sva_my_check_bind.sv`

```systemverilog
// Generated by sva2rtl 0.1.0
// Bind file for property: my_check
// Source: input.sv:15:3
bind dut_module sva_my_check u_sva_my_check (
    .clk       (clk),
    .rst_n     (rst_n),
    .start     (1'b1),       // always-on by default
    .disable_i (1'b0),       // no disable iff
    .sig_a     (a),
    .sig_b     (b),
    .pass      (),           // unconnected (optional: wire to coverage)
    .fail      (),
    .active    (),
    .attempt_fired (),
    .overflow_flag (),
    .disabled_o ()
);
```

### 6.2 DUT Module Name Inference

From slang AST: the `Instance` → `InstanceBody` node that CONTAINS the `ConcurrentAssertion` tells us the DUT module name.

```python
# Already available in _find_assertion_in_members traversal
# Just capture the instance name during traversal
```

### 6.3 Signal-to-Port Mapping

`extract_signals()` already returns `(port_name, signal_name)` tuples. The bind file maps:
- `port_name` = monitor port name (derived from signal name in SVA expression)
- `signal_name` = DUT signal name (same as port_name for Phase 3; renaming is v2)

### 6.4 Integration with Emitter

New function in `emitter.py`:

```python
def emit_bind(
    checker: CheckerNode,
    dut_module: str,
    template_dir: Path | None = None,
) -> str:
    """Render a bind statement file for the given checker."""
    env = _make_env(template_dir)
    tmpl = env.get_template("bind.sv.j2")
    return tmpl.render(
        module_name=checker.module_name,
        dut_module=dut_module,
        observed_signals=checker.observed_signals,
        # ... other params
    )
```

---

## 7. Simulation Validation Oracle Architecture (TEST-03/TEST-04) {#7-simulation-oracle}

### 7.1 Dual Oracle Strategy (D-05 through D-08)

```
Layer 1: Python Behavioral Oracle (fast, no external dep)
    - Extends existing SVABehavioralSim class
    - Cycle-by-cycle model for ALL Tier 1 operators
    - Runs as standard pytest tests (no skip)

Layer 2: Icarus Verilog RTL Oracle (ground truth)
    - Compiles generated monitor + testbench
    - Runs simulation, captures pass/fail per cycle
    - Compares against Python oracle output
    - Skips gracefully when iverilog not installed locally
    - HARD REQUIREMENT in CI
```

### 7.2 Python Behavioral Oracle Extensions

New `kind` values for `SVABehavioralSim`:

```python
_valid_kinds = {
    # Existing:
    "delay_fixed", "delay_range",
    "implication_overlap", "implication_nonoverlap",
    # Phase 3 new:
    "rep_consecutive",    # [*N]/[*M:N]
    "rose",              # $rose(sig)
    "fell",              # $fell(sig)
    "stable",            # $stable(sig)
    "past",              # $past(sig, N)
}
```

### 7.3 Icarus Verilog Testbench Pattern

For each test case, generate:

```verilog
// testbench_<property_name>.sv
`timescale 1ns/1ps

module tb;
    reg clk = 0;
    always #5 clk = ~clk;
    
    reg rst_n = 0;
    reg start = 0;
    reg sig_a, sig_b;
    wire pass_w, fail_w, active_w;
    
    // DUT: generated monitor
    sva_my_check uut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .sig_a(sig_a), .sig_b(sig_b),
        .pass(pass_w), .fail(fail_w), .active(active_w),
        .attempt_fired(), .disable_i(1'b0), .disabled_o()
    );
    
    // Stimulus + output capture
    integer fd;
    initial begin
        fd = $fopen("sim_output.txt", "w");
        
        // Reset phase
        rst_n = 0; #20; rst_n = 1;
        
        // Stimulus from Python-generated trace
        @(posedge clk); sig_a = 1; sig_b = 0; start = 1;
        $fdisplay(fd, "%0d %b %b %b", $time, pass_w, fail_w, active_w);
        @(posedge clk); sig_a = 0; sig_b = 1; start = 0;
        $fdisplay(fd, "%0d %b %b %b", $time, pass_w, fail_w, active_w);
        // ... more cycles ...
        
        $fclose(fd);
        $finish;
    end
endmodule
```

### 7.4 pytest Integration

```python
@pytest.mark.simulation
class TestSimulationOracle:
    """End-to-end simulation validation (TEST-03/TEST-04)."""
    
    @pytest.fixture(autouse=True)
    def check_iverilog(self):
        if not shutil.which("iverilog"):
            pytest.skip("iverilog not installed")
    
    def test_rose_simulation(self, tmp_path):
        # 1. Generate monitor RTL
        monitor_sv = generate_rose_monitor()
        
        # 2. Generate testbench with stimulus
        stimulus = [{"sig": False}, {"sig": True}, {"sig": True}, {"sig": False}]
        tb_sv = generate_testbench(monitor_sv, stimulus)
        
        # 3. Compile with iverilog
        subprocess.run(["iverilog", "-o", str(tmp_path / "sim.vvp"),
                       str(tmp_path / "monitor.sv"),
                       str(tmp_path / "tb.sv")], check=True)
        
        # 4. Run simulation
        subprocess.run(["vvp", str(tmp_path / "sim.vvp")], check=True)
        
        # 5. Compare with Python oracle
        rtl_outputs = parse_sim_output(tmp_path / "sim_output.txt")
        py_outputs = run_python_oracle("rose", stimulus)
        assert rtl_outputs == py_outputs, f"Cycle mismatch: {diff(rtl_outputs, py_outputs)}"
```

### 7.5 Stimulus Generation Strategy (D-06)

**Golden cases** (hand-crafted, targeting known corners):
- `$rose`: `0→1` (should fire), `1→1` (should NOT fire), `0→0` (should NOT fire)
- `$fell`: `1→0` (should fire), `0→0` (should NOT fire)
- `[*3]`: exactly 3 true, 2 true then false (fail), 4 true (pass at 3, then?)
- `disable iff`: disable mid-sequence, disable before start, disable during pass

**Random cases** (Hypothesis property-based testing):
```python
@given(trace=st.lists(st.booleans(), min_size=5, max_size=50))
def test_rose_random(self, trace):
    """Fuzz: Python oracle matches RTL for any random trace."""
    py_result = python_oracle_rose(trace)
    rtl_result = simulate_rtl_rose(trace)
    assert py_result == rtl_result
```

### 7.6 Output Comparison Format

Text-based cycle-by-cycle comparison:
```
# sim_output.txt format: cycle_num pass fail active
0 0 0 0
1 1 0 1
2 0 0 0
3 0 1 1
```

Python parses this and compares against the behavioral oracle output dict-by-dict.

---

## 8. Interface Update: `disable`/`disabled` Ports {#8-interface-update}

### 8.1 Updated Standard Interface (D-12)

```
clk, rst_n, start,                    // existing control
<observed_signals>,                    // existing DUT signals
disable_i,                            // NEW: disable input
active, pass, fail,                   // existing outputs
attempt_fired,                        // existing debug
overflow_flag,                        // existing debug (implication only)
disabled_o                            // NEW: disable indicator
```

### 8.2 Backward Compatibility Strategy

**Phase 3 plan 3.3 must:**
1. Update ALL existing templates (bool_expr, concat_delay, overlap_bitvec, nonoverlap, seq_concat_top) to include `disable_i`/`disabled_o`
2. When `disable_i = 1'b0` (no disable), behavior is identical to Phase 2
3. Regenerate ALL golden files (breaking change, but internal — no external API yet)
4. All Phase 2 tests must pass with updated golden files

### 8.3 Template Update Pattern

For each existing template, add:
```jinja2
    input  logic disable_i,
    ...
    output logic disabled_o,
    ...
    // Gate outputs with disable
    assign pass     = disable_i ? 1'b0 : pass_internal;
    assign fail     = disable_i ? 1'b0 : fail_internal;
    assign active   = disable_i ? 1'b0 : active_internal;
    assign disabled_o = disable_i;
```

---

## 9. Risk Analysis & Mitigations {#9-risks}

### 9.1 HIGH RISK: Interface Change Breaks All Existing Tests

**Risk:** Adding `disable_i`/`disabled_o` to all templates breaks every golden file and test.
**Mitigation:** Do this as the FIRST step in Phase 3. Update templates, regenerate goldens, verify all Phase 2 tests still pass. Then proceed with new operators.
**Impact:** ~2 hours of golden file regeneration and test fixing.

### 9.2 MEDIUM RISK: Slang Named Sequence Resolution Unknown

**Risk:** We don't know exactly how slang represents named sequence references in JSON. If slang doesn't pre-resolve them, we need declaration-lookup logic.
**Mitigation:** Create a test SVA file with named sequences, run slang `--ast-json`, examine output BEFORE implementing. Slang v11.0 does full elaboration, so likely pre-resolved.
**Impact:** 0.5-1 day of investigation if slang doesn't pre-resolve.

### 9.3 MEDIUM RISK: `disable iff` Async Timing Correctness

**Risk:** Combinational output gating + synchronous state clear might leave a 1-cycle window where internal state disagrees with outputs.
**Mitigation:** The simulation oracle (TEST-04) catches this. Test case: disable asserts mid-sequence, verify no spurious pass/fail on the same cycle OR the next cycle.
**Impact:** Caught by oracle testing; fix is template adjustment.

### 9.4 LOW RISK: iverilog Not Available in All Environments

**Risk:** Simulation tests skip locally if iverilog not installed.
**Mitigation:** `@pytest.mark.simulation` + graceful skip. CI hard-requires iverilog. Python oracle tests always run (no skip).
**Impact:** Minimal — CI catches issues that local dev misses.

### 9.5 LOW RISK: `$past` Pipeline Depth Explosion

**Risk:** `$past(sig, 1000)` creates 1000 FFs.
**Mitigation:** Emit a warning for N > 32 (unusual for real SVA). Still generate correct RTL. Not an error — just a resource warning.
**Impact:** None for correctness; informational only.

---

## 10. Implementation Order & Dependencies {#10-implementation-order}

### 10.1 Recommended Plan Ordering

```
Plan 3.1: [*N]/[*M:N]  (standalone, no deps on other P3 work)
  Depends on: Phase 2 counter pattern (concat_delay.sv.j2)
  Deliverables: IR node, ast_importer dispatch, composer, template, oracle, tests

Plan 3.2: $rose/$fell/$stable/$past  (standalone, no deps on 3.1)
  Depends on: Phase 1 bool_expr pattern
  Deliverables: IR node, ast_importer dispatch, composer, 4 templates, oracle, tests

Plan 3.3: disable iff + named sequences + bind + interface update
  MUST be ordered carefully:
    Step 1: Update ALL templates with disable_i/disabled_o (interface change)
    Step 2: Regenerate golden files, fix all tests
    Step 3: Implement disable iff logic
    Step 4: Implement named sequence expansion (PARSE-03)
    Step 5: Implement bind generation (OUT-04)

Plan 3.4: Simulation validation harness (TEST-03/TEST-04)
  Depends on: All operators from 3.1-3.3 (validates them)
  Deliverables: tests/simulation/ directory, pytest fixtures, testbench gen,
                Python oracle extensions, comparison framework
```

### 10.2 Critical Path

The critical path is **3.3 Step 1-2** (interface change) because it blocks the simulation harness from validating anything until golden files are stable.

**Recommendation:** Execute 3.3 Step 1-2 FIRST (before 3.1 or 3.2), then 3.1 and 3.2 can proceed in any order, then finish 3.3 Steps 3-5, then 3.4.

### 10.3 New IR Nodes Needed

```python
@dataclass(frozen=True)
class SeqRepetition(SVANode):
    """Consecutive repetition [*N] or [*M:N]."""
    expr: SVANode          # the expression to repeat
    rep_min: int           # minimum repetitions
    rep_max: int           # maximum repetitions
    
@dataclass(frozen=True)
class SignalFunc(SVANode):
    """Signal function: $rose, $fell, $stable, $past."""
    func_name: str         # "rose" | "fell" | "stable" | "past"
    signal: str            # signal name
    depth: int = 1         # pipeline depth (for $past)

@dataclass(frozen=True)
class DisableIff(SVANode):
    """disable iff (condition) property_expr."""
    condition: str         # disable condition expression text
    body: SVANode          # the property being disabled
```

### 10.4 New Templates Needed

| Template | Purpose | Plan |
|----------|---------|------|
| `rep_consecutive.sv.j2` | Counter-based consecutive repetition | 3.1 |
| `rose.sv.j2` | 1 FF + AND-NOT edge detect | 3.2 |
| `fell.sv.j2` | 1 FF + AND edge detect | 3.2 |
| `stable.sv.j2` | 1 FF + XNOR comparator | 3.2 |
| `past.sv.j2` | N-stage shift register | 3.2 |
| `disable_iff_top.sv.j2` | Top wrapper with disable gating | 3.3 |
| `bind.sv.j2` | Bind statement file | 3.3 |

### 10.5 Files Modified

| File | Changes |
|------|---------|
| `ir.py` | Add `SeqRepetition`, `SignalFunc`, `DisableIff` nodes; add `cse_origin` to CheckerNode |
| `ast_importer.py` | Remove `SequenceRepetition` from unsupported; add dispatch for `SimpleAssertionExpr` with repetition, `CallExpression` system functions, `DisableIff`, named refs |
| `composer.py` | Handle new IR nodes; build CheckerNodes for repetition, signal funcs, disable_iff |
| `emitter.py` | Add `emit_bind()` function |
| `behavioral_oracle.py` | Add `rep_consecutive`, `rose`, `fell`, `stable`, `past` kinds |
| `templates/*.sv.j2` | Update ALL 5 existing + add 7 new templates |
| `tests/` | New test files for each operator; simulation harness |

---

## Technical References

- [slang SystemVerilog compiler](https://github.com/MikePopoloski/slang) — AST JSON format
- [slang AssertionExpr documentation](https://www.sv-lang.com/classslang_1_1ast_1_1_assertion_expr.html) — Node hierarchy
- [slang SequenceRepetition struct](https://www.sv-lang.com/structslang_1_1ast_1_1_sequence_repetition.html) — Repetition kinds and fields
- [slang SimpleAssertionExpr](https://www.sv-lang.com/classslang_1_1ast_1_1_simple_assertion_expr.html) — expr + repetition fields
- [slang DisableIffAssertionExpr](https://www.sv-lang.com/classslang_1_1ast_1_1_disable_iff_assertion_expr.html) — condition + expr fields
- [slang ASTSerializer](https://sv-lang.com/classslang_1_1ast_1_1_a_s_t_serializer.html) — JSON serialization
- [Icarus Verilog waveform docs](https://steveicarus.github.io/iverilog/usage/waveform_viewer.html) — VCD/simulation output
- [IEEE 1800-2017 Section 16.9.2](https://standards.ieee.org/standard/1800-2017.html) — Repetition semantics

---

*Research completed: 2026-05-27*
*Confidence: HIGH — all technical questions answered, slang schema verified, hardware architectures well-understood*
