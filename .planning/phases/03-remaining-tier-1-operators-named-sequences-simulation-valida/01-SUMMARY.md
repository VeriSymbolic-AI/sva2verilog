# SUMMARY: Plan 3.1 — Consecutive Repetition [*N] / [*M:N]

**Completed:** 2026-05-27
**Status:** ✅ All tasks done, 303 tests pass, 0 regressions

---

## What Was Done

Delivered full end-to-end consecutive repetition (`[*N]` and `[*M:N]`) from AST import through IR, composer, template, behavioral oracle, and tests.

### Tasks Completed

| Task | Description | Outcome |
|------|-------------|---------|
| 3.1.1 | `SeqRepetition` IR node in `ir.py` | ✅ frozen, hashable, mypy clean |
| 3.1.2 | AST importer dispatch for `SimpleAssertionExpr` + consecutive repetition | ✅ `UNSUPPORTED_KINDS_PHASE1` now `{}` |
| 3.1.3 | Composer support for `SeqRepetition` → `rep_consecutive` CheckerNode | ✅ cnt_width=ceil(log2(rep_max+1)) |
| 3.1.4 | `templates/rep_consecutive.sv.j2` counter-based FSM template | ✅ disable_i/disabled_o, count_q, running_q |
| 3.1.5 | Behavioral oracle `_tick_rep_consecutive` in `behavioral_oracle.py` | ✅ pass/fail/active semantics correct |
| 3.1.6 | Fixtures (`rep_fixed.json`, `rep_range.json`), tests (`test_repetition.py`), golden files | ✅ 23 tests, all pass |

### Key Implementation Decisions

- **Counter width:** `max(1, ceil(log2(rep_max + 1)))` — same formula as `concat_delay`, rep_max=3 → 2 bits
- **Unbounded rejection:** `max="$"` raises `SvaCompileError` with `"SVA-E002"` in message
- **disable_i semantics:** synchronous — `if (!rst_n || disable_i)` resets all registers; outputs gated to 0 when disabled
- **Oracle state:** `_rep_count` and `_rep_running` added to `SVABehavioralSim`; `reset()` clears both
- **Stale test updates:** Two `test_ast_importer.py` tests that asserted `"SequenceRepetition" in UNSUPPORTED_KINDS_PHASE1` were updated to assert the opposite (Phase 3 implements this)

### Files Modified

- `src/sva2rtl/ir.py` — added `SeqRepetition(SVANode)` dataclass
- `src/sva2rtl/ast_importer.py` — dispatch for `SimpleAssertionExpr` with repetition, `_build_seq_repetition`, `_reconstruct_rep_text`; `UNSUPPORTED_KINDS_PHASE1` cleared
- `src/sva2rtl/composer.py` — `SeqRepetition` case in `compose()`, `_compose_repetition` helper
- `src/sva2rtl/behavioral_oracle.py` — `rep_consecutive` kind, `_tick_rep_consecutive`, reset support
- `templates/rep_consecutive.sv.j2` — new template
- `tests/fixtures/rep_fixed.json` — `[*3]` fixture
- `tests/fixtures/rep_range.json` — `[*2:5]` fixture
- `tests/golden/sva_rep_fixed.sv` — golden SV for `[*3]`
- `tests/golden/sva_rep_range.sv` — golden SV for `[*2:5]`
- `tests/test_repetition.py` — 23 new tests
- `tests/test_ast_importer.py` — 2 stale guard tests updated

### Test Results

```
303 passed, 10 skipped in 0.52s
mypy --strict: 0 errors (4 source files)
ruff check: All checks passed
```

### Commit

`7b04ca0` feat(phase3.1): implement consecutive repetition [*N]/[*M:N] end-to-end

---

## Must-Haves Check

- [x] `SeqRepetition` IR node exists and is frozen/hashable
- [x] AST importer handles `SimpleAssertionExpr` with consecutive repetition
- [x] Unbounded `[*0:$]` rejected with SVA-E002
- [x] Composer produces CheckerNode with `template_name="rep_consecutive"`
- [x] Template renders compilable SV with counter-based FSM
- [x] Behavioral oracle correctly models [*N]/[*M:N] semantics
- [x] All new tests pass; no regressions in existing tests
