# sva2rtl Support Matrix

This file is the authoritative support evidence ledger for v1.6. `README.md`
and `SUPPORTED_CONSTRUCTS.md` provide explanations and examples; this matrix
governs exact support status, subset boundaries, and verification evidence.

## Baseline CI Summary

Detailed remote CI evidence is recorded in `PROJECT_STATUS.md` under
`Remote CI Baseline Ledger`.

Current baseline state: run
[`28931676000`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/28931676000)
for commit `674cea1adf15dade7b664b76912b015c8da04614` completed successfully on
2026-07-08. It records lint, all Icarus matrix axes, all Verilator matrix axes,
and the push/PR `formal smoke` job. The complete proof sweep remains in the
manual and scheduled `Full Formal` workflow. Local skips for Verilator, Yosys,
or `sby` are not evidence pass.

## Support Status Legend

| Status | Meaning |
|--------|---------|
| Fully supported | Complete applicable evidence chain: real `.sv` source, compiler pipeline, Icarus, Verilator, independent oracle/reference, formal or justified N/A, synthesis/lint evidence where applicable, and rejection tests for unsupported variants. |
| Bounded evidence | Implemented and useful, but one or more industrial evidence links are missing, bounded, pending remote CI, or deferred to a later v1.6 phase. |
| Trusted boundary | Intentionally trusted component or excluded proof domain, such as the multi-clock 2-DFF synchronizer and CDC/metastability proof boundary. |
| Unsupported / rejected | Deliberately unsupported variant that should fail with explicit, actionable diagnostics and negative-test evidence where available. |

Current v1.6 evidence still assigns no construct row to `Fully supported`; the
remote push/PR CI baseline is published, Phase 9 adds structured boolean
semantic evidence, Phase 10 adds focused formal harness depth, and Phase 11
adds local Yosys generated-RTL smoke evidence plus CI wiring for generated RTL
lint. Phase 12 adds bounded source-level differential testing against the
independent Python oracle and Icarus. However, local Verilator lint and
Verilator differential checks were skipped because Verilator is absent, several
real-source fixtures remain missing, post-Phase09 Verilator reruns are still
pending for some rows, and broad all-construct full-contract proof depth remains
bounded.

## Evidence Cell Legend

| State | Meaning |
|-------|---------|
| present | Evidence exists and a concrete path or command is cited. |
| missing | Evidence is required for a stronger claim but no concrete evidence exists yet. |
| pending-remote | Evidence is configured in CI or a dual-simulator test, but the current remote run has not been recorded yet. |
| planned | Explicit future-phase work; not counted as current evidence. |
| N/A | Not applicable to this row, with rationale in notes where needed. |
| trusted-boundary | Intentionally trusted/excluded proof domain; not a missing implementation bug. |

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
| `disable iff` | `test_disable_iff_arbitrary_disable_bmc_depth15[pass]` and `[fail]` compare pass/fail with `disable_i` wired as a variable reference input. | arbitrary-disable semantics have bounded BMC depth 15. | Full-contract `disable iff` output bundle is not yet separately promoted; local Yosys smoke exists and generated Verilator lint remains pending remote CI. |
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
`active/pass/fail/overflow` where available, and writes sanitized mismatch
artifacts for later promotion to `tests/differential/regressions/`.

The first local differential run exposed and fixed a Python oracle routing bug
for single-cycle implication with a false antecedent; regression coverage was
added in `tests/test_behavioral_oracle.py`.

## Main Matrix

| Construct variant | Boundary | Status | Source fixture | Import / normalize / compose / emit | Icarus | Verilator | Behavioral oracle / reference | BMC / prove | Yosys / lint | Negative tests | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Boolean leaf / scalar boolean expression | Structured two-state subset: identifiers, integer constants, `!`, `&&`, `\|\|`, `==`, `!=`, and single-bit identifier selects; arithmetic/reductions/part-selects/calls/X/Z remain out of scope | Bounded evidence | present: `tests/fixtures/bool_assert.sv`; `tests/fixtures/bool_semantics.sv` | present: `tests/test_pipeline_e2e.py#test_e2e_bool_assert`; `tests/test_pipeline_e2e.py#test_e2e_bool_semantics_fixture_renders_supported_forms`; `tests/test_ast_importer.py`; `tests/test_composer.py`; `tests/test_optimizer.py` | present: `tests/test_pipeline_e2e.py#test_e2e_output_compiles_iverilog` | pending-remote: post-Phase09 `bool_semantics.sv` Verilator evidence not recorded locally; baseline scalar bool_expr present in CI run `28931676000` | present: `tests/test_bool_semantics.py`; `tests/test_behavioral_oracle.py`; semantic formal references in `tests/test_formal_sva_equiv.py#TestBoolExprSvaEquiv` | present: `tests/test_formal_kinduction.py#TestKinductionBoolExpr`; Phase 10 `arbitrary_start` BMC depth 15, `arbitrary_disable` full-contract BMC depth 12, and `reset_recovery` BMC depth 15 in `tests/test_formal_sva_equiv.py#TestBoolExprSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_ast_importer.py#test_build_bool_expr_rejects_unsupported_boolean_subforms`; `tests/test_ast_importer.py#test_expr_to_sv_unsupported_kind_raises` | Phase 9 removes the observed-signal shortcut for the supported subset; row remains bounded until post-Phase09 Verilator evidence and unsupported-form coverage are broadened. |
| `##N` fixed delay | Positive fixed cycle delay | Bounded evidence | present: `tests/sv_fixtures/delay_fixed_1.sv`; `tests/sv_fixtures/delay_fixed_3.sv`; `tests/sv_fixtures/delay_fixed_8.sv`; `tests/fixtures/delay_assert.sv` | present: `tests/test_pipeline_e2e.py#test_e2e_delay_assert_rejected`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_delay.py` | present: CI run `28931676000` Verilator matrix | present: `tests/simulation/test_sim_delay.py`; independent formal reference in `tests/test_formal_sva_equiv.py` | present: `tests/test_formal_sva_equiv.py#TestDelaySvaEquiv`; Phase 10 `##1` arbitrary-start BMC depth 20 and k-induction proof in `tests/test_formal_kinduction.py#TestKinductionFixedDelay` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | N/A: accepted finite-state form | Downgraded until remaining non-synthesis evidence gaps close. |
| `##[M:N]` bounded delay | Finite range with `M <= N`; lower bound 0 has `##0` caveat below | Bounded evidence | present: `tests/sv_fixtures/delay_range_0_1.sv`; `tests/sv_fixtures/delay_range_2_5.sv`; `tests/sv_fixtures/delay_range_0_15.sv` | present: `tests/test_ast_importer.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_delay.py` | present: CI run `28931676000` Verilator matrix | present: `tests/simulation/test_sim_delay.py`; independent formal reference in `tests/test_formal_sva_equiv.py` | present: `tests/test_formal_sva_equiv.py#TestDelaySvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_nyquist_gaps.py#test_nyq10_range_delay_min_gt_max_raises` | Bounded because evidence remains incomplete beyond local Yosys smoke. |
| `##0` same-cycle fusion | BoolExpr `##0` BoolExpr auto-rewritten to `(a) && (b)`; non-BoolExpr `##0` rejected | Bounded evidence | present: `tests/sv_fixtures/delay_range_0_1.sv`; JSON unit evidence in `tests/fixtures/delay_zero.json` | present: `tests/test_sequential.py`; normalizer rewrite in `_handle_fusion_delay` | present: `tests/simulation/test_sim_delay.py` | present: CI run `28931676000` Verilator matrix | present: oracle matches rewritten BoolExpr semantics | present: BMC reference for merged boolean leaf | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: Verilator lint | present: `tests/test_v15_g2a_reject.py` and importer rejection paths | v1.7 LANG-01: BoolExpr `##0` rewritten to `&&`; complex forms rejected. |
| <code>\|-&gt;</code> overlapping implication | Single-cycle and fixed-delay/NFA-liftable consequent subset | Bounded evidence | present: `tests/sv_fixtures/impl_overlap_simple.sv`; `tests/sv_fixtures/impl_overlap_delay.sv` | present: `tests/test_v151_p2_implication_nfa.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_implication.py`; `tests/simulation/test_sim_p2_implication_nfa.py` | present: CI run `28931676000` Verilator matrix | present: Python oracle and independent BMC reference | present: `tests/test_formal_sva_equiv.py`; `tests/test_v151_p2_bmc.py`; Phase 10 simple `a \|-> b` arbitrary-start BMC depth 15, full-contract BMC depth 15, and k-induction proof in `tests/test_formal_kinduction.py#TestKinductionImplication` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_v151_p2_implication_nfa.py#TestP2ImplicationNfaRejections` | Ranged delay consequents are still rejected; multi-cycle/NFA consequent proof depth remains bounded. |
| <code>\|=&gt;</code> non-overlapping implication | Single-cycle and fixed-delay/NFA-liftable consequent subset | Bounded evidence | present: `tests/sv_fixtures/impl_nonoverlap_simple.sv` | present: `tests/test_v151_p2_implication_nfa.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_implication.py`; `tests/simulation/test_sim_p2_implication_nfa.py` | present: CI run `28931676000` Verilator matrix | present: Python oracle and independent BMC reference | present: `tests/test_formal_sva_equiv.py`; `tests/test_v151_p2_bmc.py` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_multiclock.py#test_overlapping_implication_cross_clock_rejected` for invalid cross-clock overlap | Non-overlap alignment is covered; generated lint evidence remains pending remote CI. |
| `[*N]` fixed consecutive repetition | Fixed positive finite count | Bounded evidence | present: `tests/sv_fixtures/rep_fixed.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_rep_fixed`; JSON fixture `tests/fixtures/rep_fixed.json` | present: `tests/test_repetition.py`; `tests/test_ast_importer.py` | present: `tests/simulation/test_sim_repetition.py` | present: CI run `28931676000` Verilator matrix | present: Python oracle and formal reference | present: `tests/test_formal_sva_equiv.py`; Phase 10 `a[*3]` arbitrary-start BMC depth 20, full-contract BMC depth 20, and k-induction proof in `tests/test_formal_kinduction.py#TestKinductionRepConsecutive` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_repetition.py#test_import_unbounded_rejects` | Real-source E2E added; remaining boundary is remote lint evidence. |
| `[*M:N]` bounded consecutive repetition | Finite range with `M <= N` | Bounded evidence | present: `tests/sv_fixtures/rep_range.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_rep_range`; JSON fixture `tests/fixtures/rep_range.json` | present: `tests/test_repetition.py`; `tests/test_sequential.py` | present: `tests/simulation/test_sim_repetition.py` | present: CI run `28931676000` Verilator matrix | present: Python oracle and formal reference | present: `tests/test_formal_sva_equiv.py` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_nyquist_gaps.py` for invalid range patterns | Real-source E2E added; remaining boundary is remote lint evidence. |
| Sampled value functions `$rose`, `$fell`, `$stable`, `$changed`, `$past(sig,N)` | Scalar sampled-value subset; `$past` finite depth | Bounded evidence | present: `tests/sv_fixtures/rose.sv`, `fell.sv`, `stable.sv`, `changed.sv`, `past.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_rose` et al.; JSON fixtures retained | present: `tests/test_ast_importer.py`; `tests/test_formal_kinduction.py` | present: `tests/simulation/test_sim_rose.py`; `test_sim_fell.py`; `test_sim_stable.py`; `test_sim_past.py` | present: CI run `28931676000` Verilator matrix | present: simulator oracle and independent formal references | present: `tests/test_formal_sva_equiv.py`; k-induction for `$rose`, `$fell`, `$stable`, and `$changed` in `tests/test_formal_kinduction.py`; Phase 10 `$rose` arbitrary-start BMC depth 15 and full-contract BMC depth 12 | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_nyquist_gaps.py#test_nyq22_past_depth_warning` | Real-source E2E added for all five sampled-value functions; `$past` remains BMC-only. |
| `disable iff` | Disable condition gates attempts and clears active state | Bounded evidence | present: `tests/sv_fixtures/disable_iff.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_disable_iff`; JSON fixture `tests/fixtures/disable_iff.json` (slang v11 `DisableIff` kind now handled by importer) | present: importer/composer coverage via tests and templates | present: `tests/simulation/test_sim_disable_iff.py` | present: CI run `28931676000` Verilator matrix | present: simulator oracle with reset/disable semantics | present: `tests/test_formal_sva_equiv.py`; Phase 10 arbitrary-disable pass/fail BMC depth 15 in `TestDisableIffSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | N/A: accepted control form | Real-source E2E added (slang v11 DisableIff compatibility fixed); a dedicated full-contract `disable iff` bundle remains future work. |
| Named sequences | Non-circular named sequence references; circular references rejected | Bounded evidence | present: `tests/sv_fixtures/named_seq.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_named_seq`; JSON fixtures retained (slang v11 `AssertionInstance` kind now handled) | present: `tests/test_named_sequences.py`; importer coverage | present: `tests/simulation/test_sim_named_seq.py --simulator=iverilog` | pending-remote: post-Phase09 Verilator rerun required | present: simulator oracle in `tests/simulation/test_sim_named_seq.py`; broad bool leaf xfail removed by semantic bool leaf oracle | missing: no dedicated named-sequence BMC proof row | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_named_sequences.py#test_circular_ref_rejected_with_sva_e003` | Real-source E2E added (slang v11 AssertionInstance compatibility fixed); remaining boundary is dedicated BMC and remote Verilator. |
| `[->N]` fixed goto repetition | Fixed positive count; one start pulse arms attempt until Nth occurrence | Bounded evidence | present: `tests/sv_fixtures/goto_rep.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_goto_rep`; JSON fixture `tests/fixtures/goto_rep.json` | present: `tests/test_repetition.py#test_import_goto_rep`; emit golden coverage | present: `tests/simulation/test_sim_repetition.py#TestGotoRepSimulation` | present: CI run `28931676000` Verilator matrix | present: updated behavioral oracle; independent formal reference | present: `tests/test_formal_sva_equiv.py#TestGotoRepSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: ranged rejection tests in `tests/test_repetition.py` | Real-source E2E added; remaining boundary is remote lint evidence. |
| `[->M:N]` ranged goto repetition | Ranged count where `M < N` is not implemented in v1 | Unsupported / rejected | N/A: rejected variant | present: `tests/test_repetition.py#test_import_goto_rep_ranged_count_rejected` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: `tests/test_repetition.py#test_import_goto_rep_ranged_count_rejected` | Explicit `SVA-E002` rejection prevents silent lower-bound collapse. |
| `[=N]` fixed nonconsecutive repetition | Fixed positive count; relaxed tail after Nth occurrence | Bounded evidence | present: `tests/sv_fixtures/nonconsec_rep.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_nonconsec_rep`; JSON fixture `tests/fixtures/nonconsec_rep.json` | present: `tests/test_repetition.py#test_import_nonconsec_rep`; emit golden coverage | present: `tests/simulation/test_sim_repetition.py#TestNonconsecRepSimulation` | present: CI run `28931676000` Verilator matrix | present: updated behavioral oracle; independent formal reference | present: `tests/test_formal_sva_equiv.py#TestNonconsecRepSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: ranged rejection tests in `tests/test_repetition.py` | Real-source E2E added; remaining boundary is remote lint evidence. |
| `[=M:N]` ranged nonconsecutive repetition | Ranged count where `M < N` is not implemented in v1 | Unsupported / rejected | N/A: rejected variant | present: `tests/test_repetition.py#test_import_nonconsec_rep_ranged_count_rejected` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: `tests/test_repetition.py#test_import_nonconsec_rep_ranged_count_rejected` | Explicit `SVA-E002` rejection prevents silent lower-bound collapse. |
| `first_match` | Earliest completion wrapper for supported sequence operand | Bounded evidence | present: `tests/sv_fixtures/first_match.sv`; `tests/test_sv_fixture_e2e.py#test_e2e_first_match`; JSON fixture `tests/fixtures/first_match.json` | present: `tests/test_repetition.py#test_import_first_match`; emit golden coverage | present: simulation coverage through repetition/NFA suites | present: CI run `28931676000` Verilator matrix | present: behavioral oracle and independent formal reference | present: `tests/test_formal_sva_equiv.py#TestFirstMatchSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | N/A: accepted wrapper over supported operand subset | Real-source E2E added; remaining boundary is remote lint evidence. |
| Sequence `and` / `or` | Boolean/simple sequence composition | Bounded evidence | present: `tests/fixtures/and_seq.sv`; `tests/fixtures/or_seq.sv` | present: `tests/test_v13_operators.py`; `tests/test_integration.py` | present: `tests/simulation/test_sim_v13_operators.py` | present: CI run `28931676000` Verilator matrix | present: v1.3 simulation/oracle tests | missing: no dedicated non-circular BMC row for each simple `and`/`or` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | N/A: accepted finite subset | `or` evidence is weaker than `and`; both remain bounded. |
| `intersect` / `within` / `throughout` with NFA-liftable operands | Bool, fixed/ranged delay, fixed/ranged repetition, SeqOr, SeqGotoRep, SeqNonconsecRep, nested composition within K-state budget (v1.7 LANG-02..04) | Bounded evidence | present: `tests/fixtures/intersect_seq.sv`; `tests/fixtures/throughout_seq.sv`; missing real `.sv` for many NFA-lifted variants | present: `tests/test_v151_nfa_intersect.py`; `tests/test_v151_nfa_within_throughout.py`; `tests/test_v151_p3_nested.py`; `tests/test_v15_g2a_reject.py` (now acceptance) | present: `tests/simulation/test_sim_nfa_multi_cycle.py`; `tests/simulation/test_sim_v13_operators.py` | present: CI run `28931676000` Verilator matrix | present: rule-based simulator oracle and independent BMC references | present: `tests/test_v151_nfa_bmc.py`; nested compile/budget tests in `tests/test_v151_p3_nested.py` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: `tests/test_v15_g2a_reject.py` (acceptance tests); `tests/test_v151_p3_nested.py#test_k33_rejected` | v1.7 LANG-02..04: SeqOr, ranged delay/repetition, goto/nonconsec now NFA-liftable. |
| Non-liftable NFA operands in `intersect` / `within` / `throughout` | Multi-clock operands, excessive K-state (>32) | Unsupported / rejected | N/A: rejected variant | present: budget enforcement in `_lift_to_nfa` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: K-state budget rejection tests | v1.7 eliminated SeqOr/goto/nonconsec/ranged rejection; only K-budget and CDC remain. |
| Property `not` | Swaps pass/fail over supported property operand | Bounded evidence | present: `tests/fixtures/prop_not.sv` | present: `tests/test_v13_operators.py`; `tests/test_integration.py` | present: `tests/simulation/test_sim_v13_operators.py` | present: CI run `28931676000` Verilator matrix | present: behavioral oracle tests | missing: no dedicated non-circular BMC row | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | N/A: accepted finite subset | Evidence is useful but not complete. |
| Property `if...else` | Conditional selection between supported property branches | Bounded evidence | present: `tests/fixtures/if_else_prop.sv` | present: `tests/test_v13_operators.py`; `tests/test_integration.py` | present: v1.3 simulation/oracle coverage | present: CI run `28931676000` Verilator matrix | present: behavioral oracle tests | missing: no dedicated non-circular BMC row | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | N/A: accepted finite subset | Evidence is useful but not complete. |
| Bounded liveness `s_eventually [m:n]`, `eventually [m:n]`, `always [m:n]`, `s_always [m:n]`, weak `until`, `until_with` | Boolean operand, finite window or safety form | Bounded evidence | missing: JSON/direct-IR fixtures `tests/fixtures/s_eventually_1_3.json`, `always_1_3.json`, `until_ab.json` only | present: `tests/test_liveness.py` | present: `tests/simulation/test_sim_liveness.py` | present: CI run `28931676000` Verilator matrix | present: simulator oracle and independent formal references | present: `tests/test_formal_sva_equiv.py#TestBoundedLivenessSvaEquiv` | present: local Yosys smoke `tests/test_synthesis_gates.py`; pending-remote: generated Verilator lint gate `tests/test_generated_lint.py` is configured in CI | present: unbounded/strong rejection tests in `tests/test_liveness.py` | Bounded finite-state subset only; Phase 10 did not promote liveness to k-induction proof. |
| Unbounded liveness / infinite-state forms | `s_eventually a`, unbounded `always`, strong `s_until`, unbounded repetition/delay | Unsupported / rejected | N/A: rejected variant | present: `tests/test_liveness.py`; `tests/test_repetition.py` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: `tests/test_liveness.py#test_unbounded_s_eventually_rejected`; `tests/test_repetition.py#test_import_unbounded_rejects` | Not synthesizable as finite hardware monitor semantics. |
| Multi-clock path-one split/synchronize forms | Allowed `##1` clock changes and non-overlap cross-clock implication through trusted 2-DFF synchronizer | Trusted boundary | missing: no public real `.sv` fixture in root fixture corpus | present: `tests/test_multiclock.py` | missing: no dynamic multi-clock simulator ratio evidence yet | pending-remote: CI if dynamic tests are added later | trusted-boundary: per-domain semantics; CDC/metastability excluded | trusted-boundary: full CDC/metastability proof excluded | trusted-boundary: local Yosys smoke `tests/test_synthesis_gates.py` accepts generated synchronizer structure; pending-remote: generated Verilator lint gate is configured in CI; future FPGA/prototype evidence remains planned | present: `tests/test_multiclock.py#test_overlapping_implication_cross_clock_rejected`; `#test_cross_clock_delay_n_neq_1_rejected_by_slang` | Trusted 2-DFF synchronizer boundary, not full CDC proof. |
| Local variables and unsupported system functions | Sequence local variables; `$countones`, `$onehot`, arrays/multi-dimensional sampled values | Unsupported / rejected | N/A: rejected or unsupported variant | present: generic unsupported paths in `tests/test_ast_importer.py`; `tests/test_errors.py` | N/A: rejection occurs before simulation | N/A: rejection occurs before simulation | N/A: rejection path | N/A: rejection path | N/A: rejection path | present: `tests/test_errors.py`; unsupported construct tests | Demand-pulled future work only; not part of v1.6 language closure. |

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

## Downgrade Summary

- Real `.sv` source fixtures have been added for `[*N]`, `[*M:N]`, `[->N]`,
  `[=N]`, `$rose`, `$fell`, `$stable`, `$changed`, `$past`, `first_match`,
  `disable iff`, and named sequences via `tests/sv_fixtures/` and
  `tests/test_sv_fixture_e2e.py`. These rows retain `Bounded evidence`
  status until remote Verilator lint evidence is recorded.
- All slang v11 AST compatibility gaps are now closed: `DisableIff`
  (disable iff), `AssertionInstance` (named sequences), and `Binary`
  (property expressions) are all handled by the importer.
- Rows with remaining real-source, formal-depth, or synthesis gaps remain bounded
  even though the push/PR Verilator matrix is now recorded in `PROJECT_STATUS.md`.
- Rows with local Yosys smoke evidence remain bounded until the rest of each
  row's evidence chain is complete; local Verilator lint skips are not pass
  evidence.
- Rows with Phase 12 differential evidence remain bounded until Verilator
  differential evidence is recorded on a Verilator-equipped host or CI, and
  until broader slow/nightly sweeps are run.
- Multi-clock support is a `Trusted boundary`, not full CDC/metastability proof.
- Rejected rows are positive evidence only for rejection behavior, not support
  evidence for the corresponding accepted subset.
