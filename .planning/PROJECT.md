# sva2rtl

## What This Is

An Apache-2.0 open-source SVA compiler with two deliberately separated backends.
Its primary backend lowers supported SVA semantics into an auditable open-source
formal-verification harness for a user DUT; its secondary backend emits
synthesizable monitor RTL in SystemVerilog or Verilog-2001.  Both start from
slang-derived typed semantics and must fail closed when a requested meaning or
proof obligation cannot be preserved.

## Core Value

Let engineers verify useful SVA properties against real DUTs without a commercial
SVA front end, while reporting a proof, counterexample, or explicit
UNKNOWN/UNSUPPORTED result whose assumptions and coverage are reproducible.

## Current Milestone: v2.0 Open Formal Verification

**Goal:** Establish a formal-first, fully open workflow from a user DUT and SVA
source to a replayable proof or counterexample, then expand the useful SVA subset
through semantics-preserving rewrites, symbolic witnesses, and decomposition.

**Target features:**

- Add a user-facing formal command that keeps original advanced SVA out of Yosys,
  imports the DUT through slang, emits a generated checker/harness, runs SBY, and
  records exact evidence and assumptions.
- Classify finite-verdict, safety, bounded-liveness, and true-liveness semantics
  before backend selection; never report bounded exploration as an unbounded proof.
- Normalize high-value unsupported syntax into a smaller semantic kernel where
  equivalence can be independently tested or proven.
- Decouple formal state from synthesizable-monitor resource limits and add
  symbolic-witness/property-slicing interfaces for state-explosion control.
- Provide a qualified liveness path when an open live engine is installed and a
  deterministic UNKNOWN result otherwise; retain explicit CDC and 4-state limits.
- Close the evidence chain with real DUT examples, negative tests, mutation and
  differential tests, exact-commit CI/nightly/formal evidence, and honest docs.

**Explicit scope boundary:** This milestone does not claim complete IEEE 1800 SVA,
commercial-engine equivalence, analogue metastability signoff, or unrestricted
four-state semantics.  Such cases must be decomposed under a checked contract or
reported as UNKNOWN/UNSUPPORTED.

## Current State

**Baseline:** v1.7.1 package line with the completed v2.0 Open Formal
Verification capability milestone on 2026-08-04.

- `sva2rtl-formal` verifies supported SVA against a separate real DUT without
  passing the original advanced assertion to Yosys. It emits replayable,
  hashed PROVEN/FAILED/UNKNOWN/UNSUPPORTED/TIMEOUT evidence and counterexamples.
- Formal-only safety, symbolic-witness, restricted local capture, and selected
  open-liveness routes are separate from finite synthesizable monitor RTL.
- Critical covers, explicit fairness, typed interfaces, decomposition proof
  bindings, multi-clock/XZ rejection profiles, package smoke, and privacy gates
  are part of the release contract.
- Exact executable `e1405b65e79f924e4f0eee5c2fd0230d35eec22b` passed CI
  `30891680942` (13/13), nightly `30891694691` (3/3), and Full Formal
  `30891700576` (8/8). The Linux live shard ran real good/bad Super Prove cases
  with no skip.
- The support matrix remains at zero Fully supported rows because same-commit
  workflow success does not fill row-specific independent-reference,
  proof-depth, CDC, or industrial-corpus gaps.

### Stack

- Python 3.12+, uv, click, Jinja2.
- slang CLI via `--ast-json` for parsing.
- pytest, pytest-timeout, Hypothesis, ruff, mypy strict.
- Icarus and Verilator for simulation parity.
- yosys and SymbiYosys for formal and synthesis-oriented gates.
- In-project token-passing and NFA product construction in `composer.py`.

## Requirements

### Validated

- ✓ SVA parsing through slang `--ast-json` frontend — v1.0.
- ✓ Token-passing checker composition and standard monitor interface — v1.0.
- ✓ Core sequential operators: `##N`, `##[M:N]`, `|->`, `|=>`, `[*N]`, `[*M:N]` — v1.0.
- ✓ Signal functions: `$rose`, `$fell`, `$stable`, `$past`, `$changed` — v1.0/v1.3.
- ✓ `disable iff`, named-sequence inlining, bind generation, Verilog-2001 output — v1.0/v1.1.
- ✓ Tier 2 operators: `first_match`, `[->N]`, `[=N]`, sequence `and`/`or`, `intersect`, `within`, `throughout`, property `not`, property `if/else` — v1.3.
- ✓ Bounded liveness and weak until family — v1.4.
- ✓ Multi-clock path-one with trusted synchronizer boundary — v1.4.1.
- ✓ NFA composition engine for liftable multi-cycle operands and nested composition, K <= 32 — v1.5.1.
- ✓ Formal SVA-to-RTL BMC expansion to all supported operators — v1.5.2.
- ✓ `[->N]` / `[=N]` single-start semantics hardening and semantic references — current main.
- ✓ v1.6 baseline publication and support evidence matrix — Phase 8.
- ✓ Boolean semantic independence through structured IR, independent evaluator, semantic rendering, and named-sequence xfail removal — Phase 9.
- ✓ Formal harness expansion with arbitrary start, disable/reset recovery, full-contract miters, evidence ledger, and expanded k-induction targets — Phase 10.
- ✓ Generated RTL synthesis and lint gates with representative catalog, local Yosys smoke evidence, CI routing, and honest local Verilator skip policy — Phase 11.
- ✓ User-DUT formal CLI, isolated evidence bundles, conservative statuses, and real proof/counterexample replay — Phase 19.
- ✓ Direct invariant safety, nexttime and bounded rewrites, plus typed formal expressions — Phase 20.
- ✓ Symbolic-witness scale route, logical slices, checked decomposition, and critical cover gating — Phase 21.
- ✓ Open liveness routing with explicit fairness and fail-closed missing-engine UNKNOWN — Phase 22.
- ✓ Explicit multi-clock/two-state boundaries and restricted per-attempt local capture — Phase 23.
- ✓ Evidence corpus, package/privacy gates, and exact-commit remote qualification — Phase 24.

### Active

No open v2.0 requirement remains. Future work must be proposed as a new,
falsifiable milestone and must not broaden the completed milestone's claims.

### Out of Scope

- Full arbitrary multi-clock CDC assertion proof — trusted boundary only; full CDC proof is a separate tool category.
- Complete IEEE 1800 SVA support — milestone covers a measured useful subset, not every language feature.
- Commercial-tool equivalence — open results are independently useful but are not JasperGold certification.
- Arbitrary 4-state/X/Z property semantics — initial formal kernel is two-state unless explicitly encoded.
- Analogue CDC/metastability signoff — protocol properties may be proven; physical CDC signoff remains external.
- Unrestricted multi-thread local variables — begin with typed, bounded or symbolic-witness subsets.
- General C++ rewrite — v2 performance work, not v1.6.
- GUI or IDE integration — CLI-first project.
- Expanding accepted SVA syntax before the evidence matrix and oracle independence are in place.

## Context

v2.0 is formal-first. Existing monitor generation and its test corpus remain a
valuable backend and regression oracle, but optimizer equivalence is not a proof
of a user's DUT.  The central evidence object now includes the user design,
property semantics, assumptions, covers, engine/version data, hashes, result,
and counterexample when present.

The most important local planning inputs are:

- `INDUSTRIAL_VALIDATION_GAPS.md`
- `PROJECT_STATUS.md`
- `project_analysis_report.md`
- `.planning/research/SUMMARY.md`
- `.planning/PLAN-nfa-rejection-elimination.md`
- `.gsd/STATE.md`

## Constraints

- **Honesty-first:** Unsupported or insufficiently evidenced forms must reject or be documented as bounded, not silently accepted.
- **Dual-oracle contract:** Icarus and Verilator parity remains mandatory for simulation tests; local Verilator skips must be resolved through CI or a host with Verilator installed.
- **Non-circular references:** Behavioral oracle and formal references must be derived from SVA semantics, not copied from RTL timing.
- **Synthesizable output:** Generated monitors must pass synthesis-oriented acceptance where the project claims synthesizable RTL.
- **Planning privacy:** `.planning/` and `.gsd/` are gitignored local artifacts unless explicitly force-added.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| v1.6 is evidence-first, not syntax-first | Current feature coverage is strong; external trust now depends on evidence-chain closure | Pending |
| Differential testing comes after semantic oracle strengthening | Random tests inherit oracle blind spots if boolean semantics remain shortcut-based | Confirmed by Phase 9 |
| Phase numbering continues at 8 | Existing `.planning/phases/01-07-*` directories are present from earlier milestones | Pending |
| `LANG` work deferred from committed scope | `##0` and NFA expansion should land only with complete evidence rows | Pending |
| Structured BoolNode semantics are authoritative for supported boolean forms | Text remains a compatibility/rendering layer; importer, composer, oracle, optimizer, formal references, and real-source fixture now share the semantic payload | Validated in Phase 9 |
| Local missing-tool skips are non-evidence | Phase 11 keeps local Verilator absence as a skip boundary while CI installs Verilator for remote lint evidence | Validated in Phase 11 |
| Formal verification is the primary backend; monitor synthesis is secondary | The original project goal is open verification of advanced SVA, while finite hardware verdicts impose avoidable restrictions on formal safety reasoning | Validated in Phase 19–24 |
| Advanced SVA is normalized into a small checked semantic kernel | Keeping unsupported source syntax away from Yosys avoids dependence on its incomplete SVA frontend | Validated in Phase 19–23 |
| PASS is only emitted for an unbounded proof under recorded assumptions | BMC depth exhaustion, missing liveness engines, failed covers, and unchecked decomposition remain UNKNOWN | Validated in Phase 19–24 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? Move to Out of Scope with reason.
2. Requirements validated? Move to Validated with phase reference.
3. New requirements emerged? Add to Active.
4. Decisions to log? Add to Key Decisions.
5. "What This Is" still accurate? Update if drifted.

**After each milestone:**
1. Full review of all sections.
2. Core Value check.
3. Audit Out of Scope.
4. Update Context with current state.

---
*Last updated: 2026-08-04 for the v2.0 Open Formal Verification milestone.*
