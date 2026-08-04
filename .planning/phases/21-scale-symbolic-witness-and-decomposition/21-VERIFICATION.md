---
phase: 21-scale-symbolic-witness-and-decomposition
status: passed
verified: 2026-08-04
requirements: [SCALE-01, SCALE-02, SCALE-03, SCALE-04, SCALE-05]
score: 5/5
---

# Phase 21 Verification

## Verdict

Passed for the declared symbolic-witness, logical-slice, decomposition, and
critical-cover scope. The formal encoding is not constrained by monitor K/T
budgets unless that backend is explicitly selected.

## Requirement Evidence

| Requirement | Verdict | Direct evidence |
|---|---|---|
| SCALE-01 | PASS | `tests/test_formal_symbolic_witness.py` proves and refutes delay-64 real DUT cases without generating a bounded-thread monitor. |
| SCALE-02 | PASS | `tests/test_formal_evidence_gates.py` checks deterministic slice contents, signal typing, input hashes, and the explicit full-source boundary. |
| SCALE-03 | PASS | Exhaustive small-trace comparisons cover every witness choice and overlapping attempt; real SBY good/bad cases distinguish outcomes. |
| SCALE-04 | PASS | Schema-v2 decomposition validation binds DUT/original/subproperty hashes, checker identity, manifest, context, PROVEN+REACHED results, logs, and deterministic replay; mismatches reject. |
| SCALE-05 | PASS | A separate critical-cover task is mandatory; unreachable antecedent/progress/completion downgrades proof PASS to UNKNOWN. |

## Remaining Boundary

The decomposition relation model remains a reviewed trusted boundary. A
certificate proves the named relation under its recorded formal context; it is
not automatic natural-language decomposition or whole-chip completeness.
