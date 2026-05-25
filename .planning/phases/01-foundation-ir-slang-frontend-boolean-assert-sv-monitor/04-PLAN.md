---
phase: 1
plan: "04"
title: "CLI entry point + error handling"
wave: 3
depends_on: ["01", "02", "03"]
requirements: [CLI-05, CLI-06]
files_modified:
  - src/sva2rtl/cli.py
  - tests/test_cli.py
  - tests/fixtures/bool_assert.sv
  - tests/fixtures/delay_assert.sv
autonomous: true
estimated_minutes: 30
---

# Plan 04: CLI Entry Point + Error Handling

<objective>
Implement the click-based CLI entry point that wires the entire pipeline together: input file -> slang frontend -> AST importer -> composer -> emitter -> output file. The CLI maps all error types to correct exit codes and provides actionable error messages. After this plan, `uv run sva2rtl input.sv -o output.sv` works end-to-end.
</objective>

<threat_model>
- **File I/O:** Reads user-specified input file; writes to user-specified output path. Both are explicit user choices. No directory traversal concern beyond normal file operations.
- **Subprocess execution:** Delegates to `frontend.py` which runs slang. Already secured there (no shell=True, timeout, argument list).
- **Error disclosure:** Error messages include file paths and source locations. This is intentional for a developer tool — no secrets in SVA source files.
</threat_model>

<tasks>

## Task 1: Implement cli.py — Click entry point

<read_first>
- src/sva2rtl/frontend.py (invoke_slang function signature)
- src/sva2rtl/ast_importer.py (import_assertion function signature)
- src/sva2rtl/composer.py (compose function signature)
- src/sva2rtl/emitter.py (emit, write_output function signatures)
- src/sva2rtl/errors.py (all error classes for exception handling)
- .planning/phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-RESEARCH.md (Research Q7: CLI error handler pattern)
</read_first>

<action>
Create `src/sva2rtl/cli.py` with:

1. `main()` function decorated with `@click.command()`:
   - `@click.argument("input_file", type=click.Path(exists=True))`
   - `@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (default: stdout)")`
   - `@click.option("--slang-path", default="slang", envvar="SLANG_PATH", help="Path to slang binary")`

2. Pipeline orchestration inside `main`:
   - Call `invoke_slang(Path(input_file), slang_path)` -> get ast dict
   - Call `import_assertion(ast)` -> get (node, clock, original_text, label)
   - Call `compose(node, clock, label, original_text)` -> get checker_node
   - Call `emit(checker_node)` -> get sv_text
   - Call `write_output(sv_text, Path(output) if output else None)`
   - On success: `sys.exit(0)`

3. Exception handler (wrapping the pipeline):
   - `except SlangNotFound as e:` -> `click.echo(str(e), err=True)` + `sys.exit(3)`
   - `except UnsupportedConstruct as e:` -> `click.echo(str(e), err=True)` + `sys.exit(2)`
   - `except SvaError as e:` -> `click.echo(str(e), err=True)` + `sys.exit(1)`
   - `except Exception as e:` -> `click.echo(f"internal error: {e}", err=True)` + `sys.exit(1)`

Imports: click, sys, pathlib.Path, all pipeline modules and error classes.
</action>

<acceptance_criteria>
- `src/sva2rtl/cli.py` exists with a `main` function decorated by `@click.command()`
- `main` accepts `input_file` as positional argument and `--output`, `--slang-path` as options
- `--slang-path` has envvar="SLANG_PATH"
- SlangNotFound -> sys.exit(3)
- UnsupportedConstruct -> sys.exit(2)
- SvaError -> sys.exit(1)
- Unexpected Exception -> sys.exit(1) with "internal error:" prefix
- Success path calls all pipeline functions in correct order
- `uv run mypy src/sva2rtl/cli.py --strict` reports zero errors
</acceptance_criteria>

## Task 2: Create SVA test input files

<read_first>
- .planning/phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-RESEARCH.md (Research Q1: input SV examples)
</read_first>

<action>
Create test input SystemVerilog files:

1. `tests/fixtures/bool_assert.sv`:
```
module test_bool(input logic clk, rst_n, a, b);
  my_check: assert property (@(posedge clk) a && b);
endmodule
```

2. `tests/fixtures/delay_assert.sv` (for testing unsupported construct rejection):
```
module test_delay(input logic clk, rst_n, a, b);
  assert property (@(posedge clk) a ##1 b);
endmodule
```

These are real SV files that slang can parse (used in integration tests when slang is available).
</action>

<acceptance_criteria>
- `tests/fixtures/bool_assert.sv` exists with a labeled boolean assertion `my_check:`
- `tests/fixtures/delay_assert.sv` exists with `##1` (unsupported in Phase 1)
- Both files are syntactically valid SystemVerilog
- `bool_assert.sv` contains `@(posedge clk)` clock annotation
- `bool_assert.sv` module is named `test_bool`
</acceptance_criteria>

## Task 3: CLI unit and integration tests

<read_first>
- src/sva2rtl/cli.py (the module under test)
- src/sva2rtl/errors.py (error classes being tested)
- tests/fixtures/bool_assert.sv (test input)
- tests/fixtures/bool_simple.json (JSON fixture for mocking)
</read_first>

<action>
Create `tests/test_cli.py` with:

1. `test_cli_help()`: invoke CLI with `--help`, assert exit code 0 and output contains "input_file"
2. `test_cli_missing_input()`: invoke CLI with nonexistent file, assert non-zero exit code
3. `test_cli_slang_not_found()`: mock `invoke_slang` to raise `SlangNotFound`; assert exit code 3 and stderr contains "Install:"
4. `test_cli_unsupported_construct()`: mock `import_assertion` to raise `UnsupportedConstruct(message="msg", construct_name="##N", source_loc=SourceLoc("f.sv", 3, 5))`; assert exit code 2 and stderr contains "SVA-E002"
5. `test_cli_compile_error()`: mock `invoke_slang` to raise `SvaCompileError`; assert exit code 1
6. `test_cli_success_stdout()`: mock entire pipeline to return valid SV text; assert exit code 0 and stdout contains "module sva_"
7. `test_cli_success_output_file()`: mock pipeline; use `--output` with temp file; assert file created with content

Use `click.testing.CliRunner` for all tests. Use `unittest.mock.patch` to mock pipeline functions.
</action>

<acceptance_criteria>
- `tests/test_cli.py` exists with at least 7 test functions
- All tests use `click.testing.CliRunner` (not subprocess)
- `test_cli_slang_not_found` verifies exit code == 3
- `test_cli_unsupported_construct` verifies exit code == 2 and "SVA-E002" in output
- `test_cli_compile_error` verifies exit code == 1
- `test_cli_success_stdout` verifies exit code == 0
- `uv run pytest tests/test_cli.py -v` shows all tests passing
- `uv run ruff check tests/test_cli.py` reports zero violations
</acceptance_criteria>

</tasks>

<verification>
```bash
# All verification steps must pass:
uv run pytest tests/test_cli.py -v  # all pass
uv run mypy src/sva2rtl/cli.py --strict  # zero errors
uv run ruff check src/ tests/  # zero violations

# CLI responds to --help:
uv run sva2rtl --help  # exits 0, shows usage

# Exit code mapping (with mocked/absent slang):
uv run sva2rtl --slang-path /nonexistent/binary tests/fixtures/bool_assert.sv 2>/dev/null; echo $?  # -> 3
```
</verification>

<must_haves>
## truths
- Exit code 0 = success (output file written)
- Exit code 1 = compile error (slang parse failure or internal error)
- Exit code 2 = unsupported construct (with source location and construct name in message)
- Exit code 3 = slang not found (with install URL in message)
- CLI never silently miscompiles — unknown/unsupported constructs always produce non-zero exit
- Pipeline functions are called in order: invoke_slang -> import_assertion -> compose -> emit -> write_output

## goal_backward
- Provides the `sva2rtl` CLI command that is the primary user interface
- Satisfies CLI-05 (exit codes) and CLI-06 (unsupported construct error messages)
- Enables end-to-end testing in Plan 05
</must_haves>
