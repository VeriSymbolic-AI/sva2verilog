# Plan 03 Execution Summary — Phase 05: Optimization Passes

**Plan file:** `PLAN-5.3.md`
**Executed by:** agent-a1515e15181293e69
**Branch:** `worktree-agent-a1515e15181293e69`
**Date:** 2026-05-28

## Tasks Completed

### 5.3.1 — `dead_node()` pass + count utilities (commit `fe9d30b`)

Replaced the `dead_node()` stub in `optimizer.py` with a full pruning
implementation. The pass removes children tagged with either
`params["_dead"] == "true"` (explicit marker) or `params["_const_false"] == "1"`
(set by `constant_fold()`). Added two new utility functions:

- **`count_nodes(root)`** — counts all instantiation sites in the tree
  (1 + recursive sum over children); shared nodes are counted once per reference.
- **`count_modules(root)`** — counts unique `module_name` values across the
  tree (= number of `.sv` files that `emit_all()` would emit).
- **`_collect_module_names()`** — internal DFS helper for `count_modules`.

### 5.3.2 — `format_dump_tree()` optimization summary (commit `5391f08`)

Extended `debug.py`:

- New keyword argument `unoptimized_checker: CheckerNode | None = None`.
- When provided: appends an `Optimization:` line showing before/after node
  and module counts with percentage reduction
  (e.g., `Optimization: Nodes: 5 -> 3 (-40%), Modules: 4 -> 3 (-25%)`).
- When `None` (optimization disabled): appends
  `Nodes: N (optimization disabled)`.

### 5.3.3 — CLI wiring for `--dump-tree` summary (commit `38a2d12`)

Updated `cli.py` to capture `unoptimized_checker = checker_node`
immediately after `compose()` (before the `optimize()` call). The
captured value is passed as `unoptimized_checker=` to `format_dump_tree()`
when optimization ran, or `None` when `--no-optimize` was used.

### 5.3.4 — Parity + utility tests in `test_optimizer.py` (commit `fba0f1b`)

Added 33 new tests to `tests/test_optimizer.py`:

- **`count_nodes` / `count_modules` unit tests** (6 tests) — single node,
  parent+children, CSE sharing, modules-never-exceeds-nodes.
- **`dead_node` elimination tests** (4 tests) — prunes `_const_false=1`,
  prunes `_dead=true`, no-op on clean trees, `constant_fold` → `dead_node`
  round-trip.
- **`test_optimization_structural_parity`** (16 parametrized tests) —
  verifies for every fixture in `_PARITY_FIXTURES` that
  `count_nodes(opt) <= count_nodes(unopt)`,
  `count_modules(opt) <= count_modules(unopt)`, and `optimize` is idempotent.
- **`test_optimization_parity`** (`@pytest.mark.simulation`, 4 parametrized
  tests) — compiles both optimized and unoptimized checkers with Icarus
  Verilog and checks pass/fail sequences are identical under a generic
  20-cycle stimulus.

### 5.3.5 — `test_dump_tree.py` optimization summary tests + regression (commit `26f1165`)

Added 6 new unit tests:
- `test_dump_tree_no_unoptimized_checker_shows_disabled`
- `test_dump_tree_no_unoptimized_checker_shows_node_count`
- `test_dump_tree_with_unoptimized_checker_shows_optimization_line`
- `test_dump_tree_optimization_summary_format`
- `test_dump_tree_optimization_summary_shows_reduction`
- `test_dump_tree_no_unoptimized_not_shows_optimization_label`

And 3 new CLI integration tests (require slang):
- `test_cli_dump_tree_shows_optimization_summary`
- `test_cli_dump_tree_no_optimize_shows_disabled`

Fixed ruff lint issues (import ordering) introduced in task 5.3.4.

**Full regression result:** 508 passed, 17 skipped (slang/iverilog not
present in CI), 69 deselected (`@pytest.mark.simulation`).

## Files Modified

| File | Change |
|---|---|
| `src/sva2rtl/optimizer.py` | `dead_node()` implementation; `count_nodes()`, `count_modules()`, `_collect_module_names()` added |
| `src/sva2rtl/debug.py` | `format_dump_tree()` extended with `unoptimized_checker` param + summary section |
| `src/sva2rtl/cli.py` | Captures `unoptimized_checker` before `optimize()`; passes to `format_dump_tree()` |
| `tests/test_optimizer.py` | +33 tests: count utilities, dead_node, structural parity (×16), simulation parity (×4) |
| `tests/test_dump_tree.py` | +6 unit tests + 2 CLI tests for optimization summary |

## Commits

| Hash | Message |
|---|---|
| `fe9d30b` | feat(optimizer): implement dead_node elimination + count_nodes/count_modules utilities |
| `5391f08` | feat(debug): extend format_dump_tree with optimization summary stats |
| `38a2d12` | feat(cli): pass unoptimized_checker to format_dump_tree for --dump-tree |
| `fba0f1b` | test(optimizer): add parity, dead_node, and count utility tests |
| `26f1165` | test(dump_tree): add optimization summary tests + full regression pass |

## Design Decisions

- **`dead_node` dual-sentinel**: checks both `_dead="true"` (explicit) and
  `_const_false="1"` (set by `constant_fold`) so the two passes compose
  naturally without requiring additional plumbing.
- **`count_nodes` per-reference semantics**: consistent with the emitter's
  module instantiation model — a CSE-shared node that appears twice counts
  as 2 instantiation sites even though it's one module definition.
- **Optimization summary placement**: appended after the Composition Tree
  section (not before) so the primary debug content (IR + tree) is always
  visible at the top, stats at the bottom.
- **Simulation parity test skip**: simulation tests skip gracefully when
  `iverilog` is absent rather than failing, matching the existing pattern
  in `tests/simulation/conftest.py`.
