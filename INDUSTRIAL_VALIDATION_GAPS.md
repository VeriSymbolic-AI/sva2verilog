# Industrial Validation Gap Plan

> Date: 2026-08-01
> Scope: v1.7.1 post-release qualification and current `main`
> Reader: future maintainer, external reviewer, or industrial user evaluating trust
> Post-read action: decide and execute the next validation work needed before calling the project industrial-grade

## Executive Summary

sva2rtl has a strong validation base, but it should not yet be described as fully
industrial-grade. Release v1.7.1 contains the semantic and release-gate fixes
from the independent-reference audit. On 2026-08-01, same-base remote run
`30649226848` passed lint, formal smoke, coverage, Python 3.14/package, all
Icarus axes, and both macOS Verilator axes. Its three Linux Verilator-dependent
jobs failed before tests because Ubuntu 24.04 requires the separate `libfl-dev`
package for `FlexLexer.h`; F-01 fixes that dependency locally and awaits a new
same-commit remote run. Full Formal and nightly differential are additionally
blocked by the GitHub account payment/spending-limit state.
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

- Version state: v1.7.1 released at `8b5c063`; remote `main` base `243b839`
  adds self-diagnosing JUnit execution-budget errors.
- Local branch state: F-01 adds Ubuntu `libfl-dev` and a `FlexLexer.h` fail-fast
  probe on top of the remote base; it is not yet a remote evidence baseline.
- Historical remote state: GitHub Actions run
  [28931676000](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)
  completed successfully for commit
  `674cea1adf15dade7b664b76912b015c8da04614`.
- Current-base remote Icarus result: Ubuntu Python 3.12 records 1292 passed and
  183 skipped by tool/marker selection; the JUnit budget passed and no failure
  or error was recorded.
- Current-base remote Verilator result: macOS Python 3.12 records 169 passed and
  one Icarus-specific skip; the equivalent Ubuntu axes did not reach tests.
- Generated RTL gates: local Yosys synthesis and strict Verilator lint pass all
  107 synthesis/lint cases, plus 26 representative top-contract checks, for
  133 passed.
- Simulation coverage: Icarus is green on Ubuntu/macOS and Verilator is green
  on macOS for commit `243b839`; Linux Verilator requires an F-01 rerun.
- Formal coverage: current-base formal smoke records 3/3 passed. The latest full
  local file set records 125 passed and one documented liveness xfail;
  historical evidence includes 62 non-circular BMC
  equivalence checks and Phase 10 bounded/full-contract/k-induction slices.
- Static quality: ruff and mypy strict were green in the latest verification run.
- Python compatibility and distribution: current-base Python 3.14 records 1122
  passed and 126 tool/marker skips; wheel/sdist out-of-tree smoke passed.
- CI: run `30649226848` is partially green but release-blocking overall. The
  Linux Flex header dependency is fixed locally; the latest scheduled nightly
  run `30610818023` and Full Formal run `30262616745` did not start because
  GitHub reported an account payment/spending-limit block.
- Fresh local qualification (2026-08-01): full Icarus 1473 passed / 1 skipped /
  1 xfailed; generated RTL 133 passed; Full Formal 125 passed / 1 documented
  strict-liveness xfail; branch coverage 86.31%; Python 3.14 broad non-simulation
  axis 1247 passed / 1 xfailed; ruff, mypy strict, frozen lock, workflow YAML,
  installer syntax, and coverage floors passed.
- Fresh differential and distribution evidence: Icarus and Verilator fast each
  record 16 passed; date seed `20260801` slow sweeps each record 1 passed with
  64 Hypothesis examples; wheel/sdist out-of-tree smoke passed under Python 3.12
  and 3.14. These are local results, not substitutes for scheduled remote runs.

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
- Packaged all 35 runtime templates in wheel/sdist and verified clean external
  installs for SystemVerilog, Verilog-2001, NFA fragment rendering, and Icarus.
- Unified the pinned Verilator installer across CI/nightly, pinned OSS CAD Suite
  for formal jobs, isolated NFA implication shards, and made each Verilator
  differential build use a fresh directory.
- Restored the standard checker contract on the multi-clock top and corrected
  implication `attempt_fired` so it records `start`, not antecedent success.
- Extended source differential comparison to `attempt_fired` and `disabled_o`,
  and added external `disable_i` to the randomized stimulus surface.
- Added JUnit execution budgets to CI/nightly/formal jobs so unexpectedly
  skipped or missing tests cannot silently produce a green result.

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

#### Remote CI push/PR baseline is confirmed historically

Status: closed for the Phase 8 push/PR baseline. GitHub Actions run
[28931676000](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)
for commit `674cea1adf15dade7b664b76912b015c8da04614` completed successfully.
The run records success for lint, all four Icarus matrix axes, all four
Verilator matrix axes, and the `formal smoke` job.

This closes the external reproducibility blocker only for that historical commit.
The 2026-07-22 hardening worktree still requires a new same-commit remote run.
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

#### `##0` same-cycle behavior

Status: closed for the supported v1.7 subset. Boolean `a ##0 b` is rewritten to
same-cycle `a && b`; complex forms that cannot be represented safely are rejected.

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
thing as synthesis acceptance; both Yosys and local Verilator gates now execute.

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
- Local generated gate command now records `107 passed`; both Yosys and pinned
  Verilator 5.028 cases execute.
- `.github/workflows/ci.yml` now has a focused `generated-rtl` job that installs
  Yosys and Verilator and runs the generated synthesis/lint gates.
- Remaining boundary: current-worktree local lint is pass evidence, but the same
  commit still needs a remote CI record before support rows are promoted.

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

Phase 10 closure evidence (historical), followed by later P2 expansion:

- Phase 10 closed with 8 passing proof targets; the current
  `tests/test_formal_kinduction.py` suite has 10 passing targets plus one strict
  bounded-liveness xfail.
- The support matrix distinguishes k-induction-proven slices from BMC-only
  complex families and trusted boundaries.
- Liveness, complex NFA composition, `disable iff` full-contract bundles, and
  multi-clock CDC remain future proof work rather than Phase 10 claims.

#### Multi-clock support needs sharper claims

Multi-clock support is currently a split-and-synchronize subset with a trusted
2-DFF synchronizer boundary. Tests are mostly import, compose, and structural
checks. That is acceptable only if documented as a trusted CDC component, not as
full formal equivalence.

The boundary is stronger than “metastability is unproven”: the current 2-DFF is
a level synchronizer carrying a one-cycle token. A narrow source pulse can be
missed when the destination clock is slower or unfavorably phased, and multiple
events can coalesce. The compiler currently enforces neither a minimum pulse
width nor an event-rate assumption. Top-level start/disable/anti-vacuity
contract wiring and synchronous disable clearing are fixed and tested, but the
CDC transfer protocol itself is not closed.

Fix:

- Resolve documentation contradiction between multi-clock support and single-clock
  limitation statements.
- Add asynchronous clock-ratio simulation tests for the supported multi-clock forms.
- Replace the raw pulse crossing with an acknowledged handshake or a toggle
  protocol with explicit event-rate/overflow semantics.
- Add metastability-injection smoke tests where META_ENABLE is available.
- Keep full CDC/metastability proof outside scope and document it clearly.

Done when:

- Multi-clock docs say exactly what is supported, what is trusted, and what is
  excluded.
- CI has at least one dynamic multi-clock simulation.
- The CDC protocol has a falsifiable source-event-to-destination-event contract
  and no silent event loss within its published rate bound.

### P2: Medium-Priority Trust Improvements

#### No property-based differential test suite

Status: substantially closed locally by the 2026-07-22 P1 credibility pass.
The bounded source generator now emits both compilable SVA and a typed source
reference specification. Expected traces are evaluated from that source model,
not from the compiler's normalized IR or composed `CheckerNode`, removing the
previous circular-proof path. The remaining gap is current-commit scheduled
remote evidence and broader language/parameter coverage, not local execution.

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

- `tests/differential_reference.py` owns the source-level semantic model;
  `tests/differential_cases.py` independently compiles its rendered source
  through slang/import/normalize/compose/optimize.
- The deterministic catalog has 10 operator families, the fast Hypothesis path
  has 10 examples, and each seeded slow backend sweep has 64 examples over
  8-24 cycles, delay up to 8, repetition up to 6, and boolean depth up to 5.
- Live traces compare `active`, `pass`, `fail`, `attempt_fired`, `disabled_o`,
  and optional `overflow`; external `disable_i` is randomized instead of
  leaving `disabled_o` at a constant zero.
- Local current-worktree evidence: Icarus fast 16 passed and slow 1 passed;
  Verilator fast 16 passed and slow 1 passed, with no mismatches. Each slow
  test contains 64 Hypothesis examples.
- `tests/differential/regressions/repetition_overlapping_start.json` is a
  sanitized promoted replay from a real discovered mismatch, not an empty
  placeholder path.
- The independent campaign found and fixed two additional defects: slang v11
  top-level consecutive repetition silently reduced to a boolean leaf, and the
  repetition oracle mishandled a false overlapping start.
- Nightly now runs deterministic, fast, and 64-example slow campaigns on both
  simulators with fixed seed `20260722`.

Done when:

- At least one nightly or slow test job runs randomized differential testing.
- Verilator differential evidence is recorded from CI or another
  Verilator-equipped host.
- Any discovered counterexample is minimized and committed as a regression.

#### Mutation and coverage gates

Status: closed for the selected P1 semantic surfaces; expansion remains an
ongoing quality activity.

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

Current local evidence (rerun 2026-08-01):

- `bool_semantics.py`: 15/15 killed (100%).
- `behavioral_oracle.py`: 112/130 covered, valid mutants killed (86.2%);
  19 uncovered candidates are reported separately.
- `composer.py`: 41/48 covered, valid mutants killed (85.4%); 4 uncovered
  candidates are reported separately.
- `ast_importer.py`: 92/108 covered, valid mutants killed (85.2%); 8 uncovered
  candidates are reported separately.
- Reviewed RTL template mutations: 11/11 killed, covering delay upper bounds,
  repetition counter state, counter width, non-overlap consequent wiring,
  sequence-OR failure polarity, both sequence-OR failure-retention latches,
  multi-clock start wiring, multi-clock disable propagation, and implication
  attempt accounting.
- Syntax-invalid mutants are excluded rather than counted as killed. Mutation
  candidates on lines the configured baseline never executes are also excluded
  from the percentage and exposed as explicit uncovered debt.
- The scheduled mutation job runs all four Python modules separately at the
  85% threshold and the RTL template suite at a strict 100% threshold.
- Across the four Python modules, 260/301 scored mutants were killed (86.4%).
  Forty-one valid mutants survived and 31 candidates were uncovered, so this
  gate passes its current threshold but also exposes concrete test debt; it is
  not evidence that the selected semantic surfaces are exhaustive.

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
5. Record a current-commit generated-RTL CI run with Verilator lint executing
   rather than locally skipping. **Configured, not yet evidenced.**
6. Commit and push the 2026-07-22 hardening worktree, trigger all remote gates,
   and confirm a full green baseline before promoting support rows.
7. Add k-induction proofs for additional small finite-state templates.
8. Upgrade coverage threshold from 82% toward 95%.
9. FPGA prototype (FUT-03) — demand-pulled.
10. C++ rewrite v2 (FUT-04) — demand-pulled.

Do not expand the supported SVA surface before these items are complete. The
project's credibility depends more on proof quality for the claimed subset than
on claiming more constructs.
