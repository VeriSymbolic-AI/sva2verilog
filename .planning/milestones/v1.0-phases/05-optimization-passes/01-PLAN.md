---
wave: 1
depends_on: []
files_modified:
  - src/sva2rtl/optimizer.py
  - src/sva2rtl/cli.py
  - tests/test_optimizer.py
requirements:
  - PIPE-03
  - PIPE-04
  - PIPE-05
autonomous: true
---

# Plan 5.1: Optimizer Framework + Constant Folding + Concat Merging

## Goal

Create the optimizer module with the pass orchestration framework, implement the first two passes (constant folding and concat merging), wire the `--no-optimize` CLI flag, and validate with unit tests. This establishes the optimization pipeline skeleton that Plans 5.2 and 5.3 extend.

## Vertical Slice

After this plan: `sva2rtl input.sv` runs the full pipeline including optimizer (constant_fold + concat_merge + stub passes); `--no-optimize` skips the optimizer entirely; adjacent fixed delays in a seq_concat_top are merged into a single delay node; constant boolean expressions are propagated.

---

## Tasks

<task id="5.1.1">
<title>Create optimizer.py with pass orchestration and constant_fold pass</title>
<read_first>
- src/sva2rtl/normalizer.py (pattern: pure tree transform module structure, imports, docstring)
- src/sva2rtl/ir.py (CheckerNode class: frozen=True, fields, params dict, children tuple)
- src/sva2rtl/composer.py lines 350-415 (structural_hash, compute_hash_map, _VOLATILE_PARAMS)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-01 through D-04: pass architecture decisions)
</read_first>
<action>
Create `src/sva2rtl/optimizer.py` with:

1. Module docstring following normalizer.py pattern: describes pass pipeline, guarantees (idempotent after convergence, semantics-preserving), pass ordering.

2. Public entry point: `def optimize(root: CheckerNode) -> CheckerNode` — orchestrates 5 passes in fixed order: constant_fold -> concat_merge -> cse -> counter_merge -> dead_node. Uses structural_hash(root) comparison for re-run detection (max 2 iterations per D-03). Imports structural_hash from sva2rtl.composer.

3. `def constant_fold(root: CheckerNode) -> CheckerNode` — bottom-up traversal using dataclasses.replace(). Rules:
   - If a child CheckerNode with template_name="bool_expr" has params["bool_expr"] matching a constant-true pattern ("1'b1", "1", "1'b1"), mark it as constant-true
   - If all children are constant-true in a seq_concat_top, the delay chain can be simplified (delay-only, no fail possible from bool checks)
   - For Phase 5 MVP: detect literal "1'b1" and "1'b0" in bool_expr params. Constant-false children are unreachable (set a flag for dead_node pass). Return tree unchanged if no constants found.

4. Stub functions for passes not yet implemented: `def cse(root: CheckerNode) -> CheckerNode: return root`, `def counter_merge(root: CheckerNode) -> CheckerNode: return root`, `def dead_node(root: CheckerNode) -> CheckerNode: return root`.

5. Helper: `def _walk_bottom_up(node: CheckerNode, fn: Callable[[CheckerNode], CheckerNode]) -> CheckerNode` — recursive bottom-up traversal that applies fn to each node after processing children, using dataclasses.replace() to create new nodes when children change.
</action>
<acceptance_criteria>
- File `src/sva2rtl/optimizer.py` exists
- `from sva2rtl.optimizer import optimize` succeeds (importable)
- `optimize` function signature is `def optimize(root: CheckerNode) -> CheckerNode`
- `constant_fold` function signature is `def constant_fold(root: CheckerNode) -> CheckerNode`
- `structural_hash` is imported from `sva2rtl.composer`
- `dataclasses.replace` is imported from stdlib `dataclasses`
- Stub passes `cse`, `counter_merge`, `dead_node` each return their input unchanged
- `optimize()` calls passes in order: constant_fold, concat_merge, cse, counter_merge, dead_node
- `optimize()` compares structural_hash before/after and breaks early if unchanged
- `optimize()` loops at most 2 iterations
- `mypy --strict src/sva2rtl/optimizer.py` exits 0
- `ruff check src/sva2rtl/optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.1.2">
<title>Implement concat_merge pass</title>
<read_first>
- src/sva2rtl/optimizer.py (the file just created in 5.1.1)
- src/sva2rtl/ir.py (CheckerNode fields: template_name, params, children)
- templates/seq_concat_top.sv.j2 (how children are wired in token-passing chain)
- templates/concat_delay.sv.j2 (delay params: delay_min, delay_max, cnt_width, clock_signal, clock_edge)
- .planning/phases/05-optimization-passes/05-RESEARCH.md section 2.2 (concat merge algorithm)
</read_first>
<action>
Implement `def concat_merge(root: CheckerNode) -> CheckerNode` in optimizer.py:

1. Walk tree bottom-up using _walk_bottom_up helper.

2. For each node with template_name="seq_concat_top": scan its children tuple for adjacent pairs where both have template_name="concat_delay". These are mergeable.

3. Merge logic: for adjacent concat_delay children at indices [i, i+1]:
   - Merged delay_min = int(children[i].params["delay_min"]) + int(children[i+1].params["delay_min"])
   - Merged delay_max = int(children[i].params["delay_max"]) + int(children[i+1].params["delay_max"])
   - Merged cnt_width = str(max(1, (merged_delay_max).bit_length())) — compute ceil(log2(max+1))
   - Create new CheckerNode with template_name="concat_delay", module_name=f"sva_delay_{merged_delay_min}_{merged_delay_max}", params with updated values, copy clock_signal/clock_edge from source
   - Replace the two adjacent children with the single merged child

4. Only merge concat_delay nodes that are DIRECTLY adjacent (no intervening bool_expr between them). Two concat_delay children at positions i, i+1 in the children tuple are directly adjacent.

5. Handle the case where three+ consecutive concat_delay children exist: merge greedily left-to-right (first pair merges, result then checks against next).

6. Rebuild the seq_concat_top node with the new (shorter) children tuple using dataclasses.replace().
</action>
<acceptance_criteria>
- `concat_merge` function exists in optimizer.py with signature `def concat_merge(root: CheckerNode) -> CheckerNode`
- A seq_concat_top with children=[concat_delay(3,3), concat_delay(2,2)] after concat_merge has one child concat_delay with params delay_min="5", delay_max="5"
- cnt_width is correctly recomputed: for delay_max=5, cnt_width="3" (since 5.bit_length()=3)
- Non-adjacent delays (with bool_expr between them) are NOT merged
- A single-child seq_concat_top is returned unchanged
- A tree with no seq_concat_top nodes is returned unchanged
- `mypy --strict src/sva2rtl/optimizer.py` exits 0
- `ruff check src/sva2rtl/optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.1.3">
<title>Wire --no-optimize flag into CLI pipeline</title>
<read_first>
- src/sva2rtl/cli.py (current state: main() function, click options, pipeline order)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-04: --no-optimize flag description, D-15: user-facing flag)
</read_first>
<action>
Modify `src/sva2rtl/cli.py`:

1. Add import at top: `from sva2rtl.optimizer import optimize`

2. Add click option before main function definition:
   ```
   @click.option("--no-optimize", is_flag=True, default=False, help="Skip optimization passes (emit unoptimized output)")
   ```

3. Add `no_optimize: bool` parameter to `def main(...)` signature (after dump_tree).

4. Insert optimizer call in the pipeline between compose() and the dump_tree/emit section:
   - After `checker_node = compose(node, clock, label, original_text)` line
   - Add: `if not no_optimize: checker_node = optimize(checker_node)`
   - This must come BEFORE the `if dump_tree:` block so that --dump-tree shows the optimized tree

5. Update module docstring pipeline order comment to include "optimize" step:
   `invoke_slang -> import_assertion -> normalize -> compose -> optimize -> emit -> write_output`
</action>
<acceptance_criteria>
- `src/sva2rtl/cli.py` contains `from sva2rtl.optimizer import optimize`
- `--no-optimize` flag appears in click option decorators as `is_flag=True, default=False`
- `main()` function signature includes `no_optimize: bool` parameter
- Pipeline calls `optimize(checker_node)` when `no_optimize` is False
- Pipeline skips `optimize()` when `no_optimize` is True
- `optimize()` call is positioned after `compose()` and before `if dump_tree:` block
- Module docstring mentions "optimize" in pipeline order
- `sva2rtl --help` output contains "--no-optimize" with help text "Skip optimization passes"
- `mypy --strict src/sva2rtl/cli.py` exits 0
- `ruff check src/sva2rtl/cli.py` exits 0
</acceptance_criteria>
</task>

<task id="5.1.4">
<title>Unit tests for constant_fold and concat_merge passes</title>
<read_first>
- src/sva2rtl/optimizer.py (current implementation from 5.1.1 and 5.1.2)
- tests/test_normalizer.py (pattern: helper factories, identity tests, rule-specific tests, idempotency)
- src/sva2rtl/ir.py (CheckerNode constructor fields and types)
- src/sva2rtl/composer.py lines 360-388 (structural_hash for verification)
</read_first>
<action>
Create `tests/test_optimizer.py` with:

1. Helper factories following test_normalizer.py pattern:
   - `_make_loc() -> SourceLoc` — returns SourceLoc(file="test.sv", line=1, col=1)
   - `_make_bool_checker(text: str, name: str) -> CheckerNode` — template_name="bool_expr", params with bool_expr=text, clock_signal="clk", clock_edge="posedge", module_name=name
   - `_make_delay_checker(delay_min: int, delay_max: int, name: str | None = None) -> CheckerNode` — template_name="concat_delay", computes cnt_width from delay_max.bit_length(), clock_signal="clk", clock_edge="posedge". Default name is f"sva_delay_{delay_min}_{delay_max}"
   - `_make_concat_top(children: tuple[CheckerNode, ...], name: str = "sva_top") -> CheckerNode` — template_name="seq_concat_top" wrapping children

2. Identity tests:
   - `test_optimize_single_bool_identity` — single bool_expr passes through unchanged
   - `test_optimize_no_concat_top_identity` — tree without seq_concat_top unchanged
   - `test_concat_merge_non_adjacent_identity` — bool_expr between two delays prevents merge

3. Constant fold tests:
   - `test_constant_fold_no_constants` — tree without literal booleans unchanged
   - `test_constant_fold_passes_through_normal_tree` — non-constant tree identity

4. Concat merge rule tests:
   - `test_concat_merge_two_adjacent_fixed_delays` — [delay(3,3), delay(2,2)] -> [delay(5,5)] with cnt_width="3"
   - `test_concat_merge_two_adjacent_range_delays` — [delay(1,3), delay(2,4)] -> [delay(3,7)] with cnt_width="3"
   - `test_concat_merge_three_adjacent_delays` — [delay(1,1), delay(2,2), delay(3,3)] -> [delay(6,6)]
   - `test_concat_merge_preserves_non_delay_children` — [bool, delay, bool] unchanged (bool_expr nodes NOT merged)
   - `test_concat_merge_partial_merge` — [delay(1,1), bool, delay(2,2), delay(3,3)] -> [delay(1,1), bool, delay(5,5)]

5. Idempotency tests:
   - `test_optimize_idempotent` — optimize(optimize(tree)) has same structural_hash as optimize(tree)

6. Integration test:
   - `test_optimize_full_pipeline_no_error` — load a fixture (delay_fixed.json), run normalize->compose->optimize, assert no exception, assert result is CheckerNode
</action>
<acceptance_criteria>
- File `tests/test_optimizer.py` exists
- `pytest tests/test_optimizer.py -v` exits 0 (all tests pass)
- At least 12 test functions exist in the file
- Tests import from `sva2rtl.optimizer` (optimize, constant_fold, concat_merge)
- Tests import `structural_hash` from `sva2rtl.composer` for idempotency check
- Each test function has a docstring
- `ruff check tests/test_optimizer.py` exits 0
- `mypy --strict tests/test_optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.1.5">
<title>Regression validation — existing test suite passes with optimizer in pipeline</title>
<read_first>
- src/sva2rtl/cli.py (after 5.1.3 changes)
- tests/test_golden_parity.py (current golden parity tests that must still pass)
- tests/test_cli.py (CLI tests that invoke main())
</read_first>
<action>
Run the full existing test suite (502+ tests) to verify that inserting the optimizer into the pipeline does not break anything:

1. Run `pytest tests/ -x --timeout=120` — all existing tests must pass.

2. If golden parity tests fail: the optimizer (constant_fold + concat_merge) is changing output for simple cases that should pass through unchanged. Fix the optimizer to be a no-op for cases without optimizable patterns:
   - Single bool_expr nodes have no children → nothing to fold/merge
   - seq_concat_top with non-adjacent delays → no merge
   - Verify _walk_bottom_up preserves node identity when no changes apply

3. If CLI tests fail: verify --no-optimize doesn't interfere with existing flags (--dump-tree, --output).

4. Ensure `mypy --strict src/sva2rtl/` exits 0 (full package type-check).

5. Ensure `ruff check src/sva2rtl/ tests/` exits 0 (full lint).
</action>
<acceptance_criteria>
- `pytest tests/ --timeout=120` exits 0 with 502+ tests passing
- `pytest tests/test_golden_parity.py -v` exits 0 (all golden files match byte-for-byte)
- `pytest tests/test_cli.py -v` exits 0
- `pytest tests/simulation/ -v -m simulation` exits 0 (or skip if iverilog unavailable)
- `mypy --strict src/sva2rtl/` exits 0
- `ruff check src/sva2rtl/ tests/` exits 0
- No existing golden files modified
</acceptance_criteria>
</task>

---

## Verification

```bash
# All unit tests pass
pytest tests/test_optimizer.py -v

# Full regression
pytest tests/ --timeout=120

# Type safety
mypy --strict src/sva2rtl/

# Lint
ruff check src/sva2rtl/ tests/

# CLI flag works
sva2rtl --help | grep "no-optimize"
```

## must_haves

- [ ] `optimizer.py` exists with `optimize()`, `constant_fold()`, `concat_merge()` public functions
- [ ] `--no-optimize` CLI flag wired and functional
- [ ] Adjacent fixed delays merged: ##3 ##2 -> ##5 (verified by test)
- [ ] Existing 502+ tests still pass (no regression)
- [ ] Optimizer is no-op for simple cases (golden parity preserved)
