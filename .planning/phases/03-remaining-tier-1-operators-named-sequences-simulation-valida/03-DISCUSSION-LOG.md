# Phase 3: Remaining Tier 1 Operators + Named Sequences + Simulation Validation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-26
**Phase:** 3-Remaining Tier 1 Operators + Named Sequences + Simulation Validation
**Areas discussed:** Named sequence sharing, Simulation oracle design, disable iff integration, bind generation model

---

## Named Sequence Sharing

### Q1: How should named sequences be handled when used in multiple properties?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared sub-module | Named sequence becomes a standalone SV module. Multiple properties instantiate it. Saves area, matches Phase 5 CSE naturally. | |
| Inline expansion (defer sharing to Phase 5) | Named sequence is textually expanded at each use site — each property gets its own copy. Simpler codegen but duplicates FFs. | |
| Inline + tag for CSE | Expand inline for now, but tag duplicates in CheckerNode tree so Phase 5 CSE knows they're merge candidates. | ✓ |

**User's choice:** Inline + tag for CSE
**Notes:** Best of both worlds — simple codegen now with explicit merge hints for Phase 5.

### Q2: Named sequences can nest. Fully expand all nesting at import time, or limit depth?

| Option | Description | Selected |
|--------|-------------|----------|
| Full recursive expansion | Recursively expand all named references until only primitives remain. Reject actual recursion with error. | ✓ |
| Single-level expansion | Expand one level only; nested named sequences become their own tagged sub-modules. | |

**User's choice:** Full recursive expansion
**Notes:** With cycle detection to reject self-referencing sequences.

### Q3: What scope of named sequence/property declarations should Phase 3 handle?

| Option | Description | Selected |
|--------|-------------|----------|
| Same-file sequences + properties | Handle both sequence and property declarations within same module/package. Cross-file out of scope for v1. | |
| Cross-file (slang-resolved) | Also resolve named declarations from other files in the same compilation. | |
| You decide (follow slang AST) | Let Claude decide based on what slang's --ast-json provides. | ✓ |

**User's choice:** You decide (follow slang AST)
**Notes:** Follow what slang provides. If it pre-resolves cross-file references, support them.

---

## Simulation Oracle Design

### Q1: What serves as the 'ground truth' that generated monitors are validated against?

| Option | Description | Selected |
|--------|-------------|----------|
| Python behavioral model vs. RTL | Python model evaluates SVA semantics cycle-by-cycle, compared against RTL monitor output in Icarus. | |
| Icarus SVA checker vs. generated RTL | Behavioral SV testbench with native SVA assertions compared against generated monitor. | |
| Dual oracle (Python + Icarus) | Both: Python model for fast unit-level checks, Icarus co-simulation for full RTL validation. | ✓ |

**User's choice:** Dual oracle (Python + Icarus)
**Notes:** Python oracle catches logic errors early without needing simulator; Icarus catches RTL-level issues.

### Q2: How should test stimulus be generated for oracle validation?

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-crafted per operator | Targeted corner cases per operator. Labor-intensive but high confidence. | |
| Property-based random (Hypothesis) | Use Hypothesis for random stimulus traces. Good coverage but harder to debug. | |
| Golden + random hybrid | Both: hand-crafted golden for known corners + Hypothesis for fuzz discovery. | ✓ |

**User's choice:** Golden + random hybrid
**Notes:** Golden tests = regression suite; random tests = discovery tool.

### Q3: Should simulation tests require Icarus Verilog to be installed?

| Option | Description | Selected |
|--------|-------------|----------|
| Hard dependency (tests fail without Icarus) | If iverilog not installed, tests fail. Simplest CI setup. | |
| Soft skip locally, hard in CI | Skip with @pytest.mark.simulation if iverilog not found. CI installs and runs both. | ✓ |
| You decide | Let Claude decide. | |

**User's choice:** Soft skip locally, hard in CI
**Notes:** Developers can iterate without Icarus installed; CI catches simulation issues.

### Q4: How strictly should Python oracle and Icarus simulation results be compared?

| Option | Description | Selected |
|--------|-------------|----------|
| Cycle-exact output comparison | Compare pass/fail signals cycle-by-cycle from VCD. Any mismatch = failure. | ✓ |
| Event-level comparison (timing tolerant) | Only compare final counts or event timestamps. Allows minor timing differences. | |

**User's choice:** Cycle-exact output comparison
**Notes:** Python oracle must model the same registered-output delay as RTL. Strict correctness.

---

## `disable iff` Integration

### Q1: How should disable iff interact with internal FSM state?

| Option | Description | Selected |
|--------|-------------|----------|
| Output gating only | Gate only pass/fail/active outputs. Internal FSM keeps running but outputs masked. | |
| Full async state clear | Force all internal FFs to reset values combinationally. No stale state, correct semantics. | ✓ |
| Output gate + sync state clear | Outputs masked immediately, state cleared next clock edge. Middle ground. | |

**User's choice:** Full async state clear
**Notes:** Most semantically correct. Every FF cleared within same combinational cycle.

### Q2: Should the disable signal be part of the standard interface on ALL sub-modules?

| Option | Description | Selected |
|--------|-------------|----------|
| Always-present `disable` port | Add disable to standard interface on every module. Tied to 0 when not used. Uniform. | ✓ |
| Conditional `disable` port | Only add when disable iff is present. Cleaner output but conditional template logic. | |
| You decide | Let Claude decide cleanest approach. | |

**User's choice:** Always-present `disable` port
**Notes:** Uniform interface, no conditional logic in templates.

### Q3: What should monitor outputs look like while disable iff is active?

| Option | Description | Selected |
|--------|-------------|----------|
| Full silence (all outputs = 0) | pass=0, fail=0, active=0, attempt_fired=0. Complete silence. | |
| Silence + `disabled` indicator output | Same as silence plus a `disabled` output goes high. Distinguishes idle from disabled. | ✓ |

**User's choice:** Silence + `disabled` indicator output
**Notes:** Aids debugging. Standard interface grows to include `disable` input and `disabled` output.

---

## Bind Generation Model

### Q1: How should bind statement files be organized?

| Option | Description | Selected |
|--------|-------------|----------|
| One bind file per property | One monitor .sv + one bind .sv per property. Simple 1:1 mapping. | ✓ |
| Aggregate bind file | Single bind_all.sv for all properties in input file. | |
| Both (individual + aggregate) | Both options available to user. | |

**User's choice:** One bind file per property
**Notes:** Simple and predictable.

### Q2: How does the bind statement know which DUT module to target?

| Option | Description | Selected |
|--------|-------------|----------|
| CLI flag for target module | User specifies via --bind-target. Signal names inferred from expression. | |
| Infer from AST context | Extract target module from slang AST (the module containing the assertion). No extra flag. | ✓ |
| You decide | Let Claude decide based on slang AST capabilities. | |

**User's choice:** Infer from AST context
**Notes:** Slang provides module context. No extra CLI flags needed.

### Q3: How should bind statement port connections be written?

| Option | Description | Selected |
|--------|-------------|----------|
| Named ports (explicit mapping) | `.clk(clk), .rst_n(rst_n), .sig_a(a)`. Clear and debuggable. | ✓ |
| You decide | Let Claude pick clearest approach. | |

**User's choice:** Named ports (explicit mapping)
**Notes:** Explicit, debuggable, matches SystemVerilog best practices.

---

## Claude's Discretion

- Named sequence/property resolution scope (follow slang AST capabilities)
- Sub-module naming convention for new operator modules
- Internal wiring for disable signal through module hierarchy
- `$past(sig, N)` handling of non-literal N
- `[*0:$]` unbounded repetition rejection error code
- Python oracle class structure and API

## Deferred Ideas

None — discussion stayed within phase scope
