---
phase: 19-user-dut-formal-workflow
status: passed
verified: 2026-08-04
requirements: [FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, SAFE-01, SAFE-02]
score: 7/7
---

# Phase 19 Verification

## Verdict

Passed for the bounded, single-clock open-formal workflow.  This verdict does
not claim general advanced-SVA or liveness support.

## Goal-Backward Evidence

| Requirement | Verdict | Evidence |
|---|---|---|
| FLOW-01 | PASS | Installed `sva2rtl-formal` exposes DUT sources, top, property selection, clock/reset, mode, depth, timeout, engine, and output controls. |
| FLOW-02 | PASS | Bundle tests and real DUT tests prove that `evidence/property.sv` is retained but absent from SBY/Yosys inputs. |
| FLOW-03 | PASS | `manifest.json` stores relative source paths, hashes, assumptions, covers, mode, depth, backend, and semantic class; `result.json` adds versions, duration, status, log, and traces. |
| FLOW-04 | PASS | Classifier tests distinguish PROVEN, FAILED, UNKNOWN, ERROR, and TIMEOUT; a successful BMC is explicitly UNKNOWN. |
| FLOW-05 | PASS | The bad-DUT formal test retains a counterexample trace and the bundle contains the replayable `formal.sby`. |
| SAFE-01 | PASS | `classify_property()` distinguishes finite-verdict, safety, bounded-liveness, liveness, and unsupported before `select_formal_backend()`. |
| SAFE-02 | PASS | A real assertion-free DUT is bound to the generated checker with explicit start/reset/disable semantics and is proven with open tools. |

## Automated Verification

- Targeted formal-flow, CLI, and real-DUT suite: 25 passed.
- Complete pytest regression: 1606 passed, 1 skipped, 1 xfailed.
- Ruff: passed.
- mypy: passed.
- Wheel and source distribution: built successfully.
- Isolated wheel install: both entry points launch and the known-good DUT returns PROVEN.
- Negative installed smoke: a wrong top module returns ERROR, not a proof.

## Boundary Audit

- The original SVA property is parsed by slang/sva2rtl only; Yosys receives the
  DUT, generated monitor RTL, and explicit bind harness.
- Real liveness and unsupported/multi-clock classifications are rejected before
  the current backend rather than being bounded or weakened silently.
- Phase 19 still inherits synthesizable-monitor resource bounds.  Removing that
  coupling and adding direct safety lowering are Phase 20-21 obligations.
- The one expected xfail belongs to the pre-existing formal corpus and is not
  converted into pass evidence here.

## Human Verification

None required.  The phase behavior and artifacts are deterministic and covered
by executable tests plus an isolated installed-artifact proof.
