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

| Operator | Description | Example |
|----------|-------------|---------|
| `##N` | Fixed delay | `a ##2 b` |
| `##[M:N]` | Delay range | `a ##[1:3] b` |
| <code>\|-></code> | Overlapping implication | <code>a \|-> b</code> |
| <code>\|=></code> | Non-overlapping implication | <code>a \|=> b</code> |
| `[*N]` | Consecutive repetition | `a[*3]` |
| `[*M:N]` | Repetition range | `a[*1:4]` |
| `$rose()` | Rising edge detection | `$rose(sig)` |
| `$fell()` | Falling edge detection | `$fell(sig)` |
| `$stable()` | No change detection | `$stable(sig)` |
| `$past()` | Previous value reference | `$past(sig, 2)` |
| `disable iff` | Asynchronous disable | `disable iff (reset) ...` |
| Named sequences | Sequence instantiation | `sequence s; ... endsequence` |

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
git clone https://github.com/allenli/sva2rtl.git
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
