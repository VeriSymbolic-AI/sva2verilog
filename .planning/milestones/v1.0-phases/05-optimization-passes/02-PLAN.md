---
wave: 2
depends_on:
  - "01"
files_modified:
  - src/sva2rtl/optimizer.py
  - templates/seq_concat_top.sv.j2
  - tests/test_optimizer.py
requirements:
  - PIPE-03
  - PIPE-04
  - PIPE-05
autonomous: true
---

# Plan 5.2: CSE Deduplication + Counter Merging

## Goal

Implement the CSE (common subexpression elimination) and counter merging optimization passes. Structurally identical subtrees are deduplicated to share a single hardware module instance. Range counters with the same (M, N) parameters share a single counter module even when in different parent contexts. The emitter naturally handles shared nodes via the existing module_name dedup in `_emit_recursive`.

## Vertical Slice

After this plan: a property with two identical `##[2:5]` subsequences produces a single shared counter module in the generated RTL (PIPE-03). Two separate delay chains with the same parameters share a single counter module (PIPE-04). `--dump-tree` shows the deduplicated tree. All existing tests continue to pass.

---

## Tasks

<task id="5.2.1">
<title>Implement CSE pass with structural hash deduplication</title>
<read_first>
- src/sva2rtl/optimizer.py (current state after Plan 5.1)
- src/sva2rtl/composer.py lines 350-415 (structural_hash, _VOLATILE_PARAMS, compute_hash_map)
- src/sva2rtl/ir.py lines 175-244 (CheckerNode frozen dataclass, cse_origin field)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-05 through D-08: CSE decisions)
- .planning/phases/05-optimization-passes/05-RESEARCH.md section 2.3 (CSE algorithm)
</read_first>
<action>
Replace the `cse` stub in optimizer.py with full implementation:

1. `def cse(root: CheckerNode) -> CheckerNode` — top-level CSE orchestrator:
   a. Build hash groups: walk tree, compute structural_hash for every node, group by hash -> list of nodes
   b. Identify merge candidates: hash groups with 2+ members
   c. For each merge group: pick canonical representative, assign CSE canonical name `sva_cse_{template_name}_{semantic_params}` (e.g., sva_cse_concat_delay_2_5 from params delay_min and delay_max)
   d. Build replacement mapping: hash -> canonical CheckerNode (with CSE module_name, using dataclasses.replace)
   e. Rebuild tree top-down: for each node, if its hash is in the replacement map, substitute with the canonical CheckerNode. Use the SAME Python object for all occurrences (object identity sharing).
   f. Skip root node itself from CSE (root always stays unique)

2. Helper `def _build_hash_groups(node: CheckerNode) -> dict[str, list[CheckerNode]]`:
   - Recursive tree walk
   - Compute structural_hash for each node
   - Group into dict[hash -> [node, ...]]

3. Helper `def _cse_canonical_name(node: CheckerNode) -> str`:
   - Format: `sva_cse_{template_name}_{key_params}`
   - For concat_delay: `sva_cse_concat_delay_{delay_min}_{delay_max}`
   - For bool_expr: `sva_cse_bool_expr_{hash[:8]}` (use hash as disambiguator for complex expressions)
   - For rep_consecutive: `sva_cse_rep_consecutive_{rep_min}_{rep_max}`
   - For other templates: `sva_cse_{template_name}_{structural_hash}`

4. Helper `def _rebuild_with_cse(node: CheckerNode, canonical_map: dict[str, CheckerNode]) -> CheckerNode`:
   - Top-down tree rebuild
   - For each child: if child's structural_hash is in canonical_map, replace with the canonical CheckerNode object
   - Use dataclasses.replace() for parent nodes with updated children tuple
   - The canonical CheckerNode objects are shared (same id()) across the tree

5. Sanity check: after CSE, cross-reference cse_origin fields. If two nodes have the same cse_origin but different structural hashes, log a warning (indicates bug in named-sequence expansion). No hard failure — just diagnostic.

6. Collision protection (Risk 1 from research): after hash-based candidate identification, before merging, verify full structural equivalence by comparing template_name + sorted non-volatile params + recursive children. Only merge if truly identical.
</action>
<acceptance_criteria>
- `cse` function in optimizer.py is no longer a stub (contains real logic)
- Two CheckerNodes with identical template_name and params (but different module_name) are deduplicated after cse()
- The deduplicated nodes in the output tree have module_name starting with "sva_cse_"
- The deduplicated nodes are the SAME Python object (id(a) == id(b)) in the rebuilt tree
- Root node is never CSE-replaced (remains unique)
- A tree with no duplicates is returned unchanged (structurally)
- `mypy --strict src/sva2rtl/optimizer.py` exits 0
- `ruff check src/sva2rtl/optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.2.2">
<title>Implement counter_merge pass</title>
<read_first>
- src/sva2rtl/optimizer.py (current state after 5.2.1)
- src/sva2rtl/ir.py (CheckerNode: children tuple, params dict)
- templates/concat_delay.sv.j2 (counter params: delay_min, delay_max, cnt_width, clock_signal, clock_edge)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-09 through D-11: counter merge decisions)
- .planning/phases/05-optimization-passes/05-RESEARCH.md section 2.4 (counter merge algorithm)
</read_first>
<action>
Replace the `counter_merge` stub in optimizer.py with implementation:

1. `def counter_merge(root: CheckerNode) -> CheckerNode`:
   a. Collect all concat_delay nodes from the tree (recursive walk)
   b. Group by merge criterion: (delay_min, delay_max) tuple
   c. For groups with 2+ members that were NOT already handled by CSE (they still have different module_names — CSE might have already handled identical subtrees; counter_merge handles identical counters in different parent contexts)
   d. For each mergeable group: if the nodes have the same structural_hash, CSE already handled them. If they have DIFFERENT structural hashes (e.g., different observed_signals in parent), then counter_merge applies.
   e. Create a shared counter node with canonical name: `sva_cse_counter_{delay_min}_{delay_max}`
   f. Replace all instances of the merged counters with the shared node (same object identity)

2. Key distinction from CSE: counter_merge shares counters even when parent contexts differ. The shared counter's start signal will be OR'd at the parent level. However, for Phase 5 MVP, counter_merge operates post-CSE and catches cases where the counters themselves are identical but their subtrees aren't (because parents have different children).

3. Conservative approach for MVP: only merge counters that have identical structural hashes (which means CSE should have caught them). If CSE already handled them, counter_merge is a no-op for those. Counter_merge's value is primarily for cross-property sharing (D-11) where two separate top-level trees share a counter. For single-property trees (the common case in Phase 5), CSE handles it.

4. Implementation detail: walk all seq_concat_top nodes, look at their concat_delay children, and if any share the same structural hash but weren't unified by CSE (because they're in different root trees), unify them now.
</action>
<acceptance_criteria>
- `counter_merge` function in optimizer.py is no longer a stub
- Counter nodes with same (delay_min, delay_max) in different parent contexts share a single canonical module_name after counter_merge
- If CSE already deduplicated identical counters, counter_merge is a safe no-op (no double-processing)
- The pass does not modify counters that have different (delay_min, delay_max) values
- `mypy --strict src/sva2rtl/optimizer.py` exits 0
- `ruff check src/sva2rtl/optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.2.3">
<title>Fix instance name collisions in seq_concat_top template</title>
<read_first>
- templates/seq_concat_top.sv.j2 (current instance naming: u_{{ child.module_name }})
- .planning/phases/05-optimization-passes/05-RESEARCH.md section 4 (emitter integration: instance name uniqueness)
- .planning/phases/05-optimization-passes/05-CONTEXT.md (D-08: instance names use unique suffixes)
</read_first>
<action>
Modify `templates/seq_concat_top.sv.j2` to use indexed instance names that prevent collisions when CSE gives two children the same module_name:

1. Change instance name pattern from `u_{{ child.module_name }}` to `u_{{ child.module_name }}_{{ loop.index0 }}` in both the `{% if loop.first %}` and `{% else %}` blocks.

2. This ensures that if two children in the same seq_concat_top have the same module_name (after CSE deduplication), their instances are uniquely named: `u_sva_cse_concat_delay_2_5_0`, `u_sva_cse_concat_delay_2_5_1`.

3. The module DEFINITION is still emitted once (emitter dedup by module_name); only the INSTANCE names change.

4. NOTE: This changes golden file output for multi-module cases. Update the golden files that contain instance names. The affected golden files are those for seq_concat_top templates (sva_prop_*.sv). Regenerate these golden files using the test infrastructure.
</action>
<acceptance_criteria>
- `templates/seq_concat_top.sv.j2` uses `u_{{ child.module_name }}_{{ loop.index0 }}` for instance names
- Instance names in both `{% if loop.first %}` and `{% else %}` blocks use the indexed pattern
- Two children with the same module_name in a seq_concat_top produce unique instance names like `u_sva_cse_concat_delay_2_5_0` and `u_sva_cse_concat_delay_2_5_1`
- The template still compiles correctly for single-child cases (loop.index0 = 0)
</acceptance_criteria>
</task>

<task id="5.2.4">
<title>Unit tests for CSE and counter_merge passes</title>
<read_first>
- tests/test_optimizer.py (current state after Plan 5.1)
- src/sva2rtl/optimizer.py (current state with cse and counter_merge implemented)
- src/sva2rtl/composer.py lines 360-388 (structural_hash for verification)
- src/sva2rtl/ir.py (CheckerNode constructor)
</read_first>
<action>
Extend `tests/test_optimizer.py` with CSE and counter_merge tests:

1. CSE tests:
   - `test_cse_deduplicates_identical_subtrees`: Create a seq_concat_top with two children that have identical template_name="concat_delay" and same params (delay_min="2", delay_max="5"). After cse(), both children should be the same Python object (assert id(result.children[0]) == id(result.children[1]) or they share module_name starting with "sva_cse_").
   - `test_cse_preserves_non_duplicate_nodes`: Two children with different params are NOT merged.
   - `test_cse_canonical_naming`: After CSE, merged concat_delay nodes have module_name="sva_cse_concat_delay_2_5" (for delay_min=2, delay_max=5).
   - `test_cse_skips_root`: Root node's module_name is never replaced with CSE canonical name.
   - `test_cse_no_duplicates_identity`: Tree with all unique subtrees passes through CSE unchanged (structural_hash of result equals structural_hash of input).
   - `test_cse_deep_tree`: A tree with duplicates at depth 2+ correctly deduplicates the nested subtrees.

2. Counter merge tests:
   - `test_counter_merge_same_params`: Two concat_delay nodes with same (delay_min, delay_max) but different module_names are unified.
   - `test_counter_merge_different_params`: Two concat_delay nodes with different delay_min/delay_max are NOT merged.
   - `test_counter_merge_after_cse`: If CSE already unified nodes, counter_merge is a no-op (same structural hash in/out).

3. Integration test:
   - `test_cse_with_concat_merge`: Build a tree, run concat_merge then cse, verify the combined optimization reduces node count.
   - `test_full_optimize_with_duplicates`: Build tree with two identical subtrees, run optimize(), verify shared module_name in output.
</action>
<acceptance_criteria>
- At least 11 new test functions added to tests/test_optimizer.py
- `pytest tests/test_optimizer.py -v` exits 0 (all tests pass)
- CSE tests verify Python object identity sharing (id() comparison) or shared module_name
- CSE canonical naming test verifies "sva_cse_" prefix in module_name
- Counter merge tests cover both merge and no-merge cases
- `ruff check tests/test_optimizer.py` exits 0
- `mypy --strict tests/test_optimizer.py` exits 0
</acceptance_criteria>
</task>

<task id="5.2.5">
<title>Update golden files and regression validation</title>
<read_first>
- tests/golden/ (directory listing — understand which files use seq_concat_top instances)
- tests/test_golden_parity.py (how golden files are validated)
- templates/seq_concat_top.sv.j2 (after 5.2.3 changes — instance naming now indexed)
</read_first>
<action>
After the template instance name change (5.2.3), golden files for multi-module outputs need regeneration:

1. Identify affected golden files: any .sv file that contains instance declarations from seq_concat_top.sv.j2. These are the `sva_prop_*.sv` golden files (at minimum: sva_prop_81cf66e0.sv, sva_prop_e9edaa37.sv, sva_prop_5c9caf75.sv, sva_prop_75080d6b.sv).

2. Regenerate affected golden files by running the pipeline on their corresponding fixtures with --no-optimize flag (golden files represent unoptimized output per D-14). Write a helper script or pytest fixture that does: load fixture -> import -> normalize -> compose -> emit_all -> write golden.

3. Update golden files in tests/golden/ with the new indexed instance names (e.g., `u_sva_delay_3_3` becomes `u_sva_delay_3_3_1`).

4. Verify: `pytest tests/test_golden_parity.py -v` exits 0 with updated golden files.

5. Full regression: `pytest tests/ --timeout=120` all pass.

6. Simulation tests: if iverilog available, `pytest tests/simulation/ -m simulation` still pass (instance name change in RTL doesn't affect functional behavior).
</action>
<acceptance_criteria>
- `pytest tests/test_golden_parity.py -v` exits 0 (all golden files match)
- Affected golden files (sva_prop_*.sv) contain indexed instance names (`u_..._0`, `u_..._1`, etc.)
- `pytest tests/ --timeout=120` exits 0 (full regression pass)
- `mypy --strict src/sva2rtl/` exits 0
- `ruff check src/sva2rtl/ tests/` exits 0
- No functional behavior change (same pass/fail/active signals)
</acceptance_criteria>
</task>

---

## Verification

```bash
# CSE unit tests pass
pytest tests/test_optimizer.py -v -k "cse or counter"

# Golden parity with new instance names
pytest tests/test_golden_parity.py -v

# Full regression
pytest tests/ --timeout=120

# Type + lint
mypy --strict src/sva2rtl/
ruff check src/sva2rtl/ tests/
```

## must_haves

- [ ] CSE pass identifies and deduplicates structurally identical subtrees (PIPE-03)
- [ ] Deduplicated nodes share module_name with "sva_cse_" prefix
- [ ] Counter merge unifies same-parameter counters (PIPE-04)
- [ ] Instance names in seq_concat_top are unique (indexed) even with shared module_names
- [ ] All existing tests pass after golden file regeneration
- [ ] Emitter emits module definition once for shared nodes (existing dedup behavior)
