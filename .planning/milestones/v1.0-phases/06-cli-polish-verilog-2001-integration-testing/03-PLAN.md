---
wave: 2
depends_on: ["01", "02"]
files_modified:
  - .github/workflows/ci.yml
  - tests/test_integration_full.py
  - pyproject.toml
  - src/sva2rtl/cli.py
autonomous: true
---

# Plan 6.3: Integration Tests + CI + Release Polish

## Goal

Lock the integration test suite covering all Phase 6 requirements (CLI-01 through CLI-04, OUT-05), set up GitHub Actions CI, and finalize release metadata. This plan validates that Plans 6.1 and 6.2 work together end-to-end and creates the CI guard for all future work.

## Requirements

- **CLI-01**: Single entry point with `--output`, `--property`, `--verilog`, `--slang-path` flags (integration verification)
- **CLI-02**: `--dump-ast` prints slang JSON AST and exits (integration verification)
- **CLI-03**: `--dump-ir` prints normalized SVA IR tree and exits (integration verification)
- **CLI-04**: `--dump-tree` prints CheckerNode tree and exits (integration verification)
- **OUT-05**: `--verilog` flag emits Verilog-2001 compatible output (iverilog -g2001 compile verification)

## Threat Model

<threat_model>
- **CI secret exposure**: No secrets needed (public repo tools only: slang binary, iverilog from package manager). No API keys or tokens used.
- **Supply chain attack via CI dependencies**: Pin action versions to SHA or major version (actions/checkout@v4, astral-sh/setup-uv@v4). Use uv lockfile for reproducible installs.
- **DoS via large test inputs**: All test fixtures are small (< 1KB JSON); no user-supplied inputs in CI.
</threat_model>

## Tasks

<task id="6.3.1">
<title>Create GitHub Actions CI workflow</title>
<read_first>
- pyproject.toml (current tool config, dependencies, scripts)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-RESEARCH.md (Section 6: CI Configuration, slang binary install, workflow structure)
- tests/conftest.py (simulation test skip logic)
</read_first>
<action>
Create `.github/workflows/ci.yml` with:

- Trigger: `on: [push, pull_request]`
- Matrix: `os: [ubuntu-latest, macos-latest]`, `python: ["3.12", "3.13"]`
- Steps:
  1. `actions/checkout@v4`
  2. `astral-sh/setup-uv@v4`
  3. `uv python install ${{ matrix.python }}`
  4. `uv sync --dev`
  5. Install iverilog: `apt-get install -y iverilog` (Linux) / `brew install icarus-verilog` (macOS)
  6. Install slang: download prebuilt binary from `https://github.com/MikePopoloski/slang/releases` (pin version); extract and add to PATH
  7. Lint: `uv run ruff check src/ tests/`
  8. Type check: `uv run mypy src/`
  9. Test: `uv run pytest tests/ --timeout=120 -v`

Use `if: runner.os == 'Linux'` / `if: runner.os == 'macOS'` for OS-conditional steps. Set `SLANG_PATH` env var pointing to installed binary.
</action>
<acceptance_criteria>
- `.github/workflows/ci.yml` exists and is valid YAML
- Workflow triggers on push and pull_request
- Matrix includes ubuntu-latest + macos-latest and Python 3.12 + 3.13
- Steps include: checkout, setup-uv, python install, uv sync, iverilog install, slang install, ruff check, mypy, pytest
- slang binary version is pinned (not `latest`)
- `SLANG_PATH` environment variable is set in test step
</acceptance_criteria>
</task>

<task id="6.3.2">
<title>Write end-to-end integration tests for Phase 6 requirements</title>
<read_first>
- tests/test_integration.py (existing integration test patterns, _run() helper)
- tests/test_golden_parity.py (parametrized pipeline test pattern)
- src/sva2rtl/cli.py (final CLI after plan 6.1)
- src/sva2rtl/emitter.py (final emitter after plan 6.2)
- tests/fixtures/ (available JSON fixtures)
</read_first>
<action>
Create `tests/test_integration_full.py` with requirement-tagged integration tests:

1. `test_cli01_all_flags_accepted` — invoke CLI with `--help`, verify all flags listed: `--output`, `--property`, `--verilog`, `--slang-path`, `--dump-ast`, `--dump-ir`, `--dump-tree`, `--no-optimize`, `--version`
2. `test_cli02_dump_ast_valid_json` — mock invoke_slang, run `--dump-ast`, parse output with `json.loads()` → must succeed
3. `test_cli03_dump_ir_shows_tree` — mock pipeline through normalize, run `--dump-ir`, verify `=== Normalized IR ===` header and node type names (e.g., `BoolExpr`, `PropImplication`)
4. `test_cli04_dump_tree_shows_checker` — run `--dump-tree`, verify `=== Composition Tree ===` header and `CheckerNode:` prefix
5. `test_out05_verilog_no_sv_keywords` — run full pipeline with `verilog_mode=True`, verify NO `logic`/`always_ff`/`'0` in output
6. `test_out05_verilog_compiles_iverilog` — (marked `@pytest.mark.simulation`) write Verilog-2001 output to tmpfile, run `iverilog -g2001 -o /dev/null <file>`, assert exit code 0
7. `test_multi_property_all_compiled` — create fixture with 2 labeled assertions, verify both generate monitors
8. `test_property_filter_single` — verify `--property` produces output only for the named assertion
9. `test_property_filter_not_found_lists_available` — verify SVA-E005 error lists available property names

Use CliRunner for CLI tests, direct API calls for emitter/pipeline tests. Tag simulation tests with `@pytest.mark.simulation`.
</action>
<acceptance_criteria>
- `tests/test_integration_full.py` exists with at least 9 test functions
- Each test has a docstring referencing the requirement ID it validates (e.g., "Validates CLI-02")
- `uv run pytest tests/test_integration_full.py -v -m "not simulation"` exits 0
- Test names contain requirement IDs (e.g., `test_cli02_`, `test_out05_`)
- `uv run ruff check tests/test_integration_full.py` exits 0
</acceptance_criteria>
</task>

<task id="6.3.3">
<title>Update pyproject.toml with release metadata and version bump</title>
<read_first>
- pyproject.toml (current content)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-RESEARCH.md (Section 8: pyproject.toml packaging)
</read_first>
<action>
Update `pyproject.toml`:

1. Bump `version = "0.1.0"` → `version = "1.0.0"`
2. Add `license = "BSL-1.1"` (Business Source License per CLAUDE.md)
3. Add `readme = "README.md"`
4. Add `keywords = ["sva", "systemverilog", "assertion", "rtl", "formal", "eda", "monitor", "synthesis"]`
5. Add `classifiers` list: Development Status 4 Beta, Intended Audience Developers, Topic Scientific/Engineering EDA, Programming Language Python 3.12, Programming Language Python 3.13
6. Add `[project.urls]` section with Homepage, Repository, Issues pointing to GitHub (use placeholder `https://github.com/YOUR_USER/sva2rtl` — user will replace)
7. Add `pytest-timeout` to dev dependencies for CI timeout support

Keep existing `[project.scripts]`, `[build-system]`, `[tool.hatch.build.targets.wheel]`, `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` sections unchanged except adding `"integration"` marker to pytest markers.
</action>
<acceptance_criteria>
- `pyproject.toml` has `version = "1.0.0"`
- `pyproject.toml` has `license = "BSL-1.1"`
- `pyproject.toml` has `keywords` list containing "sva" and "systemverilog"
- `pyproject.toml` has `[project.urls]` section
- `pyproject.toml` `classifiers` list has at least 3 entries
- `pyproject.toml` dev dependencies include `pytest-timeout`
- `uv sync --dev` succeeds after changes
- `uv run sva2rtl --version` prints `sva2rtl, version 1.0.0` (or similar format)
</acceptance_criteria>
</task>

<task id="6.3.4">
<title>Verify full test suite passes and confirm no regressions</title>
<read_first>
- tests/test_golden_parity.py (golden file tests)
- tests/test_cli.py (existing CLI tests)
- tests/test_cli_phase6.py (new CLI tests from plan 6.1)
- tests/test_verilog_mode.py (new Verilog tests from plan 6.2)
- tests/test_integration_full.py (new integration tests from task 6.3.2)
</read_first>
<action>
Run the complete test suite and fix any failures:

1. `uv run pytest tests/ -v --timeout=120 -m "not simulation"` — all non-simulation tests pass
2. `uv run mypy --strict src/` — zero errors
3. `uv run ruff check src/ tests/` — zero errors
4. `uv run pytest tests/test_golden_parity.py -v` — all golden files still match (no regression from template changes)

If golden files need regeneration due to template formatting changes (unlikely since verilog_mode defaults to False), update them. Confirm total test count is >= 577 (pre-existing) plus new tests from plans 6.1 and 6.2.
</action>
<acceptance_criteria>
- `uv run pytest tests/ -v --timeout=120 -m "not simulation"` exits 0
- `uv run mypy --strict src/` exits 0 with no errors
- `uv run ruff check src/ tests/` exits 0
- `uv run pytest tests/test_golden_parity.py -v` exits 0 (no golden file regression)
- Total test count >= 590 (577 existing + ~15 new tests from plans 6.1/6.2/6.3)
</acceptance_criteria>
</task>

## Verification

```bash
# Full suite (excluding simulation which requires iverilog):
uv run pytest tests/ -v --timeout=120 -m "not simulation"
# Quality gates:
uv run mypy --strict src/
uv run ruff check src/ tests/
# Golden parity (critical regression check):
uv run pytest tests/test_golden_parity.py -v
# Version check:
uv run sva2rtl --version
# CI YAML validation:
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```

## must_haves

- GitHub Actions CI workflow exists and covers: lint + typecheck + test on 2 OS x 2 Python versions
- Integration tests cover CLI-01, CLI-02, CLI-03, CLI-04, OUT-05 with passing assertions
- `pyproject.toml` version bumped to 1.0.0 with release metadata
- All existing 577+ tests continue to pass (zero regression)
- Golden parity tests pass (template changes in 6.2 didn't break default SV output)
- `--version` flag outputs correct version number
