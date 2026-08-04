# Requirements: sva2rtl v2.0 Open Formal Verification

**Defined:** 2026-08-04
**Core Value:** Verify useful SVA properties against real DUTs with a fully open,
auditable workflow that reports proof, counterexample, UNKNOWN, or UNSUPPORTED
without silently weakening semantics.

## v2.0 Requirements

### Formal Workflow

- [x] **FLOW-01**: A user can run a dedicated formal command with DUT source(s), top module, separate SVA source, property selection, clock/reset, mode, depth, and output directory.
- [x] **FLOW-02**: The workflow parses SVA with slang but never passes the original advanced assertion syntax to Yosys; DUT import and generated formal logic are isolated inputs.
- [x] **FLOW-03**: Every run emits replayable sources/configuration plus a machine-readable result containing hashes, tool versions, assumptions, covers, backend, depth, duration, and status.
- [x] **FLOW-04**: Status is one of PROVEN, FAILED, UNKNOWN, UNSUPPORTED, ERROR, or TIMEOUT; only an unbounded proof may produce PROVEN.
- [x] **FLOW-05**: A failed property preserves an inspectable counterexample trace and the command needed to replay it.

### Semantic Classification and Safety

- [x] **SAFE-01**: Every property is classified as finite-verdict, safety, bounded-liveness, liveness, or unsupported before backend selection.
- [x] **SAFE-02**: Existing bounded supported properties can be asserted against a real DUT through the generated formal checker with explicit start/reset/disable semantics.
- [x] **SAFE-03**: Unbounded `always` safety properties are checked without requiring a finite synthesizable PASS verdict.
- [x] **SAFE-04**: `nexttime` and equivalent fixed-delay forms normalize into the safety/finite kernel with differential semantic tests.
- [x] **SAFE-05**: Goto/nonconsecutive/ranged forms use the existing counter/NFA kernel when equivalent and reject resource-unsound lowering rather than truncate it.
- [x] **SAFE-06**: Supported vector, reduction, comparison, bit-select, and sampled-value expressions retain width/signedness information through formal lowering.

### Scale and Decomposition

- [x] **SCALE-01**: Formal compilation does not inherit the monitor backend's K<=32 or K*T<=32 synthesis budgets unless the selected proof encoding actually requires them.
- [x] **SCALE-02**: The workflow can restrict proof inputs through a property cone/slice manifest and records the resulting assumptions.
- [x] **SCALE-03**: Overlapping-attempt properties have a symbolic-witness verification mode whose adequacy is validated against bounded exhaustive attempts on small cases.
- [x] **SCALE-04**: Decomposition results are accepted only with a certificate obligation proving `(and subproperties) -> original` or a declared stronger equivalence.
- [x] **SCALE-05**: Covers prevent vacuous or unreachable antecedents from being reported as useful proof evidence.

### Liveness and Boundary Handling

- [x] **LIVE-01**: True-liveness properties route only to a qualified open live engine or a documented liveness-to-safety reduction; otherwise the result is UNKNOWN with actionable dependency guidance.
- [x] **LIVE-02**: Strong-until semantics separate the weak-until safety obligation from eventual discharge, and never collapse the latter into a bounded PASS claim.
- [x] **LIVE-03**: Fairness assumptions are explicit, hashed, replayable, and identified as user/model assumptions in the result.
- [x] **BOUND-01**: Multi-clock properties are either split into named clock domains with explicit sampled handoff assumptions or reported UNSUPPORTED; no implicit single-clock rewrite is allowed.
- [x] **BOUND-02**: Four-state/X/Z-dependent semantics are either encoded by an explicit abstraction or reported UNSUPPORTED in the initial two-state backend.
- [x] **BOUND-03**: Local-variable support is restricted to typed static/bounded or symbolic-witness forms with per-attempt semantics; unrestricted cases reject.

### Evidence and Product Contract

- [x] **EVID-01**: Real DUT fixtures demonstrate proof, counterexample, vacuity cover failure, unsupported syntax, timeout, and missing-live-engine outcomes.
- [x] **EVID-02**: Unit, source E2E, Icarus, Verilator, Yosys/SBY, differential, mutation, packaging, and negative tests cover the new workflow.
- [x] **EVID-03**: The support matrix separates formal support from synthesizable-monitor support and upgrades a row only with same-commit evidence.
- [x] **EVID-04**: README and formal guide explain the architecture, exact commands, interpretation of results, unsupported constructs, engineering workarounds, and commercial-tool boundary.
- [x] **EVID-05**: Release qualification records complete local CI, nightly differential, Full Formal, package smoke, privacy scan, and exact-commit remote evidence when available.

## Future Requirements

- **FUT-01**: General IEEE 1800 local-variable and dynamic-sequence semantics.
- **FUT-02**: Full four-state symbolic semantics across all expressions and temporal operators.
- **FUT-03**: Protocol-independent multi-clock temporal automata plus integration with a dedicated CDC signoff tool.
- **FUT-04**: C++/MLIR implementation when measured scale requires it.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Claiming drop-in JasperGold equivalence | The project can replace an important SVA front-end/proof workflow slice, not every industrial engine, debug UI, abstraction, or certification feature. |
| Treating BMC depth as unbounded proof | It is bounded bug-finding evidence and must remain UNKNOWN when no counterexample appears. |
| Silent weakening of strong/liveness semantics | A weaker property can pass while the requested property fails. |
| Analogue metastability proof | Boolean formal models cannot sign off physical metastability. |
| Unchecked natural-language decomposition | Decomposition is useful only when the refinement obligation is itself checked. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FLOW-01..05 | Phase 19 | Complete |
| SAFE-01..02 | Phase 19 | Complete |
| SAFE-03..06 | Phase 20 | Complete |
| SCALE-01..05 | Phase 21 | Complete |
| LIVE-01..03 | Phase 22 | Complete |
| BOUND-01..03 | Phase 23 | Complete |
| EVID-01..04 | Phase 24 | Complete |
| EVID-05 | Phase 24 | Complete |

**Coverage:** 27 v2.0 requirements, 27 mapped, 0 unmapped.

---
*Requirements defined: 2026-08-04 after formal-first scope approval.*
