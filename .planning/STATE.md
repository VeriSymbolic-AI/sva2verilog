---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 06
status: ready_to_plan
last_updated: "2026-05-28T13:08:39.671Z"
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 18
  completed_plans: 18
  percent: 83
---

# Project State: sva2rtl

**Last updated:** 2026-05-28
**Current phase:** 06
**Mode:** mvp

---

## Current Status

| Item | State |
|------|-------|
| Roadmap | ✅ Created (6 phases, 40 requirements mapped) |
| Requirements | ✅ Defined (40 v1 requirements, traceability updated) |
| Research | ✅ Complete (HIGH confidence across all areas) |
| Architecture | ✅ Documented (token-passing, 9-stage pipeline) |
| Code | ✅ Phase 1-5 complete — full optimization pipeline; sva2rtl compiles SVA to optimized RTL; 577 tests pass |
| Tests | ✅ 577 tests (577 pass, 17 skip); mypy --strict + ruff clean |
| CI | ❌ Not configured |

---

## Phase Progress

| Phase | Name | Status | Requirements |
|-------|------|--------|-------------|
| 1 | Foundation: IR + Slang + Boolean → SV Monitor | ✅ Complete (5/5 plans) | PARSE-01/02/04/05, OUT-01/02/03/07/08, CLI-05/06, TEST-01 |
| 2 | Core Sequential Operators (##N, |->) | ✅ Complete (3/3 plans) | OP-01/02/03/04, OUT-06, TEST-02/05/06 |
| 3 | Remaining Tier 1 + Sim Validation | ✅ Complete (4/4 plans) | OP-05–10, PARSE-03, OUT-04, TEST-03/04 |
| 4 | Normalization + Composition Engine | ✅ Complete (3/3 plans) | PIPE-01/02 |
| 5 | Optimization Passes | ✅ Complete (3/3 plans) | PIPE-03/04/05 |
| 6 | CLI Polish + Verilog-2001 + Integration | 🔲 Not started | CLI-01–04, OUT-05 |

---

## Active Phase

**Phase 5** — Optimization Passes

### Phase 5 Plan Checklist

- [ ] **5.1** Optimizer framework + constant folding + concat merging (Wave 1)
- [ ] **5.2** CSE deduplication + counter merging (Wave 2, depends 5.1)
- [ ] **5.3** Dead-node elimination + parity suite + dump-tree summary (Wave 3, depends 5.2)

### Phase 4 Plan Checklist (COMPLETE)

- [x] **4.1** IR normalization pass — `normalizer.py`: `[*1]` identity, SeqConcat flattening, constant fold, idempotent (Wave 1) ✅ 2026-05-28
- [x] **4.2** Composition engine — structural hash + pipeline integration, `normalize()` wired into CLI + tests (Wave 1, depends 4.1) ✅ 2026-05-28
- [x] **4.3** Integration + regression validation — `--dump-tree`, golden parity, simulation oracle re-run (Wave 2) ✅ 2026-05-28

### Phase 3 Plan Checklist (COMPLETE)

- [x] **3.1** Consecutive repetition `[*N]/[*M:N]` — counter-based FSM (Wave 1)
- [x] **3.2** Signal functions `$rose/$fell/$stable/$past` — edge detect + shift register (Wave 1)
- [x] **3.3** `disable iff` + interface update + named sequences + bind generation (Wave 2)
- [x] **3.4** Simulation validation harness — dual oracle (Wave 3)

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
| 2026-05-27 | Phase 3 planned — 4 plans, 3 waves, 10 requirements. Plan-checker PASSED. |
| 2026-05-27 | Plan 3.1 complete — SeqRepetition IR, importer dispatch, composer, rep_consecutive.sv.j2 template, behavioral oracle, 23 tests; OP-05 satisfied |
| 2026-05-27 | Plan 3.3 complete — DisableIff IR/importer/composer/template, named sequence expansion (PARSE-03), bind generation (OUT-04), disable_i/disabled_o interface on all 9 templates, 3 golden files fixed (duplicate instance name bug), 42 new tests; OP-10/PARSE-03/OUT-04 satisfied; 383 tests pass |
| 2026-05-27 | Plan 3.4 complete — simulation validation harness; tb_generator.py + iverilog runner; 43 simulation tests (rose/fell/stable/past/rep/disable_iff/delay/implication); BV_WIDTH=1 RTL fix; reserved-port dedup fix; 5 oracle disable-key unit tests; 453 tests pass (10 skip); TEST-03/TEST-04 satisfied; Phase 3 COMPLETE |
| 2026-05-28 | Plan 4.1 complete — normalizer.py: [*1] identity removal, SeqConcat flattening, PropImplication preserved (D-05), 17 tests; PIPE-01 partially satisfied; 470 tests pass |
| 2026-05-28 | Plan 4.3 complete — debug.py (format_dump_tree), --dump-tree CLI flag, test_dump_tree.py (11 tests), test_golden_parity.py (16 tests), 2 E2E tests; 502 tests pass; Phase 4 COMPLETE |
| 2026-05-28 | Phase 5 planned — 3 plans, 3 waves, PIPE-03/04/05. Plan-checker PASSED. |

---

*State file created: 2026-05-25*
*Updated automatically at phase transitions and milestone boundaries*
