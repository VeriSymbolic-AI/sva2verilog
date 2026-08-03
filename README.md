# sva2rtl — SVA to Synthesizable RTL Monitor Compiler

An open-source compiler that lowers a supported, bounded subset of SystemVerilog
Assertions (SVA) into synthesizable hardware monitor modules. Generated monitors
can be simulated with Icarus Verilog and Verilator or synthesized to FPGA. The
project is licensed under [Apache License 2.0](LICENSE).

sva2rtl is not a full IEEE 1800 assertion implementation and does not claim
that every accepted construct is industrially complete. The authoritative
per-construct boundary is [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md); it currently
contains **zero `Fully supported` rows**. Implemented rows remain bounded
evidence until their complete evidence chain is closed.

## What It Does

sva2rtl takes supported SVA properties/sequences as input and generates
area-conscious SystemVerilog (or Verilog-2001) monitor modules. Each monitor
exposes a standard interface for integration into verification, emulation, and
FPGA prototyping flows.

**Key capabilities:**
- Compiles the documented finite-state SVA subset into synthesizable RTL
- Verifies selected unbounded SVA directly against a DUT with an open
  formal-only backend, without asking Yosys to parse the original SVA
- Records explicit two-state/single-clock/local-variable semantic profiles and
  machine-readable `UNSUPPORTED` evidence at hard boundaries
- Token-passing composition model for bounded concurrent-attempt evaluation
- Counter-encoded range operators for area efficiency
- Deterministic output suitable for formal equivalence checking

## Installation

The package is not currently published on PyPI. Install the current repository
source directly:

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

## Implemented SVA Overview

The tiers below organize implemented syntax; they are not certification levels.
For authoritative support status, exact subset boundaries, negative cases, and
verification evidence, see [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md).

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
| `disable iff` | Disable/reset condition | `disable iff (reset) ...` |
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

### Tier 3 — Bounded Monitor Operators (v1.4)

| Operator | Description | Example |
|----------|-------------|---------|
| `s_eventually [m:n]` | Bounded eventually (liveness) | `s_eventually [1:3] a` |
| `eventually [m:n]` | Bounded eventually (weak) | `eventually [0:4] a` |
| `always [m:n]` | Bounded always (liveness) | `always [1:3] a` |
| `s_always [m:n]` | Bounded always (strong) | `s_always [0:4] a` |
| `until` | Weak until (safety) | `a until b` |
| `until_with` | Weak until-with (safety) | `a until_with b` |

### Formal-only Unbounded Operators

These forms do not generate finite-verdict monitor RTL. The separate
`sva2rtl-formal` command lowers their proof obligations to Yosys `$live` / `$fair`
cells and SymbiYosys `mode live`:

| Property shape | Formal lowering | Synthesizable monitor |
|---|---|---|
| `s_eventually p` | Unbounded eventual obligation | Rejected |
| `a |-> s_eventually b` / `a |=> s_eventually b` | Arbitrary witness attempt plus eventual discharge | Rejected |
| `a s_until b` / `a s_until_with b` | Safety obligation plus eventual `b` | Rejected |

This backend is conditional on a compatible Super Prove executable. If it is
missing, the result is `UNKNOWN`, never a bounded or vacuous `PASS`.

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

Unbounded eventual obligations (`s_eventually a`, `s_until`, and
`s_until_with`) have no finite completion deadline under the monitor contract,
so the synthesis CLI rejects them. The formal CLI accepts the documented
single-clock Boolean shapes and routes them to an unbounded live engine instead
of changing their meaning. Unbounded `always` and unsupported nested forms
remain outside the implemented frontend. Nested
multi-path composition (`intersect` / `within` / `throughout`) is supported only
when it is NFA-liftable and the total state budget satisfies K ≤ 32
(compile-time enforced).

For construct explanations and generated templates, see
[SUPPORTED_CONSTRUCTS.md](SUPPORTED_CONSTRUCTS.md). For exact evidence status,
use [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md).

## How This Bridges the Open-Source SVA Gap

Open-source tools do not expose one uniform “full SVA” path: a tool may parse an
operator but only partially simulate assertions, while an open formal or
synthesis frontend may accept a smaller language. sva2rtl uses slang for
project-aware parsing, then lowers supported temporal operators into explicit
state, counters, token-passing logic, and bounded NFAs. Icarus, Verilator,
Yosys, and SymbiYosys therefore consume ordinary generated RTL rather than the
original advanced operator.

The monitor translation covers useful advanced bounded forms such as ranged delay and
repetition, implication, `first_match`, fixed goto/non-consecutive repetition,
NFA-liftable `intersect`/`within`/`throughout`, and bounded liveness. A separate
formal-only path lowers selected unbounded eventual and strong-until properties
to standard Yosys formal primitives; the original SVA is retained as evidence
but never sent to Yosys. Unsupported or unsafe forms fail with an actionable
error instead of being silently approximated. See
[Formal Verification and Advanced-SVA Guide](FORMAL_VERIFICATION.md)
for the lowering model, proof workflow, limitations, and safe alternatives.

### Verify a DUT without a commercial SVA frontend

Keep the DUT and the SVA property in separate files, then run:

```bash
sva2rtl-formal \
  --dut rtl/dut.sv \
  --property-file properties/progress.sv \
  --property req_eventually_ack \
  --top dut \
  --output evidence/progress
```

Safety and bounded obligations use the open Yosys/SymbiYosys path. Selected
true-liveness obligations use `mode live` and require Super Prove; pass
`--suprove-path /path/to/suprove` if it is not on `PATH`. User-supplied
fairness is never inferred: each `--fairness ready` means the explicit
assumption `GF(ready)` and is recorded and hashed in the evidence bundle.
The default `--logic-semantics two-state` profile rejects X/Z-dependent SVA.
Multi-clock properties never collapse to the primary clock; they produce
`UNSUPPORTED` evidence and must be split around a separately verified sampled
handoff. One formal-only scalar local-capture shape is documented in the
[formal guide](FORMAL_VERIFICATION.md#explicit-hard-boundary-profiles).

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
uv run pytest tests/ --simulator=iverilog
uv run pytest tests/ -m "simulation and not differential_slow" \
  --simulator=verilator
```

Run generated-RTL and formal gates only after confirming Yosys, SymbiYosys,
Z3, both simulators, and slang are installed. Exact commands and result
interpretation are in [FORMAL_VERIFICATION.md](FORMAL_VERIFICATION.md).

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

Correctness of a monitor compiler cannot be established by compiling the same
property twice and comparing the two outputs. sva2rtl separates specification
semantics from implementation structure and records proof strength without
turning a bounded result into a universal claim.

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
| 3 | Bounded model checking (SymbiYosys `bmc`) | No counterexample within a stated cycle bound and harness |
| 4 | k-induction (SymbiYosys `prove`) | Unbounded modeled equivalence for converging safety checks under stated assumptions |
| 5 | live proof (SymbiYosys `live`, Super Prove) | Unbounded modeled liveness for the documented formal-only shapes under stated assumptions/fairness |
| 6 | Synthesis and lint acceptance (Yosys, Verilator) | Generated RTL is structurally synthesizable |
| 7 | Source-level differential testing (Hypothesis) | Randomized specification-to-RTL agreement |
| 8 | Required cover reachability | Critical pass/fail/disable/overlap states are reachable within the stated bound |

Layers 3 and 4 differ in strength and this distinction is preserved throughout
the documentation. A BMC result is a *bounded* claim: it certifies that no
counterexample exists up to depth *k*. A k-induction result in `prove` mode is
an *unbounded modeled* claim over all states reachable under the harness
assumptions. Rows in
[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) record which of the two applies, and the
bound where BMC is the strongest available result. A required cover runs as a
separate task: proof PASS plus an unreachable critical cover is reported as
`UNKNOWN`, not PASS.

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

- Unbounded eventual obligations and strong-until forms are formal-only: the
  synthesis backend rejects them, while the formal backend currently accepts
  only documented single-clock Boolean/root-implication shapes. A real live
  proof is conditional on Super Prove; otherwise the result is `UNKNOWN`.
- Other unbounded forms, nested liveness combinations, liveness under property
  negation/conditionals, and general sequence eventuality remain unsupported.
- Formal semantics are explicitly two-state and single-clock. X/Z-dependent
  properties and multi-clock temporal composition are `UNSUPPORTED`; the
  experimental multi-clock monitor path is not used as formal evidence.
- Local variables are limited to one documented automatic scalar capture under
  an overlapping implication and symbolic witness. General match items,
  vector/multiple locals, ranged timing, and monitor synthesis reject.
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

For tool prerequisites, exact local and CI-equivalent commands, harness modes,
assumption review, result interpretation, advanced-operator extension steps,
and alternatives for unsupported SVA, read
[FORMAL_VERIFICATION.md](FORMAL_VERIFICATION.md).

## When to Use an Alternative

sva2rtl deliberately rejects forms it cannot lower without changing semantics.
The safe fallback depends on the requirement:

- Convert an unbounded requirement to `[m:n]` only when the protocol has a real,
  reviewed finite deadline.
- Precompute auxiliary scalar RTL for complex expressions, arrays, or local
  state, then verify that auxiliary logic as part of the trusted boundary.
- Keep the original SVA and use a simulator with the required assertion support
  when no synthesizable monitor is needed.
- For documented unbounded shapes, use `sva2rtl-formal` with the open live
  backend. For other full-SVA semantics, use an independently supporting formal
  frontend (open or commercial) and still review assumptions and covers.
- Replace experimental multi-clock level synchronization with a reviewed
  handshake, toggle, or asynchronous FIFO and run dedicated CDC analysis.
- Decompose a state-heavy property into smaller obligations only with an
  explicit argument that the obligations imply the original property.

The full decision table, including trade-offs for ranged goto, unbounded
liveness, offline trace checking, and hand-authored monitors, is in
[FORMAL_VERIFICATION.md](FORMAL_VERIFICATION.md#safe-alternatives-for-unsupported-properties).

## Cross-Tool Validation

sva2rtl's checked-in gates use slang, Icarus, Verilator, Yosys, SymbiYosys,
and Z3. An independent commercial simulator or formal engine can add useful
semantic diversity for subtle sampling, `disable iff`, repetition,
`first_match`, and clocking cases. Such a comparison is complementary evidence;
it does not automatically promote a support row or prove a chip.

Organizations interested in contributing reproducible cross-tool results can
open an issue titled `Cross-tool validation` and include tool/version, exact
source SHA, harness assumptions, proof mode/depth, and sanitized logs.

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

Licensed under the [Apache License, Version 2.0](LICENSE) (`Apache-2.0`). The
license permits use, modification, and distribution subject to its terms and
includes an express patent grant; it does not provide a warranty or grant
trademark rights. The `LICENSE` file is authoritative.
