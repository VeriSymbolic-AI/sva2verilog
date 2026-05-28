# Phase 6: CLI Polish + Verilog-2001 + Integration Testing — Patterns

**Generated:** 2026-05-28
**Source:** CONTEXT.md + RESEARCH.md + codebase analysis

---

## File Inventory

| # | File | Role | Action | Closest Analog |
|---|------|------|--------|----------------|
| 1 | `src/sva2rtl/cli.py` | CLI entry point | Modify | Self (existing) |
| 2 | `src/sva2rtl/debug.py` | Debug formatting | Modify | Self (`format_dump_tree`) |
| 3 | `src/sva2rtl/emitter.py` | RTL code generation | Modify | Self (existing) |
| 4 | `src/sva2rtl/ast_importer.py` | AST → IR translator | Modify | Self (`import_assertion`) |
| 5 | `templates/*.sv.j2` (12 files) | Jinja2 RTL templates | Modify | `templates/past.sv.j2` (has conditional) |
| 6 | `.github/workflows/ci.yml` | CI workflow | Create | — (new file) |
| 7 | `pyproject.toml` | Package metadata | Modify | Self (existing) |
| 8 | `tests/test_verilog_mode.py` | Verilog-2001 tests | Create | `tests/test_golden_parity.py` |
| 9 | `tests/test_cli_phase6.py` | New CLI flag tests | Create | `tests/test_cli.py` + `tests/test_dump_tree.py` |
| 10 | `tests/test_integration_full.py` | Requirement coverage | Create | `tests/test_integration.py` |
| 11 | `README.md` | Documentation | Create | — (new file) |
| 12 | `SUPPORTED_CONSTRUCTS.md` | Operator reference | Create | — (new file) |

---

## 1. `src/sva2rtl/cli.py` — Add CLI Flags

**Role:** CLI entry point, pipeline orchestration
**Data flow:** User args → pipeline invocation → output/early-exit
**Closest analog:** Self — existing `--dump-tree` and `--no-optimize` patterns

### Pattern: Click Option Declaration

```python
# EXISTING PATTERN (lines 46-56):
@click.option(
    "--dump-tree",
    is_flag=True,
    default=False,
    help="Print CheckerNode composition tree and exit (no RTL emitted)",
)
@click.option(
    "--no-optimize",
    is_flag=True,
    default=False,
    help="Skip optimization passes (emit unoptimized output)",
)
```

**New flags follow identical pattern:**
- `--dump-ast` → `is_flag=True`, exits before `import_assertion`
- `--dump-ir` → `is_flag=True`, exits after `normalize()`
- `--property` → `type=str, default=None`, filters after `import_assertion`
- `--verilog` → `is_flag=True`, threaded to `emit()`/`emit_all()`
- `--version` → `@click.version_option(package_name="sva2rtl")`

### Pattern: Early-Exit Debug Flag

```python
# EXISTING PATTERN (lines 80-95):
if dump_tree:
    from sva2rtl.composer import compute_hash_map
    from sva2rtl.debug import format_dump_tree

    hash_map = compute_hash_map(checker_node)
    click.echo(
        format_dump_tree(
            raw_node,
            checker_node,
            hash_map,
            unoptimized_checker=(
                unoptimized_checker if not no_optimize else None
            ),
        )
    )
    sys.exit(0)
```

**New `--dump-ast` follows this exactly:**
```python
if dump_ast:
    import json
    click.echo(json.dumps(ast, indent=2))
    sys.exit(0)
```

**New `--dump-ir` follows this exactly:**
```python
if dump_ir:
    from sva2rtl.debug import format_dump_ir
    click.echo(format_dump_ir(node))
    sys.exit(0)
```

### Pattern: Pipeline Call Order

```python
# EXISTING PATTERN (lines 70-104):
ast = invoke_slang(Path(input_file), slang_path)
# [--dump-ast exits HERE]
node, clock, original_text, label = import_assertion(ast)
# [--property filters HERE]
raw_node = node
node = normalize(node)
# [--dump-ir exits HERE]
checker_node = compose(node, clock, label, original_text)
if not no_optimize:
    checker_node = optimize(checker_node)
# [--dump-tree exits HERE]
# ... emit ...
```

### Pattern: Error Handling with Exit Codes

```python
# EXISTING PATTERN (lines 107-121):
except SlangNotFound as exc:
    click.echo(str(exc), err=True)
    sys.exit(3)
except UnsupportedConstruct as exc:
    click.echo(str(exc), err=True)
    sys.exit(2)
```

**New `--property` no-match → exit code 2:**
```python
if property_filter and not assertions:
    click.echo(f"error: property '{property_filter}' not found. Available: {available}", err=True)
    sys.exit(2)
```

---

## 2. `src/sva2rtl/debug.py` — Add `format_dump_ir()`

**Role:** Debug text formatting (no side effects)
**Data flow:** SVANode tree → formatted string
**Closest analog:** Self — `_format_ir()` private function (lines 93-145)

### Pattern: Recursive IR Formatting with Match/Case

```python
# EXISTING PATTERN (lines 93-145):
def _format_ir(node: SVANode, indent: int) -> str:
    """Recursively format an SVANode tree as indented text."""
    prefix = " " * indent
    lines: list[str] = []

    match node:
        case BoolExpr():
            lines.append(f'{prefix}BoolExpr("{node.text}")')

        case SignalFunc():
            lines.append(
                f"{prefix}SignalFunc({node.func_name}, signal={node.signal}, depth={node.depth})"
            )

        case SeqConcat():
            delays_str = ", ".join(f"({d[0]},{d[1]})" for d in node.delays)
            lines.append(f"{prefix}SeqConcat(delays=[{delays_str}])")
            for elem in node.elements:
                lines.append(_format_ir(elem, indent + 2))

        case PropImplication():
            overlap_str = "overlapping" if node.overlapping else "non-overlapping"
            lines.append(f"{prefix}PropImplication({overlap_str})")
            lines.append(f"{prefix}  antecedent:")
            lines.append(_format_ir(node.antecedent, indent + 4))
            lines.append(f"{prefix}  consequent:")
            lines.append(_format_ir(node.consequent, indent + 4))

        case DisableIff():
            # ...
            lines.append(f"{prefix}DisableIff(condition={cond_text})")
            lines.append(f"{prefix}  body:")
            lines.append(_format_ir(node.body, indent + 4))

        case _:
            lines.append(f"{prefix}{type(node).__name__}()")

    return "\n".join(lines)
```

### Pattern: Public Wrapper Function

```python
# EXISTING PATTERN (lines 28-90):
def format_dump_tree(
    ir_node: SVANode,
    checker: CheckerNode,
    hash_map: dict[str, str],
    *,
    unoptimized_checker: CheckerNode | None = None,
) -> str:
    """Format a structured dump of the IR tree and composition tree. ..."""
    lines: list[str] = []
    lines.append("=== Pre-normalized IR ===")
    lines.append(_format_ir(ir_node, indent=0))
    # ...
    return "\n".join(lines)
```

**New `format_dump_ir()` follows same pattern:**
- Public function taking `SVANode` (normalized IR)
- Calls enhanced `_format_ir()` with `show_loc=True`
- Returns plain-text multi-line string
- D-02 format: shows `loc=file:line:col` on each node, uses named child labels

---

## 3. `src/sva2rtl/emitter.py` — Thread `verilog_mode`

**Role:** Template rendering, RTL code generation
**Data flow:** CheckerNode → Jinja2 context → rendered SV text
**Closest analog:** Self — existing context-building pattern

### Pattern: Template Context Building

```python
# EXISTING PATTERN (lines 99-103 in emit()):
ctx: dict[str, object] = dict(checker.params)
ctx["observed_signals"] = checker.observed_signals
ctx["children"] = checker.children
return str(tmpl.render(**ctx))
```

**Add `verilog_mode` to context:**
```python
ctx["verilog_mode"] = verilog_mode  # bool from CLI flag
```

### Pattern: Function Signature Threading

```python
# EXISTING PATTERN — emit() signature (lines 75-76):
def emit(checker: CheckerNode, template_dir: Path | None = None) -> str:

# EXISTING PATTERN — emit_all() signature (lines 106-109):
def emit_all(
    checker: CheckerNode,
    template_dir: Path | None = None,
) -> dict[str, str]:

# EXISTING PATTERN — _emit_recursive() signature (lines 135-139):
def _emit_recursive(
    checker: CheckerNode,
    env: Environment,
    results: dict[str, str],
) -> None:
```

**Threading pattern — add `verilog_mode: bool = False` to all three:**
```python
def emit(checker: CheckerNode, template_dir: Path | None = None, *, verilog_mode: bool = False) -> str:
def emit_all(checker: CheckerNode, template_dir: Path | None = None, *, verilog_mode: bool = False) -> dict[str, str]:
def _emit_recursive(checker: CheckerNode, env: Environment, results: dict[str, str], *, verilog_mode: bool = False) -> None:
```

---

## 4. `src/sva2rtl/ast_importer.py` — Multi-Property Support

**Role:** AST → IR translation
**Data flow:** slang JSON dict → list of (SVANode, ClockSpec, str, str|None)
**Closest analog:** Self — existing `import_assertion()` + `_find_assertion_in_members()`

### Pattern: Single-Assertion Finding

```python
# EXISTING PATTERN (lines 79-130):
def import_assertion(
    ast: dict[str, Any],
) -> tuple[SVANode, ClockSpec, str, str | None]:
    """Walk *ast* and return IR for the first ConcurrentAssertion found."""
    design = ast.get("design", {})
    members: list[dict[str, Any]] = design.get("members", [])

    # First pass: collect named sequence/property declarations
    global _DECLARATIONS
    for member in members:
        if member.get("kind") == "Instance":
            body = member.get("body", {})
            if body.get("kind") == "InstanceBody":
                _DECLARATIONS = _collect_declarations(body.get("members", []))

    # Second pass: locate and import the ConcurrentAssertion.
    for member in members:
        if member.get("kind") == "Instance":
            body = member.get("body", {})
            if body.get("kind") == "InstanceBody":
                result = _find_assertion_in_members(body.get("members", []))
                if result is not None:
                    return result

    raise SvaCompileError(message="No concurrent assertion found ...")
```

### Pattern: Recursive Member Search

```python
# EXISTING PATTERN (lines 320-347):
def _find_assertion_in_members(
    members: list[dict[str, Any]],
) -> tuple[SVANode, ClockSpec, str, str | None] | None:
    """Recursively search *members* for a ConcurrentAssertion."""
    for member in members:
        kind = member.get("kind", "")
        if kind == "ConcurrentAssertion":
            return _import_concurrent_assertion(member, label=None)
        if kind == "Block":
            label = _extract_label(member)
            body = member.get("body", {})
            stmts: list[dict[str, Any]] = body.get("statements", [])
            for stmt in stmts:
                if stmt.get("kind") == "ConcurrentAssertion":
                    return _import_concurrent_assertion(stmt, label=label)
    return None
```

**New `import_all_assertions()` extends this to collect ALL matches:**
```python
def import_all_assertions(
    ast: dict[str, Any],
) -> list[tuple[SVANode, ClockSpec, str, str | None]]:
    """Walk *ast* and return IR for ALL ConcurrentAssertions found."""
    # Same two-pass structure but _find_ALL_assertions_in_members returns list
```

---

## 5. `templates/*.sv.j2` — Verilog-2001 Conditional Guards

**Role:** Jinja2 RTL templates, direct SV output
**Data flow:** Template context (params + `verilog_mode`) → rendered RTL text
**Closest analog:** `templates/past.sv.j2` already uses `{% if depth == "1" %}` conditionals

### Pattern: Existing Jinja2 Conditional in Template

```jinja2
{# EXISTING PATTERN (past.sv.j2 lines 22-56): #}
{% if depth == "1" %}
    // Single-FF form for DEPTH=1 (common case)
    logic shift_q;
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        ...
    end
{% else %}
    // Multi-FF shift register for DEPTH > 1
    logic [DEPTH-1:0] shift_q;
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        ...
    end
{% endif %}
```

### Pattern: Port Declaration (all 12 templates)

```jinja2
{# EXISTING PATTERN (bool_expr.sv.j2 lines 4-17): #}
module {{ module_name }} (
    input  logic {{ clock_signal }},
    input  logic rst_n,
    input  logic start,
{% for port_name, _ in observed_signals %}
    input  logic {{ port_name }},
{% endfor %}
    input  logic disable_i,
    output logic active,
    output logic pass,
    output logic fail,
    output logic attempt_fired,
    output logic disabled_o
);
```

**Verilog-2001 conversion pattern:**
```jinja2
module {{ module_name }} (
{% if verilog_mode %}
    input  {{ clock_signal }},
    input  rst_n,
    input  start,
{% else %}
    input  logic {{ clock_signal }},
    input  logic rst_n,
    input  logic start,
{% endif %}
```

### Pattern: Sequential Block (9 of 12 templates)

```jinja2
{# EXISTING PATTERN (bool_expr.sv.j2 lines 25-37): #}
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        if (!rst_n || disable_i) begin
            active_q        <= 1'b0;
            ...
        end else begin
            ...
        end
    end
```

**Verilog-2001 conversion:**
```jinja2
{% if verilog_mode %}
    always @({{ clock_edge }} {{ clock_signal }}) begin
{% else %}
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
{% endif %}
```

### Pattern: Internal Signal Declarations

```jinja2
{# EXISTING PATTERN (bool_expr.sv.j2 lines 20-21): #}
    logic bool_result;
    assign bool_result = ({{ bool_expr }});

{# EXISTING PATTERN (concat_delay.sv.j2 lines 35-37): #}
    logic [CNT_WIDTH-1:0] count_q;
    logic                 running_q;
    logic                 attempt_fired_q;
```

**Verilog-2001 conversion rules:**
- Internal signals in `always_ff` blocks → `reg` (e.g., `count_q`, `running_q`)
- Internal signals in `assign` statements → `wire` (e.g., `bool_result`, `rose_detect`)

```jinja2
{% if verilog_mode %}
    wire bool_result;
{% else %}
    logic bool_result;
{% endif %}
```

### Pattern: Zero Literal `'0`

```jinja2
{# EXISTING PATTERN (concat_delay.sv.j2 lines 41-43): #}
            count_q         <= '0;
            running_q       <= 1'b0;
            attempt_fired_q <= 1'b0;
```

**Verilog-2001 conversion (only for multi-bit `'0`, not `1'b0`):**
```jinja2
{% if verilog_mode %}
            count_q         <= 0;
{% else %}
            count_q         <= '0;
{% endif %}
```

### Pattern: Output Port Classification

All output ports in current templates are driven by `assign` statements (never directly by `always_ff`). Therefore in Verilog-2001, all outputs remain as `output` (wire is default). No `output reg` needed.

```jinja2
{# All templates use this pattern for outputs: #}
    assign active        = disable_i ? 1'b0 : active_q;
    assign pass          = disable_i ? 1'b0 : pass_q;
    assign fail          = disable_i ? 1'b0 : fail_q;
    assign attempt_fired = attempt_fired_q;
```

---

## 6. `.github/workflows/ci.yml` — CI Workflow

**Role:** Continuous integration, automated testing
**Data flow:** Push/PR → test matrix → pass/fail status
**Closest analog:** None in codebase (new file). Standard uv + pytest pattern.

### Pattern: Workflow Structure (from D-04)

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
      - name: Lint (ruff)
        run: uv run ruff check src/ tests/
      - name: Type check (mypy)
        run: uv run mypy src/
      - name: Test
        run: uv run pytest tests/ --timeout=120 -v
```

### Pattern: Conditional Tool Install

```yaml
# From conftest.py (graceful skip when iverilog absent):
- name: Install iverilog
  run: |
    if [ "${{ runner.os }}" == "Linux" ]; then
      sudo apt-get update && sudo apt-get install -y iverilog
    elif [ "${{ runner.os }}" == "macOS" ]; then
      brew install icarus-verilog
    fi
```

---

## 7. `pyproject.toml` — Package Metadata

**Role:** Package configuration, build system
**Data flow:** Static metadata → build/install
**Closest analog:** Self (existing)

### Pattern: Current Structure

```toml
# EXISTING (full file):
[project]
name = "sva2rtl"
version = "0.1.0"
description = "SVA to synthesizable RTL monitor compiler"
requires-python = ">=3.12"
dependencies = [
    "click>=8.0",
    "jinja2>=3.1.6",
]

[project.scripts]
sva2rtl = "sva2rtl.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Changes for v1.0:**
- `version = "1.0.0"`
- Add `license`, `authors`, `readme`, `keywords`, `classifiers`
- Add `[project.urls]` section

---

## 8. `tests/test_verilog_mode.py` — Verilog-2001 Output Tests

**Role:** Validates `--verilog` flag produces correct Verilog-2001 output
**Data flow:** JSON fixtures → pipeline(verilog_mode=True) → assertions
**Closest analog:** `tests/test_golden_parity.py`

### Pattern: Golden Parity Test with Pipeline Helper

```python
# EXISTING PATTERN (test_golden_parity.py lines 41-54):
def _run_full_pipeline(fixture_name: str) -> dict[str, str]:
    """Run the full normalize->compose->emit pipeline on a JSON fixture."""
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        return emit_all(checker)
    else:
        return {checker.module_name: emit(checker)}
```

**Verilog mode variant:**
```python
def _run_full_pipeline_verilog(fixture_name: str) -> dict[str, str]:
    """Run the pipeline with verilog_mode=True."""
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        return emit_all(checker, verilog_mode=True)
    else:
        return {checker.module_name: emit(checker, verilog_mode=True)}
```

### Pattern: Parametrized Test Cases

```python
# EXISTING PATTERN (test_golden_parity.py lines 59-82):
_SINGLE_MODULE_CASES: list[tuple[str, str]] = [
    ("bool_simple.json", "bool_simple.sv"),
    ("bool_labeled.json", "bool_labeled.sv"),
    # ...
]

@pytest.mark.parametrize(
    ("fixture", "golden_file"),
    _SINGLE_MODULE_CASES,
    ids=[g for _, g in _SINGLE_MODULE_CASES],
)
def test_golden_parity_single_module(fixture: str, golden_file: str) -> None:
    """..."""
```

### Pattern: Content Assertions (no SystemVerilog keywords)

```python
def test_verilog_mode_no_logic_keyword(fixture: str) -> None:
    """Verilog-2001 output must not contain the 'logic' keyword."""
    modules = _run_full_pipeline_verilog(fixture)
    for sv_text in modules.values():
        assert "logic" not in sv_text
        assert "always_ff" not in sv_text
```

---

## 9. `tests/test_cli_phase6.py` — New CLI Flag Tests

**Role:** Unit tests for --dump-ast, --dump-ir, --property, --verilog, --version
**Data flow:** CliRunner invocation → exit code + output assertions
**Closest analog:** `tests/test_cli.py` + `tests/test_dump_tree.py`

### Pattern: CliRunner with Mock Pipeline

```python
# EXISTING PATTERN (test_cli.py lines 30-34, 80-84):
@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()

@pytest.fixture()
def bool_assert_path(tmp_path: Path) -> Path:
    sv = tmp_path / "bool_assert.sv"
    sv.write_text(
        "module t(input logic clk, a, b);\n"
        "  p: assert property (@(posedge clk) a && b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return sv
```

### Pattern: Mocked Early-Exit Test

```python
# EXISTING PATTERN (test_cli.py lines 96-102):
def test_cli_unsupported_construct(runner: CliRunner, bool_assert_path: Path) -> None:
    exc = UnsupportedConstruct(...)
    with patch("sva2rtl.cli.invoke_slang", return_value=_MOCK_AST):
        with patch("sva2rtl.cli.import_assertion", side_effect=exc):
            result = runner.invoke(main, [str(bool_assert_path)])
    assert result.exit_code == 2
    assert "SVA-E002" in result.output
```

### Pattern: CLI Integration with Real slang (conditional)

```python
# EXISTING PATTERN (test_dump_tree.py lines 260-268):
@requires_slang
def test_cli_dump_tree_exits_0() -> None:
    runner = CliRunner()
    result = runner.invoke(main, [str(_FIXTURES / "bool_assert.sv"), "--dump-tree"])
    assert result.exit_code == 0, (
        f"Expected exit_code 0, got {result.exit_code}.\nOutput: {result.output}"
    )
```

---

## 10. `tests/test_integration_full.py` — Requirement Coverage

**Role:** End-to-end traceability: every v1 requirement has a passing test
**Data flow:** JSON fixtures → full pipeline → requirement assertion
**Closest analog:** `tests/test_integration.py`

### Pattern: Requirement-Tagged Tests

```python
# EXISTING PATTERN (test_integration.py lines 86-109):
def test_pipeline_source_loc_preserved() -> None:
    """Source location is threaded from JSON through to the emitted header comment.
    Validates PARSE-05: ..."""
    ast = _load("bool_simple.json")
    node, _clock, _text, _label = import_assertion(ast)
    assert isinstance(node, BoolExpr)
    assert node.source_loc.line > 0
```

### Pattern: Pipeline Runner

```python
# EXISTING PATTERN (test_integration.py lines 38-45):
def _run(name: str) -> str:
    """Run the full pipeline on a JSON fixture and return emitted SV text."""
    ast = _load(name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    return emit(checker)
```

### Pattern: Multi-Module Pipeline

```python
# EXISTING PATTERN (test_integration.py lines 160-175):
def test_pipeline_seq_concat_succeeds() -> None:
    from sva2rtl.emitter import emit_all
    ast = _load("unsupported_delay.json")
    ir_node, clock, text, label = import_assertion(ast)
    checker = compose(ir_node, clock, label, text)
    modules = emit_all(checker)
    assert len(modules) >= 3
```

---

## Cross-Cutting Patterns

### Pattern: Import Convention

```python
# EXISTING PATTERN (all source files):
from __future__ import annotations  # Always first

import sys
from pathlib import Path

import click

from sva2rtl.ast_importer import import_assertion
from sva2rtl.errors import SlangNotFound, SvaError, UnsupportedConstruct
```

Standard order: `__future__` → stdlib → third-party → local.

### Pattern: Docstring Convention

```python
# EXISTING PATTERN (all public functions):
def format_dump_tree(
    ir_node: SVANode,
    checker: CheckerNode,
    hash_map: dict[str, str],
    *,
    unoptimized_checker: CheckerNode | None = None,
) -> str:
    """Format a structured dump of the IR tree and composition tree.

    Returns a formatted string with two sections:
    1. ``=== Pre-normalized IR ===`` — ...
    2. ``=== Composition Tree ===`` — ...

    Parameters
    ----------
    ir_node
        The pre-normalized SVA IR tree.
    ...

    Returns
    -------
    str
        Formatted multi-line string suitable for printing to stdout.
    """
```

NumPy-style docstrings with `Parameters`, `Returns`, `Raises` sections.

### Pattern: Error Class with Structured Format

```python
# EXISTING PATTERN (errors.py lines 57-74):
@dataclass
class UnsupportedConstruct(SvaError):
    construct_name: str = ""

    def __str__(self) -> str:
        loc_prefix = f"{self.source_loc}: " if self.source_loc else ""
        return (
            f"{loc_prefix}error SVA-E002: unsupported construct "
            f"'{self.construct_name}': {self.message}"
        )
```

### Pattern: Graceful Skip in Simulation Tests

```python
# EXISTING PATTERN (tests/simulation/conftest.py):
@pytest.fixture(autouse=True)
def check_iverilog() -> None:
    """Skip simulation tests when iverilog is not installed."""
    if shutil.which("iverilog") is None:
        pytest.skip("iverilog not found — install Icarus Verilog to run simulation tests")
```

### Pattern: Template Header Comment Block

```jinja2
{# EXISTING PATTERN (all 12 templates, first 3 lines): #}
// Generated by sva2rtl {{ sva2rtl_version }}
// Source: {{ source_loc }}
// Original property: @({{ clock_edge }} {{ clock_signal }}) {{ original_text }}
```

---

## Verilog-2001 Conversion Summary Matrix

| Template | `logic` ports | `always_ff` | `'0` literal | Internal `logic` (reg) | Internal `logic` (wire) |
|----------|:---:|:---:|:---:|:---:|:---:|
| `bool_expr` | Yes | Yes | No | `active_q`, `pass_q`, `fail_q`, `attempt_fired_q` | `bool_result` |
| `concat_delay` | Yes | Yes | Yes (`count_q`) | `count_q`, `running_q`, `attempt_fired_q` | — |
| `overlap_bitvec` | Yes | Yes | Yes (`bv_q`) | `bv_q`, `overflow_flag_q`, `attempt_fired_q` | `ant_pass_w`, `con_pass_w`, etc. |
| `nonoverlap` | Yes | Yes | Yes | Similar to overlap | Similar to overlap |
| `rose` | Yes | Yes | No | `sig_prev_q`, `attempt_fired_q` | `rose_detect`, `pass_internal`, `fail_internal` |
| `fell` | Yes | Yes | No | `sig_prev_q`, `attempt_fired_q` | `fell_detect`, `pass_internal`, `fail_internal` |
| `stable` | Yes | Yes | No | `sig_prev_q`, `attempt_fired_q` | `stable_detect`, etc. |
| `past` | Yes | Yes | Yes (`shift_q`) | `shift_q`, `attempt_fired_q` | `past_value`, `pass_internal`, `fail_internal` |
| `rep_consecutive` | Yes | Yes | Yes (`count_q`) | `count_q`, `running_q`, `attempt_fired_q` | — |
| `seq_concat_top` | Yes | No | No | — | `w_pass_N`, `w_active_N`, `w_fail_N`, `w_afired_N` |
| `disable_iff_top` | Yes | No | No | — | `cond_result`, `effective_disable` |
| `bind` | No | No | No | — | — |

---

## Data Flow Diagram: CLI Pipeline with New Flags

```
INPUT_FILE
    │
    ▼
invoke_slang() ─────── [--dump-ast: json.dumps(ast) → stdout, exit 0]
    │
    ▼
import_all_assertions() ── [--property: filter by label; no-match → exit 2]
    │
    ▼
normalize() ────────── [--dump-ir: format_dump_ir(node) → stdout, exit 0]
    │
    ▼
compose()
    │
    ▼
optimize() ─────────── [--dump-tree: format_dump_tree() → stdout, exit 0]
    │
    ▼
emit(verilog_mode) ─── [--verilog: ctx["verilog_mode"] = True]
    │
    ▼
write_output()
```

---

*Patterns extracted: 2026-05-28*
*Source files analyzed: 14 source modules, 12 templates, 6 test files, pyproject.toml*
