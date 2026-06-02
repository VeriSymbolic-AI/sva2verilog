---
wave: 1
depends_on: []
files_modified:
  - src/sva2rtl/normalizer.py
  - tests/test_normalizer.py
autonomous: true
requirements:
  - PIPE-01
---

# Plan 4.1: IR Normalization Pass

## Summary

Deliver `normalizer.py` — a pure IR-to-IR preprocessing pass that canonicalizes SVA IR before composition. Implements bottom-up single-pass traversal with three normalization rules: `[*1]` identity removal, `SeqConcat` flattening, and boolean constant recognition. Standalone `PropImplication(overlapping=False)` is intentionally left untouched to preserve golden file parity. Full unit test coverage including idempotency property.

## Vertical Slice

SVA IR tree with nested `SeqConcat` and trivial `[*1]` repetition -> `normalize()` -> canonical flat IR tree with trivial nodes removed -> ready for `compose()` in Plan 4.2.

<threat_model>
- **Silent semantic change:** Normalization could subtly alter property semantics (e.g., removing a node that carries side-effect timing). Mitigated: all rules are IEEE 1800-2017 identity transformations; idempotency test + golden parity enforce semantic equivalence.
- **Golden file breakage:** If normalizer transforms already-canonical forms differently. Mitigated: normalizer only fires on non-canonical shapes (nested concat, `[*1]`); existing golden inputs are already flat/non-trivial.
- **`|=>` desugaring breaks parity:** If standalone non-overlapping implications are desugared. Mitigated: D-05 decision — normalizer does NOT desugar standalone `PropImplication(overlapping=False)`.
- **Severity:** All LOW-MEDIUM. Core mitigation is idempotency + no-transform-on-canonical-forms property.
</threat_model>

## Tasks

<task id="4.1.1">
<title>Create normalizer.py with bottom-up traversal skeleton</title>
<read_first>
- src/sva2rtl/ir.py
- src/sva2rtl/composer.py (lines 380-410 for match/case dispatch pattern)
- src/sva2rtl/ast_importer.py (lines 1-16 for module structure/docstring pattern)
</read_first>
<action>
Create `src/sva2rtl/normalizer.py`. Public function: `def normalize(node: SVANode) -> SVANode`. Bottom-up traversal using `match`/`case` on node type — recurse into children first (normalize each child), then rebuild the node with normalized children, then apply `_normalize_node()` dispatch. Leaf nodes (`BoolExpr`, `SignalFunc`) return immediately unchanged. Use `from __future__ import annotations`. Import all IR types from `sva2rtl.ir`. Module docstring explains purpose, idempotency guarantee, and lists rules.
</action>
<acceptance_criteria>
- File `src/sva2rtl/normalizer.py` exists with `def normalize(node: SVANode) -> SVANode:`
- Contains `from __future__ import annotations`
- Imports `BoolExpr, SeqConcat, SeqRepetition, SignalFunc, PropImplication, DisableIff, SVANode` from `sva2rtl.ir`
- `match`/`case` dispatch handles all 6 IR node types (BoolExpr, SeqConcat, SeqRepetition, SignalFunc, PropImplication, DisableIff)
- Default `case _:` returns `node` unchanged (never raises)
- `mypy --strict src/sva2rtl/normalizer.py` exits 0
</acceptance_criteria>
</task>

<task id="4.1.2">
<title>Implement [*1] identity removal rule</title>
<read_first>
- src/sva2rtl/normalizer.py
- src/sva2rtl/ir.py (SeqRepetition class definition — fields: expr, rep_min, rep_max)
</read_first>
<action>
In `_normalize_node()`, add a `case SeqRepetition()` branch: if `node.rep_min == 1` and `node.rep_max == 1`, return `node.expr` (the inner expression — already normalized since bottom-up). Otherwise return `node` unchanged. This removes trivial `[*1]` wrappers that add no temporal semantics.
</action>
<acceptance_criteria>
- `normalize(SeqRepetition(expr=BoolExpr(text="a", source_loc=loc), rep_min=1, rep_max=1, source_loc=loc))` returns `BoolExpr(text="a", source_loc=loc)`
- `normalize(SeqRepetition(expr=BoolExpr(text="a", source_loc=loc), rep_min=3, rep_max=5, source_loc=loc))` returns the original `SeqRepetition` unchanged (fields identical)
- `mypy --strict src/sva2rtl/normalizer.py` exits 0
</acceptance_criteria>
</task>

<task id="4.1.3">
<title>Implement SeqConcat flattening rule</title>
<read_first>
- src/sva2rtl/normalizer.py
- src/sva2rtl/ir.py (SeqConcat fields: elements: tuple[SVANode, ...], delays: tuple[tuple[int, int], ...])
- .planning/phases/04-normalization-composition-engine/04-RESEARCH.md (Q1 flatten semantics section)
</read_first>
<action>
Add private function `_flatten_concat(node: SeqConcat) -> SeqConcat`. Logic: iterate over `node.elements`; if an element is itself a `SeqConcat`, splice its elements and delays into the parent's lists. The last delay of the outer sequence at position `i` connects to the first element of the inner — the inner's delays are appended after it. Result is a new `SeqConcat` with all nested concats inlined. If no nested `SeqConcat` found, return `node` unchanged. In `_normalize_node()`, the `SeqConcat` case calls `_flatten_concat(node)`. Preserve `source_loc` from the outer node.
</action>
<acceptance_criteria>
- `normalize(SeqConcat(elements=(a, SeqConcat(elements=(b, c), delays=((3,3),), source_loc=loc)), delays=((2,2),), source_loc=loc))` returns `SeqConcat(elements=(a, b, c), delays=((2,2), (3,3)), source_loc=loc)`
- Already-flat `SeqConcat(elements=(a, b), delays=((1,1),), source_loc=loc)` returns unchanged (same object identity or structurally equal)
- Three-level nesting `SeqConcat(a, SeqConcat(b, SeqConcat(c, d)))` flattens to `SeqConcat(a, b, c, d)` in single pass (bottom-up handles nested inner first)
- `mypy --strict src/sva2rtl/normalizer.py` exits 0
</acceptance_criteria>
</task>

<task id="4.1.4">
<title>Ensure PropImplication(overlapping=False) is NOT desugared</title>
<read_first>
- src/sva2rtl/normalizer.py
- .planning/phases/04-normalization-composition-engine/04-CONTEXT.md (D-05 decision)
</read_first>
<action>
In `_normalize_node()`, the `PropImplication` case must return `node` unchanged regardless of the `overlapping` field value. The normalizer rebuilds children (antecedent/consequent are recursively normalized) but does NOT transform `overlapping=False` to `overlapping=True` with prepended `##1`. Add a comment referencing D-05 explaining this is intentional for golden file parity — `|=>` desugaring deferred to Phase 5+ or when `|=>` appears nested in complex compositions.
</action>
<acceptance_criteria>
- `normalize(PropImplication(antecedent=BoolExpr("a", loc), consequent=BoolExpr("b", loc), overlapping=False, source_loc=loc))` returns a `PropImplication` with `overlapping=False` (not desugared)
- `normalize(PropImplication(antecedent=BoolExpr("a", loc), consequent=BoolExpr("b", loc), overlapping=True, source_loc=loc))` returns the node unchanged
- No `SeqConcat` with `##1` delay is introduced by normalization of any `PropImplication`
- `mypy --strict src/sva2rtl/normalizer.py` exits 0
</acceptance_criteria>
</task>

<task id="4.1.5">
<title>Create comprehensive unit tests for normalizer</title>
<read_first>
- src/sva2rtl/normalizer.py
- tests/test_composer.py (lines 1-60 for test structure, helper factories, naming convention)
- src/sva2rtl/ir.py
</read_first>
<action>
Create `tests/test_normalizer.py`. Include helper factories `_make_loc()`, `_make_bool(text)`, `_make_concat(elements, delays)`, `_make_rep(expr, min, max)`. Test groups:

1. Identity tests (6): each IR type through normalize() unchanged when already canonical — BoolExpr, flat SeqConcat, SeqRepetition(min!=1 or max!=1), SignalFunc, PropImplication(overlapping=True), PropImplication(overlapping=False), DisableIff.

2. Rule tests (5): `[*1]` removal returns inner expr; nested SeqConcat flattens to flat; three-level nesting flattens in single pass; `[*1]` wrapping a SeqConcat both unwraps and flattens; PropImplication children are recursively normalized.

3. Idempotency tests (2): `normalize(normalize(node)) == normalize(node)` for a nested SeqConcat case and a `[*1]` case.

4. Edge cases (3): empty-ish SeqConcat (single element, no delays) unchanged; DisableIff with nested SeqConcat body gets body flattened; SeqRepetition containing nested concat gets inner concat flattened.

Use `-> None` annotations on all tests. Group with `# -- Section header` comments.
</action>
<acceptance_criteria>
- `tests/test_normalizer.py` exists with at least 16 test functions
- All tests named `test_normalize_*`
- `pytest tests/test_normalizer.py -v` exits 0 (all pass)
- `mypy --strict tests/test_normalizer.py` exits 0
- Tests cover: BoolExpr identity, SeqConcat identity, SeqRepetition identity, SignalFunc identity, PropImplication identity (both overlapping values), DisableIff identity, `[*1]` removal, concat flattening (2-level and 3-level), combined rules, idempotency (at least 2 tests)
</acceptance_criteria>
</task>

## Verification

```bash
# All normalizer unit tests pass
pytest tests/test_normalizer.py -v

# Type checking clean
mypy --strict src/sva2rtl/normalizer.py tests/test_normalizer.py

# Linter clean
ruff check src/sva2rtl/normalizer.py tests/test_normalizer.py
```

## must_haves

- [ ] `normalize()` is a pure IR->IR function with no side effects
- [ ] Bottom-up single-pass traversal (children normalized before parent)
- [ ] `[*1]` identity removal fires correctly
- [ ] SeqConcat flattening handles nested concats
- [ ] PropImplication(overlapping=False) is NOT desugared (golden parity)
- [ ] Idempotency: `normalize(normalize(x)) == normalize(x)` proven by tests
- [ ] All tests pass; mypy --strict clean
