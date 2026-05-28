# Phase 6: CLI Polish + Verilog-2001 + Integration Testing — Research

**Completed:** 2026-05-28
**Confidence:** HIGH across all areas

---

## 1. Current CLI Implementation (`cli.py` — 121 lines)

### Existing Flags
| Flag | Type | Status | Notes |
|------|------|--------|-------|
| `INPUT_FILE` | argument | Exists | `click.Path(exists=True)` |
| `--output` / `-o` | option | Exists | Output file path, default stdout |
| `--slang-path` | option | Exists | Binary path override, reads `SLANG_PATH` envvar |
| `--dump-tree` | flag | Exists | Prints CheckerNode tree + optimization summary, exits 0 |
| `--no-optimize` | flag | Exists | Skips optimizer pass |

### Flags to Add (Phase 6)
| Flag | Requirement | Implementation |
|------|-------------|----------------|
| `--dump-ast` | CLI-02 | Print raw slang JSON (pretty-printed), exit 0. Exits **before** `import_assertion`. |
| `--dump-ir` | CLI-03 | Print normalized IR tree, exit 0. Exits **after** `normalize()`, before `compose()`. |
| `--property <name>` | CLI-01 | Filter assertion by label. Applied **after** `import_assertion`. |
| `--verilog` | OUT-05 | Emit Verilog-2001 output. Threaded to emitter/templates. |
| `--version` | Release | Use `@click.version_option(package_name="sva2rtl")` |

### Pipeline Architecture & Exit Points
```
invoke_slang ─────── [--dump-ast exits here: print JSON, exit 0]
       │
import_assertion ──── [--property filters here: no-match → exit 2 + list labels]
       │
normalize ─────────── [--dump-ir exits here: print IR tree, exit 0]
       │
compose
       │
optimize (unless --no-optimize)
       │                [--dump-tree exits here: print tree, exit 0]
emit ─── (verilog_mode passed to templates)
       │
write_output
```

### Key Pattern: Early-exit flags
The existing `--dump-tree` pattern shows the idiom:
```python
if dump_tree:
    from sva2rtl.debug import format_dump_tree
    click.echo(format_dump_tree(...))
    sys.exit(0)
```
All new `--dump-*` flags should follow this exact pattern.

---

## 2. Template System — Verilog-2001 Conversion Inventory

### All 12 Templates (in `templates/`)
| Template | Has `logic`? | Has `always_ff`? | Has `'0`/`'1`? | Has params? | Notes |
|----------|:---:|:---:|:---:|:---:|-------|
| `bool_expr.sv.j2` | Yes | Yes | Yes (`'0`) | No | Simple leaf; inputs/outputs + `always_ff` |
| `concat_delay.sv.j2` | Yes | Yes | Yes (`'0`) | Yes (`CNT_WIDTH`) | Counter FSM; conditional `##0` path |
| `overlap_bitvec.sv.j2` | Yes | Yes | Yes (`'0`) | Yes (`BV_WIDTH`) | Child instances + shift register |
| `nonoverlap.sv.j2` | Yes | Yes | Yes (`'0`) | Yes (`BV_WIDTH`) | Child instances + 1-cycle delay register |
| `rose.sv.j2` | Yes | Yes | No | No | Edge detect + combinational outputs |
| `fell.sv.j2` | Yes | Yes | No | No | Edge detect + combinational outputs |
| `stable.sv.j2` | Yes | Yes | No | No | Edge detect + XNOR |
| `past.sv.j2` | Yes | Yes | Yes (`'0`) | Yes (`DEPTH`) | Shift register pipeline |
| `rep_consecutive.sv.j2` | Yes | Yes | Yes (`'0`) | Yes (`CNT_WIDTH`) | Counter-based FSM |
| `seq_concat_top.sv.j2` | Yes | No | No | No | Wire-only (no registers); child instances |
| `disable_iff_top.sv.j2` | Yes | No | No | No | Wire-only + child instance |
| `bind.sv.j2` | No | No | No | No | Pure bind statement (no module) |

### Verilog-2001 Conversion Rules (from D-01)

| SV Construct | Verilog-2001 Equivalent | Context |
|---|---|---|
| `input logic X` | `input X` | Port declarations |
| `output logic X` | `output reg X` (registered) or `output X` (wire/assign) | Port declarations |
| `logic X` (internal, in `always_ff`) | `reg X` | Internal signal declarations |
| `logic X` (internal, in `assign`) | `wire X` | Internal wire declarations |
| `always_ff @(posedge clk)` | `always @(posedge clk)` | Sequential blocks |
| `always_comb` | `always @(*)` | Combinational blocks (none in current templates) |
| `'0` | `{N{1'b0}}` or `1'b0` / `0` | Zero literals (context-dependent width) |
| `'1` | `{N{1'b1}}` or `1'b1` | One literals (not used currently) |

### Template-by-Template Conversion Specifics

**Critical observations from reading all templates:**

1. **All** 12 templates use `input logic` / `output logic` in port declarations
2. **9 of 12** templates use `always_ff @({{ clock_edge }} {{ clock_signal }})` (all except `seq_concat_top`, `disable_iff_top`, `bind`)
3. **7 of 12** use `'0` in reset assignments (e.g., `count_q <= '0;`)
4. `logic` is used for internal wire/reg declarations in **all** templates
5. **No** templates use `always_comb` — combinational logic uses `assign`
6. Parameterized modules use `#( parameter ... )` syntax — this is valid in both SV and Verilog-2001

**Jinja2 implementation approach:**
```jinja2
{% if verilog_mode %}
    input  {{ clock_signal }},
{% else %}
    input  logic {{ clock_signal }},
{% endif %}
```

For `'0` context, since it's only used in assignments where the LHS is always a declared `reg` with known width, we can use `0` (Verilog will zero-extend) or explicit `{WIDTH{1'b0}}`. The simplest correct approach: `<= '0` becomes `<= 0` in Verilog mode (`0` auto-sizes to the LHS width in Verilog-2001).

**Output port classification** (for `reg` vs `wire` in Verilog-2001):
- Ports driven by `always_ff` (registered) need `output reg`
- Ports driven by `assign` (combinational) stay as `output` (wire implicit)
- In current templates: `active`, `pass`, `fail`, `attempt_fired` are almost always wires (driven by `assign` from internal `_q` registers). Exception: templates without internal regs where outputs are directly assigned.

Actually, re-reading the templates carefully:
- **All output ports are driven by `assign` statements** (even `bool_expr.sv.j2` uses internal `_q` regs and then `assign active = ...`). So in Verilog-2001, all outputs can stay as `output` (wire is default).
- **Internal signals in `always_ff` blocks** become `reg` (e.g., `active_q`, `pass_q`, `count_q`, `running_q`, `bv_q`)
- **Internal signals in `assign` statements** become `wire` (e.g., `bool_result`, `rose_detect`, `overflow_event`)

### Template Variable Passing

The emitter currently builds context as:
```python
ctx: dict[str, object] = dict(checker.params)
ctx["observed_signals"] = checker.observed_signals
ctx["children"] = checker.children
```

Adding `verilog_mode`:
```python
ctx["verilog_mode"] = verilog_mode  # bool, from CLI flag
```

This requires threading `verilog_mode` through `emit()`, `emit_all()`, and `_emit_recursive()`.

---

## 3. `--dump-ir` Implementation

### Pattern from `format_dump_tree()` in `debug.py`
The existing function uses:
1. Match/case dispatch on SVANode type
2. 2-space indentation per nesting level  
3. Key fields displayed inline: `BoolExpr("text")`, `SeqConcat(delays=[...])`
4. Recursive descent into children

### `format_dump_ir()` — New function
Per D-02, shows the **NORMALIZED** IR (after `normalize()`, before `compose()`):
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

The existing `_format_ir()` private function in `debug.py` already does 90% of this work. Differences:
- D-02 format shows `loc=` source location on each node
- D-02 uses named child labels (e.g., `antecedent:`, `consequent:`)
- Current `_format_ir()` already handles all node types

Implementation: Refactor `_format_ir()` or create `format_dump_ir()` as a thin public wrapper that calls an enhanced version of `_format_ir()` with `show_loc=True`.

---

## 4. `--property` Multi-Property Handling

### Current State
`import_assertion()` finds the **first** `ConcurrentAssertion` in the AST and returns it. It does NOT support multiple assertions per file.

### What Needs to Change (D-03)
1. **New function**: `import_all_assertions(ast) -> list[tuple[SVANode, ClockSpec, str, str | None]]` — finds ALL assertions, returns a list
2. **CLI behavior**:
   - Default (no `--property`): compile ALL assertions, emit one monitor per assertion
   - `--property <name>`: filter by label (exact match). On no-match: exit 2 with available labels listed
3. **Label extraction**: Labels come from slang Block nodes wrapping ConcurrentAssertion. Already handled by `_extract_label()`.

### Impact on Pipeline
The current pipeline is single-assertion:
```python
node, clock, text, label = import_assertion(ast)
```

Multi-property changes this to:
```python
assertions = import_all_assertions(ast)
if property_filter:
    assertions = [a for a in assertions if a[3] == property_filter]
    if not assertions:
        available = [a[3] for a in import_all_assertions(ast) if a[3]]
        click.echo(f"error: property '{property_filter}' not found. Available: {available}", err=True)
        sys.exit(2)
for node, clock, text, label in assertions:
    node = normalize(node)
    checker = compose(node, clock, label, text)
    # ... emit each
```

---

## 5. `--dump-ast` Implementation

Per D-01 (Claude's discretion): simply pretty-print the slang JSON:
```python
if dump_ast:
    import json
    ast = invoke_slang(Path(input_file), slang_path)
    click.echo(json.dumps(ast, indent=2))
    sys.exit(0)
```

Exits **before** `import_assertion` — raw slang output, no processing.

---

## 6. GitHub Actions CI Configuration

### Matrix (D-04)
- OS: `ubuntu-latest`, `macos-latest`
- Python: `3.12`, `3.13`
- iverilog: `apt-get install iverilog` (Ubuntu), `brew install icarus-verilog` (macOS)
- slang: prebuilt binary from GitHub releases

### Slang Binary Installation in CI
[slang releases](https://github.com/MikePopoloski/slang/releases) provide prebuilt binaries for Linux and macOS. CI workflow step:
```yaml
- name: Install slang
  run: |
    SLANG_VERSION="v7.0"  # pin to specific version
    if [ "${{ runner.os }}" == "Linux" ]; then
      wget https://github.com/MikePopoloski/slang/releases/download/${SLANG_VERSION}/slang-linux.tar.gz
      tar xzf slang-linux.tar.gz
      sudo mv slang /usr/local/bin/
    elif [ "${{ runner.os }}" == "macOS" ]; then
      wget https://github.com/MikePopoloski/slang/releases/download/${SLANG_VERSION}/slang-macos.tar.gz
      tar xzf slang-macos.tar.gz
      sudo mv slang /usr/local/bin/
    fi
```

### Test Suite Split
- `pytest tests/ --timeout=120` — all tests (unit + golden + integration)
- Simulation tests auto-skip when iverilog not available (existing `conftest.py` handles this)
- Additional marker consideration: `@pytest.mark.integration` for Phase 6 end-to-end tests

### Workflow Structure
```yaml
name: CI
on: [push, pull_request]
jobs:
  test:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest]
        python: ["3.12", "3.13"]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - name: Install Python
        run: uv python install ${{ matrix.python }}
      - name: Install dependencies
        run: uv sync --dev
      - name: Install iverilog
        run: |  # OS-conditional
      - name: Install slang
        run: |  # prebuilt binary
      - name: Lint (ruff)
        run: uv run ruff check src/ tests/
      - name: Type check (mypy)
        run: uv run mypy src/
      - name: Test
        run: uv run pytest tests/ --timeout=120 -v
```

---

## 7. Verilog-2001 vs SystemVerilog — Key Differences for Templates

### Compilation Verification
`iverilog -g2001` restricts to IEEE 1364-2001 only. Key restrictions:
- No `logic` keyword (use `wire`/`reg`)
- No `always_ff` / `always_comb` (use `always @(...)`)
- No `'0` / `'1` width-inferred literals
- `parameter` declarations in module headers are valid (Verilog-2001 ANSI style)
- Concatenation `{a, b}` and part-select `[N:M]` are valid
- Ternary `? :` is valid
- `1'b0`, `1'b1` are valid
- `assign` statements are valid
- Module instantiation syntax is the same

### What Stays Identical
- Module header structure (`module name #(...) (...);`)
- `parameter` declarations (ANSI-style)
- `assign` statements
- Concatenation/replication operators
- `@(posedge clk)` event syntax
- Instance declarations (port-by-name)
- `endmodule`
- Comments (`//`)

### Summary: Only 3 Categories of Change
1. **Port declarations**: `input logic X` → `input X`; `output logic X` → `output X` or `output reg X`
2. **Internal signals**: `logic X` → `reg X` or `wire X` (context-dependent)
3. **Sequential blocks**: `always_ff @(...)` → `always @(...)`
4. **Literal zero**: `'0` → `0` (auto-sizing works in Verilog-2001 for `<=` assignments)

---

## 8. `pyproject.toml` Packaging

### Current State
Already has:
- `[project.scripts]` entry point: `sva2rtl = "sva2rtl.cli:main"`
- `hatchling` build system
- `requires-python = ">=3.12"`
- Dependencies: `click>=8.0`, `jinja2>=3.1.6`
- Dev dependencies: `hypothesis`, `mypy`, `pytest`, `ruff`

### What to Add for Release
```toml
[project]
version = "1.0.0"  # update from 0.1.0
license = "BSL-1.1"
authors = [
    { name = "Allen Li", email = "..." },
]
readme = "README.md"
keywords = ["sva", "systemverilog", "assertion", "rtl", "formal", "eda", "monitor"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]

[project.urls]
Homepage = "https://github.com/<user>/sva2rtl"
Repository = "https://github.com/<user>/sva2rtl"
Issues = "https://github.com/<user>/sva2rtl/issues"
```

### `--version` Implementation
```python
@click.version_option(package_name="sva2rtl")
```
This reads the version from `importlib.metadata` (no hardcoded string needed). Works with `uv pip install -e .` and normal installs.

---

## 9. Integration Test Architecture

### Current Test Infrastructure
- **577 tests** total (577 pass, 17 skip)
- Golden parity: `test_golden_parity.py` — 16 parametrized tests covering 29+ golden files
- Simulation: `tests/simulation/` — 8 test files with `@check_iverilog()` auto-skip
- Unit tests: per-module (ir, ast_importer, normalizer, composer, optimizer, emitter, etc.)

### Integration Test Plan (6.3)
Per requirement, need end-to-end tests covering all 40 v1 requirements. Most already exist:

| Requirement Group | Existing Tests | Gaps |
|---|---|---|
| PARSE-01..05 | test_ast_importer.py, test_frontend.py | Covered |
| OP-01..10 | test_sequential.py, test_signal_functions.py, test_repetition.py, simulation/ | Covered |
| OUT-01..08 | test_emitter.py, golden files, test_bind.py | OUT-05 (Verilog-2001) NEW |
| PIPE-01..05 | test_normalizer.py, test_optimizer.py | Covered |
| CLI-01..06 | test_cli.py | CLI-01..04 NEW (Phase 6) |
| TEST-01..06 | Already validated by existence of tests | Meta-requirement |

### New Test Files Needed
1. `tests/test_verilog_mode.py` — Verilog-2001 output tests:
   - Each template generates valid `iverilog -g2001` output
   - Golden files for Verilog-2001 variants
   - Semantic equivalence (simulation results match SV output)
2. `tests/test_cli_phase6.py` — New CLI flag tests:
   - `--dump-ast` outputs valid JSON and exits 0
   - `--dump-ir` outputs tree text and exits 0
   - `--property` filters correctly / exits 2 on no-match
   - `--verilog` produces Verilog-2001 output
   - `--version` prints version and exits 0
3. `tests/test_integration_full.py` — Requirement-tagged integration tests (traceability)

---

## 10. Error Code Table Structure

### Existing Error Codes
| Code | Error Class | Meaning |
|------|-------------|---------|
| SVA-E002 | `UnsupportedConstruct` | Unsupported SVA construct |
| SVA-E003 | `SvaCompileError` | Circular sequence ref / invalid delay range |
| SVA-E004 | `SvaCompileError` | Signal function missing argument |

### Proposed Full Table (for `SUPPORTED_CONSTRUCTS.md`)
Extend the naming convention:
- `SVA-E001`: General compile error (slang failure)
- `SVA-E002`: Unsupported construct (with suggestion)
- `SVA-E003`: Invalid sequence structure (circular, invalid range)
- `SVA-E004`: Invalid function call (missing args)
- `SVA-E005`: Property not found (--property filter failed)
- `SVA-E006`: No assertion found in input file

---

## 11. Key Implementation Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| `'0` → `0` conversion may cause width mismatch warnings in iverilog | Medium | Test each template with `iverilog -g2001 -Wall`; use explicit `{N{1'b0}}` where needed |
| `output reg` vs `output` classification in Verilog mode is template-specific | Low | All outputs currently use `assign`; classify as `output` (wire default) |
| `--property` requires multi-assertion parsing | Medium | Extend `import_assertion` to return ALL assertions; well-isolated change |
| slang prebuilt binary URL may change between releases | Low | Pin version in CI; add fallback to latest |
| `--dump-ir` must work pre-optimization (shows normalized IR) | Low | Natural pipeline position; exit after `normalize()` |

---

## 12. File Change Inventory

### Files to Modify
| File | Changes |
|------|---------|
| `src/sva2rtl/cli.py` | Add `--dump-ast`, `--dump-ir`, `--property`, `--verilog`, `--version`; multi-property loop |
| `src/sva2rtl/debug.py` | Add `format_dump_ir()` function |
| `src/sva2rtl/emitter.py` | Thread `verilog_mode: bool` through `emit()`, `emit_all()`, `_emit_recursive()` |
| `src/sva2rtl/ast_importer.py` | Add `import_all_assertions()` for multi-property support |
| `src/sva2rtl/errors.py` | (Optional) Add SVA-E005 for property-not-found |
| `pyproject.toml` | Bump version, add metadata, classifiers, URLs |
| All 12 `templates/*.sv.j2` | Add `{% if verilog_mode %}` conditional branches |

### Files to Create
| File | Purpose |
|------|---------|
| `.github/workflows/ci.yml` | GitHub Actions CI workflow |
| `tests/test_verilog_mode.py` | Verilog-2001 output tests |
| `tests/test_cli_phase6.py` | New CLI flag tests |
| `tests/test_integration_full.py` | Full requirement coverage traceability |
| `SUPPORTED_CONSTRUCTS.md` | Operator support table with examples |
| `README.md` | Primary English documentation |
| `README_zh.md` | Chinese documentation |

---

## 13. Dependency & Ordering Constraints

```
6.1 (CLI flags) ──────────── independent, can start immediately
6.2 (Verilog-2001) ────────── independent of 6.1, can start in parallel
6.3 (Integration tests) ───── depends on 6.1 + 6.2 (tests exercise all flags)
6.4 (Release polish) ──────── depends on 6.1 + 6.2 (README documents final flags)
```

**Recommended execution order:**
1. **Wave 1** (parallel): 6.1 + 6.2
2. **Wave 2** (sequential): 6.3 (after 6.1 + 6.2 complete)
3. **Wave 3** (sequential): 6.4 (after all tests pass)

---

## 14. Success Criteria Verification Plan

| Criterion | Verification Method |
|-----------|-------------------|
| `--verilog` compiles clean with `iverilog -g2001` | CI job runs `iverilog -g2001` on all template outputs |
| `--dump-ir` prints normalized IR and exits 0 | Unit test: invoke CLI, check output + exit code |
| `--dump-tree` prints composition tree and exits 0 | Already implemented; add assertion on new format |
| All 40 requirements have passing tests | Test file with `@pytest.mark.parametrize` tagging each req ID |

---

*Research completed: 2026-05-28*
*Sources: Codebase analysis of all 14 source files (3772 LOC), 12 templates, 26 test files, pyproject.toml, and planning artifacts.*
