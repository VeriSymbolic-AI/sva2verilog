---
wave: 1
depends_on:
  - 01-PLAN.md
files_modified:
  - src/sva2rtl/composer.py
  - src/sva2rtl/cli.py
  - tests/test_integration.py
  - tests/test_composer.py
autonomous: true
requirements:
  - PIPE-02
---

# Plan 4.2: Composition Engine — Structural Hash + Pipeline Integration

## Summary

Wire `normalize()` into the compiler pipeline (cli.py and test helpers), add deterministic structural hashing to `CheckerNode` trees using SHA-256, and verify that the normalize->compose chain produces byte-for-byte identical output for all existing Phase 1-3 inputs. This is the evolutionary refactoring step — minimal disruption to the existing 763-line composer, with normalization inserted in front.

## Vertical Slice

SVA input -> slang -> import -> **normalize** -> compose -> structural hash computed -> emit -> identical output as before. The `compose()` API remains unchanged; the call site inserts `normalize()` before it. Structural hash is computed post-composition and stored in a dict returned alongside the tree.

<threat_model>
- **Golden file breakage via normalize:** If normalizer modifies canonical IR forms. Mitigated: Plan 4.1 guarantees normalizer is identity on already-canonical inputs; this plan verifies with golden comparison tests.
- **Hash non-determinism:** Python `hash()` varies across runs due to PYTHONHASHSEED. Mitigated: use `hashlib.sha256` exclusively; never Python built-in `hash()`.
- **Module name changes via normalize:** If normalizer changes IR structure causing different label derivation. Mitigated: `module_name_from_label` uses the original text hash (not IR structure); normalize doesn't change original_text.
- **Import cycle:** Adding `from sva2rtl.normalizer import normalize` to `cli.py`. Mitigated: normalizer only imports from `ir.py` (no circular deps).
- **Severity:** All LOW. Core risk is golden breakage, fully testable.
</threat_model>

## Tasks

<task id="4.2.1">
<title>Add structural_hash function to composer.py</title>
<read_first>
- src/sva2rtl/composer.py (lines 1-50 for imports and module-level constants; lines 315-325 for existing hashlib.sha256 usage)
- src/sva2rtl/ir.py (CheckerNode class — fields: template_name, module_name, params, observed_signals, source_loc, children, cse_origin)
- .planning/phases/04-normalization-composition-engine/04-RESEARCH.md (Q2 structural hash design)
</read_first>
<action>
Add to `src/sva2rtl/composer.py`:

1. Module-level constant `_VOLATILE_PARAMS: frozenset[str]` containing `{"module_name", "source_loc", "sva2rtl_version", "original_text"}` — params excluded from structural hash because they are positional/presentation metadata.

2. Public function `def structural_hash(node: CheckerNode) -> str:` — recursive SHA-256 content hash. Algorithm: create `hashlib.sha256()`, update with `node.template_name`, iterate `sorted(node.params.items())` excluding `_VOLATILE_PARAMS` keys, recurse into `node.children` and update with their hashes. Return `h.hexdigest()[:8]` (8-char hex prefix).

3. Public function `def compute_hash_map(root: CheckerNode) -> dict[str, str]:` — walks the tree, returns `{node.module_name: structural_hash(node)}` for root and all descendants. Uses a simple recursive helper.

Place these after the existing `module_name_from_label` function and before `compose()`.
</action>
<acceptance_criteria>
- `src/sva2rtl/composer.py` contains `_VOLATILE_PARAMS: frozenset[str]` with exactly 4 entries
- `src/sva2rtl/composer.py` contains `def structural_hash(node: CheckerNode) -> str:`
- `src/sva2rtl/composer.py` contains `def compute_hash_map(root: CheckerNode) -> dict[str, str]:`
- `structural_hash` returns an 8-character hex string (matches `re.match(r'^[0-9a-f]{8}$', result)`)
- Same CheckerNode always produces same hash (deterministic across calls)
- Two structurally identical CheckerNodes (same template_name, same non-volatile params, same children) produce same hash regardless of module_name
- `mypy --strict src/sva2rtl/composer.py` exits 0
</acceptance_criteria>
</task>

<task id="4.2.2">
<title>Insert normalize() into cli.py pipeline</title>
<read_first>
- src/sva2rtl/cli.py
- src/sva2rtl/normalizer.py
</read_first>
<action>
Modify `src/sva2rtl/cli.py`:

1. Add import: `from sva2rtl.normalizer import normalize`
2. In the `main()` function body, after `node, clock, original_text, label = import_assertion(ast)` and before `checker_node = compose(...)`, insert: `node = normalize(node)`
3. Update the module docstring pipeline order comment to: `invoke_slang -> import_assertion -> normalize -> compose -> emit -> write_output`
</action>
<acceptance_criteria>
- `cli.py` contains `from sva2rtl.normalizer import normalize`
- `cli.py` contains `node = normalize(node)` between `import_assertion` and `compose` calls
- Module docstring contains `normalize` in the pipeline description
- `mypy --strict src/sva2rtl/cli.py` exits 0
- `python -c "from sva2rtl.cli import main"` imports without error (no circular import)
</acceptance_criteria>
</task>

<task id="4.2.3">
<title>Insert normalize() into test_integration.py _run() helper</title>
<read_first>
- tests/test_integration.py (lines 1-45 for _run helper and imports)
- src/sva2rtl/normalizer.py
</read_first>
<action>
Modify `tests/test_integration.py`:

1. Add import: `from sva2rtl.normalizer import normalize`
2. In `_run(name: str) -> str:` function, after `node, clock, text, label = import_assertion(ast)` insert `node = normalize(node)` before `checker = compose(node, clock, label, text)`
3. Update module docstring pipeline description to include normalize step.
</action>
<acceptance_criteria>
- `tests/test_integration.py` contains `from sva2rtl.normalizer import normalize`
- `_run()` function calls `normalize(node)` before `compose()`
- All existing tests in `tests/test_integration.py` still pass: `pytest tests/test_integration.py -v` exits 0
- Golden file comparisons in test_integration.py pass (byte-for-byte parity maintained)
</acceptance_criteria>
</task>

<task id="4.2.4">
<title>Add normalize->compose parity tests to test_composer.py</title>
<read_first>
- tests/test_composer.py
- src/sva2rtl/normalizer.py
- src/sva2rtl/composer.py (structural_hash, compose)
</read_first>
<action>
Add to `tests/test_composer.py`:

1. Import `from sva2rtl.normalizer import normalize` and `from sva2rtl.composer import structural_hash, compute_hash_map`

2. New test section `# -- Normalize->Compose parity (Phase 4) --` with tests:
   - `test_normalize_compose_parity_bool_expr`: BoolExpr through normalize then compose gives same CheckerNode as compose alone.
   - `test_normalize_compose_parity_seq_concat`: flat SeqConcat through normalize->compose matches compose alone.
   - `test_normalize_compose_parity_implication_overlap`: overlapping PropImplication through normalize->compose matches compose alone.
   - `test_normalize_compose_parity_implication_nonoverlap`: non-overlapping PropImplication through normalize->compose matches compose alone.

3. New test section `# -- Structural hash (Phase 4) --` with tests:
   - `test_structural_hash_deterministic`: same node produces same hash across two calls.
   - `test_structural_hash_ignores_module_name`: two nodes differing only in module_name produce same hash.
   - `test_structural_hash_differs_on_template`: two nodes with different template_name produce different hashes.
   - `test_compute_hash_map_includes_children`: a parent with 2 children produces a hash_map with 3 entries.
</action>
<acceptance_criteria>
- `tests/test_composer.py` contains at least 8 new test functions (4 parity + 4 hash)
- `pytest tests/test_composer.py -v` exits 0 (all tests pass, including new ones)
- Parity tests assert `direct_result == normalized_result` for CheckerNode equality
- Hash tests assert 8-character hex format and determinism
- `mypy --strict tests/test_composer.py` exits 0
</acceptance_criteria>
</task>

<task id="4.2.5">
<title>Run full existing test suite to confirm zero regressions</title>
<read_first>
- tests/test_integration.py
- tests/test_pipeline_e2e.py
- tests/test_composer.py
</read_first>
<action>
Run `pytest tests/ -v --tb=short` to verify that ALL existing 453+ tests still pass after normalization is inserted into the pipeline. Fix any failures caused by the normalize insertion (should be zero if Plan 4.1 is correct). Specifically verify:
- All golden file comparison tests pass (byte-for-byte parity)
- All simulation oracle tests pass (if iverilog available)
- All composer tests pass
- All CLI tests pass
</action>
<acceptance_criteria>
- `pytest tests/ --tb=short` exits 0 with 0 failures
- No golden file mismatches (all `assert_golden` calls pass)
- Test count is >= 453 (no tests were accidentally removed)
- `ruff check src/sva2rtl/` exits 0
</acceptance_criteria>
</task>

## Verification

```bash
# Full test suite passes
pytest tests/ -v --tb=short

# Type checking clean on modified files
mypy --strict src/sva2rtl/cli.py src/sva2rtl/composer.py

# Linter clean
ruff check src/sva2rtl/ tests/

# Confirm no import cycles
python -c "from sva2rtl.cli import main; from sva2rtl.normalizer import normalize; from sva2rtl.composer import structural_hash"
```

## must_haves

- [ ] `normalize()` is called in cli.py between import_assertion and compose
- [ ] `normalize()` is called in test_integration.py _run() helper
- [ ] `structural_hash()` uses hashlib.sha256 (never Python hash())
- [ ] `structural_hash()` excludes module_name, source_loc, sva2rtl_version, original_text from hash
- [ ] `structural_hash()` produces deterministic 8-char hex output
- [ ] ALL existing tests pass (zero regressions, golden parity maintained)
- [ ] mypy --strict clean on all modified files
