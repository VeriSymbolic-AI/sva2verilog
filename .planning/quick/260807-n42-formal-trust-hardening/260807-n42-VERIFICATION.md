---
quick_id: 260807-n42
status: passed-remote
date: 2026-08-07
---

# Quick Task 260807-n42 Verification

## Must-Have Verification

| Requirement | Result | Evidence |
|---|---|---|
| Only PROVEN exits zero | PASS | CLI status tests, installed-distribution smoke, and full suite enforce compile-only `UNKNOWN/11` and stable nonzero result codes. |
| Replay is bound and private | PASS | Manifest/result record tool fingerprints, solver identity, role commands, executed commands, hashes, proof and cover logs; tamper/decomposition tests reject incomplete replay. |
| Structured real-project formal context | PASS | Filelist/include/define/parameter/library/single-unit proof passes from a self-contained snapshot with no property in Yosys inputs or host path in evidence. |
| Portable open liveness route | PASS (recipe) | Doctor reports safety/live readiness; base image and x64/arm64 OSS CAD Suite archives are digest pinned. Docker build was not executable on this host. |
| Real external RTL evidence | PASS (bounded) | Unmodified OpenTitan slice proves; reviewed latency mutant fails with trace; provenance and non-CDC boundary are checked. |
| New semantic defects stay fixed | PASS | Leading-delay importer unit/mutation tests and custom-reset bind regression pass; the external good/bad formal test exercises both fixes together. |
| Public evidence is fail-closed | PASS | Support matrix remains zero Fully supported; machine ledger rejects unsupported promotion without exact-SHA qualification. |
| Local verification is broad and green | PASS | 1752 default tests, 174 Verilator simulations, 222 Full Formal tests, 133 generated RTL gates, both differential axes, mutation, packaging, static and privacy checks passed within named boundaries. |
| Exact-SHA remote qualification | PASS | Executable `5ad7e2f04c65348a709728447c64ff46acea1986`: CI `31167742453` 13/13, nightly `31167748554` 3/3, Full Formal `31167747619` 8/8; every job concluded success. |

## Verdict

Passed for merge readiness and the stated bounded scope. Local conditional
skips remain excluded from pass evidence; exact-SHA Linux remote qualification
closes the workflow gate without promoting any construct to Fully supported.
