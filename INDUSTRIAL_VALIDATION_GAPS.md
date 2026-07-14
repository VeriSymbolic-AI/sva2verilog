# Industrial Validation Gap Plan

> Date: 2026-07-14
> Scope: current main after v1.7.0 release + evidence chain hardening
> Reader: future maintainer, external reviewer, or industrial user evaluating trust
> Post-read action: decide and execute the next validation work needed before calling the project industrial-grade

## Executive Summary

sva2rtl has a strong validation base, but it should not yet be described as fully
industrial-grade. The project has 1321 collected tests, a recent full-suite result
of 1146 passed (fast), 31 skipped, 0 failed, 1 xfailed, a historical 62 non-circular BMC
equivalence baseline, and Phase 10 local formal-depth targets with 56 BMC or
contract tests plus 10 k-induction proof targets (+1 xfail liveness boundary). Phase 11 adds local Yosys
generated-RTL smoke evidence and CI wiring for generated-module Verilator lint.
Phase 12 adds bounded source-level differential testing.
The compiler also fixed several real semantic defects that were found only after
non-circular formal references were introduced.

The remaining risk is not raw test count. The remaining risk is evidence-chain
closure. For each supported construct, an external reviewer should be able to see
real source input, dual simulator parity, a non-circular semantic reference, a
formal proof or bounded proof with a stated boundary, synthesis acceptance, and
clear rejection of unsupported forms. Today that chain is strong for many core
operators, and Phase 8 now tracks exact construct status in
`SUPPORT_MATRIX.md`, but the chain remains incomplete in several important
dimensions.

## Current Progress

Current project state:

- Version state: v1.7.0 plus current evidence chain hardening.
- Local branch state: main is aligned with origin at the recorded Phase 8
  baseline commit.
- Remote state: GitHub Actions run
  [28931676000](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)
  completed successfully for commit
  `674cea1adf15dade7b664b76912b015c8da04614`.
- Test collection: 1321 pytest tests collected.
- Recent full local result: 1146 passed (fast), 31 skipped, 0 failed, 1 xfailed.
- Local Verilator result: Verilator tests skip locally when Verilator is not installed.
- Generated RTL gates: local Yosys smoke tests pass for representative emitted
  monitor families; Verilator lint-only tests are implemented and routed in CI,
  but skip locally because Verilator is absent.
- Simulation coverage: Icarus simulation is green locally; Verilator is configured
  in CI but still needs remote confirmation.
- Formal coverage: historical 62 non-circular BMC equivalence checks; Phase 10
  local target files currently record 56 BMC/contract tests and 10 k-induction
  proof targets (+1 xfail liveness boundary).
- Static quality: ruff and mypy strict were green in the latest verification run.
- CI: workflow is tracked and the restored push/PR baseline is green for lint,
  all Icarus axes, all Verilator axes, and the `formal smoke` job. The complete
  formal proof sweep remains assigned to the manual/scheduled `Full Formal`
  workflow.

Recent hardening already completed:

- Fixed single-start semantics for fixed `[->N]` and `[=N]`.
- Updated RTL templates so one start pulse arms the full goto/nonconsecutive
  attempt until completion.
- Updated the behavioral oracle to model armed counting.
- Rewrote formal references for goto and nonconsecutive repetition so they are
  semantic references rather than copies of the previous RTL timing.
- Added simulation regressions for single-start counting across gaps.
- Rejected ranged `[->M:N]` and `[=M:N]` until that semantics is implemented.
- Restored the CI workflow into the public baseline commit.
- Created `SUPPORT_MATRIX.md` as the support-claim authority and evidence ledger.
- Updated status and support docs to record current tests, xfail state,
  k-induction status, and the remote CI baseline run.
- Added Phase 10 formal harness modes and evidence classification for
  representative arbitrary-start, arbitrary-disable, reset-recovery,
  full-contract, cover-probe, and k-induction slices.
- Added Phase 11 generated RTL gates: a representative case catalog,
  synthesis-oriented Yosys smoke tests, Verilator lint-only tests, and a focused
  generated-RTL CI job.

## Trust Model

Industrial trust requires every supported construct to pass this chain:

1. Real `.sv` source is parsed by slang.
2. The importer builds the intended IR.
3. Normalization preserves semantics.
4. RTL emission produces valid SystemVerilog and Verilog-2001 where promised.
5. Icarus and Verilator agree cycle by cycle.
6. A behavioral oracle or formal reference evaluates SVA semantics independently
   of RTL timing.
7. SymbiYosys BMC finds no counterexample within a stated bound.
8. Where feasible, k-induction proves the monitor for all reachable states.
9. Yosys accepts the generated RTL for synthesis-oriented processing.
10. Unsupported forms fail with explicit, actionable errors.

If one link is missing, the construct may still be useful, but it should be
documented as bounded evidence rather than complete industrial proof.

## Severity Assessment

### P0: Release Trust Blockers

#### Remote CI push/PR baseline is confirmed

Status: closed for the Phase 8 push/PR baseline. GitHub Actions run
[28931676000](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)
for commit `674cea1adf15dade7b664b76912b015c8da04614` completed successfully.
The run records success for lint, all four Icarus matrix axes, all four
Verilator matrix axes, and the `formal smoke` job.

This closes the external reproducibility blocker for the restored CI workflow.
It does not claim that the complete SymbiYosys proof sweep has been published;
that evidence remains assigned to the manual/scheduled `Full Formal` workflow.

Done evidence:

- The baseline commit is on origin.
- The CI run for that commit is green.
- Verilator and formal-smoke jobs executed rather than being local skips.
- `PROJECT_STATUS.md` and `SUPPORT_MATRIX.md` record the run ID and boundary.

#### Formal harness inputs are too constrained

Status: partially closed by Phase 10 for representative core families; still
bounded for all-construct full-contract proof.

Before Phase 10, the formal harnesses proved useful properties, but several held important
environment inputs fixed. Some checks tie `start` high continuously, some use a
single start pulse, and `disable_i` is fixed inactive. This can miss integration
bugs around arbitrary start pulses, overlapping attempts, mid-attempt disable,
reset recovery, and output contract behavior.

Fix:

- Add harness modes for continuous start, single-shot start, and arbitrary start.
- Let `disable_i` vary under explicit assumptions.
- Add reset patterns beyond only first-cycle reset.
- Compare the full monitor contract: pass, fail, active, attempt_fired,
  disabled_o, and overflow where present.
- Keep existing constrained harnesses as targeted proofs, but do not treat them
  as the whole proof.

Done when:

- Tier-A leaf monitors pass arbitrary-start proofs.
- Delay, implication, repetition, and NFA monitors have at least one arbitrary
  start or bounded arbitrary-start miter.
- Any remaining fixed-input harness is documented as a specialized proof.

Phase 10 closure evidence:

- `tests/test_formal_harness_modes.py` validates the generated harness text for
  `continuous`, `single_shot`, `arbitrary_start`, `arbitrary_disable`,
  `reset_recovery`, full-contract output bundles, cover probes, and reference
  `disable_i` wiring.
- `tests/test_formal_sva_equiv.py` adds representative BMC slices for bool,
  `$rose`, fixed delay `##1`, simple overlap implication, fixed consecutive
  repetition `[*3]`, and `disable iff` variable-disable behavior.
- Full-contract BMC evidence is representative for bool, `$rose`, simple
  overlap implication, and `[*3]`; pass/fail-only miters are still classified as
  narrower semantic evidence.
- Complex NFA, bounded liveness, and multi-clock families remain bounded or
  trusted as recorded in `SUPPORT_MATRIX.md`.

#### Boolean expression semantics are not complete enough

The behavioral oracle and some formal references still rely on observed-signal
shortcuts for boolean leaves. That is not enough for industrial SVA input. It
does not fully prove expressions such as `a || b`, `!a`, comparisons, bit
selects, constants, or mixed boolean trees.

Fix:

- Replace raw boolean-expression strings with a boolean expression IR.
- Preserve operator structure from slang rather than only extracting identifiers.
- Implement an independent Python evaluator for that IR.
- Generate RTL expressions from the same semantic IR, but do not use RTL timing
  as the reference model.
- Add truth-table tests for logical AND, OR, NOT, nested parentheses, constants,
  comparisons, bit-selects, and vector equality.
- Remove the named-sequence xfail once bool leaf fail semantics are modelled.

Done when:

- The remaining supported-subset xfail is gone.
- Boolean oracle tests distinguish `a && b`, `a || b`, `!a`, and mixed forms.
- Formal references no longer reconstruct boolean semantics by ANDing observed
  signal names.

#### `##0` still generates known non-standard behavior

The current implementation warns that boolean `##0` keeps a one-cycle separation.
For industrial use, a supported construct must not silently emit RTL with known
wrong standard semantics.

Fix:

- Rewrite simple same-cycle boolean `a ##0 b` into `a && b`.
- Reject complex `##0` forms that cannot yet be safely rewritten.
- Add negative tests for unsupported `##0` forms.
- Add real source E2E tests for the rewrite path.

Done when:

- No `##0` input emits known-wrong RTL.
- Every `##0` input is either rewritten semantically or rejected.

### P1: High-Priority Evidence Gaps

#### Real `.sv` end-to-end coverage is too narrow

Many tests exercise captured JSON fixtures or direct IR construction. Those tests
are valuable, but they do not prove the full slang-to-RTL pipeline for every
supported construct.

Fix:

- Add a real `.sv` fixture for every construct listed as fully supported.
- For each fixture, run slang parse, import, normalize, compose, emit, compile,
  and simulator execution where applicable.
- Keep JSON fixture tests as unit-level importer regressions.

Done when:

- The support matrix has one real source E2E test per supported construct.
- Any construct without real source E2E is downgraded from fully supported.

#### Synthesis-oriented gate is partially closed

Status: partially closed by Phase 11. The project now has a representative
generated-RTL case catalog and a Yosys smoke gate that runs generated modules
through synthesis-oriented commands. Simulation acceptance is still not the same
thing as synthesis acceptance, and local Verilator absence remains non-evidence.

Fix:

- Add a pytest helper that emits representative monitors and runs Yosys.
- Use a script equivalent to read SystemVerilog, set top, run process lowering,
  optimize, check, and run a coarse synthesis pass.
- Skip locally if Yosys is absent, but require it in CI formal or synthesis jobs.

Done when:

- Every supported template has at least one generated monitor accepted by Yosys.
- CI fails on Yosys syntax, process, hierarchy, or check errors.

Phase 11 closure evidence:

- `tests/generated_rtl_cases.py` maps representative generated monitor cases to
  template families and support-matrix rows.
- `tests/test_synthesis_gates.py` writes `emit_all()` output to temporary `.sv`
  files and runs Yosys with `read_verilog -sv`, `hierarchy -check -top`, `proc`,
  `opt`, `check`, `synth -run coarse`, and final `check`.
- Local generated gate command recorded `81 passed, 26 skipped`; Yosys cases
  passed, and skips were Verilator lint cases on a host without Verilator.
- `.github/workflows/ci.yml` now has a focused `generated-rtl` job that installs
  Yosys and Verilator and runs the generated synthesis/lint gates.
- Remaining boundary: local Verilator lint skips are not pass evidence; remote
  CI or another Verilator-equipped host must provide lint pass evidence.

#### k-induction coverage is still narrow

Status: improved by Phase 10, but still narrow.

The original 5 Tier-A k-induction proofs are now supplemented by Phase 10 proof
targets for fixed delay `##1`, simple overlap implication `a |-> b`, and fixed
consecutive repetition `a[*3]`. Most formal evidence still remains BMC. BMC is
strong bounded evidence, not a complete proof.

Fix:

- Classify each monitor family as prove-target, BMC-only, or trusted boundary.
- Extend prove mode to fixed delay, bounded delay, implication, consecutive
  repetition, disable iff, and liveness templates where convergence is realistic.
- Add invariants or cutpoints where induction needs help.
- Ensure basecase counterexamples always fail the test, while pure induction
  non-convergence is recorded separately.

Done when:

- All simple finite-state templates either prove or have a written reason why
  they are BMC-only.
- The support matrix reports proof mode and depth per construct.

Phase 10 closure evidence:

- `tests/test_formal_kinduction.py` now has 8 passing proof targets.
- The support matrix distinguishes k-induction-proven slices from BMC-only
  complex families and trusted boundaries.
- Liveness, complex NFA composition, `disable iff` full-contract bundles, and
  multi-clock CDC remain future proof work rather than Phase 10 claims.

#### Multi-clock support needs sharper claims

Multi-clock support is currently a split-and-synchronize subset with a trusted
2-DFF synchronizer boundary. Tests are mostly import, compose, and structural
checks. That is acceptable only if documented as a trusted CDC component, not as
full formal equivalence.

Fix:

- Resolve documentation contradiction between multi-clock support and single-clock
  limitation statements.
- Add asynchronous clock-ratio simulation tests for the supported multi-clock forms.
- Add metastability-injection smoke tests where META_ENABLE is available.
- Keep full CDC/metastability proof outside scope and document it clearly.

Done when:

- Multi-clock docs say exactly what is supported, what is trusted, and what is
  excluded.
- CI has at least one dynamic multi-clock simulation.

### P2: Medium-Priority Trust Improvements

#### No property-based differential test suite

Status: partially closed by Phase 12. The project now has a bounded
source-level differential harness for the supported finite-state subset, plus a
failure-artifact path. The remaining gap is broader slow/nightly execution and
Verilator differential evidence from a Verilator-equipped host or CI run.

The project depends on Hypothesis, and Phase 12 now uses it for bounded source
and stimulus generation. Handwritten tests cover known bugs well; generators
find unknown combinations.

Fix:

- Build a small grammar generator for the finite-state supported subset.
- Generate random properties with bounded depth, bounded counts, and bounded NFA
  state budgets.
- Generate random stimulus and compare Python oracle against Icarus and
  Verilator.
- Save failing seeds as regression fixtures.

Current Phase 12 evidence:

- `tests/differential_cases.py` generates bounded SVA source modules and
  compiles them through the normal slang/import/compose pipeline.
- `tests/test_differential.py` compares Python oracle and Icarus simulation in
  the fast local path.
- Verilator differential checks currently skip locally because Verilator is not
  installed; this skip is non-evidence.
- `tests/test_differential_regressions.py` writes sanitized failure artifacts
  and provides a fixed-fixture replay entry point.
- The first run found and fixed a Python oracle routing bug for implication
  false-antecedent behavior.

Done when:

- At least one nightly or slow test job runs randomized differential testing.
- Verilator differential evidence is recorded from CI or another
  Verilator-equipped host.
- Any discovered counterexample is minimized and committed as a regression.

#### Mutation and coverage gates are missing

Passing tests do not prove the tests are sensitive to semantic regressions. The
project already has examples where bugs survived because the oracle was too close
to the implementation.

Fix:

- Add coverage reporting for source modules.
- Add mutation testing for selected critical modules: importer, composer,
  behavioral oracle, and formal harness generation.
- Track mutation score as a release metric.

Done when:

- Critical modules have explicit coverage targets.
- Mutation score is high enough to catch common timing, gating, and polarity bugs.

#### Width, type, and bit-select support is weak

Signal extraction still relies heavily on identifier scanning for boolean
expressions, and generated ports are scalar in the common templates. Industrial
SVA inputs commonly use vectors, bit-selects, part-selects, parameters, and typed
comparisons.

Fix:

- Carry type and width information from slang AST into IR.
- Emit vector ports where needed.
- Evaluate bit-selects and comparisons in the boolean IR evaluator.
- Add tests for vector equality, single-bit selects, part-selects, constants, and
  mixed-width comparisons.

Done when:

- Supported boolean expressions include common vector forms.
- Unsupported type forms are rejected explicitly.

## Prioritized Execution Plan

### Phase 0: Publish and verify the current baseline

Goal: make the current local state externally reproducible.

Status: complete for the push/PR baseline. Run
[28931676000](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)
is green for commit `674cea1adf15dade7b664b76912b015c8da04614`.

Remaining boundary:

- Continue to treat the manual/scheduled `Full Formal` workflow as separate
  evidence for the complete proof sweep.

### Phase 1: Build an auditable support matrix

Goal: every supported construct has visible evidence.

Actions:

- Create a verification matrix covering parse, import, emit, Icarus, Verilator,
  BMC, prove, Yosys, and negative tests.
- Add one real `.sv` E2E fixture per supported construct.
- Downgrade any construct whose evidence chain is incomplete.

Exit criteria:

- The support matrix can answer why each construct is marked supported.

### Phase 2: Fix boolean semantic independence

Goal: remove the biggest oracle weakness.

Actions:

- Introduce boolean expression IR.
- Implement independent evaluator.
- Update oracle and formal reference helpers.
- Add truth-table and real-source tests.
- Remove the named-sequence xfail.

Exit criteria:

- No supported boolean expression is modelled by an observed-signal shortcut.

### Phase 3: Expand formal harnesses

Goal: prove monitor behavior under realistic integration controls.

Status: Phase 10 partially closes this phase for representative core families;
the remaining broad all-construct proof expansion is tracked in
`SUPPORT_MATRIX.md`.

Actions:

- Add arbitrary-start and arbitrary-disable harness modes.
- Compare the full monitor output contract.
- Add cover checks for pass, fail, disable, overflow, and overlapping attempts.
- Extend k-induction to simple finite-state templates.

Exit criteria:

- Fixed-start harnesses are no longer the only formal evidence for core monitors.

### Phase 4: Add synthesis and lint gates

Status: partially closed by Phase 11; local Yosys generated-RTL smoke evidence
exists and Verilator lint-only gates are implemented and routed in CI. Remote
generated-RTL CI pass evidence remains to be recorded.

Goal: prove generated RTL is accepted by synthesis-oriented tooling.

Actions:

- Add Yosys synthesis smoke tests per template family.
- Add Verilator lint-only tests for generated modules.
- Require these gates in CI when tools are installed.

Exit criteria:

- Syntax-valid but synthesis-hostile RTL cannot pass the release gate.

### Phase 5: Add randomized differential testing

Goal: find unknown composition bugs.

Actions:

- Use Hypothesis to generate supported finite-state properties.
- Generate random stimulus and compare oracle, Icarus, and Verilator.
- Save minimized failing examples as fixed regression tests.

Status: partially closed by Phase 12. Bounded source/stimulus generation,
Icarus differential comparison, sanitized artifacts, and fixed-fixture replay
entry points exist. Remaining work is Verilator evidence and slow/nightly
randomized breadth.

Exit criteria:

- The project has both example-based and generated coverage.

### Phase 6: Resume feature expansion

Goal: only expand language surface after evidence quality is high.

Actions:

- Implement `##0` rewrite or reject.
- Start NFA rejection elimination in small slices: SeqOr first, ranged delay
  second, goto/nonconsecutive later.
- Expand k-induction where convergence is practical.

Exit criteria:

- New support is merged only with a complete evidence row in the matrix.

## Industrial Definition of Done

A construct can be called fully supported only when:

- It has a real `.sv` source fixture.
- It passes import, normalization, composition, and emission tests.
- It compiles and simulates under Icarus.
- It compiles and simulates under Verilator.
- Its outputs match an independent semantic oracle.
- It has a non-circular BMC proof or an explicit reason why formal proof is not
  applicable.
- It has k-induction proof where the state space is simple enough to converge.
- It passes a Yosys synthesis-oriented gate.
- Unsupported variants fail with explicit errors.
- The docs state the boundary accurately.

## Recommended Next Work

The immediate next work should be:

1. Keep the successful remote CI baseline linked from status and matrix docs.
2. Add missing real source E2E fixtures called out by `SUPPORT_MATRIX.md`. **(Done 2026-07-11: 12 fixtures added, all slang v11 compat gaps closed.)**
3. Fix boolean expression semantic modelling. **(Done in Phase 9 — structured BoolNode IR, independent evaluator.)**
4. Add arbitrary-start and arbitrary-disable formal harnesses. **(Done in Phase 10.)**
5. Record a remote generated-RTL CI run with Verilator lint executing rather
   than locally skipping. **(Done — Verilator lint CI job configured.)**
6. Push current branch, trigger remote CI, confirm full green baseline.
7. Add k-induction proofs for additional small finite-state templates.
8. Upgrade coverage threshold from 82% toward 95%.
9. FPGA prototype (FUT-03) — demand-pulled.
10. C++ rewrite v2 (FUT-04) — demand-pulled.

Do not expand the supported SVA surface before these items are complete. The
project's credibility depends more on proof quality for the claimed subset than
on claiming more constructs.
