---
milestone: v2.0
milestone_name: "Open Formal Verification"
created: 2026-08-04
total_phases: 6
total_requirements: 27
phase_numbering: continued_from_v1.7
---

# Roadmap — sva2rtl v2.0 Open Formal Verification

## Goal

Deliver a useful, reproducible open formal-verification workflow for real DUTs
and advanced SVA through a small checked semantic kernel, with monitor synthesis
as a separate secondary backend and no false PASS at unsupported boundaries.

## Phase Overview

| Phase | Name | Requirements | Status |
|-------|------|--------------|--------|
| 19 | User DUT Formal Workflow | FLOW-01..05, SAFE-01..02 | Complete (2026-08-04) |
| 20 | Safety Semantics and High-ROI Rewrites | SAFE-03..06 | Complete (2026-08-04) |
| 21 | Scale, Symbolic Witness, and Decomposition | SCALE-01..05 | Complete (2026-08-04) |
| 22 | Open Liveness Backend | LIVE-01..03 | Complete (2026-08-04) |
| 23 | Multi-clock, 4-state, and Local-variable Boundaries | BOUND-01..03 | Complete (2026-08-04) |
| 24 | Evidence Closure and Release Qualification | EVID-01..05 | Complete (2026-08-04) |

## Phase Details

### Phase 19: User DUT Formal Workflow

**Goal:** A user can submit a DUT and separate SVA property source and receive a
replayable SBY proof/counterexample evidence bundle without Yosys parsing the
advanced SVA source.

**Requirements:** FLOW-01, FLOW-02, FLOW-03, FLOW-04, FLOW-05, SAFE-01, SAFE-02

**Success criteria:**

1. CLI validates top/source/property/clock/reset contracts before invoking tools.
2. Generated artifact bundle is deterministic and excludes original assertions from Yosys input.
3. A correct real DUT yields PROVEN under an unbounded safety engine; a buggy DUT yields FAILED plus trace.
4. BMC-without-counterexample yields UNKNOWN, never PROVEN.
5. Missing tools, parse errors, unsupported properties, timeout, and engine failure are distinguishable.

### Phase 20: Safety Semantics and High-ROI Rewrites

**Goal:** Normalize the most useful unsupported safety syntax into the checked
formal kernel while preserving typed expression semantics.

**Requirements:** SAFE-03, SAFE-04, SAFE-05, SAFE-06

**Success criteria:**

1. Unbounded always is represented as a safety invariant with no synthetic finite PASS.
2. nexttime normalizes to fixed delay and passes source/oracle/formal differential tests.
3. Goto, nonconsecutive, and ranged constructs share one semantic implementation across compatible backends.
4. Width, signedness, reduction, vector comparison, and sampled functions have negative boundary tests.

### Phase 21: Scale, Symbolic Witness, and Decomposition

**Goal:** Avoid monitor-specific state limits in the formal backend and add
checked ways to control proof explosion.

**Requirements:** SCALE-01, SCALE-02, SCALE-03, SCALE-04, SCALE-05

**Success criteria:**

1. Formal compilation accepts a representative property above monitor K/T budgets or rejects for a formal-specific reason.
2. Slice manifests identify included signals, assumptions, and excluded cones.
3. Symbolic witness matches exhaustive small-model results and scales to overlapping starts.
4. Decomposition cannot be marked proven without a discharged refinement obligation.
5. Antecedent, progress, and completion covers are recorded and critical cover failure makes the overall result UNKNOWN.

### Phase 22: Open Liveness Backend

**Goal:** Provide sound routing for true liveness without pretending a bounded
monitor or safety proof discharges eventuality.

**Requirements:** LIVE-01, LIVE-02, LIVE-03

**Success criteria:**

1. Engine discovery reports whether a usable live engine is installed and records its version.
2. Eventually and strong-until either run through a qualified live/reduction path or return actionable UNKNOWN.
3. Weak-until safety and strong eventual-discharge obligations are separately visible.
4. Removing or altering fairness assumptions invalidates cached evidence and triggers replay.

### Phase 23: Multi-clock, 4-state, and Local-variable Boundaries

**Goal:** Convert hard semantic areas into explicit, testable profiles instead
of silent approximation.

**Requirements:** BOUND-01, BOUND-02, BOUND-03

**Success criteria:**

1. Multi-clock input must declare domains and sampled handoffs; implicit clock collapse rejects.
2. X/Z-dependent expressions reject in two-state mode and any later abstraction is named in evidence.
3. Restricted locals have typed per-attempt behavior; unsupported dynamic/threaded forms reject.
4. Documentation distinguishes protocol proof, Boolean model assumptions, and physical signoff.

### Phase 24: Evidence Closure and Release Qualification

**Goal:** Make every v2.0 claim reproducible and keep support status tied to
same-commit evidence.

**Requirements:** EVID-01, EVID-02, EVID-03, EVID-04, EVID-05

**Success criteria:**

1. Real DUT corpus covers all result statuses and critical semantic classes.
2. Fast CI, complete local CI, nightly differential/mutation, and Full Formal pass at the release commit.
3. Package/wheel/sdist smoke tests include the formal command and runtime templates.
4. Support matrix has independent Formal and Synth Monitor columns with linked evidence.
5. README/formal guide state exact limits, workarounds, and what commercial capabilities remain outside scope.

## Stop/No-Go Conditions

- Any false PROVEN result on a known-bad DUT blocks milestone completion.
- Any unsupported semantic case that silently lowers blocks milestone completion.
- A critical cover failure, unchecked assumption, or unchecked decomposition keeps status UNKNOWN.
- Liveness remains UNKNOWN unless an open live engine/reduction is qualified on the same semantics.
- Remote evidence can upgrade support only for the exact executable commit.

---
*Roadmap created: 2026-08-04 after formal-first scope approval.*
