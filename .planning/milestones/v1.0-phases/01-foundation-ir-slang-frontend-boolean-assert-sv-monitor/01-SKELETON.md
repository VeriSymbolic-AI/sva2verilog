# Walking Skeleton: sva2rtl Phase 1

**Purpose:** Define the thinnest possible end-to-end slice that proves the entire compiler pipeline works.

---

## The Slice

**Input:** A `.sv` file containing a single boolean SVA assertion:
```systemverilog
module test_bool(input logic clk, rst_n, a, b);
  my_check: assert property (@(posedge clk) a && b);
endmodule
```

**Output:** A compilable SystemVerilog monitor module (`sva_my_check.sv`) with:
- Standard port interface: `clk, rst_n, start, a, b, active, pass, fail, attempt_fired`
- Registered outputs (1-FF pipeline)
- Synchronous reset
- Original SVA text as header comment
- Module name derived from assertion label

**Proof of Life:** `iverilog -g2012 sva_my_check.sv` compiles with zero errors/warnings.

---

## Pipeline Stages (Walking Skeleton Path)

```
bool_assert.sv
      |
      v
[1] frontend.py         slang --ast-json --ast-json-source-info bool_assert.sv
      |                  -> writes JSON to temp file, reads it back as dict
      v
[2] ast_importer.py     JSON dict -> BoolExpr(text="(a && b)") + ClockSpec(edge="posedge", signal="clk")
      |                  - Extracts SourceLoc from every node
      |                  - Reconstructs boolean expression text via expr_to_sv()
      |                  - Raises UnsupportedConstruct for ##N, |->  etc.
      v
[3] composer.py         BoolExpr -> CheckerNode(template_name="bool_expr", module_name="sva_my_check", ...)
      |                  - Simple 1:1 mapping for boolean leaf
      |                  - Sets start=1'b1 (top-level always active)
      v
[4] emitter.py          CheckerNode -> Jinja2 render -> SV text string
      |                  - Loads templates/bool_expr.sv.j2
      |                  - Fills template variables from CheckerNode.params
      v
[5] cli.py              Writes output to file or stdout; handles errors -> exit codes
```

---

## Minimum Viable Artifacts

| Artifact | Purpose |
|----------|---------|
| `pyproject.toml` | Package config, dependencies, CLI entry point |
| `src/sva2rtl/__init__.py` | Package marker + version |
| `src/sva2rtl/ir.py` | `SourceLoc`, `BoolExpr`, `SeqConcat`, `PropImplication`, `ClockSpec`, `CheckerNode` |
| `src/sva2rtl/errors.py` | `SvaError`, `SlangNotFound`, `UnsupportedConstruct`, `SvaCompileError` |
| `src/sva2rtl/frontend.py` | `invoke_slang()` subprocess wrapper |
| `src/sva2rtl/ast_importer.py` | `import_assertion()` JSON -> IR + `expr_to_sv()` |
| `src/sva2rtl/composer.py` | `compose()` SVANode -> CheckerNode |
| `src/sva2rtl/emitter.py` | `emit()` CheckerNode -> SV text via Jinja2 |
| `src/sva2rtl/cli.py` | Click entry point with `--output`, `--slang-path` |
| `templates/bool_expr.sv.j2` | Boolean assertion monitor template |
| `tests/test_ir.py` | IR dataclass unit tests |
| `tests/test_ast_importer.py` | AST importer tests with JSON fixtures |
| `tests/test_emitter.py` | Emitter golden output tests |
| `tests/fixtures/bool_simple.json` | Slang JSON fixture for `a && b` |
| `tests/golden/bool_simple.sv` | Expected emitter output |

---

## Success Proof

```bash
# 1. End-to-end compile
uv run sva2rtl tests/fixtures/bool_assert.sv -o /tmp/sva_my_check.sv
echo $?   # -> 0

# 2. Generated SV compiles clean
iverilog -g2012 /tmp/sva_my_check.sv
echo $?   # -> 0

# 3. Unsupported construct → exit 2 with source location
uv run sva2rtl tests/fixtures/delay_assert.sv
echo $?   # -> 2
# stderr: "delay_assert.sv:3:25: error SVA-E002: unsupported construct '##N sequence concatenation (Phase 2)'"

# 4. Slang not found → exit 3
uv run sva2rtl --slang-path /nonexistent/slang tests/fixtures/bool_assert.sv
echo $?   # -> 3
# stderr: "slang not found at '/nonexistent/slang'.\nInstall: https://..."

# 5. All tests pass
uv run pytest tests/ -v
uv run mypy src/sva2rtl --strict
uv run ruff check src/ tests/
```

---

## What This Skeleton Does NOT Include

- No `##N`, `|->`, `|=>`, `[*N]`, or any temporal operators (Phase 2+)
- No normalization pass (Phase 4)
- No optimization (Phase 5)
- No `--verilog` flag (Phase 6)
- No `--dump-ast`, `--dump-ir`, `--dump-tree` (Phase 6)
- No `bind` wrapper generation (Phase 3)
- No multi-bit signal support (deferred)
- No named property resolution (Phase 3)

---

## Interface Contract (Locked from Phase 1)

Every generated checker module exposes:
```systemverilog
module sva_<label> (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic <observed_sig_1>,
    ...
    output logic active,
    output logic pass,
    output logic fail,
    output logic attempt_fired
);
```

This interface is **non-negotiable** and **cannot change** in subsequent phases. All Phase 2+ templates must expose this exact port set (plus operator-specific debug ports like `overflow_flag`).

---

*Walking skeleton defined: 2026-05-25*
