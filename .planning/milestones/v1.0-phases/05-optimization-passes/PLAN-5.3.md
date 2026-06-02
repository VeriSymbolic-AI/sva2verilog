# Plan 5.3: Dead-Node Elimination + Parity Suite + Dump-Tree Summary

---
wave: 3
depends_on:
  - PLAN-5.2
files_modified:
  - src/sva2rtl/optimizer.py
  - src/sva2rtl/debug.py
  - src/sva2rtl/cli.py
  - tests/test_optimizer.py
  - tests/test_dump_tree.py
requirements:
  - PIPE-03
  - PIPE-04
  - PIPE-05
autonomous: true
---

## Goal

Complete the optimization pipeline: implement dead-node elimination (PIPE-05), add the `--dump-tree` node-count summary showing before/after optimization savings (D-13), and create the full parity test suite proving that optimized output is semantically identical to unoptimized output for all golden test cases (D-12).

## Vertical Slice

After this plan: the optimization pipeline is complete (all 5 passes functional). `--dump-tree` reports `Optimization: Nodes: X -> Y (-Z%), Modules: A -> B (-C%)`. All golden fixtures produce identical simulation traces whether optimized or not (parity proven). Dead/unreachable nodes are pruned from emitted output. Phase 5 success criteria are fully met.

---

## Tasks

<task id="5.3.1">
<title>Implement dead_node elimination pass</title>
<read_first>
- src/sva2rtl/optimizer.py (current state after Plan 5.2)
- src/sva2rtl/ir.py (CheckerNode: children tuple is the only child reference mechanism)
- .planning/phases/05-optimization-passes/05-RESEARCH.md section 2.5 (dead node algorithm)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-03: dead_node runs last)
</read_first>
<action>
Replace the `dead_node` stub in optimizer.py with implementation:

1. `def dead_node(root: CheckerNode) -> CheckerNode`:
   - Since the tree is rebuilt fresh by each prior pass (all passes construct new trees), unreachable nodes are naturally garbage-collected by Python. There are no explicit "dead references" in the tree.
   - The primary role of dead_node is:
     a. **Verification**: walk the tree from root, collect all reachable node module_names. Assert the set is consistent (no orphans could exist in a fresh tree, but validate).
     b. **Pruning constant-false branches**: if constant_fold marked any subtree as unreachable (via a sentinel param like `_dead=true`), remove those children from their parents.
     c. **Return**: the tree with dead branches removed. For trees where no dead branches exist (the common case), return root unchanged.

2. Implementation approach:
   - Walk tree top-down from root
   - For each node, filter children: keep only children that are NOT marked as dead (check for params.get("_dead") == "true")
   - If children changed, rebuild node with dataclasses.replace(node, children=filtered_children)
   - This is the integration point with constant_fold: constant_fold sets `_dead=true` on unreachable subtrees, dead_node removes them.
   - For Phase 5 MVP: since constant_fold's constant detection is minimal (only literal 1'b0/1'b1), dead_node will rarely fire. Its main value is the structural guarantee and the node-counting utility.

3. Add counting utilities (public, used by debug.py):
   - `def count_nodes(root: CheckerNode) -> int`: recursive count of all nodes in tree (counting each traversal occurrence, so shared nodes counted once per parent reference)
   - `def count_modules(root: CheckerNode) -> int`: count unique module_names in tree (= number of .sv files emitted)
   - Helper `def _collect_module_names(node: CheckerNode, seen: set[str]) -> None`
</action>
<acceptance_criteria>
- `dead_node` function in optimizer.py is no longer a stub
- `count_nodes(root)` correctly counts all nodes in tree (leaf = 1, parent = 1 + sum of children counts)
- `count_modules(root)` correctly counts unique module_name values in tree
- A tree with no dead branches passes through dead_node unchanged
- A tree where a child has params["_dead"] == "true" has that child removed after dead_node
- `from sva2rtl.optimizer import count_nodes, count_modules` succeeds
- `mypy --strict src/sva2rtl/optimizer.py` exits 0
- `ruff check src/sva2rtl/optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.3.2">
<title>Extend format_dump_tree with optimization node-count summary</title>
<read_first>
- src/sva2rtl/debug.py (current format_dump_tree function, _format_checker recursive walk)
- src/sva2rtl/optimizer.py (count_nodes, count_modules from 5.3.1)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-13: summary format, D-04: --no-optimize shows unoptimized count only)
- .planning/phases/05-optimization-passes/05-PATTERNS.md section 4 (Pattern B: extending output)
</read_first>
<action>
Modify `src/sva2rtl/debug.py`:

1. Add import: `from sva2rtl.optimizer import count_nodes, count_modules`

2. Update `format_dump_tree` signature to accept optional unoptimized checker:
   ```
   def format_dump_tree(
       ir_node: SVANode,
       checker: CheckerNode,
       hash_map: dict[str, str],
       *,
       unoptimized_checker: CheckerNode | None = None,
   ) -> str:
   ```

3. At the bottom of format_dump_tree, after the Composition Tree section, add the optimization summary:
   - If `unoptimized_checker is not None` (optimization was applied):
     - Compute before_nodes = count_nodes(unoptimized_checker)
     - Compute after_nodes = count_nodes(checker)
     - Compute before_mods = count_modules(unoptimized_checker)
     - Compute after_mods = count_modules(checker)
     - Compute pct_nodes = round((1 - after_nodes / before_nodes) * 100) if before_nodes > 0 else 0
     - Compute pct_mods = round((1 - after_mods / before_mods) * 100) if before_mods > 0 else 0
     - Append blank line + summary: `f"Optimization: Nodes: {before_nodes} -> {after_nodes} (-{pct_nodes}%), Modules: {before_mods} -> {after_mods} (-{pct_mods}%)"`
   - If `unoptimized_checker is None` (--no-optimize was used or optimization skipped):
     - Append: `f"Nodes: {count_nodes(checker)} (optimization disabled)"`

4. Ensure existing callers still work (keyword-only argument with default None means backward compatible).
</action>
<acceptance_criteria>
- `format_dump_tree` signature includes `*, unoptimized_checker: CheckerNode | None = None` keyword-only parameter
- When unoptimized_checker is provided: output ends with line matching pattern `Optimization: Nodes: \d+ -> \d+ \(-\d+%\), Modules: \d+ -> \d+ \(-\d+%\)`
- When unoptimized_checker is None: output ends with line matching `Nodes: \d+ \(optimization disabled\)`
- Existing call sites (without unoptimized_checker) still work without changes (backward compatible)
- `from sva2rtl.optimizer import count_nodes, count_modules` import appears in debug.py
- `mypy --strict src/sva2rtl/debug.py` exits 0
- `ruff check src/sva2rtl/debug.py` exits 0
</acceptance_criteria>
</task>

<task id="5.3.3">
<title>Update CLI to pass unoptimized_checker to format_dump_tree</title>
<read_first>
- src/sva2rtl/cli.py (current state after Plan 5.1)
- src/sva2rtl/debug.py (after 5.3.2 changes — new format_dump_tree signature)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-04: --dump-tree shows before/after; D-15: --no-optimize)
</read_first>
<action>
Modify `src/sva2rtl/cli.py` to capture the unoptimized checker_node for the dump_tree summary:

1. After compose() and before optimize(), save the unoptimized tree:
   ```
   checker_node = compose(node, clock, label, original_text)
   unoptimized_checker = checker_node  # save for --dump-tree summary
   if not no_optimize:
       checker_node = optimize(checker_node)
   ```

2. Update the dump_tree block to pass unoptimized_checker:
   ```
   if dump_tree:
       from sva2rtl.composer import compute_hash_map
       from sva2rtl.debug import format_dump_tree

       hash_map = compute_hash_map(checker_node)
       click.echo(format_dump_tree(
           raw_node,
           checker_node,
           hash_map,
           unoptimized_checker=unoptimized_checker if not no_optimize else None,
       ))
       sys.exit(0)
   ```

3. When --no-optimize is active: pass `unoptimized_checker=None` so debug.py shows the "optimization disabled" message.

4. When optimization is active: pass the saved pre-optimization checker so debug.py can compute before/after metrics.
</action>
<acceptance_criteria>
- CLI saves `unoptimized_checker = checker_node` before optimization step
- `format_dump_tree()` call includes `unoptimized_checker=` keyword argument
- When `--no-optimize` is used with `--dump-tree`: output contains "optimization disabled"
- When `--dump-tree` is used without `--no-optimize`: output contains "Optimization: Nodes:"
- `mypy --strict src/sva2rtl/cli.py` exits 0
- `ruff check src/sva2rtl/cli.py` exits 0
</acceptance_criteria>
</task>

<task id="5.3.4">
<title>Parity test suite — optimized vs unoptimized simulation comparison</title>
<read_first>
- tests/test_optimizer.py (current state after Plan 5.2)
- tests/simulation/tb_generator.py (generate_testbench, run_simulation, extra_inputs_from_checker)
- tests/simulation/test_sim_delay.py (pattern: _build_checker, _run_stimulus)
- tests/test_golden_parity.py (pattern: _load fixture, run pipeline, compare)
- src/sva2rtl/optimizer.py (optimize function)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-12: full simulation parity, D-14: golden files unchanged)
</read_first>
<action>
Add parity tests to `tests/test_optimizer.py`:

1. Import simulation infrastructure:
   - `from tests.simulation.tb_generator import extra_inputs_from_checker, generate_testbench, run_simulation`
   - `from sva2rtl.emitter import emit_all`

2. Add parity helper function `_run_pipeline_with_flag(fixture_name: str, *, optimize_flag: bool) -> CheckerNode`:
   - Load fixture from tests/fixtures/
   - Run import_assertion -> normalize -> compose
   - If optimize_flag: run optimize()
   - Return the CheckerNode

3. Add parity simulation helper `_simulate_checker(checker: CheckerNode, stimulus: list[dict], tmp_path: Path) -> list[dict]`:
   - emit_all(checker) -> modules
   - extra_inputs_from_checker(checker) -> extra_inputs
   - generate_testbench(...) -> tb
   - run_simulation(...) -> results
   - Return results

4. Parametrized parity test over all applicable fixtures:
   ```
   _PARITY_FIXTURES = [
       "bool_simple.json",
       "bool_labeled.json",
       "delay_fixed.json",
       "delay_range.json",
       "delay_zero.json",
       "delay_three_element.json",
       "rose.json",
       "fell.json",
       "stable.json",
       "past.json",
       "rep_fixed.json",
       "rep_range.json",
       "disable_iff.json",
       "implication_overlap.json",
       "implication_nonoverlap.json",
       "implication_bitvec.json",
   ]
   ```

5. Test function `test_optimization_parity(fixture_name, tmp_path)`:
   - Mark with `@pytest.mark.simulation` (skips if iverilog unavailable)
   - Build checker_unopt = _run_pipeline_with_flag(fixture, optimize_flag=False)
   - Build checker_opt = _run_pipeline_with_flag(fixture, optimize_flag=True)
   - Generate stimulus: 20 cycles with randomized signal patterns (use deterministic seed)
   - Simulate both
   - Assert cycle-by-cycle: pass, fail, active, attempt_fired match between unopt and opt

6. Non-simulation parity test `test_optimization_structural_parity(fixture_name)`:
   - For all fixtures: verify that optimize() doesn't raise any exceptions
   - Verify the optimized tree still has a valid root with template_name, module_name, params
   - Verify count_nodes(optimized) <= count_nodes(unoptimized) (optimization never ADDS nodes)
</action>
<acceptance_criteria>
- `tests/test_optimizer.py` contains `test_optimization_parity` parametrized test
- `test_optimization_parity` is marked with `@pytest.mark.simulation`
- At least 16 fixture files listed in _PARITY_FIXTURES
- Parity tests compare cycle-by-cycle simulation output between optimized and unoptimized
- `test_optimization_structural_parity` verifies count_nodes(opt) <= count_nodes(unopt) for all fixtures
- `pytest tests/test_optimizer.py -v -k "not simulation"` exits 0 (non-sim tests pass)
- `pytest tests/test_optimizer.py -v -m simulation` exits 0 if iverilog available (sim parity passes)
- `ruff check tests/test_optimizer.py` exits 0
- `mypy --strict tests/test_optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.3.5">
<title>Update dump_tree tests and full regression validation</title>
<read_first>
- tests/test_dump_tree.py (existing dump_tree tests)
- src/sva2rtl/debug.py (after 5.3.2 changes)
- src/sva2rtl/cli.py (after 5.3.3 changes)
- tests/test_optimizer.py (after 5.3.4)
</read_first>
<action>
1. Update `tests/test_dump_tree.py` with new tests for the optimization summary:
   - `test_dump_tree_with_optimization_summary`: Call format_dump_tree with unoptimized_checker parameter. Assert output contains "Optimization: Nodes:" with numeric values.
   - `test_dump_tree_optimization_disabled`: Call format_dump_tree with unoptimized_checker=None. Assert output contains "optimization disabled".
   - `test_dump_tree_node_count_accuracy`: Build a known tree (e.g., 5 nodes), pass to format_dump_tree, verify the node count matches expected value of 5.

2. Run full regression:
   - `pytest tests/ --timeout=120` — all tests pass
   - `pytest tests/test_golden_parity.py -v` — golden files match
   - `pytest tests/test_dump_tree.py -v` — dump tree tests pass
   - `pytest tests/test_optimizer.py -v -k "not simulation"` — optimizer tests pass

3. Run type check and lint:
   - `mypy --strict src/sva2rtl/` exits 0
   - `ruff check src/sva2rtl/ tests/` exits 0

4. Verify Phase 5 success criteria from ROADMAP:
   - Success criterion 1: "Two identical ##[2:5] subsequences produce single shared counter" — verified by test_cse_deduplicates_identical_subtrees
   - Success criterion 2: "--dump-tree reports reduced node count" — verified by test_dump_tree_with_optimization_summary
   - Success criterion 3: "All Phase 1-4 simulation oracle tests pass on optimized output" — verified by test_optimization_parity
   - Success criterion 4: "Dead-state nodes pruned" — verified by dead_node pass logic + test
</action>
<acceptance_criteria>
- `tests/test_dump_tree.py` contains at least 3 new test functions for optimization summary
- `pytest tests/test_dump_tree.py -v` exits 0
- `pytest tests/ --timeout=120` exits 0 with 520+ tests passing (502 existing + new)
- `pytest tests/test_golden_parity.py -v` exits 0 (golden files match)
- `mypy --strict src/sva2rtl/` exits 0
- `ruff check src/sva2rtl/ tests/` exits 0
- `--dump-tree` output includes optimization node/module count summary line
- All Phase 5 success criteria from ROADMAP are met
</acceptance_criteria>
</task>

---

## Verification

```bash
# Dead node unit tests
pytest tests/test_optimizer.py -v -k "dead_node"

# Dump tree summary tests
pytest tests/test_dump_tree.py -v

# Parity suite (non-simulation)
pytest tests/test_optimizer.py -v -k "structural_parity"

# Parity suite (simulation, requires iverilog)
pytest tests/test_optimizer.py -v -m simulation

# Full regression
pytest tests/ --timeout=120

# Type + lint
mypy --strict src/sva2rtl/
ruff check src/sva2rtl/ tests/

# CLI integration
sva2rtl --dump-tree tests/sv_fixtures/delay_assert.sv 2>/dev/null | grep "Optimization:"
sva2rtl --no-optimize --dump-tree tests/sv_fixtures/delay_assert.sv 2>/dev/null | grep "disabled"
```

## must_haves

- [ ] dead_node pass removes unreachable/dead branches from tree (PIPE-05)
- [ ] count_nodes() and count_modules() utility functions exported from optimizer.py
- [ ] `--dump-tree` shows "Optimization: Nodes: X -> Y (-Z%), Modules: A -> B (-C%)" summary
- [ ] `--no-optimize --dump-tree` shows "Nodes: X (optimization disabled)"
- [ ] Parity proven: optimized output produces identical simulation traces as unoptimized for all fixtures
- [ ] All existing tests (520+) pass without modification
- [ ] Phase 5 success criteria (from ROADMAP) fully satisfied
