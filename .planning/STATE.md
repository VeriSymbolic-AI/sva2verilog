---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Open Formal Verification
current_phase: 20
current_phase_name: Safety Semantics and High-ROI Rewrites
status: ready_to_plan
stopped_at: Phase 19 complete (2/2); ready to plan Phase 20
last_updated: "2026-08-04T00:40:00+08:00"
last_activity: 2026-08-04
last_activity_desc: Completed and verified the user-DUT open-formal workflow
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 2
  completed_plans: 2
  percent: 17
---

# Project State: sva2rtl v2.0

## Current Position

Phase 19 is complete and independently goal-checked.  Phase 20 is next.

## Verified v2.0 Evidence

- A separate `sva2rtl-formal` command accepts real DUT sources and a separate
  SVA property source.
- Yosys never consumes the original property file; it receives copied DUT,
  generated checker RTL, and an explicit bind harness.
- Known-good DUT: PROVEN with open tools.
- Known-bad DUT: FAILED with retained counterexample trace.
- Successful BMC: UNKNOWN, never PROVEN.
- Property semantics are classified before backend selection; liveness and
  unsupported classes do not silently enter the bounded monitor backend.
- Complete local regression: 1606 passed, 1 skipped, 1 xfailed.
- Ruff, mypy, wheel/sdist build, isolated install, and installed proof smoke pass.

## Evidence Boundary

- Phase 19 is bounded to the existing single-clock generated-monitor safety
  kernel.  It is not general advanced-SVA or liveness support.
- The current formal route still inherits monitor construction limits; direct
  safety lowering and scale decoupling remain Phase 20-21 work.
- Remote same-commit CI/nightly/Full Formal evidence has not yet been recorded
  for the v2.0 implementation commits.

## Next Work

Plan and execute Phase 20 requirements SAFE-03 through SAFE-06:

1. Direct invariant lowering for unbounded `always`.
2. Sound `nexttime` normalization.
3. Formal qualification of goto/nonconsecutive/ranged forms.
4. Width/signedness/reduction/vector/sampled-value boundary tests.

## Performance Metrics

| Phase | Plan | Duration | Result |
|---|---|---:|---|
| 19 | 19-01 | 24 min | Complete |
| 19 | 19-02 | 31 min | Complete |
