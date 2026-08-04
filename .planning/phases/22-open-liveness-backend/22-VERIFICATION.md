---
phase: 22-open-liveness-backend
status: passed
verified: 2026-08-04
requirements: [LIVE-01, LIVE-02, LIVE-03]
score: 3/3
---

# Phase 22 Verification

## Verdict

Passed for the documented Boolean unbounded-eventual and strong-until shapes.
The monitor composer rejects them; the formal backend uses an open live engine
or returns actionable UNKNOWN when that engine is unavailable.

## Requirement Evidence

| Requirement | Verdict | Direct evidence |
|---|---|---|
| LIVE-01 | PASS | `tests/test_formal_liveness.py` checks property classification, `$live` lowering, source isolation, Super Prove discovery, real good/bad live proofs, missing-engine UNKNOWN, and critical cover. Exact executable `e3526836912086fdc274528ca7735dd7b6a028e1` passed remote Full Formal run `30908170695`, whose open-liveness shard executed 17/17 tests with no skip. |
| LIVE-02 | PASS | Strong until lowers to a visible weak-until safety obligation plus separate eventual discharge; no bounded PASS substitutes for the latter. |
| LIVE-03 | PASS | Identifier-only fairness lowers to `$fair`; the exact assumptions, source kind, hashes, engine metadata, and cover outcome are replayable, and changing fairness invalidates evidence. |

## Remaining Boundary

Arbitrary nested liveness, unqualified live engines, and hidden/inferred
fairness are outside scope. Missing `suprove` is UNKNOWN, never PASS.
