# sva2rtl — SVA to Synthesizable RTL Monitor Compiler

A source-available compiler that transforms SystemVerilog Assertion (SVA) properties into synthesizable hardware monitor modules. Generated monitors can be simulated with Verilator/Icarus Verilog or synthesized to FPGA. The code is available under BSL-1.1 and changes to Apache-2.0 on the date stated in [LICENSE](LICENSE).

## What It Does

sva2rtl takes SVA properties/sequences as input and generates correct, area-efficient SystemVerilog (or Verilog-2001) monitor modules. Each monitor exposes a standard interface for integration into verification and emulation flows.

**Key capabilities:**
- Compiles SVA temporal properties into synthesizable RTL
- Token-passing composition model for correct concurrent evaluation
- Counter-encoded range operators for area efficiency
- Deterministic output suitable for formal equivalence checking

## Installation

The package is not currently published on PyPI. Install the tagged source directly:

```bash
python -m pip install "sva2rtl @ git+https://github.com/VeriSymbolic-AI/sva2verilog.git@main"
```

For development, clone the repository and use the locked environment shown below.

### Prerequisites

- Python 3.12+
- [slang](https://github.com/MikePopoloski/slang/releases) v11.0+ installed and available on PATH

Verify slang is accessible:

```bash
slang --version
```

## Quick Start

Compile one boolean leaf to a SystemVerilog file:

```bash
sva2rtl bool_property.sv -o monitor.sv
```

Generate Verilog-2001 compatible output:

```bash
sva2rtl bool_property.sv --verilog -o monitor.v
```

Hierarchical properties and files with multiple assertions require an explicit output directory:

```bash
sva2rtl input.sv -o generated/
sva2rtl input.sv --property req_ack_prop -o generated_req_ack/
```

## Supported SVA Constructs

This section is a quick overview. For authoritative support status, subset
boundaries, and verification evidence, see
[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md).

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
| `[->N]` | Goto repetition; one start arms counting until Nth occurrence | `a[->3]` |
| `[=N]` | Non-consecutive repetition; one start arms counting until Nth occurrence | `a[=2]` |
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

### Experimental Multi-clock Properties (v1.4.1)

| Mode | Description | Example |
|------|-------------|---------|
| Multi-clock sequence | Per-domain sub-checkers + 2-DFF sync | `@(clk1) a ##1 @(clk2) b` |
| Multi-clock implication | Antecedent sync → consequent | `@(clk1) a \|=> @(clk2) b` |
| Multi-stage chaining | Transitive domain composition | `@(clk1) ... ##1 @(clk2) ... ##1 @(clk3) ...` |

Multi-clock output is fail-closed by default because the current 2-DFF level
synchronizer can miss narrow events or coalesce multiple events. Generate it
only for bounded experiments with `--experimental-multiclock`; this is not a
CDC sign-off claim.

Unbounded liveness (`s_eventually a`, unbounded `always a`) and the strong
`s_until` / `s_until_with` forms are rejected at compile time — they are not
synthesizable on finite state. Nested multi-path composition (intersect /
within / throughout) is supported up to a total of K ≤ 32 NFA states
(compile-time enforced). See [SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md).

For construct explanations and generated templates, see
[SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md). For exact evidence status,
use [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md).

## CLI Reference

| Flag | Description |
|------|-------------|
| `--output`, `-o` | Leaf output file, or required directory for hierarchical/multi output |
| `--force` | Replace differing generated files; without it, output is no-clobber |
| `--verilog` | Emit Verilog-2001 compatible output |
| `--experimental-multiclock` | Explicitly opt into the lossy prototype CDC path |
| `--property` | Select a specific property by name |
| `--slang-path` | Path to slang binary (if not on PATH) |
| `--source` | Additional SystemVerilog source file; repeatable |
| `--filelist`, `-F` | Slang command file; relative paths resolve from the file; repeatable |
| `--include-dir`, `-I` | Include search directory; repeatable |
| `--define`, `-D` | Preprocessor macro as `NAME` or `NAME=VALUE`; repeatable |
| `--top` | Top-level module to elaborate; repeatable |
| `--parameter`, `-G` | Top-level parameter override as `NAME=VALUE`; repeatable |
| `--library-file`, `-v` | Library source file; repeatable |
| `--library-dir`, `-y` | Library search directory; repeatable |
| `--library-ext`, `-Y` | Library extension such as `.sv`; repeatable |
| `--library`, `-L` | Library lookup-priority name; repeatable |
| `--single-unit` | Treat primary sources as one compilation unit |
| `--dump-ast` | Dump slang AST JSON and exit |
| `--dump-ir` | Dump internal IR and exit |
| `--dump-tree` | Dump composition tree and exit |
| `--no-optimize` | Skip checker-tree optimization passes |
| `--version` | Print version and exit |

### Real-project compilation context

The CLI accepts a reviewed subset of slang's project options without exposing
raw compiler-argument passthrough:

```bash
sva2rtl rtl/top.sv \
  -F project/files.f \
  -I rtl/include \
  -D ENABLE_ASSERTS=1 \
  --top soc_top \
  -G DATA_WIDTH=64 \
  -y rtl/lib -Y .sv \
  --single-unit \
  --output generated-monitors/
```

All options are passed as separate subprocess arguments; the frontend never
uses a shell. Paths and identifiers are validated before slang runs, and the
compiler-owned AST output controls cannot be replaced by a structured option.
`-F/--filelist` is still a trusted compiler-configuration input: slang command
files can alter compilation semantics even though they cannot invoke a shell.
Assertions in elaborated child instances are discovered recursively with
module-scoped declaration lookup. Reused cached instance bodies are processed
once; differing generated module identities still fail closed rather than
silently overwriting output.

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
    // Present on bounded-concurrency templates (including NFA implication):
    output logic overflow_flag, // Sticky fail-closed slot-exhaustion verdict
    output logic attempt_fired, // Sticky: set high on first start; cleared only by reset
    input  logic disable_i,     // External disable condition
    output logic disabled_o     // Indicates monitor is disabled
);
```

`overflow_flag` remains asserted, forces `fail=1`, and suppresses
`active/pass` until reset or `disable_i`. Templates without a bounded attempt
allocator omit this optional port.

## Development

```bash
git clone https://github.com/VeriSymbolic-AI/sva2verilog.git
cd sva2verilog
uv sync --dev --frozen
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

## Project Analysis

See [Project Status](PROJECT_STATUS.md) for the current verified state and
[Project Analysis (2026-07-11)](PROJECT_ANALYSIS_2026-07-11.md) for the dated
architecture/risk snapshot that motivated the hardening work.

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
| Optimize | Constant folding, boolean simplification, common subexpression elimination, and dead-logic pruning |
| Emit | Jinja2 templates generate SystemVerilog or Verilog-2001 |

## Formal Verification Methodology

Correctness of a monitor compiler cannot be established by testing the compiler
against itself. sva2rtl therefore separates *specification semantics* from
*implementation structure* at every verification layer, and states its proof
strength honestly rather than claiming uniform correctness.

### Non-Circularity Principle

The central methodological commitment is that no expected result may be derived
from the code under test.

- The behavioral oracle (`src/sva2rtl/behavioral_oracle.py`) is a pure-Python
  model of IEEE 1800 assertion semantics. It is written from the standard, not
  derived from the composition or emission code.
- The differential reference (`tests/differential_reference.py`) consumes the
  typed specification that *rendered* the SVA source, and deliberately imports
  neither compiler IR nor composition/emission modules. An importer or composer
  mistake therefore cannot silently become the expected differential result.
- Formal miters compare generated RTL against an *independently written* IEEE
  1800 reference monitor, not against a second instance of the generated logic.

### Verification Layers

| Layer | Method | Property established |
|-------|--------|----------------------|
| 1 | Behavioral oracle (Python IEEE model) | Cycle-accurate semantic agreement, structure-independent |
| 2 | Dual-simulator co-simulation (Icarus + Verilator) | Toolchain-independent simulation agreement |
| 3 | Bounded model checking (SymbiYosys `bmc`) | No counterexample within a stated cycle bound |
| 4 | k-induction (SymbiYosys `prove`) | Unbounded equivalence for converging monitors |
| 5 | Synthesis and lint acceptance (Yosys, Verilator) | Generated RTL is structurally synthesizable |
| 6 | Source-level differential testing (Hypothesis) | Randomized specification-to-RTL agreement |

Layers 3 and 4 differ in strength and this distinction is preserved throughout
the documentation. A BMC result is a *bounded* claim: it certifies that no
counterexample exists up to depth *k*. A k-induction result in `prove` mode is
an *unbounded* claim over all reachable states. Rows in
[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) record which of the two applies, and the
bound where BMC is the strongest available result.

### Miter Construction

Equivalence checking uses a miter that drives the generated monitor and the
independent reference monitor from identical stimulus and asserts observable
agreement:

```
             ┌────────────────────────┐
stimulus ───►│ generated monitor      │──► pass/fail/active ──┐
    │        └────────────────────────┘                       │
    │                                                    ┌────▼────┐
    │        ┌────────────────────────┐                  │ assert  │
    └───────►│ independent reference  │──► pass/fail/active─►  equal │
             │ (hand-written IEEE)    │                  └─────────┘
             └────────────────────────┘
```

Arbitrary-start variants relax the assumption that evaluation begins at reset,
which catches errors that only appear on mid-stream triggering.

### Stated Limitations

The project does not claim uniform formal correctness, and the following
boundaries are deliberate:

- Unbounded liveness (`s_eventually a` without a range) is rejected at compile
  time; it is not realizable on finite state.
- Multi-clock generation is disabled unless explicitly opted into as an
  experiment. Its 2-DFF level synchronizer remains a *trusted boundary*: full
  event delivery, clock-domain-crossing, and metastability proof are out of scope.
- k-induction does not converge for every operator family. Where it does not,
  the row remains BMC-bounded and says so; a non-converging induction step is
  recorded as a known boundary rather than waived.
- Nested multi-path composition is bounded at K ≤ 32 NFA states, enforced at
  compile time.

Current per-construct evidence status, including which layers have been
exercised on the current commit, is maintained in
[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md). Known gaps and their severity are
tracked in [INDUSTRIAL_VALIDATION_GAPS.md](INDUSTRIAL_VALIDATION_GAPS.md).

## Industrial Collaboration and Sponsorship

sva2rtl is validated entirely with open-source formal and simulation tools:
SymbiYosys, Yosys, Icarus Verilog, and Verilator. This is sufficient to
establish internal consistency and bounded correctness, but it leaves one
class of evidence out of reach.

### Requested: Commercial Formal Tool Access

We are seeking academic or industrial sponsorship providing evaluation access to
a commercial formal verification tool — **Cadence JasperGold** in particular,
though Siemens Questa Formal or Synopsys VC Formal would serve the same
purpose. The goal is cross-tool differential validation of SVA semantics.

Why this matters: our reference monitors encode our *reading* of IEEE 1800.
Commercial tools encode a reading that has been exercised against a very large
body of industrial designs. Comparing the two would let us either confirm
agreement or locate genuine semantic divergence. Specifically, sponsorship would
enable:

- Independent confirmation that generated monitors are equivalent to the
  original SVA under a tool whose semantics were developed independently of ours
- Detection of divergence in the semantically subtle areas — `disable iff`
  interaction with reset, sampled-value timing at clock edges, `first_match`
  and non-consecutive repetition boundaries, and multi-clock sequences
- Promotion of construct rows from BMC-bounded to cross-tool-confirmed status
- A published, reproducible open-versus-commercial formal comparison, which to
  our knowledge does not currently exist for SVA monitor synthesis

We would publish the methodology and results, and acknowledge the sponsoring
organization. Only evaluation access is needed; no funding is requested. If your
organization can help, please open an issue titled `Sponsorship: formal tool
access` on the project repository.

## References

### Academic Foundations

The token-passing composition model and the general approach of synthesizing
proven-correct monitors from declarative temporal specifications derive from the
following work. sva2rtl is an independent implementation and is not affiliated
with these authors or their institutions.

1. K. Morin-Allory and D. Borrione. "Proven correct monitors from PSL
   specifications." *Design, Automation and Test in Europe (DATE)*, 2006.
   [ACM](https://dl.acm.org/doi/10.5555/1131481.1131827)
2. D. Borrione, M. Liu, P. Ostier, and L. Fesquet. "On-Line Assertion-Based
   Verification with Proven Correct Monitors." TIMA Laboratory, 2005.
   [HAL](https://hal.science/hal-00078798v1)
3. M. Boulé and Z. Zilic. "Automata-based assertion-checker synthesis of PSL
   properties." *ACM Transactions on Design Automation of Electronic Systems
   (TODAES)*, 13(1), 2008.
   [ACM](https://dl.acm.org/doi/10.1145/1297666.1297670)
4. M. Boulé and Z. Zilic. "Efficient Automata-Based Assertion-Checker Synthesis
   of PSL Properties." *IEEE High Level Design Validation and Test Workshop
   (HLDVT)*, 2006.
   [IEEE](https://ieeexplore.ieee.org/document/4110065)
5. Y. Oddos, K. Morin-Allory, and D. Borrione. "From Assertion-Based
   Verification to Assertion-Based Synthesis." In *Advances in Design Methods
   from Modeling Languages for Embedded Systems and SoCs*, Springer, 2010.
   [Springer](https://link.springer.com/chapter/10.1007/978-3-642-23120-9_6)

### Standards

6. IEEE Std 1800-2017. *IEEE Standard for SystemVerilog — Unified Hardware
   Design, Specification, and Verification Language*. Clauses 16 (Assertions)
   and 20 (Utility system tasks and functions).
   [IEEE](https://ieeexplore.ieee.org/document/8299595)

### Tools Used

7. slang — SystemVerilog compiler and language services library (MIT). Used as
   the SVA frontend via `--ast-json`.
   [GitHub](https://github.com/MikePopoloski/slang)
8. Yosys and SymbiYosys — open-source synthesis and formal verification
   front-end. Used for BMC, k-induction, and synthesis acceptance.
   [GitHub](https://github.com/YosysHQ/oss-cad-suite-build)
9. Verilator — SystemVerilog simulator and linter. Used as a co-simulation
   oracle and generated-RTL lint gate.
   [GitHub](https://github.com/verilator/verilator)
10. Icarus Verilog — event-driven Verilog simulator. Used as the primary
    co-simulation oracle.
    [GitHub](https://github.com/steveicarus/iverilog)

The NFA composition engine, token-passing network construction, and the
checker-tree optimizer (constant folding, boolean simplification, common
subexpression elimination, dead-logic pruning) are implemented directly in this
project rather than delegated to an automata library.

### Citing sva2rtl

If sva2rtl is useful in academic work, please cite it as software:

```bibtex
@software{sva2rtl,
  title  = {sva2rtl: A SystemVerilog Assertion to Synthesizable RTL
            Monitor Compiler},
  year   = {2026},
  note   = {Version 1.7.1},
  url    = {https://github.com/VeriSymbolic-AI/sva2verilog}
}
```

## License

Licensed under the Business Source License 1.1 (BSL-1.1).

- Copying, modification, redistribution, and non-production use are permitted
- Production use is permitted by the Additional Use Grant unless it offers the
  work to third parties on a hosted or embedded basis competitive with the licensor
- Uses outside those terms require an alternative license or must cease
- Converts to Apache License 2.0 on 2030-05-29

See [LICENSE](LICENSE) for full terms.
