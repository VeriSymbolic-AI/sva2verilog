---
wave: 2
depends_on:
  - 01-PLAN.md
  - 02-PLAN.md
files_modified:
  - src/sva2rtl/debug.py
  - src/sva2rtl/cli.py
  - tests/test_dump_tree.py
  - tests/test_pipeline_e2e.py
  - tests/test_golden_parity.py
autonomous: true
requirements:
  - PIPE-01
  - PIPE-02
---

# Plan 4.3: Integration + Regression Validation — `--dump-tree` + Complex Compositions + Parity

## Summary

Deliver the `--dump-tree` CLI flag for debugging composition trees, test complex multi-operator compositions through the normalize->compose pipeline, and create a comprehensive golden file parity regression test that proves the new architecture is behaviorally equivalent for all Phase 1-3 inputs. Also re-runs all simulation oracle tests as belt-and-suspenders behavioral equivalence proof.

## Vertical Slice

Complex SVA `a |-> ##[1:3] b` -> slang -> import -> normalize (flatten/canonicalize) -> compose (token-passing tree) -> `--dump-tree` prints structured tree with hashes to stdout and exits 0. All 29 golden files regenerate byte-for-byte. All 43+ simulation tests pass unmodified.

<threat_model>
- **`--dump-tree` output instability:** Hash values could change between runs if PYTHONHASHSEED affects them. Mitigated: structural_hash uses hashlib.sha256, proven deterministic in Plan 4.2.
- **Complex composition crash:** New deeply nested patterns could hit unhandled IR shapes in composer. Mitigated: normalizer reduces to forms composer already handles; tests exercise specific complex patterns.
- **Golden parity false positive:** If the golden parity test only checks a subset of files. Mitigated: test dynamically discovers ALL .sv files in tests/golden/ directory — any new golden file added later is automatically covered.
- **Simulation oracle false pass:** If oracle tests aren't actually running (skipped silently). Mitigated: test explicitly counts test collection and asserts minimum test count.
- **Severity:** All LOW. This plan is primarily about validation, not new functionality.
</threat_model>

## Tasks

<task id="4.3.1">
<title>Create debug.py with dump_tree formatting</title>
<read_first>
- src/sva2rtl/ir.py (SVANode hierarchy, CheckerNode fields)
- src/sva2rtl/composer.py (structural_hash, compute_hash_map signatures)
- src/sva2rtl/emitter.py (lines 1-30 for module structure pattern)
- .planning/phases/04-normalization-composition-engine/04-RESEARCH.md (Q3 dump-tree format)
</read_first>
<action>
Create `src/sva2rtl/debug.py`. Public function `def format_dump_tree(ir_node: SVANode, checker: CheckerNode, hash_map: dict[str, str]) -> str`. Returns a formatted string with two sections:

1. `=== Pre-normalized IR ===` section: recursive repr-like dump of the SVANode tree. Each node shows type name and key fields (BoolExpr shows text; SeqConcat shows delay count; PropImplication shows overlapping; SeqRepetition shows rep_min/rep_max; SignalFunc shows func_name/signal; DisableIff shows "condition + body"). Indent 2 spaces per level.

2. `=== Composition Tree ===` section: recursive dump of CheckerNode tree. Each node shows: `CheckerNode: {module_name} ({template_name}) [hash:{hash}]`. Below it, indented: key semantic params (filter out module_name, source_loc, sva2rtl_version, original_text from display), children recursively. Indent 2 spaces per level.

Private helpers: `_format_ir(node: SVANode, indent: int) -> str` and `_format_checker(node: CheckerNode, hash_map: dict[str, str], indent: int) -> str`.
</action>
<acceptance_criteria>
- File `src/sva2rtl/debug.py` exists with `def format_dump_tree(ir_node: SVANode, checker: CheckerNode, hash_map: dict[str, str]) -> str:`
- Output contains `=== Pre-normalized IR ===` header
- Output contains `=== Composition Tree ===` header
- CheckerNode lines match pattern `CheckerNode: <name> (<template>) [hash:<8hex>]`
- Indentation increases by 2 spaces per nesting level
- `mypy --strict src/sva2rtl/debug.py` exits 0
</acceptance_criteria>
</task>

<task id="4.3.2">
<title>Add --dump-tree flag to cli.py</title>
<read_first>
- src/sva2rtl/cli.py
- src/sva2rtl/debug.py
- src/sva2rtl/composer.py (compute_hash_map signature)
</read_first>
<action>
Modify `src/sva2rtl/cli.py`:

1. Add click option: `@click.option("--dump-tree", is_flag=True, default=False, help="Print CheckerNode composition tree and exit (no RTL emitted)")` 

2. Add `dump_tree: bool` parameter to `main()` function signature.

3. After `checker_node = compose(...)`, add conditional: if `dump_tree` is True, import `format_dump_tree` from `sva2rtl.debug` and `compute_hash_map` from `sva2rtl.composer`, compute hash_map, call `format_dump_tree(node, checker_node, hash_map)`, print via `click.echo()`, and `sys.exit(0)` — no RTL emission.

4. The `node` passed to `format_dump_tree` should be the pre-normalized IR (save original before normalize). Add `raw_node = node` before `node = normalize(node)` and pass `raw_node` to format_dump_tree as the `ir_node` parameter.
</action>
<acceptance_criteria>
- `cli.py` contains `@click.option("--dump-tree", is_flag=True, ...)`
- `main()` signature includes `dump_tree: bool` parameter
- When `--dump-tree` is passed, output contains "=== Pre-normalized IR ===" and "=== Composition Tree ===" and `[hash:`
- When `--dump-tree` is passed, exit code is 0
- When `--dump-tree` is passed, no RTL file is written (no `emit()` call executes)
- `mypy --strict src/sva2rtl/cli.py` exits 0
</acceptance_criteria>
</task>

<task id="4.3.3">
<title>Create test_dump_tree.py with unit and integration tests</title>
<read_first>
- src/sva2rtl/debug.py
- src/sva2rtl/cli.py
- tests/test_pipeline_e2e.py (lines 30-57 for CLI test pattern with CliRunner)
- tests/conftest.py (requires_slang marker)
</read_first>
<action>
Create `tests/test_dump_tree.py` with two test groups:

1. Unit tests (no slang needed) — construct IR nodes and CheckerNodes directly, call `format_dump_tree()`, assert output structure:
   - `test_dump_tree_contains_ir_section`: output contains "=== Pre-normalized IR ===" 
   - `test_dump_tree_contains_checker_section`: output contains "=== Composition Tree ==="
   - `test_dump_tree_shows_hash`: output contains `[hash:` followed by 8 hex chars and `]`
   - `test_dump_tree_shows_template_name`: output contains the template_name of the node (e.g., "bool_expr")
   - `test_dump_tree_indents_children`: for a parent with children, child lines have more leading spaces than parent lines

2. CLI integration tests (requires_slang decorated):
   - `test_cli_dump_tree_exits_0`: `CliRunner().invoke(main, [fixture_path, "--dump-tree"])` returns exit_code 0
   - `test_cli_dump_tree_no_rtl_emitted`: with `--dump-tree` and `--output` specified, no output file is created
   - `test_cli_dump_tree_output_has_structure`: stdout contains "CheckerNode:" and "[hash:"
</action>
<acceptance_criteria>
- `tests/test_dump_tree.py` exists with at least 8 test functions
- `pytest tests/test_dump_tree.py -v -k "not requires_slang"` exits 0 (unit tests pass without slang)
- All tests annotated `-> None`
- Unit tests construct CheckerNode and call format_dump_tree directly
- CLI tests use `@requires_slang` decorator and `CliRunner`
- `mypy --strict tests/test_dump_tree.py` exits 0
</acceptance_criteria>
</task>

<task id="4.3.4">
<title>Add --dump-tree E2E test to test_pipeline_e2e.py</title>
<read_first>
- tests/test_pipeline_e2e.py (full file — see existing test patterns)
- tests/conftest.py (requires_slang)
</read_first>
<action>
Add to `tests/test_pipeline_e2e.py`:

1. New test `test_e2e_dump_tree_bool_assert`: invoke CLI with `[str(_FIXTURES / "bool_assert.sv"), "--dump-tree"]`. Assert exit_code == 0. Assert `"=== Pre-normalized IR ===" in result.output`. Assert `"=== Composition Tree ===" in result.output`. Assert `"CheckerNode:" in result.output`. Assert `"[hash:" in result.output`. Assert `"bool_expr" in result.output` (the template name for a boolean assertion).

2. New test `test_e2e_dump_tree_no_output_file`: invoke with `--dump-tree --output /tmp/should_not_exist.sv`. Assert exit_code == 0. Assert output file does NOT exist (dump-tree prevents RTL emission).

Both tests decorated with `@requires_slang`.
</action>
<acceptance_criteria>
- `tests/test_pipeline_e2e.py` contains `test_e2e_dump_tree_bool_assert` and `test_e2e_dump_tree_no_output_file`
- Both tests have `@requires_slang` decorator
- `pytest tests/test_pipeline_e2e.py -v -k dump_tree` exits 0 (when slang available)
- Tests verify exit_code == 0 and expected output markers
</acceptance_criteria>
</task>

<task id="4.3.5">
<title>Create comprehensive golden parity regression test</title>
<read_first>
- tests/test_integration.py (lines 38-80 for existing golden comparison pattern)
- tests/conftest.py (assert_golden helper function)
- tests/golden/ (all 29 .sv files listed by find command)
</read_first>
<action>
Create `tests/test_golden_parity.py`. Purpose: prove that the new normalize->compose pipeline produces byte-for-byte identical output for ALL existing golden files.

1. Import `normalize` from `sva2rtl.normalizer`, `compose` from `sva2rtl.composer`, `emit` and `emit_all` from `sva2rtl.emitter`, `import_assertion` from `sva2rtl.ast_importer`, and `assert_golden` from `tests.conftest`.

2. Function `_run_full_pipeline(fixture_name: str) -> dict[str, str]`: loads JSON fixture, runs `import_assertion -> normalize -> compose`, then `emit_all` to get all module texts as `{module_name: sv_text}` dict. For single-module outputs, wrap in a dict.

3. Use `pytest.mark.parametrize` over all JSON fixtures that have corresponding golden files. Map each fixture to its expected golden file(s). The parametrize list should cover at minimum: bool_simple, bool_labeled, overlap_impl, nonoverlap_impl, sva_rep_fixed, sva_rep_range, sva_rose, sva_fell, sva_stable, sva_past, sva_bitvec_impl, and the delay/concat fixtures.

4. Each parametrized test calls `_run_full_pipeline` and asserts golden parity via `assert_golden()` for each generated module against its committed golden file.

5. Add a non-parametrized test `test_golden_file_count_minimum`: assert that `tests/golden/` contains at least 29 .sv files (catches accidental deletion).
</action>
<acceptance_criteria>
- `tests/test_golden_parity.py` exists with parametrized tests covering all golden files
- `pytest tests/test_golden_parity.py -v` exits 0 (all golden files match byte-for-byte)
- Test uses `normalize()` in the pipeline (proving normalize is transparent for existing inputs)
- Contains `test_golden_file_count_minimum` asserting >= 29 golden files exist
- `mypy --strict tests/test_golden_parity.py` exits 0
</acceptance_criteria>
</task>

<task id="4.3.6">
<title>Run full test suite including simulation oracle as final validation</title>
<read_first>
- tests/simulation/test_sim_delay.py
- tests/simulation/test_sim_implication.py
- tests/simulation/test_sim_rose.py
</read_first>
<action>
Run the complete test suite: `pytest tests/ -v --tb=short`. Verify:

1. All 453+ existing tests pass (zero regressions).
2. All golden parity tests from task 4.3.5 pass.
3. All `--dump-tree` tests from tasks 4.3.3-4.3.4 pass.
4. All simulation oracle tests (tests/simulation/) pass (when iverilog available).
5. Total test count has increased (new tests from Plans 4.1, 4.2, 4.3 combined).
6. `mypy --strict src/sva2rtl/` exits 0.
7. `ruff check src/sva2rtl/ tests/` exits 0.

If any simulation test fails, investigate whether the normalize insertion caused a behavioral change (should not happen given Plan 4.1 guarantees, but verify).
</action>
<acceptance_criteria>
- `pytest tests/ --tb=short` exits 0 with 0 failures
- Total test count > 470 (453 existing + new Phase 4 tests)
- `mypy --strict src/sva2rtl/` exits 0
- `ruff check src/sva2rtl/ tests/` exits 0
- No simulation oracle test failures (behavioral equivalence confirmed)
- `--dump-tree` flag works end-to-end on a real SVA file with slang
</acceptance_criteria>
</task>

## Verification

```bash
# Full test suite passes with new tests
pytest tests/ -v --tb=short

# Golden parity specifically
pytest tests/test_golden_parity.py -v

# Dump-tree tests
pytest tests/test_dump_tree.py -v

# Simulation oracle (requires iverilog)
pytest tests/simulation/ -v

# Type checking and linting
mypy --strict src/sva2rtl/
ruff check src/sva2rtl/ tests/
```

## must_haves

- [ ] `--dump-tree` flag prints structured tree with hashes and exits 0 (no RTL emitted)
- [ ] `--dump-tree` output shows pre-normalized IR section and composition tree section
- [ ] All 29 golden files regenerate byte-for-byte through normalize->compose->emit pipeline
- [ ] All simulation oracle tests pass unmodified (behavioral equivalence)
- [ ] Complex compositions compile without error (Phase 4 success criteria)
- [ ] Total test count > 470; zero failures
- [ ] mypy --strict and ruff clean across entire codebase
