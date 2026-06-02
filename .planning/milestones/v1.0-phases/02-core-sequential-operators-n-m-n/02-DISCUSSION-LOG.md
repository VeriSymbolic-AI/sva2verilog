# Phase 2: Core Sequential Operators — `##N`, `##[M:N]`, `|->`, `|=>` - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 2-Core Sequential Operators
**Areas discussed:** ##N delay strategy, Overflow behavior, Module output topology

---

## ##N Delay Strategy

### Q1: How should fixed delay `##N` be implemented in RTL?

| Option | Description | Selected |
|--------|-------------|----------|
| Always shift register | ##N always uses an N-stage shift register (simple, predictable, but ##100 = 100 FFs). Matches ROADMAP plan 2.1 literally. | |
| Hybrid with threshold | ##N uses shift register for small N (≤8), counter for large N (>8). Best area efficiency with simple cases staying readable. | |
| Always counter | ##N always uses counter (same style as ##[M:N] where M=N). Uniform codegen, always area-efficient, slightly more complex for ##1. | ✓ |

**User's choice:** Always counter
**Notes:** Uniform codegen, always area-efficient. For ##1 it's a 1-bit counter (still just 1 FF + comparator).

### Q2: Since ##N is now counter-based like ##[M:N], should they share one template or remain separate?

| Option | Description | Selected |
|--------|-------------|----------|
| Single unified template | One `concat_delay.sv.j2` template handles both ##N (M=N) and ##[M:N]. Less code, one parameterized design. Window comparator trivially becomes equality for fixed case. | ✓ |
| Two separate templates | Keep two templates: `concat_fixed.sv.j2` (counter + equality compare) and `concat_range.sv.j2` (counter + window comparator). Marginally simpler RTL output for the fixed case. | |

**User's choice:** Single unified template
**Notes:** One template, less code to maintain, synthesizer optimizes `(count >= N) && (count <= N)` to equality anyway.

### Q3: For the delay counter output: should `pass` be a single-cycle pulse when the count hits the window, or stay high for the full M..N window?

| Option | Description | Selected |
|--------|-------------|----------|
| Pulse on match | The delay module's `pass` output is a single-cycle pulse at the exact window match point. Active goes high when counting, low otherwise. Downstream modules must sample the pulse. | |
| High during window | The delay module's `pass` stays high for the entire M..N window (all valid cycles). This naturally handles range delays where any cycle in the window can trigger the consequent. | ✓ |

**User's choice:** High during window
**Notes:** Semantically correct for range delays. For ##N (M=N), naturally degrades to single-cycle pulse.

### Q4: When multiple concurrent antecedent matches trigger overlapping delay evaluations, where does the concurrency tracking live?

| Option | Description | Selected |
|--------|-------------|----------|
| Single counter, |-> manages concurrency | Each new `start` pulse allocates a separate counter instance (via bit-vector tracking in the implication module above). The delay module itself only sees one active sequence at a time. | ✓ |
| Multi-tracking inside delay module | The delay module itself handles multiple overlapping start pulses with a small counter array or shift register to track N concurrent activations independently. | |

**User's choice:** Single counter, |-> manages concurrency
**Notes:** Clean separation of concerns. Delay module is purely "start → count → window match → pass."

---

## Overflow Behavior

### Q1: When the |-> bit-vector overflows, what should the monitor do?

| Option | Description | Selected |
|--------|-------------|----------|
| Best-effort + flag | overflow_flag latches, but the monitor continues best-effort with remaining tracked threads. Oldest unresolved thread is silently overwritten. | |
| Fail on overflow | overflow_flag latches AND fail fires immediately on the overflow cycle. Monitor clearly signals 'I cannot track this correctly.' Conservative — no silent degradation. | ✓ |
| Drop new threads + flag | overflow_flag latches, monitor continues tracking, but any new start pulses are dropped. Preserves correctness of already-active evaluations. | |

**User's choice:** Fail on overflow
**Notes:** Conservative, no silent degradation. For a formal verification tool, correctness over liveness.

### Q2: How should the bit-vector width be determined?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto from consequent length | Width automatically set to max consequent length. Correct for most real SVA. | |
| Auto + user-overridable parameter | Default to consequent length but allow user override via a generate parameter in the emitted module. Power users can increase for safety margin. | ✓ |

**User's choice:** Auto + user-overridable parameter
**Notes:** `parameter BV_WIDTH = <consequent_length>` at module top. Override via bind: `#(.BV_WIDTH(16))`.

### Q3: Should overflow_flag be clearable, or truly permanent until reset?

| Option | Description | Selected |
|--------|-------------|----------|
| Sticky until reset only | overflow_flag is truly sticky — only cleared by rst_n. Ensures no overflow event is ever missed. | ✓ |
| Sticky + clearable input | Sticky by default, but add a `clear_overflow` input port for test harnesses. | |

**User's choice:** Sticky until reset only
**Notes:** Simple hardware, no extra port, no ambiguity about whether overflow was acknowledged.

### Q4: After overflow triggers `fail`, should the monitor continue operating or halt?

| Option | Description | Selected |
|--------|-------------|----------|
| Continue after overflow fail | Monitor keeps operating (tracking whatever threads it can). Single fail pulse + sticky flag are the signal. | |
| Halt after overflow | All tracking stops, pass/fail go idle, only overflow_flag remains high. Requires reset to resume. | ✓ |

**User's choice:** Halt after overflow
**Notes:** No confusing post-overflow results. Users see halt, check overflow_flag, increase BV_WIDTH, re-run.

---

## Module Output Topology

### Q1: For composed operators, should the generated RTL be one flat module or a hierarchy?

| Option | Description | Selected |
|--------|-------------|----------|
| Single flat module | All logic inlined in one always_ff block. Simple for small properties. | |
| Hierarchical sub-modules | Top-level wrapper instantiates sub-modules. Each reusable, independently testable. Enables Phase 5 CSE. | ✓ |
| Flat now, hierarchical in Phase 4 | Start flat, refactor when composition engine is built. | |

**User's choice:** Hierarchical sub-modules
**Notes:** Standard RTL practice, enables CSE, each component independently verifiable. CheckerNode.children already supports this.

### Q2: Where should the module boundaries be drawn?

| Option | Description | Selected |
|--------|-------------|----------|
| One module per operator template | Each template is its own module: delay, bitvec, top wrapper. Maximum reuse potential. | ✓ |
| Leaf + top wrapper only | Two levels: leaf checker core + one top-level wrapper with all logic inline. | |

**User's choice:** One module per operator template
**Notes:** Maximum composability, each component independently testable.

### Q3: Single output file or separate files per module?

| Option | Description | Selected |
|--------|-------------|----------|
| Single .sv file per property | All modules concatenated. Simple: one input → one output. | |
| One .sv file per module | Separate files. Professional RTL convention. Synthesizers prefer it. | ✓ |

**User's choice:** One .sv file per module
**Notes:** Professional RTL convention. Synthesizers often expect one-module-per-file.

### Q4: How should the output directory be organized?

| Option | Description | Selected |
|--------|-------------|----------|
| Flat output directory | All .sv files in one flat directory. `iverilog output/*.sv` just works. | ✓ |
| Per-assertion subdirectory | Organized per assertion. Cleaner for multi-property but more nesting. | |

**User's choice:** Flat output directory
**Notes:** Simple. `iverilog output/*.sv` or `verilator --sv output/*.sv` works immediately.

---

## Claude's Discretion

- Sub-module naming convention (encode parameters into module name)
- Internal port interface between sub-modules (standard token-passing)
- Counter reset behavior on rst_n (sync reset to zero)
- `##0` zero-delay semantics (combinational pass-through)

## Deferred Ideas

None — discussion stayed within phase scope.
