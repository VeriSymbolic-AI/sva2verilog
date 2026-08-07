---
phase: 20-safety-semantics-and-high-roi-rewrites
status: passed
verified: 2026-08-04
requirements: [SAFE-03, SAFE-04, SAFE-05, SAFE-06]
score: 4/4
---

# Phase 20 Verification

## Verdict

Passed for the Phase 20 safety and bounded finite-kernel scope.  Unbounded
occurrence forms are intentionally routed to liveness rather than weakened.

## Requirement Evidence

| Requirement | Verdict | Evidence |
|---|---|---|
| SAFE-03 | PASS | Unbounded always imports as `PropAlways`, selects `direct-invariant-safety`, emits no monitor source, and distinguishes real good/bad DUTs. |
| SAFE-04 | PASS | Nexttime imports with exact delay/strength, normalizes to a true-antecedent property plus fixed-delay sequence, and distinguishes real good/bad DUTs. |
| SAFE-05 | PASS | Bounded ranged forms reuse the existing counter/NFA property kernel; goto/nonconsecutive reuse monitor templates but classify as liveness and reject from the safety backend. Partial bounds, bare sequences, and resource-unsound paths reject rather than truncate. |
| SAFE-06 | PASS | Width/signedness survive AST, IR, JSON, evaluator, generated monitor ports, and direct formal ports; reduction and signed comparison real-DUT tests distinguish PROVEN/FAILED; X/Z and vector sampled-value boundaries reject. |

## False-Assurance Audit

- A real formal negative test demonstrated that standalone `ack[*2:3]` could
  yield PROVEN because sequence no-match is not monitor fail.
- The formal compiler now rejects all bare temporal sequence roots and requires
  an explicit property obligation such as implication.
- Nested slang `Simple` repetitions are handled before unwrapping, preventing
  goto/nonconsecutive syntax inside an implication from silently becoming a
  Boolean expression.
- Successful BMC remains UNKNOWN and unbounded occurrence obligations do not
  enter the safety backend.

## Automated Evidence

- Complete pytest: 1643 passed, 1 skipped, 1 xfailed.
- Verilator dual-oracle axis: 174 passed, 2 reviewed skips.
- Full Formal: 126 passed, 1 expected bounded-liveness induction xfail.
- Yosys synthesis: 80 passed.
- Ruff and mypy: passed.

## Remaining Boundary

- Direct invariant safety is decoupled from finite monitor completion, but
  general bounded property lowering still inherits monitor/NFA resource limits.
- True liveness, including goto/nonconsecutive eventual completion, remains for
  Phase 22.
- Completion/antecedent cover gating and formal scale decoupling remain Phase 21.

## 2026-08-07 Reverification Note

Phase 20 was rechecked after the trust-hardening work found a slang-v11
single-element `SequenceConcat` boundary: a leading `##N` in an implication
consequent had been silently discarded. The importer now materializes the
implicit true start event and preserves both leading and following delays.
Unit regressions, the full AST importer mutation sweep (123/123 covered valid
mutants killed), the external OpenTitan good/mutant formal pair, the 1751-test
default suite, and the 222-test Full Formal selection passed. The Phase 20
verdict remains passed for its stated safety/bounded scope.
