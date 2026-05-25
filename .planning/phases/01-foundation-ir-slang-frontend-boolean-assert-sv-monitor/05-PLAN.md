---
phase: 1
plan: "05"
title: "Unit test framework + Phase 1 tests"
wave: 4
depends_on: ["01", "02", "03", "04"]
requirements: [TEST-01, PARSE-05, OUT-02, OUT-03]
files_modified:
  - tests/conftest.py
  - tests/test_integration.py
  - tests/test_pipeline_e2e.py
  - tests/golden/bool_simple.sv
  - tests/golden/bool_labeled.sv
autonomous: true
estimated_minutes: 35
---

# Plan 05: Unit Test Framework + Phase 1 Tests

<objective>
Configure the complete test infrastructure (pytest, mypy strict, ruff) and write integration/end-to-end tests that validate the full Phase 1 pipeline. This includes golden file comparison tests, source-location threading validation, registered-output verification, and the test fixtures needed for CI. After this plan, `uv run pytest` validates the entire Phase 1 slice and `uv run mypy --strict` + `uv run ruff check` pass clean.
</objective>

<threat_model>
- **Test isolation:** Tests use fixtures and mocks; no network access. Integration tests that require slang are marked with `@pytest.mark.skipif` for environments without slang installed.
- **File system:** Tests write to temp directories (via `tmp_path` fixture); never modify source tree.
- **No secrets or external services involved.**
</threat_model>

<tasks>

## Task 1: Configure test infrastructure with conftest.py

<read_first>
- pyproject.toml (existing test configuration)
- tests/__init__.py (existing test package)
</read_first>

<action>
Create `tests/conftest.py` with:

1. Shared fixtures:
   - `@pytest.fixture` `fixtures_dir() -> Path`: returns `Path(__file__).parent / "fixtures"`
   - `@pytest.fixture` `golden_dir() -> Path`: returns `Path(__file__).parent / "golden"`
   - `@pytest.fixture` `sample_source_loc() -> SourceLoc`: returns `SourceLoc("test.sv", 3, 5)`
   - `@pytest.fixture` `sample_clock() -> ClockSpec`: returns `ClockSpec(edge="posedge", signal="clk", source_loc=SourceLoc("test.sv", 2, 3))`
   - `@pytest.fixture` `sample_bool_expr(sample_source_loc) -> BoolExpr`: returns `BoolExpr(text="(a && b)", source_loc=sample_source_loc)`

2. Conditional skip marker:
   - `has_slang = shutil.which("slang") is not None`
   - `requires_slang = pytest.mark.skipif(not has_slang, reason="slang binary not found")`

3. Helper function:
   - `def assert_golden(actual: str, golden_path: Path) -> None`: compares actual output against golden file content, stripping trailing whitespace per line; on mismatch, shows unified diff
</action>

<acceptance_criteria>
- `tests/conftest.py` exists with at least 5 fixtures defined
- `fixtures_dir` fixture returns a Path ending in `/tests/fixtures`
- `golden_dir` fixture returns a Path ending in `/tests/golden`
- `requires_slang` marker is defined and skips when slang is absent
- `assert_golden` helper provides unified diff on mismatch (uses `difflib.unified_diff`)
- `uv run pytest --co` (collect only) succeeds without import errors
</acceptance_criteria>

## Task 2: Integration tests — full pipeline without slang

<read_first>
- src/sva2rtl/ast_importer.py (import_assertion signature)
- src/sva2rtl/composer.py (compose signature)
- src/sva2rtl/emitter.py (emit signature)
- tests/fixtures/bool_simple.json (JSON fixture)
- tests/fixtures/bool_labeled.json (JSON fixture)
- tests/golden/bool_labeled.sv (expected output)
</read_first>

<action>
Create `tests/test_integration.py` with tests that exercise the pipeline from JSON fixture to emitted SV (bypassing slang subprocess):

1. `test_pipeline_bool_simple()`:
   - Load `tests/fixtures/bool_simple.json`
   - Call `import_assertion(ast)` -> get (node, clock, text, label)
   - Call `compose(node, clock, label, text)` -> get checker
   - Call `emit(checker)` -> get sv_text
   - Assert sv_text contains `"module sva_prop_"` (unlabeled -> hash-based name)
   - Assert sv_text contains `"always_ff"`
   - Assert sv_text contains `"attempt_fired"`

2. `test_pipeline_bool_labeled()`:
   - Load `tests/fixtures/bool_labeled.json`
   - Full pipeline -> sv_text
   - Assert sv_text contains `"module sva_my_check"`
   - Compare against `tests/golden/bool_labeled.sv` using `assert_golden`

3. `test_pipeline_source_loc_preserved()`:
   - Load fixture, run import_assertion
   - Assert returned BoolExpr.source_loc.line > 0
   - Assert returned BoolExpr.source_loc.file != "<unknown>"
   - Assert emitted SV contains `"// Source: "` followed by file:line:col

4. `test_pipeline_registered_outputs()`:
   - Run full pipeline on bool_simple fixture
   - Assert sv_text contains `"active_q"`, `"pass_q"`, `"fail_q"`, `"attempt_fired_q"` (all registered)
   - Assert sv_text does NOT contain `"assign active = start"` (no combinational output)
   - Assert sv_text contains `"<= 1'b0"` (synchronous reset to zero)

5. `test_pipeline_sync_reset()`:
   - Run full pipeline
   - Assert sv_text contains `"if (!rst_n)"` (synchronous reset present)
   - Assert count of `"<= 1'b0"` occurrences >= 4 (all 4 FFs reset)

6. `test_pipeline_unsupported_raises()`:
   - Load `tests/fixtures/unsupported_delay.json`
   - Assert `import_assertion` raises `UnsupportedConstruct`
   - Assert exception has non-None `source_loc`
   - Assert "SVA-E002" in str(exception)
</action>

<acceptance_criteria>
- `tests/test_integration.py` exists with at least 6 test functions
- All tests pass with `uv run pytest tests/test_integration.py -v`
- `test_pipeline_bool_labeled` does golden file comparison
- `test_pipeline_source_loc_preserved` verifies SourceLoc threading (PARSE-05)
- `test_pipeline_registered_outputs` verifies no combinational outputs (OUT-02)
- `test_pipeline_sync_reset` verifies synchronous reset on all FFs (OUT-03)
- No test requires slang binary (all use JSON fixtures)
</acceptance_criteria>

## Task 3: End-to-end tests with slang (conditional)

<read_first>
- src/sva2rtl/cli.py (CLI entry point)
- tests/fixtures/bool_assert.sv (SV input file)
- tests/fixtures/delay_assert.sv (unsupported input)
- tests/conftest.py (requires_slang marker)
</read_first>

<action>
Create `tests/test_pipeline_e2e.py` with end-to-end tests that require slang binary (marked with `@requires_slang`):

1. `@requires_slang test_e2e_bool_assert()`:
   - Use `click.testing.CliRunner` to invoke `main` with `tests/fixtures/bool_assert.sv` and `--output` to tmp_path
   - Assert exit code == 0
   - Assert output file exists and contains `"module sva_my_check"`
   - Assert output file contains `"attempt_fired"`

2. `@requires_slang test_e2e_delay_assert_rejected()`:
   - Use CliRunner to invoke `main` with `tests/fixtures/delay_assert.sv`
   - Assert exit code == 2
   - Assert stderr contains "SVA-E002" or "unsupported"

3. `@requires_slang test_e2e_output_compiles_iverilog()`:
   - Skip if `shutil.which("iverilog")` is None
   - Run full pipeline on `bool_assert.sv` -> output to tmp_path
   - Run `subprocess.run(["iverilog", "-g2012", str(output_path)])` 
   - Assert returncode == 0 (compiles clean)

4. `@requires_slang test_e2e_slang_bad_path()`:
   - Use CliRunner with `--slang-path /nonexistent/slang`
   - Assert exit code == 3
   - Assert output contains "Install:" or "slang not found"

5. `test_e2e_nonexistent_input()`:
   - Use CliRunner with a nonexistent file path
   - Assert exit code != 0 (click reports missing file)
</action>

<acceptance_criteria>
- `tests/test_pipeline_e2e.py` exists with at least 5 test functions
- Tests 1-4 are decorated with `@requires_slang` (skip when slang absent)
- Test 3 additionally skips when iverilog is absent
- `test_e2e_bool_assert` verifies exit code 0 and output file content
- `test_e2e_delay_assert_rejected` verifies exit code 2
- `test_e2e_slang_bad_path` verifies exit code 3
- Tests that don't need slang (test 5) run unconditionally
- `uv run pytest tests/test_pipeline_e2e.py -v` runs (some may skip due to missing binaries)
</acceptance_criteria>

## Task 4: Full test suite validation + linting

<read_first>
- pyproject.toml (tool.mypy and tool.ruff configuration)
- src/sva2rtl/ (all source files)
- tests/ (all test files)
</read_first>

<action>
Run the complete validation suite and fix any issues:

1. `uv run pytest tests/ -v` — all tests must pass (with slang-dependent tests skipping gracefully)
2. `uv run mypy src/sva2rtl --strict` — zero errors
3. `uv run ruff check src/ tests/` — zero violations
4. `uv run ruff format --check src/ tests/` — formatting compliant

Fix any type annotation issues, missing imports, or lint violations discovered. Ensure all `__init__.py` files have proper `__all__` exports if needed for mypy.
</action>

<acceptance_criteria>
- `uv run pytest tests/ -v` exits with code 0 (all non-skipped tests pass)
- `uv run mypy src/sva2rtl --strict` exits with code 0 (zero type errors)
- `uv run ruff check src/ tests/` exits with code 0 (zero lint violations)
- No test uses `# type: ignore` without justification comment
- All test files follow naming convention `test_*.py`
- Total test count >= 30 (across all test files from Plans 01-05)
</acceptance_criteria>

</tasks>

<verification>
```bash
# Complete Phase 1 validation — ALL of these must pass:
uv sync
uv run pytest tests/ -v --tb=short  # all non-skipped tests pass
uv run mypy src/sva2rtl --strict    # zero type errors
uv run ruff check src/ tests/       # zero lint violations

# Test count check:
uv run pytest tests/ --co -q | tail -1  # should show >= 30 tests collected

# Integration proof (with slang, if available):
if command -v slang &>/dev/null; then
  uv run sva2rtl tests/fixtures/bool_assert.sv -o /tmp/sva_test.sv && echo "EXIT 0 OK"
  grep -q "module sva_my_check" /tmp/sva_test.sv && echo "MODULE NAME OK"
  grep -q "attempt_fired" /tmp/sva_test.sv && echo "ATTEMPT_FIRED OK"
  if command -v iverilog &>/dev/null; then
    iverilog -g2012 /tmp/sva_test.sv && echo "IVERILOG COMPILE OK"
  fi
fi
```
</verification>

<must_haves>
## truths
- All Phase 1 unit tests pass without slang binary (fixture-based)
- End-to-end tests gracefully skip when slang/iverilog not available
- mypy --strict passes on entire src/sva2rtl package (strict typing)
- ruff passes on all source and test files (code quality)
- Golden file tests lock down emitter output (prevents regression)
- Source location is verified as threaded from JSON through to emitted comment (PARSE-05)
- Registered outputs (OUT-02) and synchronous reset (OUT-03) are explicitly asserted in tests

## goal_backward
- Satisfies TEST-01 (unit tests per module: ir, ast_importer, composer, emitter, cli)
- Validates PARSE-05 (source location threading) via integration test assertions
- Validates OUT-02 (registered outputs) and OUT-03 (sync reset) via template output assertions
- Provides the test infrastructure that all future phases build upon
- Completes Phase 1: after this plan, `sva2rtl bool_assert.sv` produces a valid SV monitor
</must_haves>
