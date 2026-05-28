# Phase 5: Optimization Passes - Research

**Date:** 2026-05-28
**Purpose:** What do I need to know to PLAN this phase well?
**Requirements:** PIPE-03 (CSE), PIPE-04 (counter merging), PIPE-05 (dead-state elimination)

---

## 1. Existing Codebase State

### 1.1 What Already Exists (Reusable Assets)

| Asset | Location | Relevance |
|-------|----------|-----------|
| `structural_hash()` | `composer.py:360-388` | SHA-256 hash excluding volatile params (module_name, source_loc, sva2rtl_version, original_text). Returns 8-char hex. **Directly usable for CSE candidate detection.** |
| `compute_hash_map()` | `composer.py:391-415` | Walks tree → `{module_name: hash}`. Building block for dedup-map. |
| `_VOLATILE_PARAMS` | `composer.py:355-357` | `frozenset({"module_name", "source_loc", "sva2rtl_version", "original_text"})` — defines what doesn't affect semantic equivalence. |
| `CheckerNode` | `ir.py:175-244` | Frozen dataclass. Has `cse_origin: str | None` field. Custom `__hash__`/`__eq__` include `module_name` (so Python object identity != structural equivalence). |
| `normalize()` | `normalizer.py` | Pattern to follow: pure transform, bottom-up single pass, match/case dispatch. 180 lines. |
| `emit_all()` → `_emit_recursive()` | `emitter.py:106-151` | Already deduplicates by `module_name` (seen-set on `results` dict). **Phase 5 CSE can leverage this** — if two CheckerNodes share `module_name`, emitter emits once. |
| `format_dump_tree()` | `debug.py` | Currently shows IR + CheckerNode tree. Must extend with node count summary. |
| Behavioral oracle | `behavioral_oracle.py` | Full cycle-exact reference implementation. Reuse for parity tests. |
| Simulation harness | `tests/simulation/` | Icarus compilation + run infrastructure. 43 tests across 8 test files. |
| Golden parity tests | `tests/test_golden_parity.py` | 16 tests covering 29+ golden files. Pattern for regression. |

### 1.2 Integration Points (Files to Modify)

| File | Change |
|------|--------|
| `cli.py` (95 lines) | Add `--no-optimize` flag. Insert `optimize(checker_node)` call between `compose()` and emit. |
| `emitter.py` (225 lines) | `_emit_recursive()` already deduplicates by `module_name`. If CSE renames shared nodes to the same `module_name`, emitter handles it automatically. May need to detect `id()`-based sharing for nodes with different module_names pointing to same hardware. |
| `debug.py` (149 lines) | Add node count summary line at bottom of `format_dump_tree()` output. |
| `composer.py` (829 lines) | No changes needed — `structural_hash()` already works. |
| `normalizer.py` (180 lines) | No changes needed. |

### 1.3 Key Architectural Constraint

The `CheckerNode.module_name` is used by the emitter as the deduplication key (`_emit_recursive` uses `if checker.module_name not in results`). CSE MUST ensure that structurally-identical nodes get the SAME `module_name` (the CSE canonical name like `sva_cse_concat_delay_2_5`) so the emitter naturally emits the `.sv` file once and instantiates it multiple times.

However, `CheckerNode` is frozen — so CSE cannot mutate nodes. It must build a new tree where shared subtrees are replaced with new `CheckerNode` instances that have the CSE canonical `module_name`.

---

## 2. Algorithm Design for Each Pass

### 2.1 Constant Folding (`constant_fold`)

**What it does:** Propagates known-true and known-false boolean expressions through the tree.

**Rules:**
- `BoolExpr("1'b1")` or similar always-true → can simplify parent operators
- `BoolExpr("1'b0")` or similar always-false → can eliminate dead branches
- A delay connected to a constant-true check is effectively just a delay (no fail possible from that check)

**Implementation approach:**
- Walk tree bottom-up
- Identify constant boolean leaf nodes by pattern matching on `params["bool_expr"]`
- For Phase 5 scope: focus on trivial cases (literal 1/0). Complex constant analysis is v2.
- Return new tree with constants propagated (or original if no change)

**Complexity:** Low. Most real SVA properties don't contain literal constants, but this pass ensures the pipeline handles edge cases and enables subsequent passes.

### 2.2 Concat Merging (`concat_merge`)

**What it does:** Merges adjacent fixed delays into a single combined delay.

**Example:** `##3` followed immediately by `##2` in the CheckerNode tree → single `##5` delay node.

**Detection criterion:** Two consecutive children in a `seq_concat_top` that are both `concat_delay` template nodes, connected directly (no bool_expr check between them).

**Implementation approach:**
- Walk tree, find `seq_concat_top` nodes
- Scan children list for adjacent `concat_delay` nodes
- Merge: `delay_min = d1_min + d2_min`, `delay_max = d1_max + d2_max`
- Rebuild parent with merged delay and reduced children list
- Recalculate `cnt_width` for the merged delay

**Constraint:** Only merge when delays are directly adjacent in the token chain (no intervening bool_expr). The normalizer's `_flatten_concat` already spliced nested SeqConcats, so adjacent delays in the CheckerNode tree are genuine candidates.

**Complexity:** Medium. Must correctly handle the token-passing wiring after merging (the merged delay's `pass` connects to the next element's `start`).

### 2.3 CSE Deduplication (`cse`)

**What it does:** Identifies subtrees with identical structural hashes and replaces duplicates with references to a single shared instance.

**Algorithm:**
1. Walk tree bottom-up, compute `structural_hash()` for every node
2. Build hash → first-occurrence-node mapping
3. Walk tree again top-down, building a new tree:
   - For each node, compute its hash
   - If hash seen before: replace with a new CheckerNode having the CSE canonical name (`sva_cse_{template}_{params}`)
   - The replacement node is the SAME Python object as the canonical instance (object identity sharing)
4. The emitter's seen-set (`id()`) detects shared objects and emits module definition once

**Key insight from D-07:** CSE builds an entirely NEW tree. Duplicate subtrees point to the same Python `CheckerNode` object. The emitter detects shared references via `id()` in a seen-set and emits the module `.sv` file only once.

**Naming (D-08):** `sva_cse_{template}_{params}` e.g., `sva_cse_concat_delay_2_5`

**Verification (D-05):** After hash-based CSE, cross-check against `cse_origin` tags. Nodes with the same `cse_origin` should have matching structural hashes. Log a warning if they don't (indicates a bug in named-sequence expansion).

**Implementation detail:** Since `CheckerNode` is frozen, we must construct new nodes with updated `module_name`. Use `dataclasses.replace()` (which works with frozen dataclasses by creating a new instance).

**Critical edge case:** Two nodes with the same structural hash but different `observed_signals` or different positions in the hierarchy. The structural hash already excludes `module_name` and `source_loc`, so two `concat_delay` nodes with identical `(delay_min, delay_max, cnt_width, clock_signal, clock_edge)` will hash identically. The parent's instantiation wiring must still connect the right signals — this is handled by the parent template, not the child module itself.

### 2.4 Counter Merging (`counter_merge`)

**What it does:** Shares a single counter module across multiple consumers that need the same `(M, N)` delay window.

**Criterion (D-09):** Same `(delay_min, delay_max)` parameters AND same template type (`concat_delay`). Signal inputs may differ.

**How it differs from CSE:** CSE merges entire subtrees that are structurally identical (including children). Counter merging is more aggressive — it shares just the counter hardware even when the consumers (parent nodes) are different. Multiple properties can share one timer.

**Wiring (D-10):** Single `start` input = OR of all consumer start signals. Shared `pass` output broadcasts to all consumers simultaneously. Works because merged counters have identical M,N windows.

**Cross-property sharing (D-11):** Allowed within the same file. Two separate properties with `##[2:5]` share a single counter.

**Implementation:**
1. After CSE pass, collect all remaining `concat_delay` nodes
2. Group by `(delay_min, delay_max)` — same group = merge candidates
3. If a group has >1 member: create one shared counter node, wire OR-start from all parents
4. This may require adjusting the parent `seq_concat_top` templates to reference the shared counter

**Note:** In practice, after CSE, many identical counters will already be deduplicated. Counter merging catches the case where the COUNTERS are identical but their PARENT context differs (so CSE couldn't merge the whole subtree).

### 2.5 Dead-Node Elimination (`dead_node`)

**What it does:** Prunes unreachable nodes from the CheckerNode tree.

**Algorithm:**
1. Start from root node
2. BFS/DFS traversal marking all reachable nodes (via `children` edges)
3. Any node in the original tree not reachable from root is dead
4. Rebuild tree with only reachable nodes

**When dead nodes appear:**
- After CSE merges subtrees, some original nodes may become unreferenced
- After constant folding removes branches
- After concat merging collapses delay chains

**Implementation:** Simple reachability from root. Since `CheckerNode.children` is the only way to reference children, and we're building a new tree in each pass, unreachable nodes are naturally garbage-collected by Python. The dead-node pass is primarily a **verification pass** — it counts nodes before/after to report savings and ensures no orphans exist.

**Practical note:** If the tree is rebuilt correctly in earlier passes (new tree, shared references), dead nodes are already gone. This pass's main value is:
1. Sanity check (assert no orphans)
2. Node-count reporting for `--dump-tree`
3. Catching edge cases where a pass incorrectly preserves dead references

---

## 3. Pass Ordering Rationale

```
constant_fold → concat_merge → cse → counter_merge → dead_node
```

**Why this order (D-03):**
1. **constant_fold first:** Simplifies expressions, potentially making more subtrees structurally identical
2. **concat_merge second:** Reduces number of delay nodes (##3 ##2 → ##5), making fewer unique nodes for CSE to compare
3. **cse third:** With the simplified tree, maximum opportunities for hash-based deduplication
4. **counter_merge fourth:** After CSE, catches remaining counter-sharing opportunities that CSE missed (identical counters in different parent contexts)
5. **dead_node last:** Cleans up anything left unreachable by earlier passes

**Re-run logic (D-03):** After all 5 passes complete, compare `structural_hash(root)` before vs. after. If different, run the full pipeline once more (max 2 total iterations). This catches cascading opportunities (e.g., CSE exposes new dead nodes, which after removal might expose new CSE opportunities on the next iteration).

---

## 4. Emitter Integration for Shared Nodes

### Current Emitter Behavior

`_emit_recursive()` in `emitter.py` already deduplicates by `module_name`:
```python
if checker.module_name not in results:
    _emit_recursive(child, env, results)
```

### What CSE Needs

After CSE, shared nodes will have the same `module_name` (e.g., `sva_cse_concat_delay_2_5`). When the emitter walks the tree and encounters the same `module_name` multiple times, it:
1. Renders the `.sv` module definition ONCE (first encounter)
2. Each parent that instantiates this shared module uses the same `module_name` in its `u_<name>` instance declaration

**No emitter changes needed if CSE correctly assigns identical `module_name` values to shared nodes.** The existing `module_name` dedup handles it.

However, there's a subtlety: parent templates iterate over `children` to generate instance wiring. If the same Python object appears in multiple parents' `children` tuples, each parent will generate its own instance declaration (different instance name `u_<name>_<idx>`) pointing to the same module. This is correct RTL behavior.

### Instance Name Uniqueness

Per D-08: shared modules get CSE-prefixed canonical name. Instance names use unique suffixes. The parent template must generate unique instance names even when the module_name is the same. Current templates use patterns like `u_{module_name}` — this needs suffix disambiguation when the same module appears multiple times in one parent's children.

---

## 5. Testing Strategy

### 5.1 Parity Testing (D-12, D-14)

**Core principle:** Run the full simulation oracle on BOTH optimized AND unoptimized output for every golden test case. Compare cycle-by-cycle. Any divergence = hard failure.

**Implementation:**
```python
def test_optimization_parity(fixture, tmp_path):
    # Build unoptimized checker
    checker_unopt = pipeline(fixture, optimize=False)
    # Build optimized checker  
    checker_opt = pipeline(fixture, optimize=True)
    # Run simulation on both
    results_unopt = simulate(checker_unopt, stimulus, tmp_path)
    results_opt = simulate(checker_opt, stimulus, tmp_path)
    # Compare cycle-by-cycle
    assert results_unopt == results_opt
```

**Test cases:** All existing golden test fixtures (20+ cases covering bool, delay, implication, repetition, signal functions, disable_iff).

### 5.2 Unit Tests per Pass

- `test_constant_fold`: literal true/false propagation
- `test_concat_merge`: adjacent delay merging (##3 ##2 → ##5)
- `test_cse`: duplicate subtree detection and sharing
- `test_counter_merge`: same-parameter counter sharing
- `test_dead_node`: orphan removal after other passes

### 5.3 Node Count Reporting (D-13)

Verify that `--dump-tree` includes the summary line:
```
Optimization: Nodes: 12 -> 8 (-33%), Modules: 7 -> 5 (-29%)
```

### 5.4 `--no-optimize` Flag (D-15)

Test that:
- With `--no-optimize`: output matches unoptimized pipeline (compose → emit, no optimizer)
- Without flag: output passes parity test against unoptimized

---

## 6. Technical Risks & Mitigations

### Risk 1: Structural Hash Collisions

**Risk:** Two semantically different nodes produce the same 8-char hex hash (32-bit collision space = ~65K nodes before birthday collision becomes likely).

**Mitigation:** After hash-based CSE candidate identification, perform a full structural comparison (template_name + all non-volatile params + recursive child comparison) before merging. Hash is a fast filter; full comparison is the correctness gate.

### Risk 2: CSE Breaking Parent Wiring

**Risk:** When CSE replaces a subtree with a shared instance, the parent's signal wiring (observed_signals) may reference the old child's ports incorrectly.

**Mitigation:** CSE only shares nodes that are structurally identical — including `observed_signals`. The parent template generates wiring based on the child's `observed_signals` tuple, which is identical for structurally-equivalent nodes. No wiring breakage.

### Risk 3: Counter Merge OR-Start Fanout

**Risk:** The OR-start approach (`assign shared_start = s1 | s2 | ...`) could cause timing issues in deeply shared counters or violate the semantics when one consumer resets while another is active.

**Mitigation:** Counter merge only applies when counters have identical `(M, N)` — they have the same lifetime. The OR-start fires the counter on ANY consumer's trigger. Since all consumers expect the same window, a single counter timeline serves all of them. Each consumer independently checks its own condition in the accept window. The counter doesn't "reset" — it starts a new countdown on each OR-start pulse.

**Important caveat:** If a counter is already running when another OR-start fires, we need overlapping threads — this is the same problem solved by the bit-vector approach in `|->`. For counters used in delay chains (fire-and-forget, no overlap), OR-start is safe. For counters that might have overlapping activations, counter merge must be more conservative or reuse the bit-vector tracking pattern.

### Risk 4: Frozen Dataclass Reconstruction Cost

**Risk:** Building an entirely new tree for each pass (5 passes + potential re-run) could be slow for large trees.

**Mitigation:** CheckerNode trees for real SVA properties are small (typically <100 nodes for even complex assertions). Python object creation is fast for this scale. No performance concern for v1.

### Risk 5: Instance Name Collision After CSE

**Risk:** Two children in the same parent get the same CSE module_name → instance name collision in the emitted RTL.

**Mitigation:** Instance names should include a positional index: `u_sva_cse_concat_delay_2_5_0`, `u_sva_cse_concat_delay_2_5_1`. The parent template's `{% for child in children %}` loop provides the index.

---

## 7. Node Counting for `--dump-tree`

### What to Count

- **Nodes:** Total `CheckerNode` instances in the tree (counting shared references multiple times for "logical size", or once for "physical size")
- **Modules:** Unique `module_name` values (= number of `.sv` files emitted)

### Summary Format (D-13)

```
Optimization: Nodes: 12 -> 8 (-33%), Modules: 7 -> 5 (-29%)
```

When `--no-optimize` is used, show unoptimized count only:
```
Nodes: 12 (optimization disabled)
```

### Implementation

```python
def count_nodes(root: CheckerNode) -> int:
    """Count total logical nodes in tree (shared refs counted once per occurrence)."""
    count = 1
    for child in root.children:
        count += count_nodes(child)
    return count

def count_modules(root: CheckerNode) -> int:
    """Count unique module definitions needed."""
    seen: set[str] = set()
    _collect_module_names(root, seen)
    return len(seen)
```

---

## 8. CLI Integration

### `--no-optimize` Flag

```python
@click.option('--no-optimize', is_flag=True, default=False,
              help='Skip optimization passes (emit unoptimized output)')
```

### Pipeline Update

```python
# In main():
checker_node = compose(node, clock, label, original_text)

if not no_optimize:
    checker_node = optimize(checker_node)  # NEW

if dump_tree:
    # Show optimization summary if optimized
    ...
```

---

## 9. Module Structure Decision

Per D-01: All optimization passes live in a single `optimizer.py` module. Each pass is a plain function (D-02):

```python
# optimizer.py

def optimize(root: CheckerNode) -> CheckerNode:
    """Run all optimization passes on the CheckerNode tree."""
    prev_hash = structural_hash(root)
    for _iteration in range(2):  # max 2 iterations (D-03)
        root = constant_fold(root)
        root = concat_merge(root)
        root = cse(root)
        root = counter_merge(root)
        root = dead_node(root)
        new_hash = structural_hash(root)
        if new_hash == prev_hash:
            break
        prev_hash = new_hash
    return root

def constant_fold(root: CheckerNode) -> CheckerNode: ...
def concat_merge(root: CheckerNode) -> CheckerNode: ...
def cse(root: CheckerNode) -> CheckerNode: ...
def counter_merge(root: CheckerNode) -> CheckerNode: ...
def dead_node(root: CheckerNode) -> CheckerNode: ...
```

---

## 10. Plan Decomposition Guidance

Based on the roadmap (5.1, 5.2, 5.3) and decisions:

### Plan 5.1: Constant Folding + Concat Merging + Framework
- Create `optimizer.py` with the pass orchestration framework
- Implement `constant_fold()` pass
- Implement `concat_merge()` pass
- Add `--no-optimize` CLI flag
- Unit tests for each pass + before/after tree comparison

### Plan 5.2: CSE + Counter Merging
- Implement `cse()` pass with structural hash deduplication
- Implement `counter_merge()` pass
- Update emitter if needed for instance name disambiguation
- CSE canonical naming (`sva_cse_*`)
- Unit tests + multi-property sharing tests
- PIPE-03, PIPE-04 satisfied

### Plan 5.3: Dead-Node Elimination + Parity Suite
- Implement `dead_node()` pass
- Add re-run detection logic (hash comparison, max 2 iterations)
- Extend `format_dump_tree()` with node count summary
- Full parity test suite (all golden fixtures, optimized vs. unoptimized)
- PIPE-05 satisfied
- Integration tests proving optimization is semantics-preserving

---

## 11. Dependencies & Prerequisites

| Dependency | Status | Notes |
|------------|--------|-------|
| `structural_hash()` | ✅ Exists | Ready to use from `composer.py` |
| `CheckerNode` with `cse_origin` | ✅ Exists | Tagged during Phase 3 named-sequence expansion |
| `normalize()` pipeline | ✅ Exists | Optimization runs AFTER normalization+composition |
| Simulation oracle | ✅ Exists | `behavioral_oracle.py` + Icarus harness |
| Golden parity infrastructure | ✅ Exists | `test_golden_parity.py` pattern |
| `dataclasses.replace()` | ✅ stdlib | For creating modified frozen dataclass instances |
| `--dump-tree` flag | ✅ Exists | Extend output format |

**No new external dependencies needed.** All tools are already in the stack.

---

## 12. Success Metrics (from Roadmap)

1. Two identical `##[2:5]` subsequences → single shared counter instance (visible in `--dump-tree` + emitted module list)
2. `--dump-tree` reports reduced node count after optimization
3. All Phase 1-4 simulation oracle tests pass on optimized output (semantics preserved)
4. Dead-state nodes pruned from emitted output

---

*Research completed: 2026-05-28*
*Confidence: HIGH — all building blocks exist, algorithms are well-understood, patterns established in Phase 4*
