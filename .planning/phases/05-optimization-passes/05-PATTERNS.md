# Phase 5: Optimization Passes - Pattern Mapping

**Date:** 2026-05-28
**Purpose:** Map each file to be created/modified to the closest existing analog, extract concrete code excerpts, classify by role and data flow.

---

## Files Inventory

### New Files

| # | File | Role | Data Flow |
|---|------|------|-----------|
| 1 | `src/sva2rtl/optimizer.py` | Transform (pure tree→tree) | `CheckerNode` in → `CheckerNode` out |
| 2 | `tests/test_optimizer.py` | Unit tests | CheckerNode fixtures → pass functions → assertions |

### Modified Files

| # | File | Role | Change Summary |
|---|------|------|----------------|
| 3 | `src/sva2rtl/cli.py` | Pipeline orchestrator | Add `--no-optimize` flag, insert `optimize()` call |
| 4 | `src/sva2rtl/debug.py` | Diagnostic formatter | Add node-count summary line to `format_dump_tree()` |
| 5 | `src/sva2rtl/emitter.py` | RTL code generator | Handle instance name disambiguation for shared modules |

---

## 1. `src/sva2rtl/optimizer.py` (NEW)

### Role & Data Flow
- **Role:** Pure tree-transform module (5 internal pass functions + orchestrator)
- **Input:** `CheckerNode` tree (output of `compose()`)
- **Output:** Optimized `CheckerNode` tree (structurally equivalent semantics)
- **Side effects:** None (pure function, idempotent after convergence)

### Closest Analog: `src/sva2rtl/normalizer.py`

Both are pure tree transforms operating on frozen dataclass trees. The normalizer operates on `SVANode` (IR level); the optimizer operates on `CheckerNode` (post-composition). Same pattern: bottom-up traversal, match/case dispatch, return new tree.

#### Pattern A: Module Docstring + Imports

**Source:** `normalizer.py:1-29`
```python
"""IR normalization pass — canonicalize SVA IR before composition.

Pure IR-to-IR preprocessing pass that runs as a standalone pre-pass before
``compose()``.  Bottom-up single-pass traversal (O(n) on tree size): each
node is visited after its children are normalized.

Guarantees:
- **Idempotent:** ``normalize(normalize(x)) == normalize(x)``
- **Semantic-preserving:** All rules are IEEE 1800-2017 identity transformations
- **Golden-file safe:** Does NOT desugar standalone ``PropImplication(overlapping=False)``
...
"""

from __future__ import annotations

from sva2rtl.ir import (
    BoolExpr,
    ...
    SVANode,
)
```

**Adaptation:** Replace `SVANode` types with `CheckerNode`. Import `structural_hash` from `composer.py`. Add `dataclasses.replace` from stdlib.

#### Pattern B: Public Entry Point (pure function signature)

**Source:** `normalizer.py:32-47`
```python
def normalize(node: SVANode) -> SVANode:
    """Normalize an SVA IR tree to canonical form.

    Pure IR -> IR transformation.  Bottom-up single pass.
    Idempotent: ``normalize(normalize(x)) == normalize(x)``.

    Parameters
    ----------
    node
        Root of the SVA IR subtree to normalize.

    Returns
    -------
    SVANode
        Canonical form of the input tree.
    """
```

**Adaptation:** Signature becomes `def optimize(root: CheckerNode) -> CheckerNode`. Orchestrates 5 sub-passes with up to 2 iterations (D-03).

#### Pattern C: Internal Rule Dispatch (match/case)

**Source:** `normalizer.py:103-133`
```python
def _normalize_node(node: SVANode) -> SVANode:
    """Apply normalization rules to a single node (children already normalized)."""
    match node:
        case SeqRepetition(rep_min=1, rep_max=1):
            return node.expr

        case SeqConcat():
            return _flatten_concat(node)

        case PropImplication():
            return node

        case _:
            return node
```

**Adaptation:** For `CheckerNode`, dispatch on `node.template_name` (string) rather than class type, since all nodes are `CheckerNode`:
```python
match node.template_name:
    case "concat_delay":
        ...
    case "seq_concat_top":
        ...
```

#### Pattern D: Recursive Tree Rebuild (bottom-up)

**Source:** `normalizer.py:56-64`
```python
case SeqConcat():
    new_elements = tuple(normalize(e) for e in node.elements)
    return _normalize_node(
        SeqConcat(
            elements=new_elements,
            delays=node.delays,
            source_loc=node.source_loc,
        )
    )
```

**Adaptation:** For CheckerNode (frozen), use `dataclasses.replace()`:
```python
from dataclasses import replace

new_children = tuple(pass_fn(child) for child in node.children)
if new_children != node.children:
    return replace(node, children=new_children)
return node
```

#### Pattern E: Structural Hash for Change Detection

**Source:** `composer.py:360-388`
```python
def structural_hash(node: CheckerNode) -> str:
    """Compute a deterministic structural hash for a CheckerNode."""
    h = hashlib.sha256()
    h.update(node.template_name.encode())
    for k, v in sorted(node.params.items()):
        if k not in _VOLATILE_PARAMS:
            h.update(f"{k}={v}".encode())
    for child in node.children:
        h.update(structural_hash(child).encode())
    return h.hexdigest()[:8]
```

**Adaptation:** Import and use directly for re-run detection:
```python
from sva2rtl.composer import structural_hash

def optimize(root: CheckerNode) -> CheckerNode:
    prev_hash = structural_hash(root)
    for _iteration in range(2):
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
```

#### Pattern F: Hash Map Construction (tree walking)

**Source:** `composer.py:391-414`
```python
def compute_hash_map(root: CheckerNode) -> dict[str, str]:
    """Walk a CheckerNode tree and return {module_name: structural_hash} for all nodes."""
    result: dict[str, str] = {}
    _collect_hashes(root, result)
    return result

def _collect_hashes(node: CheckerNode, out: dict[str, str]) -> None:
    out[node.module_name] = structural_hash(node)
    for child in node.children:
        _collect_hashes(child, out)
```

**Adaptation:** CSE pass will build `hash → [node, ...]` groupings using the same recursive walk pattern:
```python
def _build_hash_groups(node: CheckerNode, groups: dict[str, list[CheckerNode]]) -> None:
    h = structural_hash(node)
    groups.setdefault(h, []).append(node)
    for child in node.children:
        _build_hash_groups(child, groups)
```

---

## 2. `tests/test_optimizer.py` (NEW)

### Role & Data Flow
- **Role:** Unit tests for each optimization pass + parity regression
- **Input:** Hand-constructed `CheckerNode` trees + JSON fixtures
- **Output:** Assertions on optimized tree structure and simulation parity

### Closest Analog: `tests/test_normalizer.py`

Both test pure tree transforms: construct input trees, call transform, assert on output structure and properties (idempotency, semantic preservation).

#### Pattern A: Test Helpers (node construction)

**Source:** `test_normalizer.py:19-37`
```python
def _make_loc(
    file: str = "test.sv", line: int = 1, col: int = 1
) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)

def _make_bool(text: str = "a") -> BoolExpr:
    return BoolExpr(text=text, source_loc=_make_loc())

def _make_concat(
    elements: tuple[BoolExpr | SeqConcat, ...],
    delays: tuple[tuple[int, int], ...],
) -> SeqConcat:
    return SeqConcat(elements=elements, delays=delays, source_loc=_make_loc())
```

**Adaptation:** Build CheckerNode fixtures directly:
```python
def _make_loc() -> SourceLoc:
    return SourceLoc(file="test.sv", line=1, col=1)

def _make_bool_checker(text: str = "a", name: str = "sva_bool_a") -> CheckerNode:
    return CheckerNode(
        template_name="bool_expr",
        module_name=name,
        params={"bool_expr": text, "clock_signal": "clk", ...},
        observed_signals=(("obs_a", "a"),),
        source_loc=_make_loc(),
    )

def _make_delay_checker(delay_min: int, delay_max: int, name: str = "sva_delay") -> CheckerNode:
    cnt_width = str(max(1, math.ceil(math.log2(delay_max + 1))))
    return CheckerNode(
        template_name="concat_delay",
        module_name=name,
        params={"delay_min": str(delay_min), "delay_max": str(delay_max), "cnt_width": cnt_width, ...},
        observed_signals=(),
        source_loc=_make_loc(),
    )
```

#### Pattern B: Identity Tests (pass-through for canonical forms)

**Source:** `test_normalizer.py:43-48`
```python
def test_normalize_bool_expr_identity() -> None:
    """BoolExpr passes through normalize unchanged."""
    node = _make_bool("a && b")
    result = normalize(node)
    assert result == node
```

**Adaptation:**
```python
def test_optimize_single_bool_identity() -> None:
    """Single bool_expr checker passes through optimization unchanged."""
    node = _make_bool_checker("a && b")
    result = optimize(node)
    assert result == node
```

#### Pattern C: Rule-specific Tests (verify transform fires)

**Source:** `test_normalizer.py:117-125`
```python
def test_normalize_rep_one_removal() -> None:
    """[*1] identity removal returns the inner expression."""
    inner = _make_bool("a")
    node = _make_rep(inner, 1, 1)
    result = normalize(node)
    assert isinstance(result, BoolExpr)
    assert result.text == "a"
```

**Adaptation:**
```python
def test_concat_merge_adjacent_delays() -> None:
    """Adjacent ##3 ##2 merges into ##5."""
    d1 = _make_delay_checker(3, 3, name="delay_3")
    d2 = _make_delay_checker(2, 2, name="delay_2")
    top = _make_concat_top(children=(d1, d2))
    result = concat_merge(top)
    # Should have one merged delay child with delay_min=5, delay_max=5
    merged = [c for c in result.children if c.template_name == "concat_delay"]
    assert len(merged) == 1
    assert merged[0].params["delay_min"] == "5"
```

#### Pattern D: Idempotency Tests

**Source:** `test_normalizer.py:186-195`
```python
def test_normalize_idempotent_nested_concat() -> None:
    """normalize(normalize(node)) == normalize(node) for nested SeqConcat."""
    ...
    once = normalize(outer)
    twice = normalize(once)
    assert once == twice
```

**Adaptation:**
```python
def test_optimize_idempotent() -> None:
    """optimize(optimize(node)) == optimize(node)."""
    tree = _make_tree_with_duplicates()
    once = optimize(tree)
    twice = optimize(once)
    assert structural_hash(once) == structural_hash(twice)
```

#### Pattern E: Parity Testing (simulation oracle)

**Source (analog):** `tests/test_golden_parity.py:41-54`
```python
def _run_full_pipeline(fixture_name: str) -> dict[str, str]:
    """Run the full normalize->compose->emit pipeline on a JSON fixture."""
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        return emit_all(checker)
    else:
        return {checker.module_name: emit(checker)}
```

**Adaptation:** Run pipeline twice (optimized and not), simulate both, compare:
```python
def _run_pipeline(fixture_name: str, *, optimize_flag: bool) -> CheckerNode:
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if optimize_flag:
        checker = optimize(checker)
    return checker

def test_optimization_parity(fixture_name: str, tmp_path: Path) -> None:
    checker_unopt = _run_pipeline(fixture_name, optimize_flag=False)
    checker_opt = _run_pipeline(fixture_name, optimize_flag=True)
    results_unopt = _simulate(checker_unopt, stimulus, tmp_path / "unopt")
    results_opt = _simulate(checker_opt, stimulus, tmp_path / "opt")
    assert results_unopt == results_opt
```

#### Pattern F: Simulation Harness Usage

**Source:** `tests/simulation/test_sim_delay.py:63-91`
```python
def _build_checker(name: str):
    ast = json.loads((_FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)

def _run_stimulus(checker, stimulus: list[dict[str, Any]], tmp_path: Path) -> list[dict]:
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]
    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=False,
    )
    return run_simulation(
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=False,
    )
```

**Adaptation:** Same pattern for parity simulation, applied to both optimized and unoptimized outputs.

---

## 3. `src/sva2rtl/cli.py` (MODIFY)

### Role & Data Flow
- **Role:** Pipeline orchestrator (Click CLI entry point)
- **Change:** Add `--no-optimize` flag, insert `optimize()` call between `compose()` and emit

### Closest Analog: Self (existing flag patterns in `cli.py`)

#### Pattern A: Click Flag Declaration

**Source:** `cli.py:44-49`
```python
@click.option(
    "--dump-tree",
    is_flag=True,
    default=False,
    help="Print CheckerNode composition tree and exit (no RTL emitted)",
)
```

**Adaptation:**
```python
@click.option(
    "--no-optimize",
    is_flag=True,
    default=False,
    help="Skip optimization passes (emit unoptimized output)",
)
```

#### Pattern B: Pipeline Function Insertion

**Source:** `cli.py:57-61`
```python
ast = invoke_slang(Path(input_file), slang_path)
node, clock, original_text, label = import_assertion(ast)
raw_node = node
node = normalize(node)
checker_node = compose(node, clock, label, original_text)
```

**Adaptation:** Insert optimizer between compose and emit:
```python
checker_node = compose(node, clock, label, original_text)

if not no_optimize:
    from sva2rtl.optimizer import optimize
    checker_node = optimize(checker_node)
```

#### Pattern C: Import at Module Top

**Source:** `cli.py:20-25`
```python
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all, write_output, write_output_dir
from sva2rtl.errors import SlangNotFound, SvaError, UnsupportedConstruct
from sva2rtl.frontend import invoke_slang
from sva2rtl.normalizer import normalize
```

**Adaptation:** Add `from sva2rtl.optimizer import optimize` to imports.

#### Pattern D: Function Signature with Flag Parameter

**Source:** `cli.py:50`
```python
def main(input_file: str, output: str | None, slang_path: str, dump_tree: bool) -> None:
```

**Adaptation:**
```python
def main(input_file: str, output: str | None, slang_path: str, dump_tree: bool, no_optimize: bool) -> None:
```

---

## 4. `src/sva2rtl/debug.py` (MODIFY)

### Role & Data Flow
- **Role:** Diagnostic text formatter for `--dump-tree`
- **Change:** Add node-count summary line at bottom of `format_dump_tree()` output

### Closest Analog: Self (existing `_format_checker` recursive walk)

#### Pattern A: Recursive Node Counting (tree walking)

**Source:** `debug.py:121-148` (existing pattern for recursive checker traversal)
```python
def _format_checker(
    node: CheckerNode,
    hash_map: dict[str, str],
    indent: int,
) -> str:
    prefix = " " * indent
    lines: list[str] = []
    ...
    for child in node.children:
        lines.append(_format_checker(child, hash_map, indent + 2))
    return "\n".join(lines)
```

**Adaptation:** Add counting helpers following the same recursive pattern:
```python
def _count_nodes(node: CheckerNode) -> int:
    """Count total logical nodes (shared refs counted once per occurrence)."""
    count = 1
    for child in node.children:
        count += _count_nodes(child)
    return count

def _count_modules(node: CheckerNode) -> int:
    """Count unique module definitions needed."""
    seen: set[str] = set()
    _collect_module_names(node, seen)
    return len(seen)

def _collect_module_names(node: CheckerNode, seen: set[str]) -> None:
    seen.add(node.module_name)
    for child in node.children:
        _collect_module_names(child, seen)
```

#### Pattern B: Extending Output with Summary Line

**Source:** `debug.py:57-63`
```python
def format_dump_tree(...) -> str:
    lines: list[str] = []
    lines.append("=== Pre-normalized IR ===")
    lines.append(_format_ir(ir_node, indent=0))
    lines.append("")
    lines.append("=== Composition Tree ===")
    lines.append(_format_checker(checker, hash_map, indent=0))
    return "\n".join(lines)
```

**Adaptation:** Add optimization summary section at the end:
```python
def format_dump_tree(
    ir_node: SVANode,
    checker: CheckerNode,
    hash_map: dict[str, str],
    *,
    unoptimized_checker: CheckerNode | None = None,
) -> str:
    lines: list[str] = []
    lines.append("=== Pre-normalized IR ===")
    lines.append(_format_ir(ir_node, indent=0))
    lines.append("")
    lines.append("=== Composition Tree ===")
    lines.append(_format_checker(checker, hash_map, indent=0))
    if unoptimized_checker is not None:
        before_nodes = _count_nodes(unoptimized_checker)
        after_nodes = _count_nodes(checker)
        before_mods = _count_modules(unoptimized_checker)
        after_mods = _count_modules(checker)
        pct_nodes = round((1 - after_nodes / before_nodes) * 100) if before_nodes else 0
        pct_mods = round((1 - after_mods / before_mods) * 100) if before_mods else 0
        lines.append("")
        lines.append(f"Optimization: Nodes: {before_nodes} -> {after_nodes} (-{pct_nodes}%), Modules: {before_mods} -> {after_mods} (-{pct_mods}%)")
    return "\n".join(lines)
```

---

## 5. `src/sva2rtl/emitter.py` (MODIFY)

### Role & Data Flow
- **Role:** Renders CheckerNode → SystemVerilog text via Jinja2 templates
- **Change:** Instance name disambiguation when same `module_name` appears multiple times in one parent's children

### Closest Analog: Self (existing `_emit_recursive` dedup pattern)

#### Pattern A: Module Deduplication by Name

**Source:** `emitter.py:135-151`
```python
def _emit_recursive(
    checker: CheckerNode,
    env: Environment,
    results: dict[str, str],
) -> None:
    """Depth-first recursive renderer; populates *results* in-place."""
    for child in checker.children:
        if child.module_name not in results:
            _emit_recursive(child, env, results)

    if checker.module_name not in results:
        template_file = checker.template_name + ".sv.j2"
        tmpl = env.get_template(template_file)
        ctx: dict[str, object] = dict(checker.params)
        ctx["observed_signals"] = checker.observed_signals
        ctx["children"] = checker.children
        results[checker.module_name] = str(tmpl.render(**ctx))
```

**Key insight:** The emitter already deduplicates by `module_name`. If CSE gives shared nodes the same `module_name`, the emitter naturally emits the `.sv` once. No changes needed to `_emit_recursive` itself.

**Potential change:** Instance name disambiguation in parent templates. Currently templates use `{% for child in children %}` with `u_{{ child.module_name }}` for instance names. If two children share the same `module_name`, instances need unique names. This is handled in the Jinja2 template by adding loop index:

```
{% for child in children %}
  {{ child.module_name }} u_{{ child.module_name }}_{{ loop.index0 }} (
{% endfor %}
```

**Verification needed:** Check if existing templates already use indexed instance names. If yes, no emitter Python change needed — only template awareness. The emitter module itself may not need code changes if CSE correctly assigns `module_name`.

---

## Summary: Pattern Reuse Map

| New/Modified File | Primary Analog | Key Patterns Reused |
|---|---|---|
| `optimizer.py` | `normalizer.py` | Pure transform signature, bottom-up traversal, match/case dispatch, frozen dataclass reconstruction |
| `optimizer.py` (CSE) | `composer.py` `structural_hash` + `compute_hash_map` | Hash-based grouping, recursive tree walk, SHA-256 dedup |
| `test_optimizer.py` | `test_normalizer.py` | Helper factories, identity tests, rule tests, idempotency |
| `test_optimizer.py` (parity) | `test_golden_parity.py` + `test_sim_delay.py` | Pipeline fixture loading, simulation harness, cycle comparison |
| `cli.py` changes | `cli.py` self (`--dump-tree`) | Click flag pattern, pipeline insertion point |
| `debug.py` changes | `debug.py` self (`_format_checker`) | Recursive tree walk, line accumulation, summary append |
| `emitter.py` changes | `emitter.py` self (`_emit_recursive`) | `module_name` dedup in `results` dict |

---

## Key Implementation Constraints

1. **Frozen dataclasses:** `CheckerNode` is `frozen=True`. All tree modifications must use `dataclasses.replace()` to create new instances.

2. **`module_name` is the emitter dedup key:** CSE must assign the canonical CSE name (e.g., `sva_cse_concat_delay_2_5`) as the `module_name` for shared nodes. The emitter then naturally deduplicates.

3. **`params` is a mutable dict inside a frozen dataclass:** Custom `__hash__`/`__eq__` on `CheckerNode` uses `frozenset(params.items())`. `dataclasses.replace(node, params={...})` creates a new dict — this is correct.

4. **`structural_hash` excludes `_VOLATILE_PARAMS`:** `module_name`, `source_loc`, `sva2rtl_version`, `original_text` are NOT part of the structural hash. Two nodes with different `module_name` but same semantic params have the same hash — this is exactly what CSE needs.

5. **`cse_origin` field on CheckerNode:** Used as a verification sanity-check. Nodes from the same named-sequence expansion should have matching structural hashes. A mismatch is a warning (bug in earlier phase).

6. **No new dependencies:** All required tools (`hashlib`, `dataclasses.replace`, `structural_hash`, simulation harness) are already available in the project.

---

*Pattern mapping completed: 2026-05-28*
*Confidence: HIGH — all patterns have direct analogs in the existing codebase*
