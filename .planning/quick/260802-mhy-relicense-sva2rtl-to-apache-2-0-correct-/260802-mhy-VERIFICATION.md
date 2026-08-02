---
quick_id: 260802-mhy
status: passed
date: 2026-08-02
verified_commit: c957bdf3d3ed9cf145f23057d9e2a94d555c30e3
---

# Quick Task 260802-mhy Verification

## Must-Have Verification

| Requirement | Result | Evidence |
|---|---|---|
| Exact Apache-2.0 root license | PASS | Local `LICENSE` matched the official Apache text byte-for-byte; SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`. |
| Metadata and public docs agree | PASS | `pyproject.toml`, README, wheel metadata, sdist, and release-identity tests use `Apache-2.0`; current public docs contain no BSL production-use restriction. |
| README claims match project truth | PASS | README defers to `SUPPORT_MATRIX.md`, reports zero Fully supported rows, and distinguishes implemented syntax from evidence strength. |
| Formal workflow is reproducible and bounded | PASS | `FORMAL_VERIFICATION.md` names tools, commands, miter, assumptions, outputs, BMC depth, induction, cover, and interpretation rules. |
| Advanced-SVA gap has a safe solution path | PASS | Supported bounded forms lower to ordinary RTL; unsupported forms fail closed and have bounded rewrite, auxiliary RTL, original-SVA tool, hand-authored monitor, CDC, or offline-trace alternatives. |
| Local verification is green | PASS | Targeted tests, full dual-simulator axes, generated RTL, Full Formal, differential, mutation, coverage, packaging, lint, type, format, and privacy checks completed with the bounded results recorded in the summary. |
| Same-commit remote qualification is green | PASS | `c957bdf`: CI `30741073680` 13/13, nightly `30741082278` 3/3, Full Formal `30741083516` 6/6. |
| No privacy data in committed change | PASS | Anonymous git identity and staged-content scans found no home path, personal email, secret, token, or private-key material. |

## Verdict

Passed for the stated open-source, documentation, bounded-compilation, and
same-commit qualification scope. This verdict is not a claim of complete IEEE
1800 support, per-construct industrial readiness, chip correctness, CDC
sign-off, or independent legal confirmation of contributor relicense authority.
