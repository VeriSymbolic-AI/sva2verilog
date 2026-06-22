---
milestone: v1.3
milestone_name: Tier 2 Operators — NFA Composition
created: 2026-06-14
total_phases: 4
total_requirements: 17
---

# Roadmap — sva2rtl v1.3

## Milestones

- ✅ **v1.0 MVP** — SVA→RTL Compiler — Phases 1-6 (shipped 2026-06-01)
- ✅ **v1.1 Hardening Release** — 7 phases, 34 requirements (shipped 2026-06-05)
- ✅ **v1.2 Quality-First Hardening** (complete) — 6 phases, ~22 requirements
- 🔄 **v1.3 Tier 2 Operators** (in progress) — 4 phases, ~17 requirements

---

## v1.3 — Tier 2 Operators: NFA Composition

**Goal:** Extend sva2rtl with Tier 2 SVA operators. Platform supports token-passing fork/join architecture for multi-path operators. All 17 requirements implemented, 868 tests pass.

**Status:** ✅ Complete (2026-06-15)

### Phase Overview

| Phase | Name | Requirements | Plan estimate | Status |
|-------|------|-------------|---------------|--------|
| 1 | Architecture Research Spike | ARCH-01, ARCH-02, ARCH-03, ARCH-04 | 1 | ✅ Complete |
| 2 | IR Expansion + Simple Operators | IR-01, OPS-01, OPS-02, OPS-03, OPS-04 | 3 | ✅ Complete |
| 3 | Complex Sequence Operators | OPS-05, OPS-06, OPS-07, OPS-08, OPS-09 | 2 | ✅ Complete |
| 4 | Property Operators + CSE + Release | OPS-10, OPS-11, CSE-01, RELEASE | 2 | ✅ Complete |

**Totals:** 4 phases · ~17 requirements · ~8 plans · All complete

---

## Phase Details

### Phase 1 — Architecture Research Spike

**Goal:** Determine whether NFA automata composition or token-passing fork/join extensions are the right foundation for multi-path sequence operators.

**Requirements:**
- **ARCH-01** — Evaluate NFA automata composition for multi-path operators
- **ARCH-02** — Evaluate token-passing fork/join extensions
- **ARCH-03** — Compare against industry approaches
- **ARCH-04** — Produce decision document with complexity estimates

**Success criteria:**
1. Architecture decision documented with clear rationale
2. Complexity estimates for each Tier 2 operator under both architectures
3. Prototype sketches for intersect + throughout under chosen architecture

**Plans:**
- [ ] 01-01-PLAN.md — Architecture research spike (NFA vs token-passing)

---

### Phase 2 — IR Expansion + Simple Operators

**Goal:** Add new IR node types; implement the simplest Tier 2 operators first to validate the chosen architecture.

**Requirements:**
- **IR-01** — New IR node types: SeqIntersect, SeqWithin, SeqThroughout, SeqFirstMatch, SeqGotoRep, SeqNonconsecRep, PropAnd, PropOr, PropNot, SignalChanged
- **OPS-01** — `$changed` — signal changed since previous cycle
- **OPS-02** — `first_match` — earliest completion wins
- **OPS-03** — `[->N]` (goto repetition) — N non-consecutive occurrences
- **OPS-04** — `[=N]` (non-consecutive repetition) — N occurrences, relaxed tail

**Success criteria:**
1. All 4 new operators pass dual-oracle simulation
2. 20+ dedicated per-operator test cases
3. Behavioral oracle models new operators

**Plans:**
- [ ] 02-01-PLAN.md — IR node expansion + ast_importer extensions
- [ ] 02-02-PLAN.md — $changed + first_match implementation
- [ ] 02-03-PLAN.md — [->N] + [=N] repetition operators

---

### Phase 3 — Complex Sequence Operators

**Goal:** Implement multi-path sequence operators requiring the NFA architecture.

**Requirements:**
- **OPS-05** — `intersect` — two sequences complete simultaneously
- **OPS-06** — `within` — one sequence contained within another
- **OPS-07** — `throughout` — condition holds continuously through a sequence
- **OPS-08** — `and` (sequence) — both sequences match
- **OPS-09** — `or` (sequence) — either sequence matches

**Success criteria:**
1. All 5 operators pass dual-oracle simulation
2. Behavioral oracle models intersect/within/throughout
3. Formal equivalence tests for composed checker trees

**Plans:**
- [ ] 03-01-PLAN.md — NFA composition engine + intersect/and/or
- [ ] 03-02-PLAN.md — within + throughout operators

---

### Phase 4 — Property Operators + CSE + Release

**Goal:** Add property-level operators, cross-property CSE, and release v1.3.0.

**Requirements:**
- **OPS-10** — `not` (property) — invert pass/fail
- **OPS-11** — `if...else` (property) — conditional property selection
- **CSE-01** — Cross-property CSE (share identical sub-checkers across root nodes)
- **RELEASE** — Tag v1.3.0, release notes, CI green

**Success criteria:**
1. All Tier 2 operators pass dual-oracle + formal
2. Cross-property CSE reduces module count on multi-property benchmarks
3. CI matrix green

**Plans:**
- [ ] 04-01-PLAN.md — Property operators (not, if/else) + cross-property CSE
- [ ] 04-02-PLAN.md — Release v1.3.0

---

## Requirement Coverage Matrix

| REQ-ID | Phase | Phase Name | Category |
|--------|-------|------------|----------|
| ARCH-01 | 1 | Architecture Spike | Research |
| ARCH-02 | 1 | Architecture Spike | Research |
| ARCH-03 | 1 | Architecture Spike | Research |
| ARCH-04 | 1 | Architecture Spike | Research |
| IR-01 | 2 | IR Expansion | Refactor |
| OPS-01 | 2 | Simple Operators | Feature |
| OPS-02 | 2 | Simple Operators | Feature |
| OPS-03 | 2 | Simple Operators | Feature |
| OPS-04 | 2 | Simple Operators | Feature |
| OPS-05 | 3 | Complex Sequence Ops | Feature |
| OPS-06 | 3 | Complex Sequence Ops | Feature |
| OPS-07 | 3 | Complex Sequence Ops | Feature |
| OPS-08 | 3 | Complex Sequence Ops | Feature |
| OPS-09 | 3 | Complex Sequence Ops | Feature |
| OPS-10 | 4 | Property Ops + CSE | Feature |
| OPS-11 | 4 | Property Ops + CSE | Feature |
| CSE-01 | 4 | Property Ops + CSE | Optimize |
| RELEASE | 4 | Release | Release |

---

## Phase Rationale

### Why architecture spike is Phase 1

Multi-path operators (intersect, within, throughout, first_match) require a fundamentally different composition model than the current token-passing pipeline. Choosing the wrong architecture would cause cascading rework across all Tier 2 operators. The spike determines whether NFA automata or token-passing fork/join is the right foundation.

### Why simple operators are Phase 2

`$changed` and `first_match` are the simplest Tier 2 operators and serve as validation that the IR expansion and architecture work. `[->N]` and `[=N]` extend the existing repetition template with liveness tracking.

### Why complex operators are Phase 3

intersect, within, throughout, and sequence and/or require the NFA composition engine from Phase 1 to be fully implemented. They are the hardest operators and validate the architecture at scale.

### Why property operators + CSE are Phase 4

not and if/else are simple pass/fail inverters and muxes that don't depend on the NFA architecture. Cross-property CSE is an independent optimization that benefits from having a full operator set to test against.

---

## Progress

| Phase | Name | Status | Plans |
|-------|------|--------|-------|
| 1 | Architecture Research Spike | ✅ complete | 1 |
| 2 | IR Expansion + Simple Operators | ✅ complete | 3 |
| 3 | Complex Sequence Operators | ✅ complete | 2 |
| 4 | Property Operators + CSE + Release | ✅ complete | 2 |

---

*ROADMAP.md updated: 2026-06-15 — v1.3 Tier 2 Operators complete (4 phases, 17 requirements, 868 tests).*
