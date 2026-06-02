# Phase 5: Optimization Passes - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 5-Optimization Passes
**Areas discussed:** Pass architecture & ordering, CSE deduplication strategy, Counter merging scope, Parity testing strategy

---

## Pass Architecture & Ordering

### Q1: How should optimization passes be organized in the source tree?

| Option | Description | Selected |
|--------|-------------|----------|
| Single file (optimizer.py) | All passes live in optimizer.py. Each pass is a function (tree -> tree). Simple, mirrors normalizer.py being one file. ~300-500 lines total. | ✓ |
| Package (optimizer/) | An optimizer/ package with one file per pass + __init__.py that exports the pipeline. Cleaner separation but more files. | |
| You decide | Let Claude decide based on final code size and complexity. | |

**User's choice:** Single file (optimizer.py)

### Q2: What protocol should each optimization pass follow?

| Option | Description | Selected |
|--------|-------------|----------|
| Plain functions (tree -> tree) | Each pass is a plain function: `def cse_pass(root: CheckerNode) -> CheckerNode`. Matches normalizer pattern. | ✓ |
| Class-based (Pass.run()) | Each pass is a class with a `run(root) -> root` method + optional state. | |
| You decide | Let Claude choose based on whether passes need to carry state. | |

**User's choice:** Plain functions (tree -> tree)

### Q3: How should passes be ordered and composed?

| Option | Description | Selected |
|--------|-------------|----------|
| Fixed pipeline order | Hardcoded sequence: constant_fold -> concat_merge -> cse -> counter_merge -> dead_node. Simple, predictable. | |
| Fixed-point iteration | Run all passes in a loop until tree stops changing. More thorough but potentially slower. | |
| Fixed order + one re-run | Fixed order but run the pipeline twice if tree changed. Pragmatic middle ground. | ✓ |

**User's choice:** Fixed order + one re-run

### Q4: How should users control optimization?

| Option | Description | Selected |
|--------|-------------|----------|
| --no-optimize (all-or-nothing) | A single flag that disables ALL passes. Used for A/B parity testing. No per-pass control. | |
| --no-optimize + node count diff | --no-optimize for whole pipeline, PLUS --dump-tree shows before/after node counts. | ✓ |
| Per-pass disable flags | --no-cse, --no-dead-prune, etc. Maximum control but adds CLI complexity. | |

**User's choice:** --no-optimize + node count diff

---

## CSE Deduplication Strategy

### Q1: What scope should CSE operate over?

| Option | Description | Selected |
|--------|-------------|----------|
| Global CSE (whole tree) | Identifies subtrees with identical structural hashes. Scope: entire tree from root. | |
| cse_origin-only CSE | Only deduplicates subtrees tagged with same cse_origin. Limits to known-identical expansions. | |
| Global + cse_origin verify | Global CSE first (hash-based), then verify cse_origin tags as sanity check. Maximum dedup with confidence. | ✓ |

**User's choice:** Global + cse_origin verify

### Q2: How should deduplicated subtrees be represented in emitted RTL?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared module + multi-instantiate | Build new tree where duplicates are replaced by refs to single canonical instance. Emitter renders shared module once, instantiates N times. | |
| One .sv per unique, multiple instances | Emit shared module once as .sv file. Parents each contain instance declarations pointing to same module. | ✓ |
| You decide | Let Claude decide the emitter integration approach. | |

**User's choice:** One .sv per unique, multiple instances

### Q3: Should CSE mutate the tree or produce a sidecar mapping?

| Option | Description | Selected |
|--------|-------------|----------|
| New tree with shared references | CSE builds new tree. Duplicates point to same Python object. Emitter detects shared refs via seen-set. | ✓ |
| Original tree + dedup map | CSE returns original tree plus dedup mapping. Emitter uses mapping to skip duplicate .sv files. | |
| You decide | Let Claude choose based on emitter integration. | |

**User's choice:** New tree with shared references

### Q4: How should module names be resolved for CSE-merged subtrees?

| Option | Description | Selected |
|--------|-------------|----------|
| First name wins + instance suffix | Shared module keeps first-encountered name. Later duplicates removed. Instance names use suffix. | |
| CSE-prefixed canonical name | Shared module gets `sva_cse_{template}_{params}` name. Clearly marks CSE-merged modules. | ✓ |
| You decide | Let Claude choose the naming convention. | |

**User's choice:** CSE-prefixed canonical name

---

## Counter Merging Scope

### Q1: What criteria determine when two counters can share hardware?

| Option | Description | Selected |
|--------|-------------|----------|
| Same (M,N) + same template type | Merge if identical (M, N) delay params AND same template type. Signal inputs may differ. | ✓ |
| Full structural identity only | Only merge counters that are structurally identical including input signal conditions. | |
| Subsumed by CSE (no separate pass) | Counter merging is just CSE. If hash matches, they merge. No separate pass needed. | |

**User's choice:** Same (M,N) + same template type

### Q2: How does counter sharing work at the hardware wiring level?

| Option | Description | Selected |
|--------|-------------|----------|
| Shared free-running + per-consumer window | Shared counter runs freely (OR'd start). Each consumer taps count value and compares own window. | |
| Shared start (OR'd) + shared pass output | Single start input (OR of all consumer starts). Pass output broadcasts to all simultaneously. | ✓ |
| You decide | Let Claude decide the wiring approach. | |

**User's choice:** Shared start (OR'd) + shared pass output

### Q3: Can counters be shared across different property boundaries?

| Option | Description | Selected |
|--------|-------------|----------|
| Within same property only | Counter merging only within single property's tree. Safer, no cross-property interactions. | |
| Across properties in same file | Share identical counters across property boundaries within same file. Maximum area savings. | ✓ |
| You decide | Let Claude decide based on implementation complexity. | |

**User's choice:** Across properties in same file

---

## Parity Testing Strategy

### Q1: How should semantic parity be proven?

| Option | Description | Selected |
|--------|-------------|----------|
| Full oracle on both outputs | Run full simulation oracle on both optimized AND unoptimized output. Compare cycle-by-cycle. | ✓ |
| Oracle on optimized only | Run oracle only on optimized output. If it matches ground-truth, it's correct by definition. | |
| Oracle + VCD trace diff | Both approaches: oracle tests + dedicated parity test that binary-diffs VCD traces. | |

**User's choice:** Full oracle on both outputs

### Q2: How should optimization effect be reported?

| Option | Description | Selected |
|--------|-------------|----------|
| Summary line in --dump-tree | Add summary at bottom: `Nodes: 12 -> 8 (-33%)`. Shows before/after when --no-optimize used. | ✓ |
| Dedicated --stats flag | New flag that prints optimization report: nodes, passes applied, modules shared. | |
| You decide | Put in --dump-tree as header comment. | |

**User's choice:** Summary line in --dump-tree

### Q3: Should golden files be updated to optimized output?

| Option | Description | Selected |
|--------|-------------|----------|
| Update goldens to optimized | Optimization is default. Existing goldens updated. --no-optimize produces old output. | |
| Dual golden sets (unopt + opt) | Keep existing + add second set. Both maintained in parallel. | |
| Goldens unchanged, oracle proves parity | Keep existing goldens. Oracle proves parity. No golden file churn. | ✓ |

**User's choice:** Goldens unchanged, oracle proves parity

### Q4: Should --no-optimize be user-facing or internal?

| Option | Description | Selected |
|--------|-------------|----------|
| --no-optimize skips all passes | User-facing CLI flag. Pipeline becomes normalize -> compose -> emit. | ✓ |
| Internal test flag only | Not exposed in CLI. Internal for parity test suite only. | |

**User's choice:** --no-optimize skips all passes

---

## Claude's Discretion

- Internal structure of pass functions (helper functions, hash table organization)
- Exact constant folding rules (literal true/false propagation)
- Concat merging rules (adjacent ##N ##M -> ##(N+M))
- Emitter seen-set implementation (id-based or module_name-based dedup detection)
- Dead-node elimination algorithm details (BFS/DFS from root)
- Test case selection for complex multi-operator parity tests
- Whether concat_merge operates at IR level or CheckerNode level

## Deferred Ideas

None — discussion stayed within phase scope
