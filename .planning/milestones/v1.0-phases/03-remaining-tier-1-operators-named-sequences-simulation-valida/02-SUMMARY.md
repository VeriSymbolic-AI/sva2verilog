# SUMMARY: Plan 3.2 — Signal Function Operators (`$rose`, `$fell`, `$stable`, `$past`)

**Completed:** 2026-05-27
**Status:** ✅ All tasks done, 341 tests pass, 0 regressions

---

## What Was Done

Delivered all four signal function operators end-to-end: `SignalFunc` IR node, AST importer dispatch for `CallExpression`, composer mapping to four Jinja2 templates, four synthesizable SV templates, behavioral oracle for all four functions, JSON fixtures, golden files, and 38 new tests.

### Tasks Completed

| Task | Description | Outcome |
|------|-------------|---------|
| 3.2.1 | `SignalFunc` IR node in `ir.py` | ✅ frozen, hashable, `depth=1` default, mypy clean |
| 3.2.2 | AST importer dispatch for `CallExpression` with `$rose/$fell/$stable/$past` | ✅ `_build_signal_func`, `_reconstruct_signal_func_text`; non-literal `$past` depth rejects with UnsupportedConstruct |
| 3.2.3 | Composer support for `SignalFunc` → template-named CheckerNode | ✅ `func_name` maps 1:1 to template name; single observed_signal entry |
| 3.2.4 | `rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2` templates | ✅ 1 FF + AND-NOT / AND / XNOR detection logic; disable_i/disabled_o gating |
| 3.2.5 | `past.sv.j2` template | ✅ N-stage shift register with `parameter DEPTH`; single-FF shortcut for depth=1 |
| 3.2.6 | Behavioral oracle for all four functions | ✅ `_tick_rose`, `_tick_fell`, `_tick_stable`, `_tick_past`; FIFO shift list for past; reset() support |
| 3.2.7 | Fixtures (`rose/fell/stable/past.json`), 38 tests, golden files | ✅ 38 tests pass; mypy --strict + ruff clean |

### Key Implementation Decisions

- **`func_name` strips `$` prefix:** `"$rose"` → `"rose"` so it maps directly to the template filename (`rose.sv.j2`) and template_name in CheckerNode
- **Non-literal `$past` depth:** `arguments[1]` must have `"kind": "IntegerLiteral"`; any non-literal (e.g., a signal) raises `UnsupportedConstruct` — prevents hardware where depth is unknowable at compile time
- **`disable_i` semantics:** `if (!rst_n | disable_i)` resets all FFs synchronously; all outputs combinationally gated to 0 when `disable_i` is high — matches the hardware contracts established in Plans 3.1 and 1.x
- **`past.sv.j2` depth-1 shortcut:** `{% if depth == "1" %}` (string comparison since all params are `dict[str, str]`) selects single `logic shift_q;` vs `logic [DEPTH-1:0] shift_q;` — avoids `[0:0]` array in Verilog
- **FIFO shift for oracle:** `self._past_shift[-1]` holds the oldest sample; shift inserts at `[0]` — correctly models an N-cycle pipeline
- **`expr_to_sv` CallExpression case:** Reconstructs the text form (e.g., `"$rose(sig)"`) rather than raising for supported functions, so signal functions embedded in larger expressions remain representable

### Files Modified

- `src/sva2rtl/ir.py` — added `SignalFunc(SVANode)` dataclass
- `src/sva2rtl/ast_importer.py` — `_SUPPORTED_SIGNAL_FUNCS`, `_build_signal_func`, `_reconstruct_signal_func_text`, dispatch in `_import_concurrent_assertion` / `_dispatch_expr_to_ir` / `expr_to_sv`
- `src/sva2rtl/composer.py` — `SignalFunc` case in `compose()`, `_compose_signal_func` helper
- `src/sva2rtl/behavioral_oracle.py` — rose/fell/stable/past kinds, `_tick_*` methods, reset support
- `templates/rose.sv.j2` — 1 FF + AND-NOT edge detect
- `templates/fell.sv.j2` — 1 FF + AND (inverted) edge detect
- `templates/stable.sv.j2` — 1 FF + XNOR comparator
- `templates/past.sv.j2` — N-stage shift register, `parameter DEPTH`
- `tests/fixtures/rose.json` — `$rose(sig)` fixture
- `tests/fixtures/fell.json` — `$fell(sig)` fixture
- `tests/fixtures/stable.json` — `$stable(sig)` fixture
- `tests/fixtures/past.json` — `$past(sig, 3)` fixture
- `tests/golden/sva_rose.sv` — golden SV for `$rose(sig)`
- `tests/golden/sva_fell.sv` — golden SV for `$fell(sig)`
- `tests/golden/sva_stable.sv` — golden SV for `$stable(sig)`
- `tests/golden/sva_past.sv` — golden SV for `$past(sig, 3)` with `parameter DEPTH = 3`
- `tests/test_signal_functions.py` — 38 new tests

### Test Results

```
341 passed, 10 skipped in 0.52s
mypy --strict: 0 errors (all modified source files)
ruff check: All checks passed
```

### Commits

- `f51b415` feat(3.2.1): add SignalFunc IR node for $rose/$fell/$stable/$past
- `89aab03` feat(3.2.2): add AST importer dispatch for $rose/$fell/$stable/$past
- `4fe5f39` feat(3.2.3): add composer support for SignalFunc IR nodes
- `59e35ba` feat(3.2.4-5): add rose, fell, stable, past Jinja2 templates
- `5ae3829` feat(3.2.6): add behavioral oracle for rose, fell, stable, past
- `76686da` test(3.2.7): add fixtures, golden files, and 38-test suite for signal functions

---

## Must-Haves Check

- [x] `SignalFunc` IR node exists and is frozen/hashable
- [x] AST importer dispatches `CallExpression` with `$rose/$fell/$stable/$past`
- [x] Non-literal `$past(sig, N)` depth rejected as `UnsupportedConstruct`
- [x] Composer maps each `func_name` to its corresponding template
- [x] 4 templates render correct detection logic (AND-NOT, AND, XNOR, shift register)
- [x] All templates include `disable_i`/`disabled_o` ports
- [x] Behavioral oracle correctly models all 4 signal functions
- [x] All new tests pass; no regressions in existing tests (341 pass, 10 skip)
