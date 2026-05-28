# Phase 5: Optimization Passes - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers area-efficient RTL output through a series of semantics-preserving optimization passes on the composed CheckerNode tree. Identical subexpressions share hardware via CSE (common subexpression elimination). Range counters with the same parameters share a single module instance. Unreachable nodes are pruned. All optimizations are provably semantics-preserving via before/after simulation oracle parity. A `--no-optimize` flag enables A/B comparison, and `--dump-tree` reports node count reduction.

</domain>

<decisions>
## Implementation Decisions

### Pass Architecture & Ordering
- **D-01:** All optimization passes live in a single `optimizer.py` module (mirrors `normalizer.py` pattern). No separate package — passes are concise tree transforms.
- **D-02:** Each pass is a plain function with signature `def pass_name(root: CheckerNode) -> CheckerNode`. No class-based protocol. Matches the normalizer pattern.
- **D-03:** Fixed pipeline order with one re-run: `constant_fold -> concat_merge -> cse -> counter_merge -> dead_node`. After all passes complete, check if the tree changed (structural hash comparison on root). If yes, run the full pipeline once more (max 2 total iterations). This catches cascading opportunities (e.g., CSE exposes new dead nodes) without unbounded iteration.
- **D-04:** A single `--no-optimize` CLI flag disables ALL optimization passes. Pipeline becomes `normalize -> compose -> emit` (same as Phase 4). Additionally, `--dump-tree` includes a summary line showing before/after node counts: `Nodes: 12 -> 8 (-33%)`. No per-pass disable flags — keeps CLI surface minimal.

### CSE Deduplication Strategy
- **D-05:** Global CSE operates over the entire tree from root using structural hashes (Phase 4's `structural_hash()` function). All subtrees with identical hashes are merge candidates. The `cse_origin` tag (from Phase 3 named sequence expansion) is used as a verification sanity check — tagged nodes should match hash-based duplicates. Maximum deduplication with confidence markers.
- **D-06:** Emitted RTL: one `.sv` file per unique module definition, multiple instantiations across the hierarchy. If CSE identifies three identical delay counters, one `.sv` file is emitted and three `module_name u_N(...)` instance declarations appear in their respective parents.
- **D-07:** CSE builds an entirely new CheckerNode tree. Duplicate subtrees point to the same Python CheckerNode object (identity). The emitter detects shared references (via a seen-set on `id()`) and emits the module `.sv` file only once. The original tree is preserved for comparison/debugging.
- **D-08:** Shared modules get a CSE-prefixed canonical name: `sva_cse_{template}_{params}` (e.g., `sva_cse_concat_delay_2_5`). This clearly distinguishes CSE-merged modules from original non-merged modules in the output. Instance names use unique suffixes.

### Counter Merging
- **D-09:** Counter merge criterion: same `(M, N)` delay parameters AND same template type (`concat_delay`). Signal inputs may differ — the counter just counts clock cycles, and each consumer checks its own condition in the accept window. Shared counter, separate condition checks handled by the pass output broadcast.
- **D-10:** Hardware wiring for shared counters: single start input (OR of all consumer start signals) + shared `pass` output that broadcasts to all consumers simultaneously. Works because merged counters have identical M,N windows — they fire at the same relative time.
- **D-11:** Counter sharing is allowed across property boundaries within the same file. If two properties have identical `##[2:5]` counters, they share a single counter module. Maximum area savings.

### Parity Testing Strategy
- **D-12:** Full simulation oracle runs on BOTH optimized AND unoptimized output for every golden test case. Pass/fail/attempt_fired compared cycle-by-cycle between the two. Any divergence is a hard test failure. Uses the Phase 3 Icarus behavioral oracle infrastructure.
- **D-13:** `--dump-tree` includes a summary line at the bottom: `Nodes: {before} -> {after} (-{percent}%)`. When `--no-optimize` is used, shows the unoptimized count only.
- **D-14:** Existing golden files remain unchanged (unoptimized output). Optimization correctness is proven via simulation oracle parity, not golden file comparison. No golden file churn in Phase 5. Phase 6 locks final golden files.
- **D-15:** `--no-optimize` is a user-facing CLI flag. Skips all optimization passes entirely. Available for debugging and parity testing by users as well as the test suite.

### Claude's Discretion
- Internal structure of pass functions (helper functions, hash table organization for CSE)
- Exact constant folding rules (propagate literal true/false through BoolExpr)
- Concat merging rules (adjacent `##N ##M` -> `##(N+M)` in the IR before composition)
- How the emitter's seen-set detects shared references (id-based or module_name-based)
- Dead-node elimination algorithm details (BFS/DFS from root, prune unreachable)
- Test case selection for complex multi-operator parity tests
- Whether concat_merge operates at IR level (pre-compose) or CheckerNode level (post-compose)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Pipeline
- `.planning/ROADMAP.md` Phase 5 section — Plan breakdown (5.1-5.3), success criteria, requirements (PIPE-03, PIPE-04, PIPE-05)
- `.planning/REQUIREMENTS.md` — PIPE-03 (CSE), PIPE-04 (counter merging), PIPE-05 (dead-state elimination)
- `.planning/PROJECT.md` $$Key Decisions — Frozen dataclasses for CSE, counter encoding, token-passing architecture

### Prior Phase Context (patterns to follow)
- `.planning/phases/04-normalization-composition-engine/04-CONTEXT.md` — Phase 4 decisions: normalizer architecture (D-01/D-02), structural hash (D-07), `--dump-tree` format (D-08/D-09), golden parity (D-11/D-12/D-13)
- `.planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-CONTEXT.md` — Phase 3 decisions: CSE tagging via cse_origin (D-01/D-02), simulation oracle architecture (D-05/D-06/D-07/D-08)
- `.planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md` — Phase 2 decisions: counter encoding (D-01/D-02), module topology (D-08/D-09/D-10), overflow behavior (D-05/D-07)

### Existing Implementation (modify/extend these files)
- `src/sva2rtl/composer.py` — 829 lines; contains `structural_hash()`, `compute_hash_map()`, `compose()`. CSE pass uses structural_hash for deduplication.
- `src/sva2rtl/normalizer.py` — 181 lines; pattern to follow for optimizer.py (pure transform, bottom-up, idempotent)
- `src/sva2rtl/ir.py` — CheckerNode (frozen dataclass with `cse_origin` field, custom `__hash__`/`__eq__`)
- `src/sva2rtl/cli.py` — Add `--no-optimize` flag here; update `--dump-tree` to include node count summary
- `src/sva2rtl/emitter.py` — Must detect shared CheckerNode references and emit each `.sv` only once
- `src/sva2rtl/debug.py` — `format_dump_tree()` to include node count summary line
- `tests/golden/*.sv` — 20+ golden files (remain unchanged; parity via oracle)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `structural_hash(node: CheckerNode) -> str` in composer.py: deterministic SHA-256 based hash reflecting template type, params, and children. Directly usable for CSE candidate identification.
- `compute_hash_map(root: CheckerNode) -> dict[str, str]`: walks tree and returns {module_name: hash}. Building block for CSE dedup-map construction.
- `CheckerNode.cse_origin: str | None`: CSE provenance tag from Phase 3 named sequence expansion. Verification channel for hash-based CSE.
- `normalize()` in normalizer.py: pattern for pure tree transform function (input tree -> output tree, no side effects, idempotent).
- Phase 3 simulation oracle (`behavioral_oracle.py` + Icarus runner): complete infrastructure for cycle-exact pass/fail comparison. Reuse directly for parity tests.
- `format_dump_tree()` in debug.py: existing --dump-tree renderer. Extend with node count summary.

### Established Patterns
- `match`/`case` dispatch on node type (normalizer.py, composer.py, ast_importer.py)
- Frozen dataclass tree construction (all IR nodes + CheckerNode)
- Click CLI flag pattern (`--dump-ast`, `--dump-tree` print and exit 0)
- Golden file testing: fixture regenerates, pytest diffs against committed files
- Simulation oracle: dual-layer Python behavioral + Icarus RTL co-simulation

### Integration Points
- `cli.py` pipeline: currently `frontend -> import -> normalize -> compose -> emit`. Becomes `frontend -> import -> normalize -> compose -> optimize -> emit`. `--no-optimize` skips the `optimize` step.
- `emitter.py`: must handle shared CheckerNode references (same Python object appearing multiple times in tree). Emit module .sv file once, instantiate multiple times.
- `debug.py` `format_dump_tree()`: add node count before/after summary line at the bottom.
- Test suite: new `test_optimizer.py` with parity tests running oracle on both optimized and unoptimized output.

</code_context>

<specifics>
## Specific Ideas

- Pipeline order: constant_fold -> concat_merge -> cse -> counter_merge -> dead_node. Rationale: folding/merging simplifies the tree before CSE runs (more matching hashes), CSE runs before counter_merge (CSE may already handle some counters), dead_node runs last to clean up anything exposed by earlier passes.
- Re-run detection: compare `structural_hash(root)` before and after the full pipeline. If different, run pipeline once more.
- CSE canonical name format: `sva_cse_concat_delay_2_5` (template=concat_delay, M=2, N=5). Includes params in the name for debuggability.
- Counter OR-start wiring: `assign shared_start = consumer_1_start | consumer_2_start | ... ;`
- Node count summary format in --dump-tree: `\nOptimization: Nodes: 12 -> 8 (-33%), Modules: 7 -> 5 (-29%)`
- The `--no-optimize` flag is a simple boolean click option: `@click.option('--no-optimize', is_flag=True, help='Skip optimization passes')`

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 5-Optimization Passes*
*Context gathered: 2026-05-28*
