---
phase: 20-safety-semantics-and-high-roi-rewrites
plan: 02
status: complete
completed: 2026-08-04
requirements-completed: [SAFE-05, SAFE-06]
commit: 6673472
---

# Phase 20 Plan 02 Summary

- Added width/signedness-preserving structured Boolean IR, serialization,
  evaluation, monitor ports, and formal-bind ports.
- Added reduction AND/OR/XOR and relational comparison semantics.
- Fixed nested `Simple` repetitions in implication consequents; they were
  previously silently unwrapped to a Boolean leaf.
- Classified unbounded goto/nonconsecutive occurrence obligations as liveness.
- Added a bare-sequence formal guard after a real bad DUT exposed a false
  PROVEN result for standalone `ack[*2:3]`.
- Qualified ranged delay/repetition inside explicit property implications with
  real PROVEN/FAILED DUT pairs.
- Preserved goto/nonconsecutive monitor compilation while refusing to claim a
  safety proof without a live backend.

## Verification

- Full pytest: 1643 passed, 1 skipped, 1 xfailed.
- Verilator simulation axis: 174 passed, 2 reviewed skips.
- Full Formal selection: 126 passed, 1 expected xfail.
- Yosys synthesis gates: 80 passed.
- Ruff and mypy: passed.
