---
phase: 2
reviewers: [claude-self]
reviewed_at: 2026-05-26T00:00:00Z
plans_reviewed: [PLAN-2.1.md, PLAN-2.2.md, PLAN-2.3.md]
---

# Cross-AI Plan Review — Phase 2

## Claude Review (Self-Review, Independent Session)

### PLAN-2.1 (Wave 1): Unified Delay Template

**Summary:** PLAN-2.1 is well-scoped with sound core architectural decisions: counter encoding always (D-01), unified template (D-02), and concurrency kept out of delays (D-04). However, several SVA-domain edge cases are unaddressed — notably `##0`, counter-width parameterization completeness, and the dual-use ambiguity of the `pass` window signal when consumed by the implication template.

**Strengths:**
- D-02 unified template avoids maintenance split between exact and ranged delays
- D-03 (pass HIGH for window) is correct for feeding downstream implication templates
- Hierarchical CheckerNode composition supports multi-element sequences (`a ##2 b ##3 c`)
- Separating multi-file emitter prevents integration afterthoughts
- D-04 (concurrency in `|->` not delay) keeps `concat_delay.sv.j2` stateless

**Concerns:**
- **HIGH** — `##0` unhandled: Zero-cycle delay is valid SVA (`a ##0 b` = same-cycle AND). Counter at N=0 requires immediate window-open or explicit rejection. Silent misbehavior breaks downstream composition.
- **HIGH** — Counter width computation not formally specified in template contract: If hardcoded or left implicit, large delays (e.g., `##256`) could wrap silently.
- **HIGH** — `pass` signal dual-use semantic not reconciled: standalone monitor needs single-cycle pulse; BV-composition needs window-level HIGH (D-03). Without parameterization, one use-case breaks.
- **MEDIUM** — Multi-element `SeqConcat` chaining not tested (`a ##2 b ##3 c` with three elements)
- **MEDIUM** — `##[M:N]` with M=0 not specifically addressed (window open immediately on start)
- **MEDIUM** — Reset semantics during active count unspecified
- **MEDIUM** — Input validation for M > N (e.g., `##[5:2]`) missing
- **LOW** — Multi-file emitter naming collision potential
- **LOW** — `##[N:N]` normalization to `##N` not specified

**Suggestions:**
- Add `##0` as explicit gated case (combinational pass-through or Phase 2 compile-time error)
- Specify `COUNTER_WIDTH` as required computed parameter: `max(1, ceil(log2(MAX_DELAY + 1)))`
- Add standalone/composition mode parameter or thin wrapper to resolve pass-signal ambiguity
- Add three-element SeqConcat test fixture
- Document reset behavior in template header comment block

**Risk Assessment:** MEDIUM-HIGH

---

### PLAN-2.2 (Wave 2): Overlapping and Non-Overlapping Implication

**Summary:** PLAN-2.2 addresses the most complex component — concurrent thread tracking via bit-vector. Key decisions (D-05 hard halt, D-06 auto BV_WIDTH, D-07 sticky) are adopted. However, the BV_WIDTH auto-computation algorithm is unspecified, the hard-halt RTL semantics are ambiguous, and the per-thread counter array mechanism is absent from deliverables.

**Strengths:**
- Bit-vector approach is correct synthesizable encoding for concurrent threads
- Separating overlap/nonoverlap templates avoids conditional maze
- OUT-06 overflow_flag as first-class port prevents silent degradation
- D-07 sticky flag essential for waveform debugging
- BV_WIDTH auto + overridable (D-06) balances ergonomics and control

**Concerns:**
- **HIGH** — BV_WIDTH auto-computation algorithm completely unspecified. Semantically correct value = `MAX_CONSEQUENT_DELAY + 1`. Under/over-estimate have different failure modes.
- **HIGH** — Hard-halt overflow RTL semantics undefined: (a) stop new matches but existing threads continue? (b) freeze entire state? (c) abandon all in-flight threads? Structurally different RTL.
- **HIGH** — Per-thread counter array (`[BV_WIDTH-1:0][COUNTER_WIDTH-1:0]`) absent from deliverables. This is the actual state-holding mechanism for D-04.
- **HIGH** — `active` signal semantics under sticky fail undefined
- **MEDIUM** — `|=>` decomposition strategy not specified (embed 1-cycle shift vs. decompose to `##1 |->`)
- **MEDIUM** — Thread bit-clear timing on simultaneous pass + new-start (priority hazard)
- **MEDIUM** — Multiple simultaneous thread failures: `fail` should pulse once (OR-reduction)
- **MEDIUM** — `start` behavior when BV is full not documented
- **LOW** — `pass` port semantics for implication: per-thread or all-threads?
- **LOW** — Generate-loop Verilator compatibility not mentioned

**Suggestions:**
- Define BV_WIDTH auto algorithm: `max(MAX_DELAY_IN_CONSEQUENT + 1, DEFAULT_WIDTH)`
- Commit to overflow hard-halt definition: "gate new antecedent acceptance; existing threads continue to completion"
- Add explicit sub-task for per-thread counter array design
- Specify `|=>` strategy (decompose-first vs. embed-shift)
- Specify `active` behavior under sticky fail: stays high until all in-flight resolve

**Risk Assessment:** HIGH

---

### PLAN-2.3 (Wave 3): Integration Tests, Stress Tests, Boundary Tests

**Summary:** Testing plan is well-aligned with success criteria and wave ordering is correct. However, it relies on an implicit reference model without specifying what it is, golden files lack a regeneration workflow, and critical edge cases (reset during active threads, exact BV_WIDTH boundary) are not explicitly included.

**Strengths:**
- 20-cycle concurrent thread fixture maps directly to SC#2
- Golden file determinism harness addresses SC#4
- Boundary test for overflow_flag maps to SC#3
- Phase 1 regression validation task present
- Separate stress test task signals awareness of concurrency complexity

**Concerns:**
- **HIGH** — Reference model not specified: "behavioral simulation" without a defined oracle means tests prove internal consistency, not IEEE 1800 semantic correctness
- **HIGH** — No test for rst_n during active threads (10 of 20 active, reset asserts)
- **HIGH** — BV overflow boundary test relies on undefined BV_WIDTH algorithm
- **MEDIUM** — Golden file brittleness without `--update-golden` regeneration workflow
- **MEDIUM** — No Verilator/Icarus compilation smoke test (`verilator --lint-only`)
- **MEDIUM** — Concurrent thread test BV_WIDTH not parameterized (must test both sides of boundary)
- **MEDIUM** — No invalid-input test coverage (`##[5:2]`, `##[-1:3]`, `BV_WIDTH=0`)
- **LOW** — No hypothesis-based fuzz tests for random delay values/pulse patterns
- **LOW** — `##[1:1]` = `##1` equivalence not tested
- **LOW** — No performance/scale test (BV_WIDTH=64, 1000 cycles)

**Suggestions:**
- Define reference model: implement minimal Python `SVABehavioralSim` class (~100 lines)
- Add rst_n-during-active-threads test case
- Add `--update-golden` as documented workflow
- Add `verilator --lint-only` as mandatory CI step
- Parameterize overflow boundary test: test at BV_WIDTH, BV_WIDTH-1, BV_WIDTH+1
- Add hypothesis-based fuzz task for AST importer

**Risk Assessment:** MEDIUM

---

## Consensus Summary

### Agreed Strengths
- Counter encoding (D-01) and unified template (D-02) are architecturally sound
- Hierarchical CheckerNode composition is the correct abstraction
- Wave ordering (delay -> implication -> tests) respects real dependencies
- Bit-vector approach for concurrent threads is the correct synthesis-friendly encoding
- Phase 1 backward compatibility is explicitly tested

### Agreed Concerns (Priority Ordered)
1. **HIGH** — BV_WIDTH auto-computation algorithm unspecified (threatens SC#2, SC#3)
2. **HIGH** — Hard-halt overflow RTL semantics ambiguous (structurally different implementations)
3. **HIGH** — `##0` zero-delay case unhandled (valid SVA, correctness risk)
4. **HIGH** — `pass` signal dual-use between standalone and BV-composition modes
5. **HIGH** — No behavioral reference oracle for test validation
6. **HIGH** — Reset during active threads not tested
7. **MEDIUM** — Per-thread counter array absent from PLAN-2.2 deliverables
8. **MEDIUM** — No Verilator lint gate on generated RTL
9. **MEDIUM** — Multi-element SeqConcat chaining untested
10. **MEDIUM** — Invalid input rejection not specified (`##[5:2]`, `##[-1:3]`)

### Recommended Pre-Execution Gates
1. Resolve BV_WIDTH auto algorithm in writing before PLAN-2.2 starts
2. Commit to hard-halt overflow definition (one sentence suffices)
3. Decide `##0` handling: support or reject-with-error
4. Document inter-wave contract: what `concat_delay.sv.j2` promises to `overlap_bitvec.sv.j2`
5. Add `verilator --lint-only` to PLAN-2.3 CI task

### Divergent Views
N/A (single reviewer)

---

*Reviewed: 2026-05-26*
*To incorporate feedback: `/gsd:plan-phase 2 --reviews`*
