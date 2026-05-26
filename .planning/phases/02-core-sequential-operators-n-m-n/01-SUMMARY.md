# Plan 2.1 Execution Summary

**Plan**: `02-core-sequential-operators-n-m-n` — Plan 01  
**Branch**: `worktree-agent-a4ede4cf8d84f122c`  
**Base commit**: `50743a84169866acf46e855d7b8149ce44e13c33`  
**Completed**: 2026-05-26

---

## Objective

End-to-end compilation of `##N` (fixed delay) and `##[M:N]` (range delay) SVA sequences into counter-encoded synthesizable RTL monitors. Every generated monitor exposes `(clk, rst_n, start, pass, fail, active, attempt_fired)` ports and uses the token-passing composition model.

---

## Tasks Completed

### Task 2.1.1 — `templates/concat_delay.sv.j2` (commit `8ffc34a`)

Created the unified delay counter Jinja2 template. Key design decisions:

- `##0` path: pure combinational (`assign pass = start`), no counter registers
- `##N` / `##[M:N]` path: counter-based, `CNT_WIDTH` parameter, single running/count state machine
- `'0` used for reset (not `{N{1'b0}}` which conflicts with Jinja2 `}}` delimiters)
- `attempt_fired` is sticky (set on start, cleared only by `rst_n`)

### Task 2.1.2 — `src/sva2rtl/ast_importer.py` (commit `929da43`)

Extended the AST importer to handle `SequenceConcat` nodes:

- Removed `"SequenceConcat"` from `UNSUPPORTED_KINDS_PHASE1`
- Added `_build_seq_concat()`: parses elements + delays, skips the last element's `(0,0)` sentinel delay
- Added `_dispatch_expr_to_ir()`: maps `SequenceExpr` sub-nodes to `BoolExpr` IR
- Added `_reconstruct_seq_text()`: rebuilds human-readable `a ##3 b` text from `SeqConcat` IR
- Added `SVA-E003` validation: raises `SvaCompileError` on invalid delay ranges (min > max)
- `import_assertion()` now dispatches on `"SequenceConcat"` vs. other `expr` kinds via `match`

### Task 2.1.3 — `src/sva2rtl/composer.py` (commit `2320647`)

Extended the composer with hierarchical `SeqConcat` support:

- `compose()` now dispatches via `match node:` on `BoolExpr` vs. `SeqConcat`
- `_compose_seq_concat()`: interleaves bool-expr checker nodes with delay checker nodes, builds top-level `seq_concat_top` `CheckerNode` with correct child list
- `_make_delay_node()`: creates `concat_delay` template `CheckerNode` with `cnt_width = max(1, ceil(log2(delay_max+1)))`
- `_collect_signals()`: deduplicates observed signals across all children for top-level port list
- **Critical fix**: strips `sva_` prefix when building child labels to prevent `sva_sva_prop_xxx_e0` double-prefix bug

### Task 2.1.4 — `src/sva2rtl/emitter.py` + `templates/seq_concat_top.sv.j2` (commit `3caa70f`)

Created the hierarchical top wrapper template and multi-file emit:

- `seq_concat_top.sv.j2`: wires N children via token-passing chain; first child gets `start`, each subsequent child gets `w_pass_{i-1}`; aggregates `active`/`fail` with OR, `pass` from last child, `attempt_fired` from first child
- `emit_all(checker)`: returns `dict[str, str]` in dependency order (children before parents) via depth-first recursion; prevents re-rendering shared sub-modules
- `write_output_dir(modules, output_dir)`: writes one `.sv` file per module to flat output directory, creating missing dirs

### Task 2.1.5 — `src/sva2rtl/cli.py` (commit `4e33914`)

Updated CLI to route hierarchical vs. flat output:

- If `checker_node.children` is non-empty: calls `emit_all()` + `write_output_dir()` to a directory
- If `checker_node.children` is empty: calls `emit()` + `write_output()` as before (stdout or single file)
- Updated `test_cli.py`: added `mock_checker.children = ()` to existing tests to keep them on the single-file path

### Task 2.1.6 — Fixture JSONs + Golden SV Files (commit `e982e74`)

Created 4 fixture JSONs and 18 golden SV files:

| Fixture | Property | Modules Generated |
|---------|----------|-------------------|
| `delay_fixed.json` | `a ##3 b` | `sva_prop_81cf66e0_e0`, `sva_delay_3_3`, `sva_prop_81cf66e0_e1`, `sva_prop_81cf66e0` |
| `delay_range.json` | `a ##[2:5] b` | `sva_prop_e9edaa37_e0`, `sva_delay_2_5`, `sva_prop_e9edaa37_e1`, `sva_prop_e9edaa37` |
| `delay_zero.json` | `a ##0 b` | `sva_prop_75080d6b_e0`, `sva_delay_0_0`, `sva_prop_75080d6b_e1`, `sva_prop_75080d6b` |
| `delay_three_element.json` | `a ##1 b ##2 c` | 6 modules (3 bool + 2 delay + 1 top) |

### Task 2.1.7 — Unit Tests (commit `e982e74`)

Extended `tests/test_emitter.py` with 24 new tests:

- `emit_all()` structural tests: module name sets, child-before-parent ordering, `##0` combinational path, 3-element sequence count
- `emit_all()` content tests: `CNT_WIDTH` values, instantiation names, token-passing wiring, final `pass` assignment
- `test_emit_all_golden_match` parametrized across 9 golden files (delay modules + top wrappers)
- `write_output_dir()` tests: file creation, content correctness, missing-dir creation

Also updated `tests/test_ast_importer.py`, `tests/test_composer.py`, and `tests/test_integration.py` in earlier commits to cover the new `SeqConcat` pipeline path.

---

## Test Results

```
165 passed, 5 skipped
mypy --strict: no issues found in 19 source files
```

Test count grew from 141 (pre-phase-2) to 165 (+24 emitter tests in final commit).

---

## Architecture Notes

### Counter Encoding Formula

```
cnt_width = max(1, ceil(log2(delay_max + 1)))  if delay_max > 0  else 1
```

Examples: `##1` → 1 bit, `##3` → 2 bits, `##[2:5]` → 3 bits, `##0` → 1 bit (parameter present but counter not used)

### Slang JSON Sentinel

Every `SequenceConcat` element in slang's `--ast-json` output carries the delay **after** it. The last element always has `min=0, max=0` as a trailing sentinel and must be skipped during IR construction.

### Token-Passing Chain

```
start → [bool_e0] → w_pass_0 → [delay_0_N] → w_pass_1 → [bool_e1] → pass
```

The top wrapper ORs all `active` and `fail` signals; `pass` comes from the final child's output; `attempt_fired` comes from the first child (tracks sequence initiation).

---

## Commits

| Hash | Message |
|------|---------|
| `8ffc34a` | feat(phase2): add concat_delay.sv.j2 template for ##N and ##[M:N] delays |
| `929da43` | feat(phase2): handle SequenceConcat in ast_importer; update tests |
| `2320647` | feat(phase2): extend composer with SeqConcat hierarchical CheckerNode support |
| `3caa70f` | feat(phase2): add emit_all/write_output_dir and seq_concat_top template |
| `4e33914` | feat(phase2): update cli.py for multi-file hierarchical output |
| `e982e74` | feat(phase2): add delay fixture JSONs, golden SV files, and emitter tests |
