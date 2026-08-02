# Formal Verification and Advanced-SVA Guide

This guide explains what sva2rtl verifies, how to reproduce the checked-in
formal gates, how the compiler makes a bounded advanced-SVA subset usable with
open-source tools, and what to do when a property is outside that subset.

The short version is:

1. `slang` parses and elaborates the original SystemVerilog project.
2. sva2rtl lowers a supported finite-state SVA property to ordinary
   synthesizable RTL.
3. Icarus and Verilator execute the generated monitor against an independent
   behavioral reference.
4. SymbiYosys drives the generated monitor and an independently authored
   reference monitor with the same unconstrained inputs and searches for an
   observable disagreement.
5. Yosys and Verilator separately check synthesis and lint acceptance.

This is a verification workflow, not a blanket correctness certificate. The
authoritative per-construct evidence and remaining gaps are in
[SUPPORT_MATRIX.md](SUPPORT_MATRIX.md).

## Why Lower SVA to RTL?

An SVA-capable parser, simulator, formal engine, and synthesizer solve different
problems. A tool may parse a temporal operator but not simulate it, synthesize
it, or support it in its formal frontend. Verilator, for example, documents
partial assertion support, while SymbiYosys primarily consumes a formal Verilog
model through Yosys.

sva2rtl separates these concerns:

```text
full-project parsing        bounded temporal lowering       standard RTL tools
SVA + design context  -->  monitor state/counters/NFA  --> simulation/synthesis/formal
       slang                       sva2rtl                 Icarus/Verilator/Yosys/SBY
```

The compiler does not ask the downstream open-source tool to implement the
original high-level operator. It converts each supported bounded operator into
explicit state, counters, token movement, and output logic first. The
downstream tool sees normal SystemVerilog or Verilog-2001 RTL.

This currently covers fixed and ranged delay/repetition, implication,
`first_match`, fixed goto/non-consecutive repetition, bounded NFA-liftable
`intersect`/`within`/`throughout`, bounded eventually/always, and weak
until forms. It does not make every legal SVA property synthesizable or prove
that every implemented row is industrially complete.

## Evidence Model

Each verification layer answers a different question:

| Layer | Question answered | What it does not prove |
|---|---|---|
| Independent Python oracle | Do sampled traces match a separate semantic model? | All possible traces |
| Icarus + Verilator | Do two simulation engines agree with the reference on exercised traces? | Unexercised states or synthesis correctness |
| BMC (`sby`, mode `bmc`) | Is there a counterexample within depth `k`? | Behavior after `k` cycles |
| Induction (`sby`, mode `prove`) | Does the modeled safety/equivalence invariant hold for all reachable states when the proof converges? | Behavior excluded by harness assumptions |
| Cover (`sby`, mode `cover`) | Can critical pass/fail/disable/overlap states be reached within the bound? | Equivalence by itself |
| Yosys synthesis + Verilator lint | Is the generated structure accepted by independent RTL tools? | Temporal semantic equivalence |
| Mutation testing | Can the selected tests detect reviewed injected faults? | Completeness outside the mutation model |

A green layer must not be promoted into a stronger claim. In particular,
synthesis acceptance is not semantic equivalence, a BMC pass is not an
unbounded proof, and a mutation score is not a proof of completeness.

## Prerequisites

The repository uses a locked Python environment and expects these executables
on `PATH`:

- Python 3.12+
- `slang` 11.0+
- `iverilog`
- Verilator 5.028 for exact CI parity
- Yosys, SymbiYosys (`sby`), and Z3 from one coherent OSS CAD Suite release
- `uv` 0.12.1 for exact CI parity

The workflows pin the exact tool installers and versions. For results intended
to match CI, use the versions in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml),
[`differential-nightly.yml`](.github/workflows/differential-nightly.yml), and
[`formal-full.yml`](.github/workflows/formal-full.yml) rather than a floating
system package.

Check the local environment before treating skips as evidence:

```bash
uv --version
python3 --version
slang --version
iverilog -V
verilator --version
yosys --version
sby --version
z3 --version
```

Then install the locked Python dependencies:

```bash
uv sync --dev --frozen
```

If `sby`, Yosys, a simulator, or slang is absent, the corresponding tests may
skip or fail. A missing-tool skip means “not executed”; it is never a pass.

## Compile a Property

Given a source file such as:

```systemverilog
module protocol(input logic clk, rst_n, req, ack);
  req_ack: assert property (
    @(posedge clk) disable iff (!rst_n)
    req |-> ##[1:3] ack
  );
endmodule
```

generate monitor RTL with:

```bash
sva2rtl protocol.sv --property req_ack -o generated/
```

Real projects should pass the same include paths, defines, filelists, top,
parameters, and libraries used to elaborate the design:

```bash
sva2rtl rtl/top.sv \
  -F project/files.f \
  -I rtl/include \
  -D ENABLE_ASSERTS=1 \
  --top soc_top \
  -G DATA_WIDTH=64 \
  -y rtl/lib -Y .sv \
  --single-unit \
  -o generated-monitors/
```

Compilation alone establishes only that the property was accepted and RTL was
emitted. It does not establish semantic equivalence.

## Build a Non-Circular Formal Miter

The formal tests use two different proof targets:

- `src/sva2rtl/formal.py` checks optimized RTL against unoptimized RTL. This
  protects optimizer semantics but cannot prove the original translation.
- `src/sva2rtl/formal_equiv.py` compares emitted RTL against an independently
  written reference derived from the property semantics. This is the stronger
  SVA-to-RTL check.

For a new operator or production property, build the second kind of check:

```text
                         same free inputs
                              |
                  +-----------+-----------+
                  |                       |
          generated monitor       independent reference
                  |                       |
       pass/fail/active/...       pass/fail/active/...
                  |                       |
                  +---------- assert equal+
```

The reference must not import compiler IR, reuse composer timing, instantiate
the generated template, or calculate expected results by calling production
oracle code. A structurally different shift-register or explicit-state model is
preferred.

### Define the Harness Contract

Before running a solver, record these choices:

- Clock and reset convention.
- `start` mode: continuous, single shot, or arbitrary.
- Whether `disable_i` is held low or arbitrary.
- Whether reset occurs only initially or can recover after activity.
- Compared outputs: at minimum `pass`/`fail`; where applicable also `active`,
  `attempt_fired`, `disabled_o`, and `overflow_flag`.
- Overlapping-attempt policy and finite slot budget.
- All environmental assumptions and why each is valid.
- BMC/cover depth and why it exceeds the longest relevant property latency.

The repository represents these choices with `FormalHarnessConfig` and
`FormalOutputContract`. Stronger tests vary start, disable, and reset instead
of tying them to convenient constants.

### Require Reachability

An assertion can pass vacuously if reset never releases, start never fires, or
the reference state is unreachable. Add cover probes for critical outcomes such
as pass, fail, disable, overlap, or overflow. sva2rtl runs required cover probes
as a separate `mode cover` task after the primary BMC/prove task.

Project policy is fail-closed:

- primary proof fails or produces a counterexample: **FAIL**;
- primary proof passes but a required cover is not reached: **UNKNOWN**;
- solver error or timeout: **ERROR/UNKNOWN**, never PASS;
- only primary PASS plus all required covers PASS is admissible evidence.

### Interpret the Result

| Result | Permitted statement |
|---|---|
| BMC PASS at depth 20 | No modeled disagreement was found in cycles 0 through 20 under the listed assumptions |
| `prove` PASS | The modeled equivalence invariant was proven for all reachable states under the listed assumptions |
| Cover PASS at depth 20 | The named outcome is reachable within 20 cycles |
| BMC/prove FAIL | A counterexample or proof failure exists; inspect the trace and fix the implementation, reference, or invalid assumption |
| Cover FAIL after proof PASS | Evidence is UNKNOWN because the proof may be vacuous or the bound may be too small |
| xfail/skip | The case is a recorded boundary and contributes no passing evidence |

Always retain the exact source SHA, tool versions, harness, mode, depth,
assumptions, result log, and counterexample trace. Without those, “formal PASS”
is not replayable evidence.

## Reproduce the Repository Gates

### 1. Static quality and metadata

```bash
uv run ruff check src/ tests/
uv run mypy --strict \
  src/ \
  tests/generated_rtl_cases.py \
  tests/test_formal_sva_equiv.py \
  tests/test_formal_kinduction.py \
  tests/test_formal_templates.py \
  tests/test_sequential.py
uv lock --check
```

### 2. Full Icarus and Verilator simulation

```bash
uv run pytest tests/ \
  --simulator=iverilog -v --timeout=120

uv run pytest tests/ \
  -m "simulation and not differential_slow" \
  --simulator=verilator -v --timeout=120
```

The first command is the broad suite and includes the default Icarus simulation
axis. The second command is the explicit Verilator simulation axis. A test that
passes under only one backend does not satisfy the dual-oracle contract.

### 3. Generated RTL acceptance

```bash
uv run pytest \
  tests/test_synthesis_gates.py \
  tests/test_generated_lint.py \
  -v --timeout=180
```

### 4. Full formal suite

The remote Full Formal workflow runs six isolated shards. The equivalent local
selection is:

```bash
uv run pytest \
  tests/test_formal_passes.py \
  tests/test_formal_templates.py \
  tests/test_formal_sva_equiv.py \
  tests/test_v151_nfa_bmc.py \
  tests/test_v151_p2_bmc.py::TestOverlapImplNfaMiter \
  tests/test_v151_p2_bmc.py::TestNonoverlapImplNfaMiter \
  tests/test_formal_kinduction.py \
  -v --timeout=600
```

One dynamically classified bounded-liveness induction non-convergence is the
only currently admitted xfail in the checked-in workflow. A counterexample,
tool failure, unexpected skip, or any other xfail is a hard failure.

### 5. Differential tests on both simulators

```bash
uv run pytest tests/test_differential.py \
  -m "not differential_slow" --simulator=iverilog \
  --hypothesis-seed=20260722 -v --timeout=600
uv run pytest tests/test_differential.py \
  -m "not differential_slow" --simulator=verilator \
  --hypothesis-seed=20260722 -v --timeout=600

uv run pytest tests/test_differential.py \
  -m differential_slow --simulator=iverilog \
  --hypothesis-seed=20260802 -v --timeout=600
uv run pytest tests/test_differential.py \
  -m differential_slow --simulator=verilator \
  --hypothesis-seed=20260802 -v --timeout=600
```

Use a fixed seed for replay and a rotating date seed for exploration. Preserve
sanitized mismatch artifacts so a failure becomes a deterministic regression.

### 6. Mutation tests

```bash
uv run python tools/mutation/run_mutation.py --module bool_semantics.py
uv run python tools/mutation/run_mutation.py --module behavioral_oracle.py
uv run python tools/mutation/run_mutation.py --module composer.py
uv run python tools/mutation/run_mutation.py --module ast_importer.py
uv run python tools/mutation/run_template_mutation.py
```

Read the denominator. Invalid mutants and uncovered candidates are reported
separately; a 100% score over covered valid mutants is not 100% project
completeness.

### 7. Package the exact source

```bash
uv build --out-dir dist
uv run python tools/ci/smoke_distribution.py dist/*.whl dist/*.tar.gz
```

## Add or Extend an Advanced Operator Safely

An operator is not complete when it merely parses or emits compilable RTL. Use
this minimum evidence chain:

1. Add a real `.sv` fixture parsed by slang, including accepted and rejected
   syntax variants.
2. Map the slang AST to typed immutable IR without losing bounds or clocking.
3. Normalize only semantics-preserving sugar.
4. Lower the operator to an explicit bounded implementation: counters for
   ranges, token-passing composition for hierarchical sequences, or an NFA for
   multi-path timing.
5. Enforce resource budgets at compile time. Do not silently truncate ranges,
   states, or overlapping attempts.
6. Add a separate Python semantic model and deterministic trace tests.
7. Run the same traces through Icarus and Verilator.
8. Write a structurally independent formal reference and compare the complete
   observable monitor contract.
9. Run BMC beyond maximum latency, attempt induction where appropriate, and
   require critical cover reachability.
10. Add Yosys synthesis, Verilator lint, negative diagnostics, differential
    generation, replay, and reviewed mutation faults.
11. Update `SUPPORT_MATRIX.md` with exact files, bounds, assumptions, and the
    source SHA. Do not promote a row based only on a workflow-level green run.

## Current Limitations

The current v1.7.1 boundary is deliberately finite and fail-closed:

- The support matrix currently contains **zero `Fully supported` construct
  rows**. Implemented rows have bounded evidence or a trusted boundary.
- Boolean expressions are a structured two-state subset. Arithmetic,
  reductions, general part-selects, calls, and X/Z semantics remain outside it.
- Sampled-value operands are scalar; packed vectors, arrays, compound
  expressions, and optional clock/gating arguments are not supported.
- Ranged goto/non-consecutive repetition (`[->M:N]`, `[=M:N]` with `M < N`),
  local variables, recursive properties, and several system functions remain
  unsupported.
- NFA-lifted nested multi-path composition has a compile-time state budget
  `K <= 32`; bounded implication concurrency has finite thread slots.
- Unbounded eventual obligations have no finite completion deadline under the
  current pass/fail monitor interface. Unbounded `always` and other legal forms
  are also not implemented even where a different streaming monitor could be
  designed. Rejection is a v1 scope decision, not a claim that every such form
  is mathematically impossible in hardware.
- Experimental multi-clock output uses a 2-DFF level synchronizer. It can miss
  narrow pulses or merge events and is not CDC or metastability sign-off.
- slang is a trusted parsing/elaboration boundary. The maintained real-project
  corpora are small and not representative of arbitrary industrial builds.
- Formal results apply only to the checked harness, assumptions, outputs, depth
  or induction model, and exact tool/source versions. They are not chip-level
  correctness or production-release proof.

## Safe Alternatives for Unsupported Properties

Choose the fallback based on the semantic requirement rather than forcing a
property through the compiler:

| Situation | Recommended alternative | Trade-off |
|---|---|---|
| A finite system deadline exists | Replace `$`/unbounded eventuality with a reviewed `[m:n]` bound derived from the protocol | Changes the property unless the bound is a real requirement |
| Ranged goto/non-consecutive repetition | Expand a small finite range into explicit fixed-count properties, or write a bounded reference-state monitor | More properties/RTL and more proof state |
| Local variables, complex expressions, arrays | Compute auxiliary RTL signals first, then assert over scalar supported signals | Auxiliary logic becomes part of the trusted/modelled boundary |
| Full legal SVA needed only in simulation | Keep the original assertion and use a simulator with the required SVA semantics | No synthesizable FPGA monitor |
| Full SVA or unbounded/liveness proof needed | Use a commercial formal platform or another independently supported frontend on the original property | Licensing/tool access; still requires assumption and cover review |
| Multi-clock event delivery | Use a reviewed handshake, toggle, or asynchronous FIFO CDC protocol and verify each domain separately; run CDC analysis | Higher area/latency but avoids the lossy level synchronizer |
| Online hardware verdict is impossible or misleading | Evaluate traces offline, or split a liveness goal into safety assertions plus explicit progress covers/fairness assumptions | Produces different evidence, not a finite hardware PASS certificate |
| Property is too large for the state/thread budget | Decompose it into independently checkable obligations with an explicit composition argument | Decomposition can miss interactions if the argument is incomplete |

For critical use, retain the original SVA as the specification and treat the
generated monitor as one implementation. Cross-check it with an independent
simulator or formal tool whenever possible.

## Remote Same-Commit Qualification

Local results and historical green runs do not qualify a new commit. After
pushing the exact source SHA, let the push trigger `ci.yml`, then manually
dispatch the two scheduled workflows on `main`:

```bash
gh workflow run differential-nightly.yml --ref main
gh workflow run formal-full.yml --ref main
```

Record each run ID, head SHA, conclusion, and job conclusions. Update support
evidence only when the run head SHA equals the intended executable commit.

## Further Reading

- [Support matrix and evidence ledger](SUPPORT_MATRIX.md)
- [Supported constructs and diagnostics](SUPPORTED_CONSTRUCTS.md)
- [Industrial validation gaps](INDUSTRIAL_VALIDATION_GAPS.md)
- [YosysHQ SBY documentation](https://yosyshq.readthedocs.io/projects/sby/en/stable/)
- [YosysHQ formal Verilog extensions](https://yosyshq.readthedocs.io/projects/sby/en/latest/verilog.html)
- [Verilator language support](https://verilator.org/guide/latest/languages.html)
