---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 01
status: ready_to_plan
last_updated: 2026-05-25T12:39:29.295Z
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 5
  completed_plans: 5
  percent: 17
stopped_at: Phase 01 complete (5/5) — ready to discuss Phase 2
---

# Project State: sva2rtl

**Last updated:** 2026-05-25
**Current phase:** 2
**Mode:** mvp

---

## Current Status

| Item | State |
|------|-------|
| Roadmap | ✅ Created (6 phases, 40 requirements mapped) |
| Requirements | ✅ Defined (40 v1 requirements, traceability updated) |
| Research | ✅ Complete (HIGH confidence across all areas) |
| Architecture | ✅ Documented (token-passing, 9-stage pipeline) |
| Code | ✅ Phase 1 complete — all 5 plans done; sva2rtl bool_assert.sv works end-to-end |
| Tests | ✅ 131 tests collected (126 pass, 5 skip); mypy --strict + ruff clean |
| CI | ❌ Not configured |

---

## Phase Progress

| Phase | Name | Status | Requirements |
|-------|------|--------|-------------|
| 1 | Foundation: IR + Slang + Boolean → SV Monitor | ✅ Complete (5/5 plans) | PARSE-01/02/04/05, OUT-01/02/03/07/08, CLI-05/06, TEST-01 |
| 2 | Core Sequential Operators (##N, |->)  | 🔲 Not started | OP-01/02/03/04, OUT-06, TEST-02/05/06 |
| 3 | Remaining Tier 1 + Sim Validation | 🔲 Not started | OP-05–10, PARSE-03, OUT-04, TEST-03/04 |
| 4 | Normalization + Composition Engine | 🔲 Not started | PIPE-01/02 |
| 5 | Optimization Passes | 🔲 Not started | PIPE-03/04/05 |
| 6 | CLI Polish + Verilog-2001 + Integration | 🔲 Not started | CLI-01–04, OUT-05 |

---

## Active Phase

**Phase 2** — Core Sequential Operators (##N, |->)

### Phase 1 Plan Checklist (COMPLETE)

- [x] **1.1** Project skeleton + SVA IR (`ir.py`, `errors.py`, package setup)
- [x] **1.2** Slang frontend + AST importer (`frontend.py`, `ast_importer.py`)
- [x] **1.3** Template emitter + bool_expr template (`emitter.py`, `templates/bool_expr.sv.j2`)
- [x] **1.4** CLI entry point + error handling (`cli.py`)
- [x] **1.5** Unit test framework + Phase 1 tests

### Phase 1 Success Criteria (ALL MET)

- [x] `sva2rtl bool.sv` produces a `.sv` file that compiles clean under `iverilog`
- [x] Generated monitor exposes standard ports; `attempt_fired` goes high correctly in simulation
- [x] Unsupported operator → exit code 2 with source location, no silent miscompile ✅ (CLI-05/CLI-06 satisfied)
- [x] Slang not found → exit code 3 with install message ✅ (CLI-05 satisfied)
- [x] All unit tests pass; mypy --strict reports zero errors

---

## Key Decisions (Settled)

| Decision | Rationale |
|----------|-----------|
| Python 3.12+ with slang CLI (`--ast-json`) | Fastest iteration; JSON AST is stable; avoids C++ build complexity |
| Token-passing architecture (TIMA Lab) | Linear O(n) area, compositional, proven in academic literature |
| Bit-vector method for `|->` | Simple, hardware-efficient, handles 85%+ of real SVA |
| Counter encoding over state expansion | `##[0:100]` = 7-bit counter vs. 101 parallel paths — critical area |
| Frozen dataclasses for IR | Structural hashing for CSE; immutable for safe sharing across passes |
| `attempt_fired` first-class from Phase 1 | Prevents vacuous satisfaction going undetected; cannot be retrofitted |
| `SourceLoc` first-class on IR nodes | Prevents Phase 5 pitfall (source location not threaded through IR) |
| Normalization before Phase 4 operators | Phases 2–3 use direct wiring; Phase 4 installs proper composition engine |

---

## Risks Being Tracked

| Risk | Mitigation | Status |
|------|-----------|--------|
| Vacuous satisfaction (P1.1) | `attempt_fired` port first-class from Phase 1; every test asserts it | ⏳ Mitigation planned |
| Bit-vector overflow / silent thread drop (P1.3) | Parameterized bit-width; sticky `overflow_flag`; concurrent-attempt stress tests | ⏳ Mitigation planned |
| Source location not threaded (P5.1) | `SourceLoc` first-class field on all IR nodes from Phase 1 | ⏳ Mitigation planned |
| `disable iff` is asynchronous (P1.6) | Async combinational gate template; verified in Phase 3 simulation | ⏳ Mitigation planned |
| NFA→DFA state explosion (P4.1) | Token-passing architecture; DFA only for NFAs ≤ 8 states | ⏳ Mitigation planned |
| slang JSON schema completeness | Node-kind inventory script in Phase 1.5 | ⏳ Mitigation planned |

---

## Requirement Status Summary

- **Total v1:** 40
- **Completed:** 0
- **In progress:** 0
- **Not started:** 40

---

## Transition Log

| Date | Event |
|------|-------|
| 2026-05-25 | Project initialized; research complete; roadmap created |
| 2026-05-25 | Plan 1.3 complete — composer.py, emitter.py, templates/bool_expr.sv.j2, golden files (bool_labeled.sv, bool_simple.sv), 44 new tests (104 total); OUT-01/02/03/07/08 satisfied |
| 2026-05-25 | Plan 1.4 complete — cli.py click entry point, SV fixture files, 9 CLI tests; CLI-05/CLI-06 satisfied |
| 2026-05-25 | Plan 1.5 complete — conftest.py, test_integration.py (12 tests), test_pipeline_e2e.py (6 tests); TEST-01/PARSE-05/OUT-02/OUT-03 satisfied; Phase 1 COMPLETE (131 tests: 126 pass, 5 skip) |

---

*State file created: 2026-05-25*
*Updated automatically at phase transitions and milestone boundaries*
