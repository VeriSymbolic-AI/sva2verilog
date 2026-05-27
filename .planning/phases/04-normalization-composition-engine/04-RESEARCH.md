# Phase 4: Normalization + Composition Engine — Research

**Date:** 2026-05-27
**Phase:** 4
**Requirements:** PIPE-01, PIPE-02
**Confidence:** HIGH across all research areas

---

## Executive Summary

Phase 4 inserts a normalization pre-pass (`normalizer.py`) into the pipeline and refactors the existing `composer.py` to consume normalized IR with stable structural hashing. The core constraint is **byte-for-byte golden file parity** for all existing Phase 1-3 outputs — normalization must be transparent for already-canonical forms. This research covers the normalization rules, structural hashing strategy, `--dump-tree` design, and integration approach.

---

## Q1: What normalization rules are needed and what are their semantics?

### Rules (from CONTEXT.md decisions D-01 through D-04)

| Rule | Input | Output | Rationale |
|------|-------|--------|-----------|
| `\|=>` desugaring | `PropImplication(overlapping=False)` | `PropImplication(overlapping=True, consequent=SeqConcat([##1, original_con]))` | IEEE 1800-2017 Section 16.12.7 defines `\|=>` as syntactic sugar for `\|-> ##1`. Normalization to a single canonical implication form eliminates the `nonoverlap.sv.j2` template path for new complex compositions. |
| Flatten `SeqConcat` chains | `SeqConcat([a, SeqConcat([b, c])])` | `SeqConcat([a, b, c])` with merged delays | Nested concats are semantically flat sequences. Flattening enables consistent delay-chain analysis and prevents over-instantiation of wrapper modules. |
| `##[N:N]` canonicalization | `SeqConcat(delays=[(N, N)])` | `SeqConcat(delays=[(N, N)])` — no IR change | Already canonical in current IR (min==max). The normalizer validates this but doesn't transform. Ensures `##5` and `##[5:5]` produce identical IR. |
| `[*1]` identity removal | `SeqRepetition(expr=X, rep_min=1, rep_max=1)` | `X` (inner expr directly) | Trivial repetition adds no temporal meaning; removing it simplifies the tree and avoids instantiating a counter for a no-op. |
| Boolean constant normalization | `BoolExpr(text="1'b1")` or equivalent | Keep as-is (no practical constants in SVA from slang) | Defensive rule — slang already evaluates constant expressions. Normalizer recognizes patterns like `1'b1`, `1'b0` but doesn't need to act on them in practice. |

### Critical Constraint: `|=>` Desugaring and Golden File Parity

**Problem:** The existing `nonoverlap_impl.sv` golden file was generated via the `nonoverlap.sv.j2` template (which has a built-in 1-cycle delay register). If we naively desugar `|=>` into `##1 |->`, the composition would use `overlap_bitvec.sv.j2` with a `##1` delay child — producing *different* RTL.

**Solution (from D-05):** Evolutionary refactoring. The normalizer runs, but the composer still dispatches `PropImplication(overlapping=False)` to the existing `nonoverlap` template. The desugaring only activates for *new complex compositions* where the non-overlapping implication is nested inside other operators. For standalone `a |=> b` the composer recognizes the canonical pattern and routes to the existing template to preserve golden parity.

**Alternative approach:** Don't desugar standalone `|=>` at all in Phase 4 — only desugar when `|=>` appears as a sub-expression of a larger property. This is simpler and directly satisfies golden parity.

### Flatten Semantics

Given `(a ##2 (b ##3 c))`, the inner `SeqConcat` can be flattened:
- Before: `SeqConcat(elements=[a, SeqConcat(elements=[b, c], delays=[(3,3)])], delays=[(2,2)])`
- After: `SeqConcat(elements=[a, b, c], delays=[(2,2), (3,3)])`

The last delay of the outer concatenation connects to the first element of the inner concatenation — no delay modification needed, just structural reassembly.

### Idempotency Guarantee

Since the normalizer operates bottom-up in a single pass, and each rule transforms non-canonical to canonical forms (never the reverse), `normalize(normalize(x)) == normalize(x)` holds trivially. The test suite should assert this property.

---

## Q2: How should the structural hash be implemented?

### Requirements (from D-07)
- Deterministic across Python runs (independent of `PYTHONHASHSEED`)
- Content-based (reflects type + params + children structure)
- Stable for CSE candidate detection in Phase 5
- Efficient (O(n) over the tree)

### Design: SHA-256-based recursive content hash

```python
import hashlib

def structural_hash(node: CheckerNode) -> str:
    """Compute a deterministic structural hash for a CheckerNode.
    
    Uses SHA-256 (via hashlib) to avoid PYTHONHASHSEED randomization.
    Returns an 8-character hex digest for compact display.
    """
    h = hashlib.sha256()
    h.update(node.template_name.encode())
    # Sort params for deterministic ordering
    for k, v in sorted(node.params.items()):
        # Exclude volatile params (module_name, source_loc, sva2rtl_version)
        if k not in ("module_name", "source_loc", "sva2rtl_version", "original_text"):
            h.update(f"{k}={v}".encode())
    # Recurse into children
    for child in node.children:
        h.update(structural_hash(child).encode())
    return h.hexdigest()[:8]
```

### Key Decisions

1. **Exclude module_name from hash** — module names encode positional labels (`_e0`, `_ant`, `_con`) which differ between structurally identical subtrees.
2. **Exclude source_loc** — two identical expressions at different source locations should hash the same for CSE.
3. **Exclude sva2rtl_version and original_text** — these are presentation metadata, not structural content.
4. **Include template_name + semantic params** — these define what hardware gets instantiated.
5. **Include child hashes recursively** — structural identity means the entire subtree matches.
6. **Use SHA-256 (hashlib)** — Python's built-in `hash()` varies across runs due to hash randomization. `hashlib.sha256` is always deterministic.
7. **8-character hex prefix** — sufficient for display in `--dump-tree` (collision probability negligible for typical assertion sizes < 1000 nodes).

### Where to store

Add `structural_hash` as a computed property or a post-composition annotation on `CheckerNode`. Since `CheckerNode` is frozen, we can compute it lazily via a module-level cache dict keyed by `id(node)`, or compute during composition and store externally (hash → node mapping for Phase 5 CSE).

**Chosen approach:** Compute after composition and store in a `dict[CheckerNode, str]` mapping returned alongside the tree. This avoids changing the frozen dataclass interface.

---

## Q3: How should `--dump-tree` be implemented?

### Format (from D-08, D-09, D-10)

```
=== Pre-normalized IR ===
PropImplication(overlapping=False)
  antecedent: BoolExpr("a")
  consequent: BoolExpr("b")

=== Post-normalization CheckerNode Tree ===
CheckerNode: sva_nonoverlap_check (nonoverlap) [hash:a3f2c1d7]
  bv_width: 1
  wiring: ant.pass -> bv_q shift -> con.start
  children:
    CheckerNode: sva_nonoverlap_check_ant (bool_expr) [hash:e4b2a91c]
      bool_expr: a
    CheckerNode: sva_nonoverlap_check_con (bool_expr) [hash:f7d3b82e]
      bool_expr: b
```

### Implementation

1. **Location:** New function `dump_tree(node: SVANode, checker: CheckerNode, hashes: dict) -> str` in a `debug.py` module (or inline in `cli.py`).
2. **Pre-normalized section:** Simple recursive `repr`-like dump of the raw IR tree from `ast_importer`.
3. **Post-normalized section:** Recursive indented dump of the `CheckerNode` tree with:
   - Node type (template_name)
   - Module name
   - Key params (filtered: only semantic params like `bv_width`, `delay_min`, `bool_expr`)
   - Structural hash
   - Wiring annotation (describe token-passing connections based on parent-child relationship and template semantics)
4. **CLI integration:** Add `--dump-tree` flag to `cli.py`. Print to stdout and `sys.exit(0)`. Same pattern as the existing (planned) `--dump-ast`.

### Wiring Annotation Logic

Based on template type of the parent:
- `overlap_bitvec` / `nonoverlap`: "ant.pass -> bv_q[0] -> shift -> con.start"
- `seq_concat_top`: "e0.pass -> delay.start -> delay.pass -> e1.start"
- `disable_iff_top`: "condition gates body.disable_i"

---

## Q4: How to guarantee golden file parity?

### The Constraint

All 29 golden files in `tests/golden/` must regenerate byte-for-byte after normalization is inserted into the pipeline. This means for every existing input pattern, `normalize()` must return structurally equivalent IR that the composer maps to the exact same `CheckerNode` tree (same template selection, same params, same module names).

### Analysis of Current Inputs

| Golden File | IR Type | Normalization Effect |
|---|---|---|
| `bool_labeled.sv`, `bool_simple.sv` | `BoolExpr` | **None** — BoolExpr has no normalization rules |
| `sva_delay_*.sv` | Part of `SeqConcat` | **None** — delays are already canonical `(N,N)` or `(M,N)` |
| `sva_prop_*.sv` | `SeqConcat` (2-3 elements) | **None** — flat concat with no nested SeqConcat |
| `overlap_impl.sv` | `PropImplication(overlapping=True)` | **None** — overlapping is already canonical |
| `nonoverlap_impl.sv` | `PropImplication(overlapping=False)` | **CRITICAL** — must NOT desugar to `##1 |->` |
| `sva_rose.sv`, `sva_fell.sv`, etc. | `SignalFunc` | **None** — no normalization rules for signal functions |
| `sva_rep_fixed.sv`, `sva_rep_range.sv` | `SeqRepetition` | **Potentially `[*1]` removal** — check if any golden has rep_min=rep_max=1 |
| `sva_bitvec_impl.sv` | `PropImplication` + `SeqConcat` | **None** — already flat |

### Strategy

1. **Skip `|=>` desugaring for standalone properties:** The normalizer recognizes the pattern "top-level `PropImplication(overlapping=False)` with simple antecedent/consequent" and leaves it unchanged. Only desugar when `|=>` is nested inside another property operator.

2. **SeqConcat flatten is safe:** No existing golden file has nested `SeqConcat` (the `ast_importer` already flattens during import). The normalize rule is additive — it handles cases that could arise from Phase 4's new complex compositions but doesn't touch existing flat structures.

3. **`[*1]` check:** Need to verify no existing golden uses `rep_min=1, rep_max=1`. Looking at the golden files: `sva_rep_fixed.sv` uses `[*3]`, `sva_rep_range.sv` uses `[*2:5]`. Neither is `[*1]`, so the identity removal rule won't fire on existing inputs.

4. **Regression test fixture (D-12):** A pytest fixture that regenerates ALL golden files and does byte-for-byte diff against committed versions. Any deviation = hard failure. This runs as part of the normal test suite (not just CI).

---

## Q5: What is the integration approach for normalizer into the pipeline?

### Current Pipeline

```
cli.py: invoke_slang -> import_assertion -> compose -> emit -> write_output
```

### New Pipeline

```
cli.py: invoke_slang -> import_assertion -> normalize -> compose -> emit -> write_output
```

### API Change

```python
# Before (current):
checker_node = compose(node, clock, label, original_text)

# After:
from sva2rtl.normalizer import normalize
normalized_node = normalize(node)
checker_node = compose(normalized_node, clock, label, original_text)
```

### Normalizer Module Interface

```python
# src/sva2rtl/normalizer.py

def normalize(node: SVANode) -> SVANode:
    """Normalize an SVA IR tree to canonical form.
    
    Pure IR→IR transformation. Bottom-up single pass.
    Idempotent: normalize(normalize(x)) == normalize(x).
    
    Rules applied:
    - [*1] identity removal (SeqRepetition with min=max=1 → inner expr)
    - SeqConcat flattening (nested SeqConcat → flat SeqConcat)
    - Boolean constant recognition (defensive, usually no-op)
    
    Note: |=> desugaring is NOT applied for standalone implications
    (golden file parity). Only applied when |=> is nested in complex
    compositions.
    """
    ...
```

### Composer Changes (D-05, D-06)

Minimal — the existing `compose()` function already handles all IR node types. The only change is that normalized IR arrives (e.g., no nested `SeqConcat`, no `[*1]` wrappers). Since the composer already handled flat `SeqConcat` and never saw `[*1]`, there's no behavioral change for existing inputs.

---

## Q6: What complex composition patterns does Phase 4 enable?

### Target Pattern (from Roadmap success criteria)

```systemverilog
a |-> ##[1:3] (b [*2:4] ##1 c)
```

This requires:
1. Antecedent `a` (BoolExpr)
2. Overlapping implication `|->`
3. Consequent is a `SeqConcat` containing:
   - A `##[1:3]` delay
   - A nested sub-sequence: `b [*2:4] ##1 c`
     - `b [*2:4]` (repetition)
     - `##1` delay
     - `c` (BoolExpr)

The normalizer would flatten the nested structure if it arrives as nested `SeqConcat`. The composer then recursively builds:
- Top: `overlap_bitvec` (BV_WIDTH = sum of max delays in consequent)
- Antecedent child: `bool_expr` for `a`
- Consequent child: `seq_concat_top` containing:
  - `concat_delay` (1, 3)
  - `rep_consecutive` for `b [*2:4]`
  - `concat_delay` (1, 1)
  - `bool_expr` for `c`

### `a |=> ##[1:3] b` (Roadmap success criterion 1)

With desugaring active (for this new complex case):
1. Normalize: `|=>` → `|->` with `##1` prepended to consequent
2. Compose as `PropImplication(overlapping=True)` with consequent = `SeqConcat([dummy_bool, ##1, b_with_range_delay])`
3. Result verified by simulation oracle against the Phase 2 direct `nonoverlap` implementation

**Decision: Don't desugar `|=>` in Phase 4.** The existing `nonoverlap.sv.j2` template handles the 1-cycle offset correctly for all cases. Desugaring would only be needed if we wanted to eliminate the `nonoverlap` template entirely — which we don't need to do. The ROADMAP says "replaces ad-hoc direct wiring" but D-05 says "evolutionary refactoring — keep existing composer mostly intact." Golden parity wins.

**Revised approach:** The normalizer handles `SeqConcat` flattening and `[*1]` removal. The `|=>` desugaring is deferred or made conditional (only for deeply nested `|=>` inside other sequences). For Phase 4's success criteria, `a |=> ##[1:3] b` compiles via the existing `nonoverlap` template path (already works from Phase 2-3), and the simulation oracle confirms correctness.

---

## Q7: What patterns should the normalizer follow from existing code?

### Existing Pattern: `match`/`case` dispatch

Both `composer.py` and `ast_importer.py` use Python 3.12 `match`/`case` on node types:

```python
match node:
    case BoolExpr():
        return _compose_bool_expr(...)
    case SeqConcat():
        return _compose_seq_concat(...)
```

The normalizer should follow the same pattern:

```python
def _normalize_node(node: SVANode) -> SVANode:
    """Bottom-up normalize a single node (children already normalized)."""
    match node:
        case SeqRepetition(rep_min=1, rep_max=1):
            return node.expr  # [*1] → identity
        case SeqConcat():
            return _flatten_concat(node)
        case _:
            return node  # unchanged
```

### Bottom-Up Traversal

```python
def normalize(node: SVANode) -> SVANode:
    """Top-level entry: bottom-up normalization."""
    match node:
        case BoolExpr() | SignalFunc():
            return node  # leaf nodes — no children to recurse into
        case SeqConcat():
            new_elements = tuple(normalize(e) for e in node.elements)
            rebuilt = SeqConcat(elements=new_elements, delays=node.delays, source_loc=node.source_loc)
            return _normalize_node(rebuilt)
        case SeqRepetition():
            new_expr = normalize(node.expr)
            rebuilt = SeqRepetition(expr=new_expr, rep_min=node.rep_min, rep_max=node.rep_max, source_loc=node.source_loc)
            return _normalize_node(rebuilt)
        case PropImplication():
            new_ant = normalize(node.antecedent)
            new_con = normalize(node.consequent)
            rebuilt = PropImplication(antecedent=new_ant, consequent=new_con, overlapping=node.overlapping, source_loc=node.source_loc)
            return _normalize_node(rebuilt)
        case DisableIff():
            new_body = normalize(node.body)
            rebuilt = DisableIff(condition=node.condition, body=new_body, source_loc=node.source_loc)
            return _normalize_node(rebuilt)
        case _:
            return node
```

### Frozen Dataclass Reconstruction

Since all IR nodes are `@dataclass(frozen=True)`, normalization cannot mutate — it must construct new nodes. This is already the pattern throughout the codebase. The `SeqConcat` flatten rule creates a new `SeqConcat` with merged elements/delays tuples.

---

## Q8: What testing strategy validates normalization correctness?

### Unit Tests for `normalizer.py`

1. **Identity tests:** Each IR type passes through unchanged when already canonical
   - `BoolExpr` → same `BoolExpr`
   - `SeqConcat` (flat, no nested) → same structure
   - `PropImplication(overlapping=True)` → unchanged
   - `PropImplication(overlapping=False)` → unchanged (standalone)
   - `SeqRepetition(rep_min=3, rep_max=5)` → unchanged
   - `SignalFunc` → unchanged

2. **Normalization rule tests:**
   - `SeqRepetition(rep_min=1, rep_max=1, expr=X)` → `X`
   - Nested `SeqConcat` → flat `SeqConcat` with correct delay merge
   - Multiple nested levels flatten correctly

3. **Idempotency property tests (hypothesis):**
   ```python
   @given(st.from_type(SVANode))
   def test_normalize_idempotent(node):
       assert normalize(normalize(node)) == normalize(node)
   ```

4. **Golden file parity (D-12):**
   - Regenerate all 29 golden files through `normalize → compose → emit`
   - Byte-for-byte diff against committed golden files
   - Automated as `test_golden_parity_all()` in the test suite

### Integration Tests

5. **Complex composition tests:**
   - `a |-> ##[1:3] (b [*2:4] ##1 c)` compiles without error
   - `--dump-tree` produces well-formed output

6. **Simulation oracle re-run (D-13):**
   - All 43+ Phase 3 simulation tests pass unmodified
   - Belt-and-suspenders behavioral equivalence proof

---

## Q9: What are the risks and mitigations?

| Risk | Impact | Mitigation |
|------|--------|-----------|
| `|=>` desugaring breaks golden parity | HIGH — 1+ golden file changes | Don't desugar standalone `|=>` (D-05 evolutionary approach) |
| SeqConcat flatten changes module names | HIGH — sub-module names encode position (`_e0`, `_e1`) | Only flatten genuinely nested concats (not existing flat ones) |
| Structural hash non-determinism | MEDIUM — flaky `--dump-tree` output | Use `hashlib.sha256` (never Python `hash()`), sort param keys |
| Normalizer introduces new IR shapes composer can't handle | MEDIUM — runtime crash | Normalizer only reduces to forms composer already handles |
| `[*1]` removal changes observed_signals propagation | LOW — if `[*1]` wrapper had signals | Verify no existing test uses `[*1]`; normalizer tests cover this |
| Bottom-up traversal misses cross-node interactions | LOW — rules are local | Each rule is self-contained; no inter-node dependencies |

---

## Q10: File inventory — what gets created/modified?

### New Files

| File | Purpose |
|------|---------|
| `src/sva2rtl/normalizer.py` | IR normalization pass (Plan 4.1) |
| `src/sva2rtl/debug.py` | `--dump-tree` formatting (Plan 4.3) |
| `tests/test_normalizer.py` | Unit tests for normalizer rules |
| `tests/test_dump_tree.py` | Tests for `--dump-tree` output format |

### Modified Files

| File | Change |
|------|--------|
| `src/sva2rtl/cli.py` | Add `--dump-tree` flag; insert `normalize()` call in pipeline |
| `src/sva2rtl/composer.py` | Add structural hash computation after tree build; minor refactoring |
| `tests/test_integration.py` | Update pipeline calls to include `normalize()` |
| `tests/test_pipeline_e2e.py` | Add `--dump-tree` test case |
| `tests/test_composer.py` | Verify normalize→compose chain produces same results |

### Unchanged Files (verification only)

| File | Verification |
|------|-------------|
| All 29 `tests/golden/*.sv` | Must regenerate byte-for-byte (D-11) |
| All `tests/simulation/test_sim_*.py` | Must pass unmodified (D-13) |
| `src/sva2rtl/ir.py` | No changes needed — frozen dataclasses already sufficient |
| `templates/*.sv.j2` | No template changes needed |

---

## Q11: Dependency ordering and plan sequencing

### Plan 4.1 (IR normalization pass) — Independent, Wave 1

- Creates `normalizer.py` with all rules
- Full unit test coverage
- No dependency on other Phase 4 work

### Plan 4.2 (Composition engine refinement) — Depends on 4.1, Wave 1

- Inserts `normalize()` into the pipeline
- Adds structural hash computation
- Tests that `normalize → compose` produces identical results for existing inputs

### Plan 4.3 (Integration + regression) — Depends on 4.1 + 4.2, Wave 2

- `--dump-tree` CLI flag
- Complex composition end-to-end tests
- Full golden file parity assertion
- Simulation oracle re-run

---

## References

### IEEE Standard
- IEEE 1800-2017 Section 16.12.7 — formal definition of `|=>` as equivalent to `|-> ##1`

### Implementation Patterns
- [Numba Rewrite Pass Architecture](https://numba.pydata.org/numba-doc/0.23.0/developer/rewrites.html) — Match/Apply interface for IR rewrites
- [LLVM IRNormalizer](https://llvm.org/doxygen/IRNormalizer_8h_source.html) — Canonicalization pass design in production compilers
- [Python hashlib deterministic hashing](https://thelinuxcode.com/python-hashlib-sha256/) — SHA-256 for cross-run deterministic hashing

### Project Internal References
- `.planning/phases/04-normalization-composition-engine/04-CONTEXT.md` — All user decisions (D-01 through D-13)
- `.planning/ROADMAP.md` Phase 4 — Plans 4.1-4.3, success criteria
- `src/sva2rtl/composer.py` — Existing 763-line composition engine (evolutionary target)
- `src/sva2rtl/ir.py` — Frozen dataclass IR hierarchy

---

*Research complete: 2026-05-27*
*Confidence: HIGH — all normalization rules have clear semantics, golden parity strategy is well-defined, implementation patterns directly follow existing codebase conventions*
