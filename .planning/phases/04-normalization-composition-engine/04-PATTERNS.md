# Phase 4: Normalization + Composition Engine — Pattern Mapping

**Date:** 2026-05-27
**Phase:** 4
**Source:** 04-CONTEXT.md, 04-RESEARCH.md

---

## File Inventory

### New Files

| # | File | Role | Plan |
|---|------|------|------|
| 1 | `src/sva2rtl/normalizer.py` | IR transform pass | 4.1 |
| 2 | `src/sva2rtl/debug.py` | Debug output formatter | 4.3 |
| 3 | `tests/test_normalizer.py` | Unit tests | 4.1 |
| 4 | `tests/test_dump_tree.py` | Integration tests | 4.3 |

### Modified Files

| # | File | Role | Plan |
|---|------|------|------|
| 5 | `src/sva2rtl/cli.py` | CLI entry point (add `--dump-tree`, insert `normalize()`) | 4.2/4.3 |
| 6 | `src/sva2rtl/composer.py` | Add structural hash computation | 4.2 |
| 7 | `tests/test_integration.py` | Update pipeline calls with `normalize()` | 4.2 |
| 8 | `tests/test_pipeline_e2e.py` | Add `--dump-tree` CLI test | 4.3 |
| 9 | `tests/test_composer.py` | Verify normalize->compose parity | 4.2 |

---

## Pattern Mapping

### File 1: `src/sva2rtl/normalizer.py`

**Role:** Pure IR-to-IR transform pass (pre-processing before composer)
**Data flow:** `SVANode` in -> canonical `SVANode` out
**Closest analog:** `src/sva2rtl/ast_importer.py` — both walk IR tree recursively using `match`/`case`

#### Pattern: Module structure & docstring

From `src/sva2rtl/ast_importer.py` lines 1-16:
```python
"""JSON AST -> SVA IR translator.

Walks the slang --ast-json dict and produces a (SVANode, ClockSpec, str, str | None)
tuple for the first ConcurrentAssertion found:

    (ir_node, clock_spec, original_sva_text, label_or_None)

Design decisions (from Research Q1, Q6, pitfalls P5.1, P8.1, P8.2, P8.4):
- extract_source_loc() is called on *every* node visited (P5.1 prevention).
...
"""

from __future__ import annotations

from typing import Any

from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    DisableIff,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SignalFunc,
    SourceLoc,
    SVANode,
)
```

**Apply as:** Same structure — triple-quoted docstring explaining purpose, `from __future__ import annotations`, import all IR types from `sva2rtl.ir`.

#### Pattern: `match`/`case` dispatch on IR node type

From `src/sva2rtl/composer.py` lines 389-410:
```python
match node:
    case BoolExpr():
        return _compose_bool_expr(node, clock, label, original_text, cse_origin)
    case SeqConcat():
        return _compose_seq_concat(node, clock, label, original_text, cse_origin)
    case SeqRepetition():
        return _compose_repetition(node, clock, label, original_text, cse_origin)
    case SignalFunc():
        return _compose_signal_func(node, clock, label, original_text, cse_origin)
    case PropImplication():
        return _compose_implication(node, clock, label, original_text, cse_origin)
    case DisableIff():
        return _compose_disable_iff(node, clock, label, original_text, cse_origin)
    case _:
        raise UnsupportedConstruct(...)
```

**Apply as:** Normalizer uses same `match`/`case` dispatch but with bottom-up traversal (recurse into children first, then normalize current node). The default case returns `node` unchanged (not raise).

#### Pattern: Private helper function naming

From `src/sva2rtl/composer.py` — private helpers named `_compose_bool_expr`, `_compose_seq_concat`, etc.

**Apply as:** Private helpers named `_normalize_node`, `_flatten_concat`, etc.

#### Pattern: Frozen dataclass reconstruction (immutable IR)

From `src/sva2rtl/ast_importer.py` lines 587-591:
```python
return SeqConcat(
    elements=tuple(elements),
    delays=tuple(delays),
    source_loc=source_loc,
)
```

**Apply as:** Normalizer constructs new frozen nodes when children change. Same pattern: `SeqConcat(elements=new_elements, delays=new_delays, source_loc=node.source_loc)`.

---

### File 2: `src/sva2rtl/debug.py`

**Role:** Debug output formatting for `--dump-tree`
**Data flow:** `(SVANode, CheckerNode, hash_dict)` in -> formatted string out
**Closest analog:** `src/sva2rtl/emitter.py` — both render structured data to text

#### Pattern: Module with public function + private helpers

From `src/sva2rtl/emitter.py` lines 75-80:
```python
# -- Public API ────────────────────────────────────────────────────────────

def emit(checker: CheckerNode, template_dir: Path | None = None) -> str:
    """Render a ``CheckerNode`` to a SystemVerilog string via Jinja2.
    ...
    """
```

**Apply as:** Public function `dump_tree(ir_node: SVANode, checker: CheckerNode, hashes: dict[CheckerNode, str]) -> str` with private helpers `_format_ir_tree()` and `_format_checker_tree()`.

#### Pattern: Recursive tree traversal for text generation

From `src/sva2rtl/ast_importer.py` lines 594-614 (`_reconstruct_seq_text`):
```python
def _reconstruct_seq_text(node: SeqConcat) -> str:
    """Reconstruct an SVA text representation from a SeqConcat IR node."""
    parts: list[str] = []
    for i, elem in enumerate(node.elements):
        if isinstance(elem, BoolExpr):
            parts.append(elem.text)
        elif isinstance(elem, SeqConcat):
            parts.append(_reconstruct_seq_text(elem))
        ...
    return " ".join(parts)
```

**Apply as:** Recursive indent-based tree formatting — each level adds indentation, recursively formats children.

---

### File 3: `tests/test_normalizer.py`

**Role:** Unit tests for normalization rules
**Data flow:** Construct IR nodes -> call `normalize()` -> assert output structure
**Closest analog:** `tests/test_composer.py`

#### Pattern: Helper factory functions for IR construction

From `tests/test_composer.py` lines 24-29:
```python
def _make_loc(file: str = "test.sv", line: int = 3, col: int = 5) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _make_clock(edge: str = "posedge", signal: str = "clk") -> ClockSpec:
    return ClockSpec(edge=edge, signal=signal, source_loc=_make_loc())
```

**Apply as:** Reuse `_make_loc()` helper; add normalizer-specific factories like `_make_seq_rep(min, max, expr)`.

#### Pattern: Test naming convention

From `tests/test_composer.py`:
```python
def test_compose_bool_expr_returns_checker_node() -> None:
def test_compose_seq_concat_template_name() -> None:
def test_compose_implication_overlap_template_name() -> None:
```

**Apply as:** `test_normalize_` prefix: `test_normalize_star1_identity_removal`, `test_normalize_flatten_nested_concat`, `test_normalize_idempotent`, etc.

#### Pattern: Direct IR construction for testing (no fixtures needed)

From `tests/test_composer.py` lines 233-243:
```python
def test_compose_seq_concat_returns_checker_node() -> None:
    """SeqConcat passed to compose() returns a CheckerNode (no longer unsupported)."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "my_check", "a ##1 b")
    assert isinstance(checker, CheckerNode)
```

**Apply as:** Same pattern — construct IR nodes directly, call `normalize()`, assert result structure using `isinstance` and field comparisons on the returned frozen dataclass.

#### Pattern: Test return type annotation

From `tests/test_composer.py`:
```python
def test_compose_bool_expr_returns_checker_node() -> None:
```

**Apply as:** All tests annotated `-> None`.

---

### File 4: `tests/test_dump_tree.py`

**Role:** Integration tests for `--dump-tree` CLI flag output
**Data flow:** Invoke CLI with `--dump-tree` -> capture stdout -> assert content
**Closest analog:** `tests/test_pipeline_e2e.py`

#### Pattern: CLI testing with CliRunner

From `tests/test_pipeline_e2e.py` lines 42-56:
```python
@requires_slang
def test_e2e_bool_assert(tmp_path: Path) -> None:
    """Full pipeline on bool_assert.sv exits 0 and produces a valid SV file."""
    runner = CliRunner()
    output_file = tmp_path / "bool_out.sv"
    result = runner.invoke(
        main,
        [str(_FIXTURES / "bool_assert.sv"), "--output", str(output_file)],
    )
    assert result.exit_code == 0, (
        f"Expected exit code 0, got {result.exit_code}.\nOutput: {result.output}"
    )
```

**Apply as:** Same pattern for `--dump-tree` — invoke CLI, assert exit code 0, assert output contains expected tree structure markers (e.g., `"CheckerNode:"`, `"[hash:"`, indentation).

#### Pattern: `requires_slang` skip marker

From `tests/conftest.py` lines 33-37:
```python
has_slang: bool = shutil.which("slang") is not None
requires_slang = pytest.mark.skipif(
    not has_slang,
    reason="slang binary not found — install from ...",
)
```

**Apply as:** Decorate slang-dependent `--dump-tree` tests with `@requires_slang`.

#### Pattern: Mock-based unit testing (without slang dependency)

From `tests/test_cli.py` lines 71-80:
```python
def test_cli_slang_not_found(runner: CliRunner, bool_assert_path: Path) -> None:
    """SlangNotFound maps to exit code 3 and stderr mentions Install:."""
    exc = SlangNotFound(...)
    with patch("sva2rtl.cli.invoke_slang", side_effect=exc):
```

**Apply as:** Can test `--dump-tree` with mocked pipeline if needed, but prefer real slang invocation for integration-level testing.

---

### File 5: `src/sva2rtl/cli.py` (modified)

**Role:** Add `--dump-tree` flag and insert `normalize()` into pipeline
**Data flow:** `normalize()` inserted between `import_assertion()` and `compose()`
**Closest analog:** Self (existing `--dump-ast` pattern mentioned in CONTEXT.md, and current pipeline wiring)

#### Pattern: Click option declaration

From `src/sva2rtl/cli.py` lines 29-41:
```python
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file path (default: stdout)",
)
@click.option(
    "--slang-path",
    default="slang",
    envvar="SLANG_PATH",
    help="Path to slang binary (default: slang on PATH)",
    show_envvar=True,
)
```

**Apply as:** Add `@click.option("--dump-tree", is_flag=True, default=False, help="Print composition tree and exit")`.

#### Pattern: Pipeline call sequence

From `src/sva2rtl/cli.py` lines 51-53:
```python
ast = invoke_slang(Path(input_file), slang_path)
node, clock, original_text, label = import_assertion(ast)
checker_node = compose(node, clock, label, original_text)
```

**Apply as:** Insert `normalize()` call:
```python
ast = invoke_slang(Path(input_file), slang_path)
node, clock, original_text, label = import_assertion(ast)
normalized_node = normalize(node)
checker_node = compose(normalized_node, clock, label, original_text)
```

#### Pattern: Early-exit flag (print and exit 0)

From D-10 (spec): same behavior as `--dump-ast`. The pattern for "print diagnostic and exit 0" is:
```python
if dump_tree:
    from sva2rtl.debug import dump_tree as format_tree
    click.echo(format_tree(node, checker_node, hashes))
    sys.exit(0)
```

---

### File 6: `src/sva2rtl/composer.py` (modified)

**Role:** Add structural hash computation after tree build
**Data flow:** `CheckerNode` tree in -> `dict[CheckerNode, str]` hash mapping out
**Closest analog:** Self (existing `module_name_from_label` uses `hashlib.sha256`)

#### Pattern: SHA-256 for deterministic hashing

From `src/sva2rtl/composer.py` lines 318-322:
```python
h = hashlib.sha256(property_text.encode()).hexdigest()[:8]
return f"sva_prop_{h}"
```

**Apply as:** Structural hash uses same `hashlib.sha256` + `hexdigest()[:8]` pattern:
```python
def structural_hash(node: CheckerNode) -> str:
    h = hashlib.sha256()
    h.update(node.template_name.encode())
    for k, v in sorted(node.params.items()):
        if k not in _VOLATILE_PARAMS:
            h.update(f"{k}={v}".encode())
    for child in node.children:
        h.update(structural_hash(child).encode())
    return h.hexdigest()[:8]
```

#### Pattern: Module-level constants for excluded sets

From `src/sva2rtl/composer.py` lines 41-289 (`_SV_KEYWORDS: frozenset[str]`):
```python
_SV_KEYWORDS: frozenset[str] = frozenset({...})
```

**Apply as:** Define `_VOLATILE_PARAMS` frozenset for params excluded from hash:
```python
_VOLATILE_PARAMS: frozenset[str] = frozenset({
    "module_name", "source_loc", "sva2rtl_version", "original_text"
})
```

---

### File 7: `tests/test_integration.py` (modified)

**Role:** Update pipeline calls to include `normalize()` step
**Data flow:** JSON fixture -> `import_assertion` -> `normalize` -> `compose` -> `emit`
**Closest analog:** Self (existing `_run()` helper)

#### Pattern: Pipeline helper function

From `tests/test_integration.py` lines 33-43:
```python
def _run(name: str) -> str:
    """Run the full pipeline on a JSON fixture and return emitted SV text."""
    ast = _load(name)
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    return emit(checker)
```

**Apply as:** Insert `normalize()`:
```python
def _run(name: str) -> str:
    """Run the full pipeline on a JSON fixture and return emitted SV text."""
    ast = _load(name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    return emit(checker)
```

---

### File 8: `tests/test_pipeline_e2e.py` (modified)

**Role:** Add `--dump-tree` end-to-end CLI test
**Data flow:** CLI invocation with `--dump-tree` flag -> validate stdout
**Closest analog:** Self (existing test_e2e_bool_assert_stdout)

#### Pattern: Stdout output validation

From `tests/test_pipeline_e2e.py` lines 164-178:
```python
@requires_slang
def test_e2e_bool_assert_stdout() -> None:
    """Full pipeline without --output writes SV to stdout (exit 0)."""
    runner = CliRunner()
    result = runner.invoke(main, [str(_FIXTURES / "bool_assert.sv")])

    assert result.exit_code == 0, (
        f"Expected exit code 0 in stdout mode, got {result.exit_code}.\nOutput: {result.output}"
    )
    assert "module sva_my_check" in result.output
    assert "endmodule" in result.output
```

**Apply as:**
```python
@requires_slang
def test_e2e_dump_tree() -> None:
    """--dump-tree prints composition tree to stdout and exits 0."""
    runner = CliRunner()
    result = runner.invoke(main, [str(_FIXTURES / "bool_assert.sv"), "--dump-tree"])

    assert result.exit_code == 0
    assert "CheckerNode:" in result.output
    assert "[hash:" in result.output
```

---

### File 9: `tests/test_composer.py` (modified)

**Role:** Verify normalize->compose produces same results for existing inputs
**Data flow:** Construct IR -> normalize -> compose -> assert CheckerNode unchanged
**Closest analog:** Self (existing composition tests)

#### Pattern: Before/after parity assertion

From `tests/test_composer.py` lines 233-244:
```python
def test_compose_seq_concat_returns_checker_node() -> None:
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(
        source_loc=loc,
        elements=(
            BoolExpr(text="a", source_loc=loc),
            BoolExpr(text="b", source_loc=loc),
        ),
        delays=((1, 1),),
    )
    checker = compose(node, clock, "my_check", "a ##1 b")
    assert isinstance(checker, CheckerNode)
```

**Apply as:** Add tests that compose with and without normalize and compare results:
```python
def test_compose_with_normalize_parity_seq_concat() -> None:
    """normalize() + compose() produces same result as compose() alone for flat concat."""
    loc = _make_loc()
    clock = _make_clock()
    node = SeqConcat(...)
    direct = compose(node, clock, "my_check", "a ##1 b")
    normalized = compose(normalize(node), clock, "my_check", "a ##1 b")
    assert direct == normalized
```

---

## Cross-Cutting Patterns

### Import Convention

All source modules use:
```python
from __future__ import annotations
```

### Docstring Convention

Google-style docstrings with Parameters/Returns/Raises sections using NumPy-style formatting (dashes under section headers):
```python
def normalize(node: SVANode) -> SVANode:
    """Normalize an SVA IR tree to canonical form.

    Pure IR->IR transformation. Bottom-up single pass.
    Idempotent: normalize(normalize(x)) == normalize(x).

    Parameters
    ----------
    node:
        The SVA IR tree to normalize.

    Returns
    -------
    SVANode
        Canonical-form IR tree.
    """
```

### Error Handling Convention

From `src/sva2rtl/errors.py` — custom exception classes with source_loc:
```python
@dataclass
class SvaError(Exception):
    message: str
    source_loc: SourceLoc | None = field(default=None)
```

**Apply as:** Normalizer should never raise (it only reduces forms, never introduces errors). The `match` default case returns `node` unchanged.

### Test Module Structure

All test files follow:
1. Module docstring
2. `from __future__ import annotations`
3. Imports (stdlib, pytest, project)
4. Private helpers at top
5. Tests grouped by feature with `# -- Section header` comments

### Golden File Assertion Pattern

From `tests/conftest.py` lines 83-117:
```python
def assert_golden(actual: str, golden_path: Path) -> None:
    """Assert that *actual* matches the content of *golden_path*."""
    golden = golden_path.read_text(encoding="utf-8")
    def _norm(s: str) -> list[str]:
        return [line.rstrip() for line in s.splitlines()]
    actual_lines = _norm(actual)
    golden_lines = _norm(golden)
    if actual_lines != golden_lines:
        diff = "\n".join(difflib.unified_diff(...))
        raise AssertionError(f"Output does not match golden file {golden_path}:\n{diff}")
```

**Apply as:** Golden parity tests in Phase 4 use this exact helper. A new `test_golden_parity_all()` function loops over all golden files and asserts each one.

---

## Data Flow Summary

```
                    Phase 4 insertion point
                           |
                           v
invoke_slang -> import_assertion -> [normalize] -> compose -> emit -> write_output
                                        ^              |
                                        |              v
                                   normalizer.py   structural_hash() added here
                                                       |
                                                       v
                                              dict[CheckerNode, str]
                                                       |
                                    --dump-tree -----> debug.py -> stdout + exit(0)
```

---

## Key Constraints Summary

| Constraint | Enforcement |
|---|---|
| Golden file byte-for-byte parity (D-11) | `assert_golden()` on all 29 files in test suite |
| Normalizer idempotency (D-02) | `normalize(normalize(x)) == normalize(x)` property test |
| No `\|=>` desugaring for standalone (D-05) | Normalizer leaves top-level `PropImplication(overlapping=False)` unchanged |
| Deterministic hash across runs (D-07) | `hashlib.sha256` (never Python `hash()`), sorted param keys |
| `--dump-tree` prints and exits 0 (D-10) | Same pattern as `--dump-ast`: `click.echo()` + `sys.exit(0)` |
| Bottom-up single pass O(n) (D-02) | Children normalized before parent in match/case dispatch |

---

*Pattern mapping complete: 2026-05-27*
*All files classified by role, data flow, and closest codebase analog with concrete code excerpts.*
