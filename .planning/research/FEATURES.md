# SVA→RTL Compiler: Feature Analysis

**Research type:** Project Research — Features dimension
**Date:** 2026-05-25
**Consumer:** Requirements definition

---

## 1. Table Stakes

> Must have or the tool is useless.

### 1.1 Core SVA Operator Coverage

| Feature | Hardware Construct | Complexity |
|---|---|---|
| Boolean expressions in properties | Combinational logic | LOW |
| Fixed delay `##n` | Shift register / counter | LOW |
| Range delay `##[n:m]` | Counter with bounds check | MEDIUM |
| `$rose`, `$fell`, `$stable` | Edge-detect flip-flop | LOW |
| `$past(sig, n)` | Delay pipeline registers | LOW-MEDIUM |
| Consecutive repetition `[*n]`, `[*n:m]` | Counter + FSM | MEDIUM |
| Overlapping implication `\|->` | FSM gating on antecedent match | MEDIUM |
| Non-overlapping implication `\|=>` | FSM gating with one-cycle delay | MEDIUM |
| `disable iff (reset_expr)` | Synchronous clear on FSM | MEDIUM |
| Named `sequence` and `property` definitions | Modular instantiation | MEDIUM |

### 1.2 Single-Clock Semantics

- Explicit `@(posedge clk)` clocking block
- `default clocking` block support
- Correct LRM-compliant clock sampling

### 1.3 Synthesizable RTL Output

- No `initial` blocks, no `$display` — pure synthesizable RTL
- One module per assertion (or per property group)
- Standard port interface: `clk`, `rst_n`, observed signals, `pass`, `fail`
- Output in SystemVerilog or Verilog-2001 (configurable)
- Self-contained, no black-box dependencies

### 1.4 Integration: `bind`-Based File Generation

- Generate `bind <module_name> <monitor_name> <inst> (...)` wrapper
- Auto-infer port connections from DUT port names

### 1.5 Error Reporting With Source Location

- Parse errors with `file:line:col` attribution
- "Unsupported operator" errors (never silently miscompile)
- Non-zero exit code on error

### 1.6 CLI Interface

- Input: one or more `.sv` files
- `--output` flag for output path
- `--verilog` flag for Verilog-2001 output
- Exit code 0/1 for CI integration

---

## 2. Differentiators

> Competitive advantage — makes users choose this over DIY.

### 2.1 Extended Operator Coverage (Tier 2)

| Feature | Complexity | Dependency |
|---|---|---|
| Go-to repetition `[->n]` | HIGH | Consecutive repetition |
| Non-consecutive repetition `[=n]` | HIGH | Consecutive repetition |
| `first_match(seq)` | HIGH | Named sequence support |
| `intersect` | HIGH | FSM composition |
| `within` | HIGH | `intersect` |
| `throughout` | HIGH | Range delay |

### 2.2 Optimization Passes

| Feature | What It Does | Complexity |
|---|---|---|
| Dead-state pruning | Remove unreachable states | MEDIUM |
| FSM state minimization | Hopcroft/Myhill-Nerode | HIGH |
| Common sub-expression elimination | Share logic between monitors | HIGH |
| Counter merging | Share delay pipelines | MEDIUM |
| Area estimation report | LUT/FF count before synthesis | MEDIUM |

### 2.3 Developer Experience

| Feature | Complexity |
|---|---|
| AST dump mode (`--dump-ast`) | LOW |
| IR dump mode (`--dump-ir`) | LOW |
| FSM visualization (Graphviz DOT) | MEDIUM |
| Verbose synthesis report: operator → RTL mapping | LOW |
| Vacuity warning (unreachable antecedent) | HIGH |

### 2.4 Local Variables in Sequences (v2+)

- Capture signal values at match-time for later comparison
- Requires registers latched at FSM transition points
- VERY HIGH complexity — strongest differentiator

### 2.5 Multi-Clock Domain Support (v2+)

- Per-sequence clock annotation
- Multi-clocked implication
- CDC-safe sampling warnings

### 2.6 Coverage Instrumentation

- `cover property` → dedicated `cover_hit` output
- Sequence progress coverage points
- UVM-compatible coverage event output

---

## 3. Anti-Features

> Things to deliberately NOT build.

| Anti-Feature | Reason |
|---|---|
| Silent miscompilation of unsupported constructs | Destroys trust; always reject-with-message |
| Full LRM for simulation-only constructs (`$display`, `$fatal`, dynamic delays) | Detect and reject; not synthesizable |
| Custom SystemVerilog parser | Use slang; writing a parser is 12-24 months wasted |
| Formal verification engine | Use SymbiYosys/JasperGold; tool generates monitors, not proofs |
| Simulation testbench infrastructure | UVM/cocotb/pyuvm already cover this |
| EDA vendor plugin wrappers | Users use this alongside vendors, not as plugin |
| GUI / Visual property editor | Terminal-first; GUI is v3+ at best |
| Approximate/sampling-based monitoring | Exact formal semantics is the value proposition |
| Correctness-sacrificing optimization | Never change observable behavior for area |

---

## 4. Feature Dependency Chain

```
Parser Frontend (slang)
│
├── Boolean expressions
├── $rose/$fell/$stable
├── $past(sig, n)
├── Fixed delay ##n
├── Range delay ##[n:m]          ─── All feed into ───→ Single-clock RTL output
├── Consecutive repetition                                  → bind generation
├── Overlapping implication                                 → CLI + exit codes
├── Non-overlapping implication
├── disable iff
│
├── Named sequence/property (reuse + composition)
│
├── [->], [=]  ────────────── depends on: consecutive repetition
├── first_match ───────────── depends on: named sequence FSM
├── intersect ─────────────── depends on: FSM composition
├── within ────────────────── depends on: intersect
├── throughout ────────────── depends on: range delay
│
├── Local variables ────────── depends on: named sequences + FSM state labeling
│
├── Optimization passes ────── depends on: complete FSM IR
│   ├── Dead-state pruning
│   ├── State minimization
│   ├── CSE across assertions
│   └── Area estimation
│
└── Multi-clock support ────── depends on: single-clock working correctly
```

---

## 5. Priority Matrix

| Feature Group | Priority |
|---|---|
| Core synthesizable subset (§1.1) | P0 — v1 required |
| Single-clock semantics (§1.2) | P0 — v1 required |
| Synthesizable RTL output (§1.3) | P0 — v1 required |
| bind generation (§1.4) | P0 — v1 required |
| Error reporting (§1.5) | P0 — v1 required |
| CLI interface (§1.6) | P0 — v1 required |
| Tier 2 operators (§2.1) | P1 — v1 stretch / v2 |
| Dead-state pruning (§2.2) | P1 — quick win |
| FSM visualization (§2.3) | P1 — low effort, high visibility |
| Multi-clock (§2.5) | P2 — v2 |
| Local variables (§2.4) | P2 — v2 |
| Coverage instrumentation (§2.6) | P2 — v2 |
| LTL strong operators | P3 — v3 |

---

*Sources: IEEE 1800-2017 LRM, slang (MikePopoloski/slang), sahadipayan/SVA_to_RTL, SymbiYosys docs, Design-Reuse.com synthesizable assertion article*
