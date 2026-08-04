# sva2rtl Support Matrix

This file is the authoritative support evidence ledger for the v1.7.1 package
line plus the v2.0 Open Formal Verification capability milestone. `README.md`
and `SUPPORTED_CONSTRUCTS.md` provide explanations and examples; this matrix
governs exact support status, subset boundaries, and verification evidence.

## Baseline CI Summary

Detailed remote CI evidence is recorded in `PROJECT_STATUS.md` under
`Remote CI Baseline Ledger`.

Historical baseline: run
[`28931676000`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)
for commit `674cea1adf15dade7b664b76912b015c8da04614` completed successfully on
2026-07-08 — lint, all Icarus/Verilator matrix axes, and formal smoke.

Current v1.7.1 post-release qualification baseline: commit
`b0551057a66badf1008e6146528a1a448d5063bf` completed all three remote gates:

- CI run [`30683023280`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30683023280):
  all 13 jobs passed, including all eight dual-platform / dual-Python /
  dual-simulator axes and generated RTL synthesis/lint.
- Differential nightly run [`30683026683`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30683026683):
  Icarus, Verilator, and full mutation jobs passed.
- Full Formal run [`30683026438`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30683026438):
  all six formal shards passed.

F-01 is therefore remote-verified. The nightly run also exposed a clean-checkout
artifact-root defect that was reproduced by a workflow regression and fixed in
the same baseline. Yosys synthesis remains complementary structural evidence,
not an equivalent replacement for Verilator or formal equivalence.

Latest follow-on hardening baseline: commit
`1841ed40a149ef6971225fe00255e9587d5995ae` completed all three remote gates:

- CI run [`30686814681`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30686814681):
  all 13 jobs passed, including the eight dual-platform simulator axes and
  generated RTL gates under the pinned Node.js 24 actions.
- Differential nightly run [`30686818970`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30686818970):
  Icarus and Verilator fast/slow differential plus the full Python and 12/12
  RTL-template mutation sweeps passed.
- Full Formal run [`30686820029`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30686820029):
  all six formal shards passed.

The latest remotely qualified executable is commit
`c957bdf3d3ed9cf145f23057d9e2a94d555c30e3` on 2026-08-02. It records full
Icarus 1580 passed / 1 skipped / 1 dynamically classified k-induction xfail,
generated RTL 133/133, Full Formal 126 passed / 1 identical bounded-liveness
xfail, branch coverage 88.12%, and full local Verilator simulation 174 passed /
1 reviewed skip. Both backends pass fixed-seed fast and date-seeded slow
differential sweeps. The four Python mutation surfaces kill 317/317 covered
valid mutants; 32 uncovered candidates remain outside the denominator.
Reviewed RTL-template mutation remains 12/12. This baseline also carries the
Apache-2.0 relicense, release-metadata checks, corrected public scope, and the
formal/advanced-SVA guide.

For the exact `c957bdf` executable, differential nightly run
[`30741082278`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30741082278)
passed all three jobs, and Full Formal run
[`30741083516`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30741083516)
passed all six shards. CI run
[`30741073680`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30741073680)
passed all 13 jobs, including all eight OS/Python/simulator axes, generated RTL,
coverage, Formal smoke, lint, Python 3.14, and installed-distribution gates.
Neither local nor remote gates close per-construct independent-reference,
proof-depth, CDC, or industrial-corpus gaps.

The completed v2.0 formal-first executable baseline is
`e1405b65e79f924e4f0eee5c2fd0230d35eec22b` on 2026-08-04:

- CI run [`30891680942`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30891680942)
  passed all 13 jobs, including all eight OS/Python/simulator axes.
- Differential nightly run [`30891694691`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30891694691)
  passed all three differential and mutation jobs.
- Full Formal run [`30891700576`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30891700576)
  passed all eight shards. The Linux open-liveness shard executed 15/15 tests
  with no skip using Super Prove, and the open-user-DUT shard executed 75/75
  tests with no skip.

**Qualification overlay:** CI run `30891680942` qualifies executable
`e1405b6`; its same-commit nightly and Full Formal runs are named above. This
overlay supplies workflow-level remote evidence but does not fill a row's
independent-reference, proof-depth, real-source, rejection, CDC, or
industrial-corpus gaps, and therefore does not change any support status by
itself.

## Support Status Legend

| Status | Meaning |
|--------|---------|
| Fully supported | Complete applicable evidence chain: real `.sv` source, compiler pipeline, Icarus, Verilator, independent oracle/reference, formal or justified N/A, synthesis/lint evidence where applicable, and rejection tests for unsupported variants. |
| Bounded evidence | Implemented and useful, but one or more industrial evidence links are missing, bounded, pending remote CI, or deferred to a later phase. |
| Trusted boundary | Intentionally trusted component or excluded proof domain, such as the multi-clock 2-DFF synchronizer and CDC/metastability proof boundary. |
| Unsupported / rejected | Deliberately unsupported variant that should fail with explicit, actionable diagnostics and negative-test evidence where available. |

Current v1.7/v2.0 evidence: **0 construct rows are promoted to `Fully supported`**.
Same-commit dual-simulator, generated-lint, nightly, and Full Formal evidence is
present for executable `e1405b6`. The six strongest rows (`##N`, `[*N]`, sampled
value functions, overlapping implication, `first_match`, and `disable iff`)
remain `Bounded evidence` until their row-specific real-source,
independent-reference, full-contract/formal, and unsupported-variant links are
individually audited.
The remaining rows stay at `Bounded evidence`, `Trusted boundary`, or
`Unsupported / rejected` as listed.

## Formal vs Synth Monitor Matrix

This v2.0 overlay separates the project's primary formal workflow from the
secondary RTL-monitor product. “Formal-only” never implies a synthesizable
finite PASS output; “monitor implemented” never implies a DUT proof.

| Construct family | Formal backend/status | Formal evidence | Synth monitor status | Monitor evidence | Main boundary |
|---|---|---|---|---|---|
| Structured Boolean/invariant | Direct invariant or generated-monitor safety | real good/bad DUT prove/trace, cover, typed expression tests | Implemented | dual simulation, independent reference, Yosys/lint | two-state expression subset; scalar or one fixed packed dimension only |
| Fixed/ranged delay, nexttime, bounded repetition | Symbolic witness or generated-monitor safety | real DUT prove/fail, bounded exhaustive witness comparison | Implemented within documented bounds | dual simulation, BMC, synthesis/lint | finite delay/state/resource contract |
| Bounded implication with overlapping starts | Symbolic witness avoids monitor T/K budget | delay-64 good/bad proofs and exhaustive small attempts | Implemented with finite thread slots | overflow fail-closed plus simulation/formal | monitor has finite concurrency; formal witness does not |
| Bounded eventually/always, weak until | Safety/BMC/prove as row-specific evidence permits | independent references and named proof depths | Implemented | simulation, synthesis/lint | bounded liveness is not true unbounded liveness |
| Unbounded `always p` | Formal-only direct invariant | real DUT good/bad unbounded safety proof | Rejected | N/A | no finite PASS verdict |
| Boolean unbounded eventual / implication-to-eventual | Formal-only SBY `mode live` / Super Prove | source isolation, AIG prep, cover, missing-engine UNKNOWN; real good/bad Linux qualification in Full Formal `30891700576` | Rejected | N/A | needs qualified live solver; no arbitrary nesting |
| Boolean strong until | Formal-only safety plus eventual discharge | obligation split, cover, and qualified Linux live solver in Full Formal `30891700576` | Rejected | N/A | explicit fairness and live-solver boundary |
| Restricted automatic scalar local capture | Formal-only symbolic witness with private `captured_q` | real good/bad/changing-value solver cases; user-DUT shard 75/75 in Full Formal `30891700576` | Rejected | explicit composer rejection with `sva2rtl-formal` routing | exact one-local/fixed-delay whitelist |
| Multi-clock temporal composition | `UNSUPPORTED` in single-clock formal profile | sanitized boundary bundle, empty Yosys inputs | Experimental trusted 2-DFF path only | structural/synthesis/lint, no event-delivery proof | split per domain; prove handoff; separate CDC signoff |
| X/Z-dependent semantics | `UNSUPPORTED` in two-state profile | real X/Z negative sources and hashed profile | Rejected | N/A | no implicit four-state-to-two-state coercion |
| General locals, dynamic/unbounded/nested unsupported forms | `UNSUPPORTED`, or replay-bound external decomposition evidence | precise negative tests; schema-v2 subproof/relation bundles require PROVEN+REACHED, manifest/input hashes, checker and formal-context binding, PASS logs, and deterministic replay | Rejected | N/A | the relation model is a reviewed trusted boundary; fabricated status JSON, BMC aggregation, mismatched proof context, and mismatched DUT/property types reject |

No row is promoted to `Fully supported` merely because both columns contain
some evidence. Promotion still requires every applicable row-specific link and
same-commit remote qualification; the table above is a capability split, not a
certification shortcut.

## Evidence Cell Legend

| State | Meaning |
|-------|---------|
| present | Evidence exists and a concrete path or command is cited. |
| missing | Evidence is required for a stronger claim but no concrete evidence exists yet. |
| pending-remote | Evidence is configured in CI or a dual-simulator test, but the current remote run has not been recorded yet. |
| planned | Explicit future-phase work; not counted as current evidence. |
| N/A | Not applicable to this row, with rationale in notes where needed. |
| trusted-boundary | Intentionally trusted/excluded proof domain; not a missing implementation bug. |

## Structured Project Frontend Boundary

F-11 is closed for the structured v1 compilation-context subset at `c957bdf`.
`SlangCompilationContext` and the CLI represent source files, `-F` filelists,
include paths, defines, top modules, parameter overrides, library
files/directories/extensions/order, and single-unit mode as validated argv. The
compiler owns the AST-output options and does not expose a raw arbitrary-argument
escape hatch. Nested elaborated instance bodies and two-state parameter constants
are covered by real slang integration tests; a dedicated simulation regression
executes filelist/include/define/top/parameter specialization through emitted RTL
and compares Icarus and Verilator cycle outputs with the behavioral oracle.
The `c957bdf` baseline replaces temporary project generation with two versioned
corpora under `tests/project_corpus/`: parameter specialization and library
directory/extension resolution. The first corpus also carries a hand-authored,
cycle-exact source expectation, so a shared RTL/oracle error cannot pass solely
through mutual agreement.

This frontend evidence is still bounded. Filelist contents are trusted compiler
configuration, escaped identifiers and multiple colliding parameterized-instance
labels fail closed, and the two small maintained corpora are not representative
industrial designs. Nested filelists, ambiguous library resolution, repeated
parameterized instances, tool-specific option sets, and large dependency graphs
remain uncovered. These gaps do not invalidate the structured subset, but
prevent broader project compatibility claims.

## Phase 10 Formal Evidence Ledger

Phase 10 strengthens formal evidence for representative monitor families without
upgrading any row to `Fully supported`. Evidence below is local and bounded by
the named harness mode, BMC depth, or k-induction target. Historical all-operator
BMC evidence remains recorded in the main matrix and `PROJECT_STATUS.md`.

| Construct family | Phase 10 evidence | Claim strength | Remaining boundary |
|---|---|---|---|
| Boolean leaf / scalar expression | `tests/test_formal_sva_equiv.py#TestBoolExprSvaEquiv`: `arbitrary_start` BMC depth 15, `arbitrary_disable` full-contract BMC depth 12, `reset_recovery` BMC depth 15; `tests/test_formal_kinduction.py#TestKinductionBoolExpr` still proves the leaf target. | k-induction proven for the simple leaf target; richer harness modes have bounded BMC evidence. | Broader structured boolean subset still depends on Phase 9 semantic tests plus bounded formal slices, not universal full-contract proof. |
| Sampled value functions | `$rose` has `arbitrary_start` BMC depth 15 and full-contract BMC depth 12; `$rose`, `$fell`, `$stable`, and `$changed` keep k-induction proof tests. | k-induction proven for the four sampled-value edge/state functions listed; `$rose` also has Phase 10 full-contract BMC. | `$past(sig,N)` remains BMC-only; sampled-value real-source fixture coverage is still incomplete. |
| Fixed delay `##1` | `test_delay_fixed_arbitrary_start_bmc_depth20`; `test_fixed_delay_kinduction_prove`. | representative fixed-delay slice is k-induction proven and has arbitrary-start BMC depth 20. | Bounded/ranged delay families still require row-specific synthesis and broader proof depth. |
| Overlapping implication `a \|-> b` | `test_overlap_arbitrary_start_bmc_depth15`; `test_overlap_full_contract_bmc_depth15`; `test_overlap_implication_kinduction_prove`. | representative simple overlap implication is k-induction proven and has full-contract BMC including `overflow_flag`. | Multi-cycle/NFA consequents remain bounded by existing BMC and simulation evidence. |
| Fixed consecutive repetition `a[*3]` | `test_rep_fixed_arbitrary_start_bmc_depth20`; `test_rep_fixed_full_contract_bmc_depth20`; `test_rep_fixed_kinduction_prove`. | representative fixed-count consecutive repetition is k-induction proven and has full-contract BMC depth 20. | Ranged repetition and NFA-lifted repetition contexts remain BMC-only. |
| `disable iff` | `test_disable_iff_arbitrary_disable_bmc_depth15[pass]` and `[fail]` compare pass/fail with `disable_i` wired as a variable reference input. | arbitrary-disable semantics have bounded BMC depth 15. | Full-contract `disable iff` output bundle is not yet separately promoted; local Yosys smoke exists and generated Verilator lint is present at executable `de3f697` in CI run `30709818712`. |
| Cover probes | Full-contract representatives enable cover probes for pass, fail, disable, overlap, or overflow reachability where applicable. | reachability sanity evidence only. | Cover statements are not equivalence proof and do not replace assertions. |
| Complex NFA, bounded liveness, multi-clock | No Phase 10 k-induction promotion. | remains bounded evidence or trusted boundary as listed in the main matrix. | Full arbitrary-start/full-contract proof expansion is deferred to later phases. |

## Phase 11 Generated RTL Evidence Ledger

Phase 11 adds a focused generated-RTL gate for representative template
families. Local evidence was collected on 2026-07-09 with:

- `UV_CACHE_DIR=.uv-cache uv run --no-sync pytest tests/test_synthesis_gates.py tests/test_generated_lint.py -q --timeout=180`
- Result: 81 passed, 26 skipped.
- Yosys evidence: all representative Yosys smoke cases passed. The helper writes
  `emit_all()` output to temporary `.sv` files, runs `read_verilog -sv`,
  `hierarchy -check -top`, `proc`, `opt`, `check`, `synth -run coarse`, and a
  final `check`.
- Verilator lint evidence: the generated lint gate is implemented and routed in
  the `generated-rtl` CI job, but local lint cases skipped because Verilator was
  not installed. This local skip is not pass evidence.
- Multi-clock evidence remains a trusted boundary: Yosys accepts generated
  synchronizer structure, but this is not a CDC or metastability proof.

**Updated 2026-07-22:** Verilator 5.028 is installed locally. The combined
generated synthesis/strict-lint command now records **107 passed, 0 skipped**.
The strict lint policy keeps unexpected `-Wall` warnings fatal while suppressing
only stable-interface diagnostics such as intentionally unused public ports.

**Updated 2026-07-26:** the gate also checks the standard top-level
`rst_n/start/disable_i/active/pass/fail/attempt_fired/disabled_o` contract on
all 26 representative generated monitors, plus `overflow_flag` on templates
with bounded attempt allocators. The combined generated gate records
**133 passed, 0 skipped** locally.

**Updated 2026-08-01:** `nfa_generic` and `implication_nfa` now expose the
optional `overflow_flag` contract. A start presented while all NFA thread slots
are occupied is no longer silently dropped: overflow is sticky and fail-closed
until reset or external disable. Accepting threads retire immediately, and a
dead thread emits one failure verdict instead of repeatedly failing because the
public `attempt_fired` evidence bit is sticky.

Representative cases live in `tests/generated_rtl_cases.py`; Yosys tests live
in `tests/test_synthesis_gates.py`; Verilator lint tests live in
`tests/test_generated_lint.py`.

## Phase 12 Differential Evidence Ledger

Phase 12 adds bounded source-level differential testing for the supported
finite-state subset. Local evidence was collected on 2026-07-09 with:

- `uv run pytest tests/test_differential_cases.py tests/test_differential_oracle.py tests/test_differential_regressions.py -q`
- Result: 28 passed, 1 skipped. The skip is the committed-fixture replay entry
  point because no minimized differential failure fixtures have been promoted yet.
- `uv run pytest tests/test_differential.py -q --simulator=iverilog`
- Result: 2 passed, 1 skipped. The skip is the opt-in
  `differential_slow` sweep, which is intentionally excluded from fast local
  loops unless selected explicitly.
- `uv run pytest tests/test_differential.py -q --simulator=verilator`
- Result: 3 skipped because Verilator is not installed locally. This is
  non-evidence, not a pass.

**Updated 2026-07-22:** the nightly workflow commands pass locally: Icarus
`differential_slow` records **1 passed**, and Verilator smoke/fast records **2
passed, 1 deselected**. The scheduled remote run remains pending for the
current commit.

**Updated 2026-07-26:** live differential observations now include
`attempt_fired` and `disabled_o`. External `disable_i` is part of deterministic
and Hypothesis stimulus, so `disabled_o` is exercised high and low. Icarus and
Verilator fast each record **16 passed**; date-seeded slow sweeps each record
**1 passed**, with 64 Hypothesis examples inside each slow test. Historical
schema-v1 replay files without the two new fields remain readable but do not
substitute for new live full-contract traces.

**Updated 2026-07-11**: A nightly differential workflow
(`.github/workflows/differential-nightly.yml`) has been added to capture both
the slow iverilog sweep and the Verilator smoke/fast differential evidence on
a Verilator-equipped CI runner. The push/PR CI's Verilator axis already runs
the non-slow differential tests.

The Phase 12 differential harness lives in `tests/differential_cases.py`,
`tests/test_differential_cases.py`, `tests/test_differential_oracle.py`,
`tests/test_differential.py`, and `tests/test_differential_regressions.py`.
It generates bounded SVA source modules, compiles them through slang and the
normal importer/normalizer/composer path, generates bounded stimulus, compares
`active/pass/fail/attempt_fired/disabled_o/overflow` where available, and writes sanitized mismatch
artifacts for later promotion to `tests/differential/regressions/`.

The first local differential run exposed and fixed a Python oracle routing bug
for single-cycle implication with a false antecedent; regression coverage was
added in `tests/test_behavioral_oracle.py`.

**Deep-audit update 2026-07-22:** the source reference no longer imports the
production behavioral oracle. The deterministic catalog covers 14 cases,
including all five sampled-value families and `##8`; the randomized grammar is
truthfully bounded to one temporal operator around boolean leaves. Nightly keeps
the historical seed and adds a UTC-date seed, with sanitized mismatch artifacts
uploaded on failure. A new NFA invariant regression also caught and fixed ranged
delay exits targeting an out-of-range state; `tests/test_composer_mutation_boundaries.py`
now checks every transition endpoint and both `##[2:4]` early exits.

## Main Matrix

| Construct variant | Boundary | Status | Source fixture | Import / normalize / compose / emit | Icarus | Verilator | Behavioral oracle / reference | BMC / prove | Yosys / lint | Negative tests | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Boolean leaf / scalar boolean expression | Structured two-state subset: scalar or one-dimensional fixed packed identifiers, integer constants, `!`, `&&`, `\|\|`, `==`, `!=`, and single-bit identifier selects; arithmetic/general part-selects/calls/multi-dimensional or aggregate types/X/Z remain out of scope | Bounded evidence | present: `tests/fixtures/bool_assert.sv`; `tests/fixtures/bool_semantics.sv` | present: `tests/test_pipeline_e2e.py#test_e2e_bool_assert`; `tests/test_pipeline_e2e.py#test_e2e_bool_semantics_fixture_renders_supported_forms`; `tests/test_ast_importer.py`; `tests/test_composer.py`; `tests/test_optimizer.py` | present: `tests/test_pipeline_e2e.py#test_e2e_output_compiles_iverilog` | present at executable baseline `de3f697`: Verilator matrix in CI run `30709818712` | present: `tests/test_bool_semantics.py`; `tests/test_behavioral_oracle.py`; semantic formal references in `tests/test_formal_sva_equiv.py#TestBoolExprSvaEquiv` | present: `tests/test_formal_kinduction.py#TestKinductionBoolExpr`; Phase 10 `arbitrary_start` BMC depth 15, `arbitrary_disable` full-contract BMC depth 12, and `reset_recovery` BMC depth 15 in `tests/test_formal_sva_equiv.py#TestBoolExprSvaEquiv` | present: local Yosys smoke and Verilator strict lint; present at executable baseline `de3f697`: generated RTL gate passed in CI run `30709818712` | present: `tests/test_ast_importer.py#test_build_bool_expr_rejects_unsupported_boolean_subforms`; `tests/test_ast_importer.py#test_expr_to_sv_unsupported_kind_raises`; exact-type and false-PROVEN regressions in `tests/test_ast_importer.py` and `tests/test_formal_advanced_safety.py` | Multi-dimensional and complex types fail closed rather than partially parsing the first packed range; row remains bounded until row-specific evidence is broadened. |
| `##N` fixed delay | Positive fixed cycle delay | Bounded evidence | present: `tests/sv_fixtures/delay_fixed_1.sv`; `tests/sv_fixtures/delay_fixed_3.sv`; `tests/sv_fixtures/delay_fixed_8.sv`; `tests/fixtures/delay_assert.sv` | present: `tests/test_pipeline_e2e.py#test_e2e_delay_assert_rejected`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_delay.py` | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: `tests/simulation/test_sim_delay.py`; independent formal reference in `tests/test_formal_sva_equiv.py` | present: `tests/test_formal_sva_equiv.py#TestDelaySvaEquiv`; Phase 10 `##1` k-induction proof in `tests/test_formal_kinduction.py#TestKinductionFixedDelay` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: generated RTL lint in CI run `30709818712` | N/A: accepted finite-state form | Strong bounded evidence; promotion still waits for row-specific independent and formal boundary closure. |
| `##[M:N]` bounded delay | Finite range with `M <= N`; lower bound 0 has `##0` caveat below | Bounded evidence | present: `tests/sv_fixtures/delay_range_0_1.sv`; `tests/sv_fixtures/delay_range_2_5.sv`; `tests/sv_fixtures/delay_range_0_15.sv` | present: `tests/test_ast_importer.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_delay.py` | present: CI run `28931676000` Verilator matrix | present: `tests/simulation/test_sim_delay.py`; independent formal reference in `tests/test_formal_sva_equiv.py` | present: `tests/test_formal_sva_equiv.py#TestDelaySvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: `tests/test_nyquist_gaps.py#test_nyq10_range_delay_min_gt_max_raises` | Bounded because evidence remains incomplete beyond local Yosys smoke. |
| `##0` same-cycle fusion | BoolExpr `##0` BoolExpr auto-rewritten to `(a) && (b)`; non-BoolExpr `##0` rejected | Bounded evidence | present: `tests/sv_fixtures/delay_range_0_1.sv`; JSON unit evidence in `tests/fixtures/delay_zero.json` | present: `tests/test_sequential.py`; normalizer rewrite in `_handle_fusion_delay` | present: `tests/simulation/test_sim_delay.py` | present: CI run `28931676000` Verilator matrix | present: oracle matches rewritten BoolExpr semantics | present: BMC reference for merged boolean leaf | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: Verilator lint in CI run `30709818712` | present: `tests/test_v15_g2a_reject.py` and importer rejection paths | v1.7 LANG-01: BoolExpr `##0` rewritten to `&&`; complex forms rejected. |
| <code>\|-&gt;</code> overlapping implication | Single-cycle and fixed-delay/NFA-liftable consequent subset | Bounded evidence | present: `tests/sv_fixtures/impl_overlap_simple.sv`; `tests/sv_fixtures/impl_overlap_delay.sv` | present: `tests/test_v151_p2_implication_nfa.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_implication.py`; `tests/simulation/test_sim_p2_implication_nfa.py`; false-antecedent `attempt_fired` regression runs under both backends | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: source reference compares full checker contract and external disable | present: `tests/test_formal_sva_equiv.py`; `tests/test_v151_p2_bmc.py`; Phase 10 simple `a \|-> b` k-induction proof in `tests/test_formal_kinduction.py#TestKinductionImplication` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: generated RTL lint in CI run `30709818712` | present: `tests/test_v151_p2_implication_nfa.py#TestP2ImplicationNfaRejections` | Simple overlap is k-induction proven; `attempt_fired` records `start` rather than antecedent success; promotion waits for row-specific independent and full-contract closure. |
| <code>\|=&gt;</code> non-overlapping implication | Single-cycle and fixed-delay/NFA-liftable consequent subset | Bounded evidence | present: `tests/sv_fixtures/impl_nonoverlap_simple.sv` | present: `tests/test_v151_p2_implication_nfa.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_implication.py`; `tests/simulation/test_sim_p2_implication_nfa.py`; false-antecedent `attempt_fired` regression runs under both backends | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: source reference compares full checker contract and external disable | present: `tests/test_formal_sva_equiv.py`; `tests/test_v151_p2_bmc.py` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: `tests/test_multiclock.py#test_overlapping_implication_cross_clock_rejected` for invalid cross-clock overlap | Non-overlap alignment and start-based anti-vacuity evidence are covered; generated lint is present at `de3f697`; other row-specific gaps remain. |
| `[*N]` fixed consecutive repetition | Fixed positive finite count | Bounded evidence | present: `tests/sv_fixtures/rep_fixed.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_rep_fixed`; JSON fixture `tests/fixtures/rep_fixed.json` | present: `tests/test_repetition.py`; `tests/test_ast_importer.py` | present: `tests/simulation/test_sim_repetition.py` | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: Python oracle and formal reference | present: `tests/test_formal_sva_equiv.py`; Phase 10 `a[*3]` k-induction proof in `tests/test_formal_kinduction.py#TestKinductionRepConsecutive` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: generated RTL lint in CI run `30709818712` | present: `tests/test_repetition.py#test_import_unbounded_rejects` | k-induction proven; promotion still waits for row-specific independent and formal boundary closure. |
| `[*M:N]` bounded consecutive repetition | Finite range with `M <= N` | Bounded evidence | present: `tests/sv_fixtures/rep_range.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_rep_range`; JSON fixture `tests/fixtures/rep_range.json` | present: `tests/test_repetition.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_repetition.py` | present: CI run `28931676000` Verilator matrix | present: Python oracle and formal reference | present: `tests/test_formal_sva_equiv.py` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: `tests/test_nyquist_gaps.py` for invalid range patterns | Real-source E2E added; generated lint is present at `de3f697`; other row-specific gaps remain. |
| Sampled value functions `$rose`, `$fell`, `$stable`, `$changed`, `$past(sig,N)` | Plain scalar identifier only; `$past` positive finite depth; optional sampled arguments excluded | Bounded evidence | present: `tests/sv_fixtures/rose.sv`, `fell.sv`, `stable.sv`, `changed.sv`, `past.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_rose` et al.; JSON fixtures retained | present: `tests/test_ast_importer.py`; `tests/test_formal_kinduction.py` | present: `tests/simulation/test_sim_rose.py`; `test_sim_fell.py`; `test_sim_stable.py`; `test_sim_past.py`; reserved-port alias runs under both backends | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: simulator oracle and independent formal references | present: `tests/test_formal_sva_equiv.py`; k-induction for `$rose`, `$fell`, `$stable`, `$changed` in `tests/test_formal_kinduction.py`; Phase 10 `$rose` full-contract BMC depth 12 | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: generated RTL lint in CI run `30709818712` | present: vector/expression/optional-argument/non-positive-depth rejection in `tests/test_ast_importer_mutation_boundaries.py`; manual-IR identifier/clock collision rejection in `tests/test_signal_functions.py` | Four edge/state functions are k-induction proven; `$past` is BMC-only and promotion waits for row-specific independent and full-contract closure. |
| `disable iff` | Disable condition gates attempts and clears active state | Bounded evidence | present: `tests/sv_fixtures/disable_iff.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_disable_iff`; JSON fixture `tests/fixtures/disable_iff.json` (slang v11 `DisableIff` kind now handled by importer) | present: importer/composer coverage via tests and templates | present: `tests/simulation/test_sim_disable_iff.py` | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: simulator oracle with reset/disable semantics | present: `tests/test_formal_sva_equiv.py`; Phase 10 arbitrary-disable pass/fail BMC depth 15 in `TestDisableIffSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: generated RTL lint in CI run `30709818712` | N/A: accepted control form | Full-contract bundle remains future work; promotion still waits for row-specific full-contract closure. |
| Named sequences | Non-circular named sequence references; circular references rejected | Bounded evidence | present: `tests/sv_fixtures/named_seq.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_named_seq`; JSON fixtures retained (slang v11 `AssertionInstance` kind now handled) | present: `tests/test_named_sequences.py`; importer coverage | present: `tests/simulation/test_sim_named_seq.py --simulator=iverilog` | present at executable baseline `de3f697`: Verilator matrix in CI run `30709818712` | present: source-authored `a ##1 b` reference and simulator oracle | present: `tests/test_formal_sva_equiv.py#TestNamedSequenceSvaEquiv`, independent pass/fail BMC depth 18 | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: `tests/test_named_sequences.py#test_circular_ref_rejected_with_sva_e003` | Dedicated non-circular BMC is now present; row remains bounded by its non-remote row-specific gaps. |
| `[->N]` fixed goto repetition | Fixed positive count; one start pulse arms attempt until Nth occurrence | Bounded evidence | present: `tests/sv_fixtures/goto_rep.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_goto_rep`; JSON fixture `tests/fixtures/goto_rep.json` | present: `tests/test_repetition.py#test_import_goto_rep`; emit golden coverage | present: `tests/simulation/test_sim_repetition.py#TestGotoRepSimulation` | present: CI run `28931676000` Verilator matrix | present: updated behavioral oracle; independent formal reference | present: `tests/test_formal_sva_equiv.py#TestGotoRepSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: ranged rejection tests in `tests/test_repetition.py` | Real-source E2E added; generated lint is present at `de3f697`; other row-specific gaps remain. |
| `[->M:N]` ranged goto repetition | Ranged count where `M < N` is not implemented in v1 | Unsupported / rejected | N/A: rejected variant | present: `tests/test_repetition.py#test_import_goto_rep_ranged_count_rejected` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: `tests/test_repetition.py#test_import_goto_rep_ranged_count_rejected` | Explicit `SVA-E002` rejection prevents silent lower-bound collapse. |
| `[=N]` fixed nonconsecutive repetition | Fixed positive count; relaxed tail after Nth occurrence | Bounded evidence | present: `tests/sv_fixtures/nonconsec_rep.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_nonconsec_rep`; JSON fixture `tests/fixtures/nonconsec_rep.json` | present: `tests/test_repetition.py#test_import_nonconsec_rep`; emit golden coverage | present: `tests/simulation/test_sim_repetition.py#TestNonconsecRepSimulation` | present: CI run `28931676000` Verilator matrix | present: updated behavioral oracle; independent formal reference | present: `tests/test_formal_sva_equiv.py#TestNonconsecRepSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: ranged rejection tests in `tests/test_repetition.py` | Real-source E2E added; generated lint is present at `de3f697`; other row-specific gaps remain. |
| `[=M:N]` ranged nonconsecutive repetition | Ranged count where `M < N` is not implemented in v1 | Unsupported / rejected | N/A: rejected variant | present: `tests/test_repetition.py#test_import_nonconsec_rep_ranged_count_rejected` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: `tests/test_repetition.py#test_import_nonconsec_rep_ranged_count_rejected` | Explicit `SVA-E002` rejection prevents silent lower-bound collapse. |
| `first_match` | Earliest completion wrapper for supported sequence operand | Bounded evidence | present: `tests/sv_fixtures/first_match.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_first_match`; JSON fixture `tests/fixtures/first_match.json` | present: `tests/test_repetition.py#test_import_first_match`; emit golden coverage | present: simulation coverage through repetition/NFA suites | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: behavioral oracle and independent formal reference | present: `tests/test_formal_sva_equiv.py#TestFirstMatchSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: generated RTL lint in CI run `30709818712` | N/A: accepted wrapper over supported operand subset | Strong bounded evidence; promotion still waits for row-specific independent and formal boundary closure. |
| Sequence `and` / `or` | Boolean/simple sequence composition | Bounded evidence | present: `tests/fixtures/and_seq.sv`; `tests/fixtures/or_seq.sv` | present: `tests/test_v13_operators.py`; `tests/test_integration.py` | present: `tests/simulation/test_sim_v13_operators.py`, including no-contradictory-fail regression for `or` | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: semantic hierarchical oracle plus source-authored truth-table references | present: `tests/test_formal_sva_equiv.py#TestSimpleBinarySequenceSvaEquiv`, independent pass/fail BMC depth 15 for both operators | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | N/A: accepted finite subset | Independent BMC exposed and closed the `or` contradictory pass/fail defect; both rows remain bounded by row-specific independent and formal gaps. |
| `intersect` / `within` / `throughout` with NFA-liftable operands | Bool, fixed/ranged delay, fixed/ranged repetition, SeqOr, SeqGotoRep, SeqNonconsecRep, nested composition within K-state budget (v1.7 LANG-02..04) | Bounded evidence | present: `tests/fixtures/intersect_seq.sv`; `tests/fixtures/throughout_seq.sv`; missing real `.sv` for many NFA-lifted variants | present: `tests/test_v151_nfa_intersect.py`; `tests/test_v151_nfa_within_throughout.py`; `tests/test_v151_p3_nested.py`; `tests/test_v15_g2a_reject.py` (now acceptance) | present: `tests/simulation/test_sim_nfa_multi_cycle.py`; `tests/simulation/test_sim_v13_operators.py` | present: CI run `28931676000` Verilator matrix | present: rule-based simulator oracle and independent BMC references | present: `tests/test_v151_nfa_bmc.py`; nested compile/budget tests in `tests/test_v151_p3_nested.py` | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: `tests/test_v15_g2a_reject.py` (acceptance tests); `tests/test_v151_p3_nested.py#test_k33_rejected` | v1.7 LANG-02..04: SeqOr, ranged delay/repetition, goto/nonconsec now NFA-liftable. |
| Non-liftable NFA operands in `intersect` / `within` / `throughout` | Multi-clock operands, excessive K-state (>32) | Unsupported / rejected | N/A: rejected variant | present: budget enforcement in `_lift_to_nfa` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: K-state budget rejection tests | v1.7 eliminated SeqOr/goto/nonconsec/ranged rejection; only K-budget and CDC remain. |
| Property `not` | Swaps pass/fail over supported property operand | Bounded evidence | present: `tests/fixtures/prop_not.sv` | present: `tests/test_v13_operators.py`; `tests/test_integration.py` | present: `tests/simulation/test_sim_v13_operators.py` | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: behavioral oracle tests and source-authored violation expression | present: `tests/test_formal_sva_equiv.py#TestPropertyNotSvaEquiv`, independent BMC depth 15 | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | N/A: accepted finite subset | Non-circular BMC is present; row remains bounded by row-specific independent and full-contract gaps. |
| Property `if...else` | Conditional selection between supported property branches | Bounded evidence | present: `tests/fixtures/if_else_prop.sv` | present: `tests/test_v13_operators.py`; `tests/test_integration.py` | present: v1.3 simulation/oracle coverage | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: behavioral oracle tests and source-authored branch expression | present: `tests/test_formal_sva_equiv.py#TestPropIfElseSvaEquiv`, independent BMC depth 15 | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | N/A: accepted finite subset | Non-circular BMC is present; row remains bounded by row-specific independent and full-contract gaps. |
| Bounded liveness `s_eventually [m:n]`, `eventually [m:n]`, `always [m:n]`, `s_always [m:n]`, weak `until`, `until_with` | Boolean operand, finite window or safety form | Bounded evidence | missing: JSON/direct-IR fixtures `tests/fixtures/s_eventually_1_3.json`, `always_1_3.json`, `until_ab.json` only | present: `tests/test_liveness.py` | present: `tests/simulation/test_sim_liveness.py` | historical: CI run `28931676000`; qualified at executable baseline `de3f697` by CI run `30709818712` | present: simulator oracle and source-authored formal references | present: `TestSEventuallySvaEquiv`, `TestSAlwaysSvaEquiv`, and `TestUntilSvaEquiv` in `tests/test_formal_sva_equiv.py`, independent pass/fail BMC depth 20 | present: local Yosys smoke `tests/test_synthesis_gates.py`; present at executable baseline `de3f697`: `tests/test_generated_lint.py` passed in CI run `30709818712` | present: unbounded/strong rejection tests in `tests/test_liveness.py` | Bounded finite-state subset only; liveness remains BMC-only rather than k-induction proven. |
| Formal-only unbounded liveness | Boolean `s_eventually p`; Boolean `a \|-> s_eventually b` / `a \|=> s_eventually b`; Boolean `a s_until b` / `a s_until_with b` | Conditional formal evidence; monitor rejected | present: real `.sv` sources generated in `tests/test_formal_liveness.py` | present: slang import to `PropEventually` / `PropStrongUntil`, formal-only lowering, `$live` / `$fair` harness, and enforced monitor-composer rejection | N/A: no finite-verdict simulation monitor | N/A: no finite-verdict simulation monitor | present: obligation-shape and safety-split structural checks; independent external live-oracle diversity remains missing | conditional: SymbiYosys `mode live`, `aiger suprove`; AIG preparation and fail-closed missing-engine `UNKNOWN` are locally tested; real good/bad proof tests run when `suprove` is installed | N/A: proof harness only, not synthesized monitor RTL | present: BMC rejection, missing-engine `UNKNOWN`, invalid fairness, monitor-composer rejection, and unsupported-shape paths | This partially replaces a commercial SVA frontend for the named shapes. `PROVEN` requires a real live-engine pass plus critical cover reachability; no live solver or failed cover is never PASS. |
| Other unbounded / infinite-state forms | Nested/property-composed liveness outside the documented profiles, unbounded repetition/delay, non-Boolean live operands | Unsupported / rejected | N/A: rejected variant | present: explicit classifier/lowering boundaries in `tests/test_formal_liveness.py`, `tests/test_liveness.py`, and `tests/test_repetition.py` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: formal-shape and unbounded-repetition rejection tests | Unbounded Boolean `always` is a separate supported formal-only invariant row above. Do not replace unsupported forms with an arbitrary bound unless the protocol itself specifies that deadline. Use checked decomposition or another frontend with the required semantics. |
| Four-state / X/Z-dependent semantics | X/Z/? literals, wildcard/case equality, or any result depending on unknown/high-impedance values | Unsupported in named two-state profile | present: real X and Z source cases generated in `tests/test_formal_boundaries.py` | present: literal rejection plus hashed `semantic_profile.json` declaring `logic_semantics=two-state` and `x_z_semantics=unsupported` | N/A: rejected | N/A: rejected | N/A: no coercion oracle | explicit `UNSUPPORTED`, empty Yosys inputs, no SBY project | N/A: rejected | present: X and Z literal cases plus invalid profile choice | A two-state Boolean/bit-vector proof is not four-state SVA evidence. Use an explicit four-state frontend or remove X/Z dependence from the reviewed property. |
| Multi-clock path-one split/synchronize forms | Monitor: allowed `##1` clock changes and non-overlap cross-clock implication through trusted 2-DFF level synchronizer with explicit opt-in; Formal: no implicit clock collapse | Trusted monitor boundary / Formal unsupported | present: real source is generated in `tests/test_formal_boundaries.py`; monitor fixtures remain test-authored | present: `tests/test_multiclock.py`; formal classifier and sanitized unsupported evidence in `tests/test_formal_boundaries.py` | missing: no dynamic asynchronous clock-ratio or pulse-loss evidence | pending-remote: CI if dynamic tests are added later | trusted-boundary: per-domain monitor semantics only; formal workflow requires per-domain decomposition and reviewed sampled handoff | formal: explicit `UNSUPPORTED`, empty Yosys inputs, no SBY project; CDC/metastability remains excluded | trusted-boundary: local Yosys smoke and Verilator lint accept generated synchronizer structure under opt-in | present: default monitor rejection plus machine-readable formal rejection | No formal result is inferred from the experimental synchronizer. Split by domain and separately verify a handshake/toggle/FIFO handoff plus CDC signoff. |
| Restricted automatic scalar local capture | Exactly one 1-bit automatic `logic`/`bit`, one blocking capture, positive fixed delay, Boolean guard/condition, overlapping implication; formal-only | Conditional formal evidence / Synth rejected | present: real slang source generated in `tests/test_formal_locals.py` | present: `PropLocalCapture`, exact whitelist importer, symbolic-witness lowering, private `captured_q`; monitor composer rejection | N/A: no monitor | N/A: no monitor | present: saved-value-vs-current-value solver regression and structural local-not-a-port checks | present locally: correct DUT `PROVEN` plus cover; bad ack and changing captured input `FAILED` with trace in `tests/test_formal_locals.py` | N/A: formal harness only | present: vector/multiple locals, non-overlap, ranged delay, and monitor mode reject | Symbolic witness gives each selected attempt private capture state; universal selector quantification covers all attempts. Wider/general match-item semantics remain unsupported. |
| Other local variables and unsupported system functions | Vector/multiple/static locals, other match items or timing; `$countones`, `$onehot`, arrays/multi-dimensional sampled values | Unsupported / rejected | N/A: rejected variant | present: precise local boundary tests in `tests/test_formal_locals.py`; generic paths in `tests/test_ast_importer.py` / `tests/test_errors.py` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejected before solver | N/A: rejection path | present: unsupported evidence and construct-specific negative tests | Precompute explicit RTL state or use another frontend; no silent local sharing or two-state approximation is allowed. |

## Real Source Fixture Inventory

| Fixture | Rows covered | Evidence note |
|---------|--------------|---------------|
| `tests/fixtures/bool_assert.sv` | Boolean leaf / scalar expression | Full CLI source pipeline and Icarus compile evidence. |
| `tests/fixtures/bool_semantics.sv` | Structured boolean subset | Real-source fixture for OR, NOT, constants, nesting, equality/inequality, and single-bit bit-select rendering. |
| `tests/fixtures/delay_assert.sv` | `##N` fixed delay | Full CLI source pipeline evidence. |
| `tests/sv_fixtures/delay_fixed_1.sv` | `##N` fixed delay | Dedicated real-source fixture corpus. |
| `tests/sv_fixtures/delay_fixed_3.sv` | `##N` fixed delay | Dedicated real-source fixture corpus. |
| `tests/sv_fixtures/delay_fixed_8.sv` | `##N` fixed delay | Dedicated real-source fixture corpus. |
| `tests/sv_fixtures/delay_range_0_1.sv` | `##[M:N]`; `##0` boundary | Covers range lower-bound zero, but not semantic rewrite closure. |
| `tests/sv_fixtures/delay_range_2_5.sv` | `##[M:N]` bounded delay | Dedicated real-source fixture corpus. |
| `tests/sv_fixtures/delay_range_0_15.sv` | `##[M:N]` bounded delay | Dedicated real-source fixture corpus. |
| `tests/sv_fixtures/impl_overlap_simple.sv` | <code>\|-&gt;</code> simple overlap implication | Dedicated real-source fixture corpus. |
| `tests/sv_fixtures/impl_overlap_delay.sv` | <code>\|-&gt;</code> implication with delayed consequent | Dedicated real-source fixture corpus. |
| `tests/sv_fixtures/impl_nonoverlap_simple.sv` | <code>\|=&gt;</code> simple non-overlap implication | Dedicated real-source fixture corpus. |
| `tests/fixtures/and_seq.sv` | Sequence `and` | Legacy real-source fixture. |
| `tests/fixtures/or_seq.sv` | Sequence `or` | Legacy real-source fixture. |
| `tests/fixtures/intersect_seq.sv` | Boolean `intersect` | Legacy real-source fixture. |
| `tests/fixtures/throughout_seq.sv` | `throughout` with fixed-delay body | Legacy real-source fixture. |
| `tests/fixtures/prop_not.sv` | Property `not` | Legacy real-source fixture. |
| `tests/fixtures/if_else_prop.sv` | Property `if...else` | Legacy real-source fixture. |
| `tests/sv_fixtures/rep_fixed.sv` | `[*N]` fixed consecutive repetition | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_rep_fixed`. |
| `tests/sv_fixtures/rep_range.sv` | `[*M:N]` ranged consecutive repetition | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_rep_range`. |
| `tests/sv_fixtures/goto_rep.sv` | `[->N]` fixed goto repetition | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_goto_rep`. |
| `tests/sv_fixtures/nonconsec_rep.sv` | `[=N]` fixed nonconsecutive repetition | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_nonconsec_rep`. |
| `tests/sv_fixtures/rose.sv` | `$rose` sampled value | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_rose`; iverilog gate included. |
| `tests/sv_fixtures/fell.sv` | `$fell` sampled value | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_fell`. |
| `tests/sv_fixtures/stable.sv` | `$stable` sampled value | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_stable`. |
| `tests/sv_fixtures/changed.sv` | `$changed` sampled value | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_changed`. |
| `tests/sv_fixtures/past.sv` | `$past(sig,N)` sampled value | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_past`. |
| `tests/sv_fixtures/first_match.sv` | `first_match` wrapper | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_first_match`. |
| `tests/sv_fixtures/disable_iff.sv` | `disable iff` condition | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_disable_iff`; slang v11 `DisableIff` AST kind compatibility fixed. |
| `tests/sv_fixtures/named_seq.sv` | Named sequence reference | Real-source E2E via `test_sv_fixture_e2e.py#test_e2e_named_seq`; slang v11 `AssertionInstance` AST kind compatibility fixed. |

JSON fixtures and direct-IR unit tests remain valuable importer/composer/oracle
evidence, but they are not real-source evidence for `Fully supported` status.

## Evidence Status Summary

- **0 rows Fully supported** in the current v1.7.1/v2.0 qualification branch.
  F-01 and all same-commit remote workflow gates are closed; the strongest rows
  remain bounded until their remaining row-specific evidence gaps are closed.
- Real `.sv` source fixtures have been added for `[*N]`, `[*M:N]`, `[->N]`,
  `[=N]`, `$rose`, `$fell`, `$stable`, `$changed`, `$past`, `first_match`,
  `disable iff`, and named sequences via `tests/sv_fixtures/` and
  `tests/test_sv_fixture_e2e.py`.
- All slang v11 AST compatibility gaps are now closed: `DisableIff`
  (disable iff), `AssertionInstance` (named sequences), and `Binary`
  (property expressions) are all handled by the importer.
- Rows with remaining real-source, formal-depth, or synthesis gaps remain
  bounded even though the push/PR Verilator matrix is recorded in
  `PROJECT_STATUS.md`.
- Rows with local Yosys smoke evidence remain bounded until the rest of their
  evidence chain is complete.
- Verilator simulation and generated-RTL lint are confirmed with pinned 5.028
  on Linux and macOS in same-commit run `30683023280`; differential nightly and
  Full Formal are recorded in runs `30683026683` and `30683026438`. Yosys
  synthesis does not replace simulator or formal evidence.
- Multi-clock support remains a `Trusted boundary`.
- Rejected rows are positive evidence for rejection behavior only.
