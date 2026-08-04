---
phase: 22-open-liveness-backend
plan: 01
status: complete
completed: 2026-08-04
commit: a292c29
requirements: [LIVE-01, LIVE-02]
requirements-completed: [LIVE-01, LIVE-02]
---

# Plan 22-01 Summary

Implemented formal-only IR and slang import for unbounded eventually and strong
until. The monitor composer remains fail-closed. The formal flow lowers the
documented Boolean shapes to Yosys `$live`, separates strong-until safety from
eventual discharge, discovers Super Prove, and returns actionable `UNKNOWN`
when the live solver is unavailable.

Verification: liveness/frontend/CLI/document contracts passed; the generated
live bundle reaches AIG preparation locally without a live solver. Real solver
good/bad cases remain conditional on `suprove` availability.
