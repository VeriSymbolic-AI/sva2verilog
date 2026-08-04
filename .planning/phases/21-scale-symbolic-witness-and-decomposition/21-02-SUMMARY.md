---
phase: 21-scale-symbolic-witness-and-decomposition
plan: 02
status: complete
requirements: [SCALE-02, SCALE-04, SCALE-05]
requirements-completed: [SCALE-02, SCALE-04, SCALE-05]
---

# Plan 21-02 Summary

Every formal bundle now includes a hashed logical-property-cone manifest and a
separate SBY cover task. A prove PASS is retained as `PROVEN` only when all
critical cover statements are reached; unreachable or ambiguous cover results
downgrade the final result to `UNKNOWN`.

Optional decomposition certificates are validated before bundle creation. The
original property hash, relation proof, every subproperty, every obligation
result, checker identity, and proof-artifact hash must be present and verified.
Copied evidence uses stable sanitized paths and does not retain host paths.

Verification: 66 focused tests passed, including real reachable and vacuous SBY
cases; Ruff, mypy, and `git diff --check` passed.
