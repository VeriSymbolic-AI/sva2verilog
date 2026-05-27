---
plan: "3.3"
status: complete
completed: "2026-05-27"
tests_before: 341
tests_after: 383
tests_added: 42
requirements_satisfied:
  - OP-10
  - PARSE-03
  - OUT-04
---

# Plan 3.3 Summary: `disable iff` + Interface Update + Named Sequences + Bind Generation

## What Was Built

Seven tasks spanning interface standardization, three new operator constructs, and a
module-naming bug fix that was uncovered during test authoring.

---

### Task 3.3.1 — Update ALL existing templates with `disable_i`/`disabled_o` ports

All 5 existing templates (`bool_expr.sv.j2`, `concat_delay.sv.j2`, `overlap_bitvec.sv.j2`,
`nonoverlap.sv.j2`, `seq_concat_top.sv.j2`) received uniform interface additions:

- `input  logic disable_i` added after signal ports
- `output logic disabled_o` added as the final output port
- `always_ff` reset conditions changed from `if (!rst_n)` to `if (!rst_n | disable_i)` so
  accumulated state clears synchronously when disable is asserted
- Combinational output gating (`disable_i ? 1'b0 : ...`) on `active`, `pass`, and `fail`
  suppresses outputs on the same clock cycle disable is asserted — no 1-cycle spurious window
- `assign disabled_o = disable_i;` propagates disable status up the hierarchy
- Child instantiations in wrapper templates (`overlap_bitvec`, `nonoverlap`, `seq_concat_top`)
  thread `.disable_i(disable_i)` and `.disabled_o()` to every child instance

---

### Task 3.3.2 — Regenerate all Phase 1–2 golden files

All 28 golden files in `tests/golden/` were regenerated to include the new
`disable_i`/`disabled_o` ports, updated reset conditions, and gated output assignments.
All existing tests (integration, emitter, sequential) pass against the updated files.

---

### Task 3.3.3 — Add `DisableIff` IR node and AST importer dispatch

- `DisableIff(SVANode)` frozen dataclass added to `ir.py` with fields
  `condition: SVANode` and `body: SVANode`
- `ast_importer.py` extended to detect `PropertySpec.disableIff` (slang's JSON does **not**
  emit a separate `"kind": "DisableIff"` node — the disable condition is an optional field on
  `PropertySpec`, not a wrapping node)
- Condition reconstructed via `expr_to_sv()`, wrapped in `BoolExpr`; body composed from the
  `expr` field of the same `PropertySpec`
- Reconstructed text prefixed: `"disable iff ({cond}) {body_text}"`
- `tests/fixtures/disable_iff.json` created: uses `@(posedge clk) disable iff (!rst_n) a |-> b`

---

### Task 3.3.4 — Composer and template for `disable_iff_top`

- `_compose_disable_iff()` added to `composer.py`:
  - Derives unique `body_label = f"{base}_body"` for the body child so its module name
    never collides with the wrapper when `label=None` (both would otherwise hash the same
    `original_text`)
  - Collects signals: condition signals first, then body signals (deduped)
  - Returns `CheckerNode(template_name="disable_iff_top", children=(body_checker,), ...)`
- `templates/disable_iff_top.sv.j2` created:
  - Has `input logic disable_i` (supports chained disable from outer context)
  - Evaluates condition combinationally: `assign cond_result = ({cond_expr});`
  - OR-combines with incoming disable: `assign effective_disable = disable_i | cond_result;`
  - Instantiates body child with `.disable_i(effective_disable)`
  - Gates own outputs with `disable_i` (not `effective_disable`) — condition-triggered
    suppression already handled by body child's own gating

---

### Task 3.3.5 — Named sequence/property inline expansion (PARSE-03)

- `cse_origin: str | None = None` field added to `CheckerNode` (with explicit `__hash__`
  and `__eq__` exclusion so identity is structure-based, not provenance-based)
- `ast_importer.py` extended to detect slang's `SequenceInstance` node kind (the reference
  form used when a property references a named sequence by name)
- Named sequence body is inlined at the use site via a recursive dispatch call; `cse_origin`
  is set to the sequence declaration name for Phase 5 CSE identification
- Circular reference detection: `visited: set[str]` tracks the expansion stack; a second
  visit raises `SvaCompileError` with code "SVA-E003"
- `tests/fixtures/named_seq.json` created: module with a `sequence s = a ##1 b` declaration
  and a property that references `s`
- `tests/test_named_sequences.py` created: 8 tests covering IR field, inline expansion,
  circular-reference rejection, and CSE origin tagging

---

### Task 3.3.6 — Bind statement generation (OUT-04)

- `templates/bind.sv.j2` created: generates `bind <dut> <module> u_<module> (...)` with
  correct port connections, always-on `.start(1'b1)`, and `.disable_i(1'b0)` default
- `emit_bind(checker, dut_module)` public function added to `emitter.py`
- `tests/test_bind.py` created: 7 tests covering output structure, port connections,
  DUT module name, default start/disable values, and endmodule presence

---

### Task 3.3.7 — Fix 3 failing `test_disable_iff.py` tests + golden file updates

**Root cause discovered during test authoring:** `_compose_implication` in `composer.py`
was passing `label=None` to both antecedent and consequent children along with the same
`original_text`. When `label=None`, `module_name_from_label` produces a SHA-256 hash of
`original_text` — so both children got **the same module name as the parent** when the parent
also had `label=None`.

In the `emit_all` traversal, `_emit_recursive` skips a module whose `module_name` is already
in the results dict. For the `disable iff` case:
1. The grandchild antecedent `BoolExpr("a")` was rendered first and registered as
   `results["sva_prop_7ad1ea48"]`
2. When the top-level `disable_iff_top` wrapper tried to register, `"sva_prop_7ad1ea48"` was
   already in `results` — so the wrapper was silently skipped
3. `modules[checker.module_name]` returned the antecedent's bool_expr content instead of the
   disable_iff_top content — causing all three assertions about `cond_result`,
   `effective_disable`, and `.disable_i` to fail

**Fix:** `_compose_implication` now derives `base` from `module_name` (same pattern as
`_compose_seq_concat` uses for `_e{i}` children) and passes unique labels:

```python
base = module_name[4:] if module_name.startswith("sva_") else module_name
ant_checker = compose(node.antecedent, clock, f"{base}_ant", original_text)
con_checker = compose(node.consequent, clock, f"{base}_con", original_text)
```

**Side effect — also fixed a pre-existing SV bug:** The old golden files for
`overlap_impl.sv`, `nonoverlap_impl.sv`, and `sva_bitvec_impl.sv` contained **duplicate
instance names** (both ant and con child instances had the same module type and instance name
like `sva_prop_47ec2b81 u_sva_prop_47ec2b81`). This is invalid SystemVerilog. After the fix,
children get distinct names (`sva_impl_check_ant u_sva_impl_check_ant` and
`sva_impl_check_con u_sva_impl_check_con`), and the three golden files were regenerated.

---

## Files Changed

| File | Change |
|------|--------|
| `src/sva2rtl/ir.py` | Added `DisableIff` dataclass; added `cse_origin` to `CheckerNode` |
| `src/sva2rtl/ast_importer.py` | Dispatch for `PropertySpec.disableIff`; named sequence inline expansion; `SequenceInstance` handler |
| `src/sva2rtl/composer.py` | `_compose_disable_iff`; `_compose_implication` sub-label fix |
| `src/sva2rtl/emitter.py` | `emit_bind()` function |
| `templates/bool_expr.sv.j2` | `disable_i`/`disabled_o` ports + gating |
| `templates/concat_delay.sv.j2` | `disable_i`/`disabled_o` ports + gating |
| `templates/overlap_bitvec.sv.j2` | `disable_i`/`disabled_o` ports + child threading + gating |
| `templates/nonoverlap.sv.j2` | `disable_i`/`disabled_o` ports + child threading + gating |
| `templates/seq_concat_top.sv.j2` | `disable_i`/`disabled_o` ports + child threading + gating |
| `templates/rep_consecutive.sv.j2` | `disable_i`/`disabled_o` ports + gating (Plan 3.1 template) |
| `templates/rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2`, `past.sv.j2` | `disable_i`/`disabled_o` ports + gating (Plan 3.2 templates) |
| `templates/disable_iff_top.sv.j2` | New template |
| `templates/bind.sv.j2` | New template |
| `tests/fixtures/disable_iff.json` | New fixture |
| `tests/fixtures/named_seq.json` | New fixture |
| `tests/test_disable_iff.py` | New test file (16 tests) |
| `tests/test_named_sequences.py` | New test file (8 tests) |
| `tests/test_bind.py` | New test file (7 tests) |
| `tests/golden/*.sv` (28 files) | Regenerated with updated interface |
| `tests/golden/overlap_impl.sv` | Regenerated with `_ant`/`_con` child names |
| `tests/golden/nonoverlap_impl.sv` | Regenerated with `_ant`/`_con` child names |
| `tests/golden/sva_bitvec_impl.sv` | Regenerated with `_ant`/`_con` child names |

---

## Test Results

| Metric | Before | After |
|--------|--------|-------|
| Tests collected | 341 | 383 |
| Tests passing | 331 | 383 |
| Tests failing | 0 | 0 |
| Tests skipped | 10 | 10 |
| Tests fixed (were failing) | — | 3 (disable_iff emitter tests) |

All 383 tests pass. `mypy --strict src/sva2rtl/` and `ruff check src/ tests/` clean.

---

## Requirements Satisfied

- **OP-10**: `disable iff` operator supported with combinational async output suppression
- **PARSE-03**: Named sequence/property inline expansion with `cse_origin` tagging
- **OUT-04**: `emit_bind()` generates valid SystemVerilog `bind` statements

---

## Key Lessons Learned

1. **Module naming collisions are silent and hard to debug.** The `_emit_recursive` dedup
   logic (correct for CSE) can accidentally suppress a parent module when a grandchild
   claims the same hash-derived name. Always give wrapper children unique sub-labels.

2. **Slang's `disable iff` is a field, not a node kind.** `PropertySpec.disableIff` is an
   optional field on the `PropertySpec` object, not a separate AST node with
   `"kind": "DisableIff"`. The importer must check the field, not dispatch on kind.

3. **Golden files for composite modules must be checked for duplicate instance names.**
   The pre-existing `sva_prop_XXXXXXXX u_sva_prop_XXXXXXXX` duplicate was masked by the
   dedup logic; fixing the naming bug exposed and corrected it.
