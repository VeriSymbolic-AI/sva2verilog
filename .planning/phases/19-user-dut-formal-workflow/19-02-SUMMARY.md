---
phase: 19-user-dut-formal-workflow
plan: 02
subsystem: formal
tags: [cli, sby, real-dut, packaging, evidence]
requires:
  - phase: 19-user-dut-formal-workflow
    plan: 01
    provides: source-isolated formal evidence core
provides:
  - installed sva2rtl-formal command
  - real good-DUT proof and bad-DUT counterexample qualification
  - isolated wheel installation smoke for both command-line entry points
affects: [safety-backend, support-matrix, release-evidence]
tech-stack:
  added: []
  patterns: [dedicated-formal-cli, real-dut-oracle, installed-artifact-smoke]
key-files:
  created:
    - src/sva2rtl/formal_cli.py
    - tests/test_formal_cli.py
    - tests/test_formal_user_dut.py
  modified:
    - pyproject.toml
    - tests/test_packaging.py
key-decisions:
  - "Keep monitor generation and DUT formal verification as separate installed commands."
  - "Treat successful BMC as UNKNOWN, not as an unbounded proof."
patterns-established:
  - "Qualify the installed wheel with a real SBY proof, not only import tests."
requirements-completed: [FLOW-01, FLOW-03, FLOW-04, FLOW-05, SAFE-02]
coverage:
  - id: D4
    description: "Dedicated formal CLI exposes all Phase 19 inputs and stable exit codes"
    requirement: FLOW-01
    verification:
      - kind: integration
        ref: "tests/test_formal_cli.py"
        status: pass
      - kind: package-smoke
        ref: "isolated-wheel:sva2rtl-formal --help"
        status: pass
    human_judgment: false
  - id: D5
    description: "Real user DUT is distinguished as PROVEN or FAILED by open formal tools"
    requirement: FLOW-04
    verification:
      - kind: formal
        ref: "tests/test_formal_user_dut.py"
        status: pass
      - kind: installed-formal-smoke
        ref: "isolated-wheel:good-dut=PROVEN"
        status: pass
    human_judgment: false
  - id: D6
    description: "Existing monitor CLI and package artifact remain compatible"
    requirement: FLOW-05
    verification:
      - kind: regression
        ref: "pytest=1604-pass,1-skip,1-xfail"
        status: pass
      - kind: package-smoke
        ref: "isolated-wheel:sva2rtl --version"
        status: pass
    human_judgment: false
duration: 31min
completed: 2026-08-04
status: complete
---

# Phase 19 Plan 02: User CLI and Real-DUT Qualification Summary

**A packaged, replayable open-formal workflow that proves a real DUT or retains its counterexample**

## Performance

- **Duration:** 31 min
- **Completed:** 2026-08-04
- **Tasks:** 3/3
- **Full regression:** 1606 passed, 1 skipped, 1 xfailed

## Accomplishments

- Added the dedicated `sva2rtl-formal` CLI without changing the existing monitor CLI.
- Qualified real good/bad DUTs with local slang, Yosys, SymbiYosys, and SMT solving.
- Verified prove PASS becomes PROVEN, a counterexample becomes FAILED with a trace, and BMC PASS remains UNKNOWN.
- Built wheel and sdist, installed the wheel into a clean environment, and exercised both installed commands plus a real proof.

## Task Commits

1. **Formal CLI RED contracts:** `477f131`
2. **Dedicated formal CLI:** `fd277d5`
3. **Real-DUT and package qualification:** `32f7d66`
4. **Semantic classification gap closure:** `8a7d0b7`

## Verification Evidence

- `uv run pytest -q`: 1606 passed, 1 skipped, 1 xfailed.
- `uv run ruff check .`: passed.
- `uv run mypy src/sva2rtl`: passed.
- `uv build`: wheel and source distribution built successfully.
- Isolated wheel: both CLI entry points launch; known-good DUT returns PROVEN.
- Deliberately wrong top-module input returns ERROR rather than a false PROVEN result.

## Decisions Made

- Keep CLI status text and process exit codes aligned with the machine-readable result status.
- Require the user to name the DUT top explicitly; a wrong name fails closed.
- Preserve the original property as evidence while excluding it from Yosys inputs.

## Deviations from Plan

None - all planned tasks and artifact-level smoke checks completed.

## Issues Encountered

- An initial isolated smoke used the DUT filename as the top name. The engine correctly returned ERROR; rerunning with the declared module name returned PROVEN.

## User Setup Required

- The formal execution path requires `slang`, `yosys` with `read_slang`, `sby`, and a supported SMT solver on `PATH`. Compile-only mode requires only `slang`.

## Next Phase Readiness

- The basic user-DUT safety loop is ready.
- Advanced property operators still inherit the monitor backend's bounded support and must not yet be described as generally supported.

## Self-Check: PASSED

- Real proof, real counterexample, BMC non-proof, timeout/error paths, packaging, full regression, lint, and type checking are covered.

---
*Phase: 19-user-dut-formal-workflow*
*Completed: 2026-08-04*
