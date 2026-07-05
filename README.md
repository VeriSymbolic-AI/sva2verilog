# sva2rtl — SVA to Synthesizable RTL Monitor Compiler

An open-source compiler that transforms SystemVerilog Assertion (SVA) properties into synthesizable hardware monitor modules. Generated monitors can be simulated with Verilator/Icarus Verilog or synthesized to FPGA. No mature open-source tool exists in this space — sva2rtl fills a critical gap in the EDA toolchain.

## What It Does

sva2rtl takes SVA properties/sequences as input and generates correct, area-efficient SystemVerilog (or Verilog-2001) monitor modules. Each monitor exposes a standard interface for integration into verification and emulation flows.

**Key capabilities:**
- Compiles SVA temporal properties into synthesizable RTL
- Token-passing composition model for correct concurrent evaluation
- Counter-encoded range operators for area efficiency
- Deterministic output suitable for formal equivalence checking

## Installation

```bash
pip install sva2rtl
```

Or with uv:

```bash
uv pip install sva2rtl
```

### Prerequisites

- Python 3.12+
- [slang](https://github.com/MikePopoloski/slang/releases) v11.0+ installed and available on PATH

Verify slang is accessible:

```bash
slang --version
```

## Quick Start

Compile an SVA property to a SystemVerilog monitor:

```bash
sva2rtl input.sv -o monitor.sv
```

Generate Verilog-2001 compatible output:

```bash
sva2rtl input.sv --verilog -o monitor.v
```

Compile a specific property from a file with multiple assertions:

```bash
sva2rtl input.sv --property req_ack_prop -o monitor.sv
```

## Supported SVA Constructs

### Tier 1 — Core Sequential Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `##N` | Fixed delay | `a ##2 b` |
| `##[M:N]` | Delay range | `a ##[1:3] b` |
| <code>\|-></code> | Overlapping implication (incl. multi-cycle consequent) | <code>a \|-> b</code> |
| <code>\|=></code> | Non-overlapping implication (incl. multi-cycle consequent) | <code>a \|=> b</code> |
| `[*N]` | Consecutive repetition | `a[*3]` |
| `[*M:N]` | Repetition range | `a[*1:4]` |
| `$rose()` | Rising edge detection | `$rose(sig)` |
| `$fell()` | Falling edge detection | `$fell(sig)` |
| `$stable()` | No change detection | `$stable(sig)` |
| `$past()` | Previous value reference | `$past(sig, 2)` |
| `$changed()` | Signal changed since previous cycle | `$changed(sig)` |
| `disable iff` | Asynchronous disable | `disable iff (reset) ...` |
| Named sequences | Sequence instantiation | `sequence s; ... endsequence` |

### Tier 2 — Complex Sequence Operators (v1.3 + v1.5.1 NFA)

| Operator | Description | Example |
|----------|-------------|---------|
| `first_match` | Earliest completion wins | `first_match(a ##[1:3] b)` |
| `[->N]` | Goto repetition (N non-consecutive) | `a[->3]` |
| `[=N]` | Non-consecutive repetition | `a[=2]` |
| `and` | Both sequences match (same start) | `s1 and s2` |
| `or` | Either sequence matches | `s1 or s2` |
| `intersect` | Both sequences complete simultaneously (incl. multi-cycle via NFA) | `s1 intersect s2` |
| `within` | Inner sequence within outer's window (incl. multi-cycle via NFA) | `s1 within s2` |
| `throughout` | Condition holds throughout sequence (incl. multi-cycle via NFA) | `en throughout s1` |
| `not` | Invert pass/fail (property) | `not (prop)` |
| `if...else` | Conditional property selection | `if (cond) p1 else p2` |

### Tier 3 — Bounded Liveness Operators (v1.4)

| Operator | Description | Example |
|----------|-------------|---------|
| `s_eventually [m:n]` | Bounded eventually (liveness) | `s_eventually [1:3] a` |
| `eventually [m:n]` | Bounded eventually (weak) | `eventually [0:4] a` |
| `always [m:n]` | Bounded always (liveness) | `always [1:3] a` |
| `s_always [m:n]` | Bounded always (strong) | `s_always [0:4] a` |
| `until` | Weak until (safety) | `a until b` |
| `until_with` | Weak until-with (safety) | `a until_with b` |

### Multi-clock Properties (v1.4.1)

| Mode | Description | Example |
|------|-------------|---------|
| Multi-clock sequence | Per-domain sub-checkers + 2-DFF sync | `@(clk1) a ##1 @(clk2) b` |
| Multi-clock implication | Antecedent sync → consequent | `@(clk1) a \|=> @(clk2) b` |
| Multi-stage chaining | Transitive domain composition | `@(clk1) ... ##1 @(clk2) ... ##1 @(clk3) ...` |

Unbounded liveness (`s_eventually a`, unbounded `always a`) and the strong
`s_until` / `s_until_with` forms are rejected at compile time — they are not
synthesizable on finite state. Nested multi-path composition (intersect /
within / throughout) is supported up to a total of K ≤ 32 NFA states
(compile-time enforced). See [SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md).

For the full construct reference with generated templates, see [SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md).

## CLI Reference

| Flag | Description |
|------|-------------|
| `--output`, `-o` | Output file path (default: stdout) |
| `--verilog` | Emit Verilog-2001 compatible output |
| `--property`, `-p` | Select a specific property by name |
| `--slang-path` | Path to slang binary (if not on PATH) |
| `--dump-ast` | Dump slang AST JSON and exit |
| `--dump-ir` | Dump internal IR and exit |
| `--dump-tree` | Dump composition tree and exit |
| `--no-optimize` | Skip DFA minimization and CSE passes |
| `--version` | Print version and exit |

## Generated Monitor Interface

Every generated monitor exposes a standard port interface:

```systemverilog
module sva_monitor_<name> (
    input  logic clk,           // System clock
    input  logic rst_n,         // Active-low synchronous reset
    input  logic start,         // Trigger: begin property evaluation
    output logic pass,          // Asserted for one cycle on property match
    output logic fail,          // Asserted for one cycle on property violation
    output logic active,        // High while evaluation is in progress
    output logic attempt_fired, // Sticky: set high on first start; cleared only by reset
    input  logic disable_i,     // External disable condition
    output logic disabled_o     // Indicates monitor is disabled
);
```

## Development

```bash
git clone https://github.com/VeriSymbolic-AI/sva2verilog.git
cd sva2rtl
uv sync --dev
```

Run tests:

```bash
uv run pytest tests/
```

Type checking:

```bash
uv run mypy --strict src/
```

Lint and format:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Architecture

sva2rtl uses a token-passing composition model (inspired by TIMA Lab research) with operator-aware templates and counter encoding for range operators.

**Pipeline:**

```
SVA Source → slang --ast-json → IR → Normalize → Compose → Optimize → Emit RTL
```

| Stage | Description |
|-------|-------------|
| Parse | slang parses SVA, emits elaborated AST as JSON |
| Import | AST JSON mapped to frozen-dataclass IR nodes |
| Normalize | Desugar operators, flatten nested sequences |
| Compose | Build token-passing network via operator templates |
| Optimize | DFA minimization (Hopcroft), common subexpression elimination |
| Emit | Jinja2 templates generate SystemVerilog or Verilog-2001 |

## License

Licensed under the Business Source License 1.1 (BSL-1.1).

- Free for individual, academic, and evaluation use
- Commercial production use by organizations with >$10M annual revenue requires a license
- Converts to Apache License 2.0 on 2030-05-29

See [LICENSE](LICENSE) for full terms.
