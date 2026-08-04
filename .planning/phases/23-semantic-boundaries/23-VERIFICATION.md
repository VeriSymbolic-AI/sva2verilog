---
phase: 23-semantic-boundaries
status: passed
verified: 2026-08-04
requirements: [BOUND-01, BOUND-02, BOUND-03]
score: 3/3
---

# Phase 23 Verification

## Verdict

Passed for the explicit fail-closed boundary profiles and the one whitelisted
automatic scalar local-capture form.

## Requirement Evidence

| Requirement | Verdict | Direct evidence |
|---|---|---|
| BOUND-01 | PASS | Real multi-clock SVA produces sanitized UNSUPPORTED evidence, no Yosys inputs, and no implicit clock collapse. Documentation requires per-domain proof, reviewed handoff, and separate CDC signoff. |
| BOUND-02 | PASS | Real X/Z-dependent sources reject under the hashed two-state profile before solver input; there is no implicit four-state coercion. |
| BOUND-03 | PASS | One automatic scalar overlapping fixed-delay capture uses a private per-attempt witness register. Real good/bad/changing-value cases distinguish outcomes; vector, multiple, nonblocking, ranged, nested, and monitor forms reject. |

## Remaining Boundary

General locals, arbitrary four-state semantics, cross-domain temporal
automata, and analogue metastability proof remain explicitly unsupported.
