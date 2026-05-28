# Plan 6.1: CLI Flags + Multi-Property Support + `--dump-ir`

---
wave: 1
depends_on: []
files_modified:
  - src/sva2rtl/cli.py
  - src/sva2rtl/debug.py
  - src/sva2rtl/ast_importer.py
  - src/sva2rtl/errors.py
  - tests/test_cli_phase6.py
autonomous: true
---

## Goal

Deliver all Phase 6 CLI flags as a complete vertical slice: `--dump-ast`, `--dump-ir`, `--property`, `--verilog` (flag wiring only, template changes in 6.2), `--version`, plus multi-property pipeline support. Each flag is independently testable via CliRunner.

## Requirements

- **CLI-01**: Single entry point with `--output`, `--property`, `--verilog`, `--slang-path` flags
- **CLI-02**: `--dump-ast` prints slang JSON AST and exits
- **CLI-03**: `--dump-ir` prints normalized SVA IR tree and exits
- **CLI-04**: `--dump-tree` prints CheckerNode tree and exits (already exists; verify integration)

## Threat Model

<threat_model>
- **Path traversal via --output / --slang-path**: Mitigated by click.Path validation (exists=True for input); output writes only to user-specified path; slang-path used only as subprocess binary (no path concatenation)
- **Command injection via --slang-path**: Already mitigated in frontend.py (subprocess.run with list args, not shell=True)
- **DoS via malicious input**: slang subprocess has implicit timeout from OS; Python JSON parsing has built-in size limits; no infinite loops in importer
</threat_model>

## Tasks

<task id="6.1.1">
<title>Add `import_all_assertions()` to ast_importer.py</title>
<read_first>
- src/sva2rtl/ast_importer.py (current `import_assertion()`, `_find_assertion_in_members()`)
- src/sva2rtl/ir.py (SVANode, ClockSpec types)
</read_first>
<action>
Add public function `import_all_assertions(ast: dict[str, Any]) -> list[tuple[SVANode, ClockSpec, str, str | None]]` that collects ALL ConcurrentAssertions (not just the first). Reuse existing `_collect_declarations()` first-pass and create `_find_all_assertions_in_members()` which returns a list instead of the first match. The existing `import_assertion()` should remain unchanged (backwards compatible). Add type annotations matching the existing return type pattern.
</action>
<acceptance_criteria>
- `ast_importer.py` contains `def import_all_assertions(` with return type `list[tuple[SVANode, ClockSpec, str, str | None]]`
- For AST with 2 assertions, `import_all_assertions()` returns a list of length 2
- For AST with 0 assertions, raises `SvaCompileError` with "No concurrent assertion found"
- `import_assertion()` still works unchanged (returns first assertion only)
- `mypy --strict src/sva2rtl/ast_importer.py` exits 0
</acceptance_criteria>
</task>

<task id="6.1.2">
<title>Add `format_dump_ir()` to debug.py</title>
<read_first>
- src/sva2rtl/debug.py (existing `_format_ir()`, `format_dump_tree()`)
- src/sva2rtl/ir.py (SVANode types, SourceLoc field)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-CONTEXT.md (D-02 format spec)
</read_first>
<action>
Add public function `format_dump_ir(node: SVANode) -> str` that returns a formatted normalized IR tree with source locations shown on each node. Enhance the existing `_format_ir()` to accept an optional `show_loc: bool = False` parameter. When `show_loc=True`, each node line appends `, loc=<file>:<line>:<col>` from `node.source_loc`. The public `format_dump_ir()` wraps this with a header `=== Normalized IR ===` and calls `_format_ir(node, indent=0, show_loc=True)`. Follow D-02 output format: 2-space indentation, named child labels (`antecedent:`, `consequent:`, `body:`).
</action>
<acceptance_criteria>
- `debug.py` contains `def format_dump_ir(node: SVANode) -> str`
- Output starts with `=== Normalized IR ===`
- BoolExpr nodes show `loc=<file>:<line>:<col>` in output
- PropImplication shows `antecedent:` and `consequent:` labels
- DisableIff shows `body:` label
- `mypy --strict src/sva2rtl/debug.py` exits 0
</acceptance_criteria>
</task>

<task id="6.1.3">
<title>Add SVA-E005 error for `--property` no-match</title>
<read_first>
- src/sva2rtl/errors.py (existing error class hierarchy)
</read_first>
<action>
Add `PropertyNotFound` error class inheriting from `SvaError`. Fields: `property_name: str = ""`, `available: list[str] = field(default_factory=list)`. `__str__` format: `"error SVA-E005: property '<name>' not found. Available: [<comma-separated labels>]"`. This error maps to exit code 2 (same as UnsupportedConstruct — user input error, not compiler bug).
</action>
<acceptance_criteria>
- `errors.py` contains `class PropertyNotFound(SvaError):`
- `str(PropertyNotFound(message="", property_name="foo", available=["bar", "baz"]))` contains `SVA-E005` and `property 'foo' not found` and `bar` and `baz`
- `mypy --strict src/sva2rtl/errors.py` exits 0
</acceptance_criteria>
</task>

<task id="6.1.4">
<title>Implement all new CLI flags in cli.py</title>
<read_first>
- src/sva2rtl/cli.py (current main() function, existing flags, pipeline order)
- src/sva2rtl/debug.py (format_dump_ir signature from task 6.1.2)
- src/sva2rtl/ast_importer.py (import_all_assertions signature from task 6.1.1)
- src/sva2rtl/errors.py (PropertyNotFound from task 6.1.3)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-RESEARCH.md (pipeline exit points diagram)
</read_first>
<action>
Rewrite `main()` in cli.py to add these click decorators and pipeline changes:

1. `@click.version_option(package_name="sva2rtl")` — prints version, exits 0
2. `--dump-ast` (is_flag=True) — after `invoke_slang()`, print `json.dumps(ast, indent=2)`, exit 0
3. `--dump-ir` (is_flag=True) — after `normalize()`, print `format_dump_ir(node)`, exit 0
4. `--property` (type=str, default=None) — filter after `import_all_assertions()`; on no-match raise `PropertyNotFound`
5. `--verilog` (is_flag=True) — threaded to `emit()`/`emit_all()` as `verilog_mode=True`

Multi-property loop: replace `import_assertion(ast)` with `import_all_assertions(ast)`. When `--property` is given, filter list by label match. When multiple assertions present without `--property`, iterate and emit all. `PropertyNotFound` caught with exit code 2. Import `import_all_assertions` from `sva2rtl.ast_importer`. Import `PropertyNotFound` from `sva2rtl.errors`.

Pipeline exit order: invoke_slang → [--dump-ast] → import_all_assertions → [--property filter] → normalize → [--dump-ir] → compose → optimize → [--dump-tree] → emit(verilog_mode) → write_output.
</action>
<acceptance_criteria>
- `cli.py` contains `@click.version_option(package_name="sva2rtl")`
- `cli.py` contains `@click.option("--dump-ast"` with `is_flag=True`
- `cli.py` contains `@click.option("--dump-ir"` with `is_flag=True`
- `cli.py` contains `@click.option("--property"` with `type=str`
- `cli.py` contains `@click.option("--verilog"` with `is_flag=True`
- `cli.py` imports `import_all_assertions` and `PropertyNotFound`
- `PropertyNotFound` is caught and maps to `sys.exit(2)`
- `--dump-ast` path calls `json.dumps(ast, indent=2)` then `sys.exit(0)`
- `--dump-ir` path calls `format_dump_ir` then `sys.exit(0)`
- `mypy --strict src/sva2rtl/cli.py` exits 0
</acceptance_criteria>
</task>

<task id="6.1.5">
<title>Write tests for all new CLI flags</title>
<read_first>
- tests/test_cli.py (existing CliRunner patterns, mock fixtures)
- tests/test_dump_tree.py (existing --dump-tree test patterns with @requires_slang)
- src/sva2rtl/cli.py (updated main() from task 6.1.4)
</read_first>
<action>
Create `tests/test_cli_phase6.py` with tests:

1. `test_cli_version_flag` — `--version` exits 0, output contains "sva2rtl" and a version number pattern
2. `test_cli_dump_ast_exits_0` — mock `invoke_slang` returning a dict, assert `--dump-ast` exits 0, output is valid JSON
3. `test_cli_dump_ast_no_rtl_emitted` — with `--dump-ast`, assert `emit` is NOT called
4. `test_cli_dump_ir_exits_0` — mock pipeline through normalize(), assert `--dump-ir` exits 0, output contains `=== Normalized IR ===`
5. `test_cli_dump_ir_no_rtl_emitted` — with `--dump-ir`, assert `emit` is NOT called
6. `test_cli_property_filter_match` — mock `import_all_assertions` returning 2 assertions with labels "a" and "b"; `--property a` compiles only assertion "a"
7. `test_cli_property_filter_no_match_exits_2` — `--property nonexistent` exits 2, output contains `SVA-E005`
8. `test_cli_verilog_flag_passed_to_emit` — mock pipeline, assert `emit` or `emit_all` called with `verilog_mode=True`
9. `test_cli_multi_property_default_compiles_all` — without `--property`, all assertions are compiled

Use CliRunner + unittest.mock.patch pattern from test_cli.py. Each test: runner.invoke(main, [...]), assert exit_code, assert output content.
</action>
<acceptance_criteria>
- `tests/test_cli_phase6.py` exists with at least 9 test functions
- `uv run pytest tests/test_cli_phase6.py -v` exits 0 (all pass)
- Tests cover `--version`, `--dump-ast`, `--dump-ir`, `--property` (match + no-match), `--verilog` flag threading
- No test requires slang to be installed (all use mocks)
- `uv run ruff check tests/test_cli_phase6.py` exits 0
</acceptance_criteria>
</task>

## Verification

```bash
uv run mypy --strict src/sva2rtl/cli.py src/sva2rtl/debug.py src/sva2rtl/ast_importer.py src/sva2rtl/errors.py
uv run pytest tests/test_cli_phase6.py tests/test_cli.py tests/test_dump_tree.py -v
uv run ruff check src/ tests/
```

## must_haves

- `--dump-ast` prints JSON and exits 0 (CLI-02)
- `--dump-ir` prints normalized IR tree with source locations and exits 0 (CLI-03)
- `--property <name>` filters compilation to a single named assertion (CLI-01)
- `--property` no-match exits 2 with SVA-E005 listing available labels (CLI-01)
- `--verilog` flag exists and is threaded to emitter (CLI-01 partial, OUT-05 wiring)
- `--version` prints version and exits 0 (CLI-01)
- Multi-property support: all assertions compiled by default (CLI-01)
- All existing tests continue to pass (no regression)
