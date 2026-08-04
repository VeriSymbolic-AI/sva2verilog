# Formal Verification and Advanced-SVA Guide

This guide explains what sva2rtl verifies, how to reproduce the checked-in
formal gates, how the compiler makes a bounded advanced-SVA subset usable with
open-source tools, and what to do when a property is outside that subset.

The short version is:

1. `slang` parses and elaborates the original SystemVerilog project.
2. sva2rtl classifies the property before choosing a backend: finite/safety
   forms lower to monitor or proof RTL; selected unbounded forms lower to
   Yosys `$live` / `$fair` proof obligations.
3. Icarus and Verilator execute the generated monitor against an independent
   behavioral reference.
4. `sva2rtl-formal` keeps the original SVA out of Yosys, binds generated proof
   logic to the DUT, and runs safety, cover, or live tasks as appropriate.
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

The monitor backend currently covers fixed and ranged delay/repetition, implication,
`first_match`, fixed goto/non-consecutive repetition, bounded NFA-liftable
`intersect`/`within`/`throughout`, bounded eventually/always, and weak
until forms. The formal-only backend additionally covers documented Boolean
`s_eventually`, implication-to-`s_eventually`, and strong-until shapes. It does
not make every legal SVA property synthesizable or prove that every implemented
row is industrially complete.

## Evidence Model

Each verification layer answers a different question:

| Layer | Question answered | What it does not prove |
|---|---|---|
| Independent Python oracle | Do sampled traces match a separate semantic model? | All possible traces |
| Icarus + Verilator | Do two simulation engines agree with the reference on exercised traces? | Unexercised states or synthesis correctness |
| BMC (`sby`, mode `bmc`) | Is there a counterexample within depth `k`? | Behavior after `k` cycles |
| Induction (`sby`, mode `prove`) | Does the modeled safety/equivalence invariant hold for all reachable states when the proof converges? | Behavior excluded by harness assumptions |
| Liveness (`sby`, mode `live`) | Does every selected modeled obligation eventually discharge under the listed fairness assumptions? | Unsupported shapes, unfair environments, or hardware PASS generation |
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
- For unbounded live proof only: Super Prove (`suprove`), currently listed by
  [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build#architecture-support)
  for Linux x64; other platforms may need a compatible remote runner or their
  own build
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
suprove --version
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

## Verify a User DUT Directly

The formal CLI is the primary workaround for open formal frontends that cannot
parse advanced SVA. Put assertion-free design sources under `--dut` and keep the
original assertion in a separate property file:

```systemverilog
module progress_spec(input logic clk, rst_n, req, ack, ready);
  req_eventually_ack: assert property (
    @(posedge clk) disable iff (!rst_n)
    req |-> s_eventually ack
  );
endmodule
```

```bash
sva2rtl-formal \
  --dut rtl/dut.sv \
  --property-file properties/progress.sv \
  --property req_eventually_ack \
  --top dut \
  --suprove-path /path/to/suprove \
  --output evidence/req-eventually-ack
```

The evidence bundle contains copied and hashed DUT/property inputs,
`formal_bind.sv`, `formal.sby`, a separate cover task, the property slice,
tool discovery, logs, traces, and `result.json`. The original property is an
evidence input only and is intentionally absent from `yosys_inputs`; Yosys sees
the DUT plus generated formal primitives.

This separation is enforced rather than assumed. Before bundle creation, slang
elaborates the selected DUT top independently. Concurrent and immediate
assert, assume, or cover statements in any `--dut` source are errors. Every
observed signal must exist in the DUT and exactly match the property
declaration's packed width and signedness; clock and reset must be one bit. The resulting
`evidence/interface_contract.json` is hashed by the manifest. A property that
declares a 1-bit signal while the DUT exposes a vector is rejected instead of
silently proving only the low bit. Only clock, reset, fairness, and property-
observed DUT signals enter this interface type check; unrelated internal or
debug signals do not expand the property contract. The accepted type grammar
for contract signals is intentionally strict: scalar integral types and one
fixed packed dimension are supported. Multi-dimensional packed, unpacked-array,
aggregate, or trailing type syntax rejects before a proof bundle or Yosys input
is created rather than being partially parsed or silently flattened. The CLI
still records the rejection in a source-isolated `UNSUPPORTED` evidence bundle.

### Supported formal-only liveness shapes

| Original property | Generated proof obligations |
|---|---|
| `s_eventually p` | `GF(p)` |
| `a |-> s_eventually b` | Every arbitrarily selected matching antecedent attempt eventually reaches `b` |
| `a |=> s_eventually b` | The same obligation, armed one sample later |
| `a s_until b` | Invariant `a || b` plus `GF(b)` |
| `a s_until_with b` | Invariant `a` before/at completion plus `GF(b)` |

Operands in this initial route must be structured Boolean expressions in one
clock domain. Nested liveness, property conditionals/negation around liveness,
and arbitrary sequence operands remain unsupported. Unbounded Boolean `always`
is supported by the separate direct-invariant safety route and does not require
Super Prove. Restricted local-variable support uses the separately documented
symbolic-witness profile. The ordinary monitor CLI rejects all these
formal-only nodes so they cannot accidentally become a misleading finite PASS
output.

### Fairness is explicit, never guessed

Some DUTs can satisfy progress only when their environment is fair. For
example, `--fairness ready` adds the model assumption `GF(ready)`—`ready` must
be true infinitely often:

```bash
sva2rtl-formal \
  --dut rtl/dut.sv \
  --property-file properties/progress.sv \
  --property req_eventually_ack \
  --top dut \
  --fairness ready \
  --output evidence/progress-with-fairness
```

Every fairness signal is identifier-validated, serialized to
`evidence/fairness.json`, and hashed by the manifest. Fairness is an assumption
about the model, not a discovered fact about the design. A proof under an
unjustified fairness assumption can hide a real deadlock, so it requires the
same review as any other formal assumption.

Fairness identifiers must resolve to a one-bit DUT signal. For a vector
condition, create and review an explicit one-bit RTL predicate (for example a
reduction OR) and use that predicate as the fairness signal; implicit vector
truncation is never allowed.

### Replay-bound decomposition for an unsupported original

An unsupported original property can be discharged through engineering
decomposition only when every evidence link is independently replayable. Pass a
schema-version-2 JSON certificate with `--decomposition-certificate`. It must
bind all of the following by SHA-256:

- the unchanged original property and ordered DUT sources;
- every subproperty source and its `sva2rtl-formal` `result.json`;
- a separate equivalent-or-stronger relation proof for
  `(and subproperties) -> original`;
- the exact checker identities and ordered subproperty hashes.

Each referenced result must be an unbounded `PROVEN` result with `REACHED`
cover, zero proof/cover exit codes, a matching manifest hash, matching property
and DUT hashes, a manifest-bound checker identity, deterministic replay
commands, and PASS logs. Its selected top, clock, reset, unbounded proof mode,
attempt model, two-state profile, and fairness assumptions must exactly match
the aggregate run. The complete
relation and member replay bundles are copied under
`evidence/decomposition/`. A hand-written JSON file containing only
`"status": "PROVEN"` is rejected.

This aggregate route requires `--mode prove`; it never upgrades a BMC run into
an unbounded result. If the original shape is unsupported but this chain validates, the original SVA
is retained only as hashed evidence and the aggregate has empty `yosys_inputs`.
The aggregator revalidates every copied proof before reporting `PROVEN`. This
does not invent a decomposition or certify that a human-authored relation model
expresses the intended requirement: the relation property itself remains a
reviewed formal-model boundary, exactly like assumptions in any proof harness.
Use a wrong relation model and the proof answers the wrong question.

Certificate paths are relative to the certificate file. The minimal shape is:

```json
{
  "schema_version": 2,
  "relation": "equivalent",
  "relation_status": "PROVEN",
  "relation_checker": "sva_relation_checker",
  "relation_proof_artifact_path": "relation-proof/result.json",
  "relation_proof_artifact_sha256": "<sha256>",
  "original_property_sha256": "<sha256>",
  "dut_source_sha256s": ["<sha256-in---dut-order>"],
  "subproperties": [
    {
      "id": "bounded_obligation_1",
      "property_path": "properties/bounded_obligation_1.sv",
      "property_sha256": "<sha256>",
      "obligation_status": "PROVEN",
      "checker": "sva_bounded_obligation_1",
      "proof_artifact_path": "proof-1/result.json",
      "proof_artifact_sha256": "<sha256>"
    }
  ]
}
```

The relation result additionally records `relation`,
`original_property_sha256`, ordered `subproperty_sha256s`, and ordered
`dut_source_sha256s`; these must agree with the certificate. Create the proof
and cover runs first, add the relation claim to that replay-bound result, then
hash the final result file into the certificate. Changing any source, result,
manifest, or log requires regenerating the certificate.

After bundle construction, aggregation uses the copied and manifest-hashed
property/DUT snapshot rather than reopening the caller's original paths. The
bundle therefore remains inspectable and aggregatable if the workspace files
move later; changing a copied bundle input still fails the pre-run hash gate.

The result schema binds each normal proof to `manifest_sha256`,
`property_sha256`, checker identity, and explicit replay commands. Inputs are
rehashed immediately before solver execution; modifying a generated bind,
source, project, profile, or manifest invalidates the run.

`--force` can replace only a directory previously created by this formal
workflow and carrying its private evidence marker. It refuses filesystem/home/
working roots, DUT/property/decomposition-input ancestors, regular files, and
arbitrary non-evidence directories.

### What happens without Super Prove?

The compiler still builds the live AIG and runs the independent cover task, but
the primary result is `UNKNOWN` with installation guidance. BMC may find a
finite counterexample to a progress encoding, but a bounded no-counterexample
result cannot prove that something eventually happens at an unknown future
time. Safe choices are:

1. Run the unchanged evidence bundle on a Linux x64 OSS CAD Suite worker that
   includes `suprove`.
2. Use a real, reviewed finite deadline only if the protocol specification
   actually has one; then verify the bounded property as safety.
3. Decompose the property into smaller obligations only with a checked
   equivalent/stronger relation certificate and `PROVEN` member artifacts.
4. Use another independently supporting formal frontend. Do not relabel its
   result as sva2rtl evidence unless inputs, assumptions, and semantics match.

This route partially replaces a commercial SVA tool: it removes the commercial
frontend requirement for the exact supported shapes and uses open formal IR.
It does not replace broad IEEE 1800 SVA semantics, commercial debug capacity,
CDC sign-off, or large industrial proof engines.

### Explicit hard-boundary profiles

Every normal or rejected formal bundle records and hashes
`evidence/semantic_profile.json`. The initial profile is deliberately narrow:

- `logic_semantics: two-state`: the solver models Boolean/bit-vector values.
  SVA literals or operators whose result depends on X, Z, or wildcard matching
  reject instead of coercing unknowns to 0/1.
- `clock_semantics: single-clock`: a nested `ClockedSeq` never collapses onto
  the primary clock. It returns `UNSUPPORTED`; the engineering workaround is to
  prove per-domain properties and separately verify a reviewed handshake,
  toggle, or asynchronous-FIFO handoff plus CDC signoff.
- `local_variable_semantics: restricted-symbolic-witness-only`: the accepted
  form is one automatic 1-bit `logic`/`bit`, one blocking capture assignment,
  positive fixed delay, Boolean guard/condition, and overlapping implication:

```systemverilog
sequence captured_check;
  logic saved;
  (guard, saved = data) ##2 (ack && data == saved);
endsequence
assert property (@(posedge clk) req |-> captured_check);
```

The formal backend selects an arbitrary `req` attempt, gives it a private
`captured_q`, and checks the delayed condition. Universal proof over the
unconstrained selector covers every attempt without sharing local state. The
local identifier is not a DUT port. Vector/multiple/static locals, nonblocking
or multiple match items, non-overlapping implication, ranged/dynamic delay, and
nested local semantics return `UNSUPPORTED`. Monitor synthesis also rejects
this formal-only IR.

For an unsupported boundary, the CLI exits 12 and still writes copied/hashed
inputs, the semantic profile, a sanitized reason/remediation, and
`result.json`. It writes no `formal.sby`, lists no Yosys inputs, and cannot
produce `PROVEN`.

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
| `live` PASS plus cover PASS | The modeled liveness obligation was proven under the recorded assumptions and fairness |
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

The remote Full Formal workflow runs eight isolated shards. The equivalent
local selection is:

```bash
uv run pytest \
  tests/test_formal_passes.py \
  tests/test_formal_templates.py \
  tests/test_formal_sva_equiv.py \
  tests/test_v151_nfa_bmc.py \
  tests/test_v151_p2_bmc.py::TestOverlapImplNfaMiter \
  tests/test_v151_p2_bmc.py::TestNonoverlapImplNfaMiter \
  tests/test_formal_kinduction.py \
  tests/test_formal_user_dut.py \
  tests/test_formal_safety_rewrites.py \
  tests/test_formal_advanced_safety.py \
  tests/test_formal_symbolic_witness.py \
  tests/test_formal_evidence_gates.py \
  tests/test_formal_boundaries.py \
  tests/test_formal_locals.py \
  tests/test_formal_status_corpus.py \
  tests/test_formal_liveness.py \
  -v --timeout=600
```

One dynamically classified bounded-liveness induction non-convergence is the
only currently admitted xfail in the checked-in workflow. A counterexample,
tool failure, unexpected skip, or any other xfail is a hard failure.

The command above qualifies the safety/equivalence shards. The live backend has
a separate conditional gate:

```bash
uv run pytest tests/test_formal_liveness.py -v --timeout=600
```

On a host without `suprove`, the real good/bad solver cases skip and the suite
instead checks source isolation, AIG preparation, cover reachability, and the
fail-closed `UNKNOWN` result. Those checks are useful pipeline evidence but are
not a completed live proof.

The checked-in real-source outcome catalog is
`tests/formal_user_dut/status_corpus.json`. It names fixtures for `PROVEN`,
counterexample `FAILED`, bounded/vacuous/missing-live `UNKNOWN`, semantic
`UNSUPPORTED`, and process `TIMEOUT`. Tests verify that DUT fixtures contain no
assertions and property fixtures remain separate evidence inputs.

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
uv run python tools/ci/check_release_privacy.py dist/*.whl dist/*.tar.gz
uv run python tools/ci/check_release_privacy.py
```

The installed-distribution smoke invokes both `sva2rtl` and
`sva2rtl-formal --compile-only` from a temporary directory, then checks the
semantic profile and confirms the original SVA is absent from Yosys inputs.
The privacy gate checks tracked source plus built archives without printing a
matched secret value.

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
  general part-selects, calls, multi-dimensional packed/unpacked arrays,
  aggregates, and X/Z semantics remain outside it. Supported identifiers are
  scalar integral types or have one fixed packed dimension.
- Sampled-value operands are scalar; packed vectors, arrays, compound
  expressions, and optional clock/gating arguments are not supported.
- Ranged goto/non-consecutive repetition (`[->M:N]`, `[=M:N]` with `M < N`),
  general local variables, recursive properties, and several system functions
  remain unsupported. Only the exact formal-only scalar capture shape above is
  accepted.
- NFA-lifted nested multi-path composition has a compile-time state budget
  `K <= 32`; bounded implication concurrency has finite thread slots.
- Unbounded Boolean `always` is supported only by the formal direct-invariant
  route; it deliberately has no finite-completion monitor PASS.
- Unbounded eventual and strong-until obligations have no finite completion
  deadline under the pass/fail monitor interface. They are formal-only for the
  exact shapes listed above; Super Prove absence yields `UNKNOWN`. Unbounded
  forms outside the documented Boolean profiles remain unsupported even where
  a different streaming monitor could be designed.
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
| Local variables, complex expressions, arrays, multi-dimensional packed or aggregate types | Compute auxiliary RTL signals or a reviewed one-dimensional packed alias first, then assert over supported signals | Auxiliary/flattening logic becomes part of the trusted/modelled boundary |
| Full legal SVA needed only in simulation | Keep the original assertion and use a simulator with the required SVA semantics | No synthesizable FPGA monitor |
| Full SVA or unbounded/liveness proof needed | Use `sva2rtl-formal` for the documented shapes; otherwise use another independently supported open or commercial frontend on the original property | Open live proof still requires Super Prove and explicit assumptions; unsupported SVA remains outside this tool |
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

The completed v2.0 executable baseline is
`e3526836912086fdc274528ca7735dd7b6a028e1`: CI
[`30908155956`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30908155956)
passed 13/13 jobs, nightly
[`30908168285`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30908168285)
passed 3/3 jobs, and Full Formal
[`30908170695`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30908170695)
passed 8/8 shards. This is workflow-level evidence for that exact executable,
not automatic promotion of any support-matrix row.

## Further Reading

- [Support matrix and evidence ledger](SUPPORT_MATRIX.md)
- [Supported constructs and diagnostics](SUPPORTED_CONSTRUCTS.md)
- [Industrial validation gaps](INDUSTRIAL_VALIDATION_GAPS.md)
- [YosysHQ SBY documentation](https://yosyshq.readthedocs.io/projects/sby/en/stable/)
- [SBY live mode and `aiger suprove`](https://symbiyosys.readthedocs.io/en/latest/reference.html)
- [Yosys formal `$live` and `$fair` cells](https://yosyshq.readthedocs.io/projects/yosys/en/v0.59.1/cmd/index_formal.html)
- [OSS CAD Suite architecture support](https://github.com/YosysHQ/oss-cad-suite-build#architecture-support)
- [YosysHQ formal Verilog extensions](https://yosyshq.readthedocs.io/projects/sby/en/latest/verilog.html)
- [Verilator language support](https://verilator.org/guide/latest/languages.html)
