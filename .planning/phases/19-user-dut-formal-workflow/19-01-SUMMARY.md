---
phase: 19-user-dut-formal-workflow
plan: 01
subsystem: formal
tags: [sby, yosys, slang, evidence, fail-closed]
requires:
  - phase: 10-formal-harness-expansion
    provides: formal timeout and evidence conventions
provides:
  - source-isolated user-DUT formal bundle generator
  - conservative formal status classifier
  - machine-readable manifest and result contracts
affects: [formal-cli, safety-backend, support-matrix]
tech-stack:
  added: []
  patterns: [separate-property-frontend, replayable-evidence-bundle, fail-closed-status]
key-files:
  created: [src/sva2rtl/formal_flow.py, tests/test_formal_flow.py]
  modified: []
key-decisions:
  - "Only prove-mode PASS can become PROVEN; BMC PASS remains UNKNOWN."
  - "The original property source is evidence-only and never an SBY/Yosys input."
patterns-established:
  - "Evidence JSON stores bundle-relative paths and SHA-256 hashes, never host paths."
requirements-completed: [FLOW-02, FLOW-03, FLOW-04, FLOW-05, SAFE-01, SAFE-02]
coverage:
  - id: D1
    description: "Mode-aware fail-closed proof status classification"
    requirement: FLOW-04
    verification:
      - kind: unit
        ref: "tests/test_formal_flow.py#test_classify_prove_pass_as_proven"
        status: pass
      - kind: unit
        ref: "tests/test_formal_flow.py#test_classify_bmc_pass_as_unknown_not_proven"
        status: pass
    human_judgment: false
  - id: D2
    description: "Property-isolated deterministic formal evidence bundle"
    requirement: FLOW-02
    verification:
      - kind: unit
        ref: "tests/test_formal_flow.py#test_bundle_excludes_property_from_sby_and_uses_relative_manifest_paths"
        status: pass
    human_judgment: false
  - id: D3
    description: "Generated explicit-port bind assertion and reachability cover"
    requirement: SAFE-02
    verification:
      - kind: unit
        ref: "tests/test_formal_flow.py#test_formal_bind_uses_explicit_ports_assert_and_cover"
        status: pass
    human_judgment: false
duration: 24min
completed: 2026-08-04
status: complete
---

# Phase 19 Plan 01: Formal Evidence Core Summary

**Source-isolated SBY evidence bundles with explicit bound assertions and conservative proof classification**

## Performance

- **Duration:** 24 min
- **Completed:** 2026-08-04
- **Tasks:** 3/3
- **Files modified:** 2

## Accomplishments

- Added validated formal run/evidence/result contracts and relative-path SHA-256 manifests.
- Added generated monitor bind assertion with reset assumptions and reachability cover.
- Added process-group timeout handling and proof/BMC/counterexample/error classification.

## Task Commits

1. **RED contract tests:** `327ec0e`
2. **Formal evidence core:** `1d85c27`
3. **Semantic classification gap closure:** `8a7d0b7`

## Files Created/Modified

- `src/sva2rtl/formal_flow.py` — formal bundle, harness, runner, and classifier.
- `tests/test_formal_flow.py` — 10 contract and negative tests.

## Decisions Made

- Use a separate installed formal CLI rather than breaking the existing single-command monitor CLI.
- Keep the original property in `evidence/property.sv`, outside `[files]` and `read_slang`.
- Record compile-only output as UNKNOWN until an engine run produces stronger evidence.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The default uv cache is sandbox-inaccessible; tests use a task-specific cache under `/private/tmp` without changing project configuration.

## User Setup Required

None - tool dependency discovery is handled by the formal runner and CLI.

## Next Phase Readiness

- Ready for Plan 19-02 CLI and real DUT qualification.
- No support row can be upgraded until real SBY proof/counterexample tests pass.

## Self-Check: PASSED

- Property classification and backend-selection contract tests pass.
- The complete repository regression records 1606 passed, 1 skipped, and 1 xfailed.
- ruff and mypy strict pass for the new module.
- Key files and both task commits exist.

---
*Phase: 19-user-dut-formal-workflow*
*Completed: 2026-08-04*
