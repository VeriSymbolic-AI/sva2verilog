# Phase 6: CLI Polish + Verilog-2001 + Integration Testing - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers a production-ready v1.0 release of sva2rtl: full CLI debug modes (`--dump-ast`, `--dump-ir`, `--property`), Verilog-2001 compatible output via `--verilog` flag, a locked integration test suite covering all 40 v1 requirements, GitHub Actions CI, and release packaging (versioning, pyproject.toml, README).

</domain>

<decisions>
## Implementation Decisions

### Verilog-2001 Conversion
- **D-01:** Use Jinja2 conditional branches (`{% if verilog_mode %}`) within existing templates. Single source of truth — no duplicate template set. The emitter passes `verilog_mode: bool` to all template render calls based on the `--verilog` CLI flag. Conversion rules:
  - `input logic X` → `input X` (wire is default in Verilog-2001)
  - `output logic X` → `output reg X` (for registered outputs) or `output X` (for wire/assign outputs)
  - `logic X` (internal) → `reg X` (if in always block) or `wire X` (if assign)
  - `always_ff @(posedge clk)` → `always @(posedge clk)`
  - `always_comb` → `always @(*)` or `assign` (context-dependent)
  - `'0` / `'1` → `1'b0` / `1'b1`
  - All 12 templates updated with these guards

### --dump-ir Output Format
- **D-02:** Indented tree format with each node showing type, key parameters, and source location. Example:
  ```
  PropImplication (op='|->')
    antecedent:
      BoolExpr (text='a', loc=test.sv:3:25)
    consequent:
      SeqConcat
        elements:
          - BoolExpr (text='b', loc=test.sv:3:33)
        delays:
          - (2, 5)  // ##[2:5]
  ```
  Implemented in a new `format_dump_ir()` function in `debug.py` (mirrors `format_dump_tree()` pattern). 2-space indentation per level. No color codes (plain text for piping).

### --property Selection + Multi-Property Handling
- **D-03:** Default behavior: compile ALL `assert property` statements in the input file, each generating an independent monitor. `--property <name>` filters by label (exact match on the property label extracted from SVA). On no match: exit code 2 with error message listing all available property labels. On match: compile only that property. This is a filter, not a new mode — the pipeline runs identically but only emits the matched property's output.

### CI + Release Strategy
- **D-04:** GitHub Actions with matrix: `ubuntu-latest` + `macos-latest`, Python 3.12 + 3.13. Icarus Verilog installed via `apt-get install iverilog` (Ubuntu) and `brew install icarus-verilog` (macOS). Test suite split: `pytest tests/ --timeout=120` for unit/golden/integration; simulation tests run only when iverilog is available (graceful skip otherwise). uv for dependency management. slang installed via prebuilt binary download in CI.

### Documentation Language
- **D-05:** English README.md as primary (international open-source standard). Chinese README_zh.md as secondary copy. Both include: quick-start install, first usage example, supported SVA operators table, CLI reference, architecture overview, license.

### Claude's Discretion
- `--dump-ast` implementation details (likely just pretty-prints the slang JSON with indentation)
- Integration test organization (per-requirement vs per-operator grouping)
- `SUPPORTED_CONSTRUCTS.md` structure and operator examples
- Error code table format (SVA-E001 through SVA-Exx)
- `pyproject.toml` metadata details (classifiers, URLs, entry_points)
- `--version` flag implementation (click built-in or manual)
- Golden file locking strategy for optimized output

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap
- `.planning/ROADMAP.md` Phase 6 section — Plan breakdown (6.1-6.4), success criteria, requirements
- `.planning/REQUIREMENTS.md` — CLI-01 through CLI-04 (CLI flags), OUT-05 (Verilog-2001 output)

### Architecture & Patterns
- `.planning/PROJECT.md` — Technology stack (click 8.x, Jinja2 3.1.6, uv, ruff, mypy)
- `.planning/phases/05-optimization-passes/05-CONTEXT.md` — D-04 (--no-optimize flag pattern), D-13 (--dump-tree summary format), D-15 (user-facing flag conventions)
- `.planning/phases/04-normalization-composition-engine/04-CONTEXT.md` — Composition engine patterns, CheckerNode tree structure

### Existing Implementation (patterns to follow)
- `src/sva2rtl/cli.py` — Current CLI structure (click options, pipeline order)
- `src/sva2rtl/debug.py` — `format_dump_tree()` pattern for --dump-ir implementation
- `src/sva2rtl/emitter.py` — `emit_all()` template rendering (where verilog_mode gets passed)
- `templates/bool_expr.sv.j2` — Template structure reference for Jinja2 conditional guards
- `tests/test_golden_parity.py` — Golden file test pattern for integration tests

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `debug.py` `format_dump_tree()` — Direct pattern for `format_dump_ir()` implementation (same recursive walk + indentation approach)
- `emitter.py` `emit_all()` — Template rendering entry point; `verilog_mode` flag gets threaded here
- `cli.py` click decorator pattern — Well-established; `--dump-ir`, `--dump-ast`, `--property`, `--verilog`, `--version` follow identical pattern
- `tests/test_golden_parity.py` — Existing fixture→pipeline→compare infrastructure reusable for integration tests
- `tests/simulation/tb_generator.py` — Icarus Verilog testbench generation (reuse for `--verilog` validation)

### Established Patterns
- CLI pipeline order: `invoke_slang → import_assertion → normalize → compose → optimize → emit → write_output`
- `--dump-*` flags exit early (before emit) with exit code 0
- Template variables passed as flat dict to Jinja2 `render()` — add `verilog_mode` to this dict
- Golden files in `tests/golden/` with byte-for-byte comparison
- `@pytest.mark.simulation` for tests requiring iverilog

### Integration Points
- `emitter.py` `_render_template()` — Where `verilog_mode` parameter enters the template context
- `ast_importer.py` `import_assertion()` — Where `--property` filter logic applies (filter after import, before normalize)
- `frontend.py` `invoke_slang()` — Where `--dump-ast` exits (print raw JSON, exit 0)
- `pyproject.toml` — Entry point registration for `sva2rtl` CLI command

</code_context>

<specifics>
## Specific Ideas

- Verilog-2001 output should compile clean with `iverilog -g2001` — zero warnings
- `--dump-ir` shows the NORMALIZED IR (after normalizer, before composer) — this is a debugging window into IR transforms
- Error message for `--property` no-match should list all available labels so users can discover property names
- CI should run slang from prebuilt binary (not compile from source) — slang releases provide binaries

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-cli-polish-verilog-2001-integration-testing*
*Context gathered: 2026-05-28*
