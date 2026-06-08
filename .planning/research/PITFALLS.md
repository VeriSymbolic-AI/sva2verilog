# PITFALLS — SVA-to-RTL Compiler

> **Purpose:** Prevent known mistakes during roadmap and implementation planning.
> **Scope:** Python-based compiler converting SVA into synthesizable RTL monitors.

---

## Quick-Reference Danger Matrix

| Pitfall | Severity | Easy to Miss? | Phase |
|---------|----------|--------------|-------|
| P1.1 Vacuous satisfaction | HIGH | YES | Phase 1 |
| P1.2 Overlapping implication off-by-one | HIGH | YES | Phase 1 |
| P1.3 Bit-vector overflow (multi-thread) | HIGH | YES | Phase 1 |
| P1.4 `throughout` every-tick semantics | HIGH | YES | Phase 1 |
| P1.5 `intersect` same-start-AND-end | HIGH | YES | Phase 1 |
| P1.6 `disable iff` async semantics | MEDIUM | YES | Phase 1 |
| P1.8 Strong vs. weak in hardware | HIGH | MEDIUM | Pre-Phase 1 |
| P2.1 Combinational loop in monitor | HIGH | YES | Phase 2 |
| P2.3 Counter bit-width overflow | HIGH | YES | Phase 2 |
| P2.4 Missing monitor reset | HIGH | NO | Phase 1 |
| P3.1 Single-thread testing only | HIGH | YES | Phase 2 |
| P3.4 No boundary tests | HIGH | YES | Phase 2 |
| P3.5 Vacuity not tested | HIGH | YES | Phase 1/2 |
| P4.1 NFA->DFA state explosion | HIGH | NO | Phase 1 |
| P4.2 Unbounded repetition | HIGH | NO | Phase 1 |
| P5.1 Errors reference generated RTL | MEDIUM | YES | Phase 1 |
| P8.1 Slang AST node types differ | HIGH | YES | Phase 1 |
| P8.2 Token duplication on branches | HIGH | YES | Phase 1 |
| P8.4 Implicit clocking wrong clock | HIGH | NO | Phase 1 |

---

## 1. SVA Semantic Edge Cases

### P1.1 — Vacuous Satisfaction

**What goes wrong:** `A |-> B` passes because antecedent A never fires. Monitor reports "pass" but checked nothing.

**Prevention:**
- Emit companion `attempt_fired` output wire (first-class, not optional)
- Document: meaningful pass = `(fail==0) AND (attempt_fired==1)`
- Tests must assert `attempt_fired` went high

**Phase:** Architecture (Phase 1) — interface design must include this from start.

### P1.2 — Overlapping vs Non-Overlapping Off-by-One

**What goes wrong:** `|->` starts consequent same cycle; `|=>` starts next cycle. Confusing produces exactly one-cycle-off behavior that passes simple tests.

**Prevention:**
- Separate templates with `_ovlp`/`_novlp` suffix, never share
- Dedicated test vectors that differentiate same-cycle vs next-cycle start
- Use behavioral SVA simulation as oracle

**Phase:** Operator templates (Phase 1).

### P1.3 — Bit-Vector Overflow (Multiple Simultaneous Threads)

**What goes wrong:** Antecedent fires every cycle. More threads than bit-vector width → oldest silently dropped. False negatives with no indication.

**Prevention:**
- Bit-width = max_consequent_length (computed at compile time, not hardcoded)
- Emit `overflow_flag` sticky output
- Mandatory concurrent-attempt stress tests

**Phase:** Template parameterization (Phase 1/2).

### P1.4 — `throughout` Must Check Every Tick

**What goes wrong:** Checking only start/end instead of every cycle. Mid-sequence glitches escape.

**Prevention:** Implement as continuous AND of `expr` with `seq_active` signal every cycle, feeding sticky violation FF.

**Phase:** Operator templates (Phase 1).

### P1.5 — `intersect` Requires Same Start AND Same End Time

**What goes wrong:** Implemented as same-start-only. Sequences of different lengths incorrectly match.

**Prevention:** Synchronized product NFA — accepting output is AND of both NFAs' accept in same clock cycle.

**Phase:** NFA construction (Phase 2/3).

### P1.6 — `disable iff` Is Asynchronous

**What goes wrong:** Treated as synchronous reset → one-cycle window of spurious failure.

**Prevention:** Gate all outputs combinationally with disable condition. Async clear on FFs.

**Phase:** Templates (Phase 1).

### P1.8 — Strong vs. Weak: Scope Decision Required Pre-Implementation

**What goes wrong:** `strong(seq)` requires liveness (eventually matches). Hardware can only do safety (no violation seen). Treating both identically loses liveness guarantees silently.

**Prevention:**
- Phase 1 explicitly = safety properties only
- `strong()` emits compile error, not silent weakening
- Document this architectural boundary

**Phase:** Pre-Phase 1 scope decision.

---

## 2. Hardware Synthesis Gotchas

### P2.1 — Combinational Loops

**Prevention:** All state transitions through registered FFs. Post-generation loop detection. Verilator/Yosys lint in CI.

### P2.2 — Unregistered Outputs Inject Glitches

**Prevention:** ALL primary outputs (fail, pass, attempt_fired) must be registered. Template invariant.

### P2.3 — Counter Bit-Width Wrap-Around

**Prevention:** Width = `ceil(log2(max_bound + 1)) + 1`. Parameterize, never hardcode. Warning for bounds > 1000.

### P2.4 — Missing Reset at Power-On

**Prevention:** Every FF has synchronous reset to idle state. Reset test in every template's test suite.

### P2.5 — Wrong Clock Sensitivity

**Prevention:** All blocks use `always_ff @(posedge clk)`. Never `@(clk)`. Template constant, not string literal.

---

## 3. Testing Blind Spots

### P3.1 — Single-Thread Testing Only

**Prevention:** Mandatory concurrent-attempt test per template: antecedent fires every cycle for 2x consequent_length.

### P3.4 — No Boundary Tests

**Prevention:** For every bounded operator `##[N:M]`, test at N-1 (fail), N (pass), M (pass), M+1 (fail).

### P3.5 — Vacuity Not Verified

**Prevention:** Every test asserts BOTH expected `fail_out` AND expected `attempt_fired`.

### P3.3 — Sim-vs-Synthesis Mismatch

**Prevention:** Gate-level sim step in CI (Yosys + iverilog). `(* keep *)` on state registers.

---

## 4. Performance & Complexity Traps

### P4.1 — NFA->DFA Exponential Blowup

**What goes wrong:** Subset construction on N-state NFA → up to 2^N DFA states.

**Prevention:** Use token-passing architecture (TIMA Lab) — preserves NFA structure, no determinization. Only DFA-convert for NFAs with <= 8 states.

**Phase:** Core architecture (Phase 1). This is the fundamental design choice.

### P4.2 — Unbounded Repetition `[*]` and `[$]`

**Prevention:** Phase 1 rejects with compile error. Provide `--max-rep=N` flag for bounded approximation with explicit warning.

### P4.3 — `intersect` Product NFA Explosion (M x N states)

**Prevention:** Limit nesting depth. State-count budget per property (warn > 64, error > 512).

---

## 5. API & Usability

### P5.1 — Errors Reference Generated RTL, Not Source SVA

**Prevention:** Thread `SourceLocation(file, line, col)` from slang AST through entire pipeline. All errors include original SVA location.

**Phase:** IR design (Phase 1). Retrofitting is extremely painful.

### P5.2 — No Supported-Construct Documentation

**Prevention:** Maintain `SUPPORTED_CONSTRUCTS.md` from Phase 1. Named error codes (SVA-E001, etc.).

### P5.4 — No Observable Monitor State

**Prevention:** Expose `attempt_fired`, `pending_count`, `overflow_flag` as debug outputs (gated by parameter).

---

## 6. Architecture Traps

### P8.1 — Slang AST Uses SVA-Specific Node Types

**Prevention:** Enumerate all SVA node kinds from slang before writing visitors. Test that every expected kind is visited.

### P8.2 — Token Duplication on Parallel Branches

**What goes wrong:** At `or` nodes, token must be DUPLICATED (not moved) into both branches. Missing → one branch never checked.

**Prevention:** Formal token-passing spec before implementation. Token-count invariant checker. Test each branch in isolation.

### P8.4 — Implicit Clocking Uses Wrong Clock

**Prevention:** Require explicit `@(posedge clk)` or `--default-clock` flag. Never silently assume clock name.

### P8.5 — Non-Idiomatic RTL

**Prevention:** Use `case` statements (not if/else chains) for FSMs. Add `(* fsm_encoding *)` pragmas. Synthesis sanity check in CI.

---

## Top "Silent Killers" Summary

| # | Pitfall | Why insidious |
|---|---------|---------------|
| P1.1 | Vacuous satisfaction | Monitor reports "pass" but checked nothing |
| P1.3 | Bit-vector overflow | Silently drops pending threads |
| P1.4 | `throughout` boundary-only | Mid-window violations escape |
| P1.5 | `intersect` same-start only | Different-length sequences match |
| P8.2 | Token duplication missing | One branch of `or` never checked |
| P6.1 | Silent approximations | Users think exact, get approximate |

---

*Last updated: 2026-05-25*
