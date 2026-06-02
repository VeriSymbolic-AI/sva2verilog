---
wave: 1
depends_on: []
files_modified:
  - src/sva2rtl/emitter.py
  - templates/bool_expr.sv.j2
  - templates/concat_delay.sv.j2
  - templates/overlap_bitvec.sv.j2
  - templates/nonoverlap.sv.j2
  - templates/rose.sv.j2
  - templates/fell.sv.j2
  - templates/stable.sv.j2
  - templates/past.sv.j2
  - templates/rep_consecutive.sv.j2
  - templates/seq_concat_top.sv.j2
  - templates/disable_iff_top.sv.j2
  - tests/test_verilog_mode.py
autonomous: true
---

# Plan 6.2: Verilog-2001 Output Mode (`--verilog` Template Conversion)

## Goal

Deliver Verilog-2001 compatible output: when `verilog_mode=True` is passed to the emitter, all 11 RTL templates (excluding `bind.sv.j2`) produce output that compiles clean with `iverilog -g2001`. This is a complete vertical slice — the feature is testable in isolation via the emitter API without requiring CLI changes from Plan 6.1.

## Requirements

- **OUT-05**: `--verilog` flag emits Verilog-2001 compatible output (`wire`/`reg`, `always @(posedge)`)

## Threat Model

<threat_model>
- **Template injection**: Not applicable — templates are static files in the repo, not user-supplied. `verilog_mode` is a boolean only.
- **Output file overwrite**: Already handled by emitter's write_output() path validation (user controls --output path).
- **Malformed RTL causing synthesis tool crash**: Mitigated by iverilog -g2001 compile tests validating output correctness.
</threat_model>

## Tasks

<task id="6.2.1">
<title>Thread `verilog_mode` through emitter API</title>
<read_first>
- src/sva2rtl/emitter.py (current `emit()`, `emit_all()`, `_emit_recursive()` signatures and context building)
</read_first>
<action>
Add `verilog_mode: bool = False` keyword-only parameter to `emit()`, `emit_all()`, and `_emit_recursive()`. In each function's context-building section, add `ctx["verilog_mode"] = verilog_mode`. Thread the parameter from `emit_all()` → `_emit_recursive()` calls. Function signatures become:
- `def emit(checker: CheckerNode, template_dir: Path | None = None, *, verilog_mode: bool = False) -> str:`
- `def emit_all(checker: CheckerNode, template_dir: Path | None = None, *, verilog_mode: bool = False) -> dict[str, str]:`
- `def _emit_recursive(checker: CheckerNode, env: Environment, results: dict[str, str], *, verilog_mode: bool = False) -> None:`

Also add `verilog_mode` to `emit_bind()` for completeness (bind template has no logic/always_ff so it's a no-op, but API consistency matters).
</action>
<acceptance_criteria>
- `emit()` signature includes `*, verilog_mode: bool = False`
- `emit_all()` signature includes `*, verilog_mode: bool = False`
- `_emit_recursive()` signature includes `*, verilog_mode: bool = False`
- `ctx["verilog_mode"] = verilog_mode` appears in `emit()` context building
- `ctx["verilog_mode"] = verilog_mode` appears in `_emit_recursive()` context building
- `emit(checker, verilog_mode=False)` produces identical output to current behavior (no regression)
- `mypy --strict src/sva2rtl/emitter.py` exits 0
</acceptance_criteria>
</task>

<task id="6.2.2">
<title>Convert `bool_expr.sv.j2` to support Verilog-2001</title>
<read_first>
- templates/bool_expr.sv.j2 (current template content)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-PATTERNS.md (Verilog-2001 conversion patterns section)
</read_first>
<action>
Add `{% if verilog_mode %}` / `{% else %}` guards for:
1. Port declarations: `input logic X` → `input X`; `output logic X` → `output X`
2. Internal signals: `logic bool_result` → `wire bool_result`; `logic active_q, pass_q, fail_q, attempt_fired_q` → `reg active_q, pass_q, fail_q, attempt_fired_q`
3. Sequential block: `always_ff @(...)` → `always @(...)`

No `'0` literals exist in this template (uses `1'b0`), so no literal conversion needed. All output ports use `assign` (wire default in Verilog-2001), so outputs stay as `output X` not `output reg X`.
</action>
<acceptance_criteria>
- Template renders without error when `verilog_mode=True`
- Rendered Verilog-2001 output contains NO `logic` keyword
- Rendered Verilog-2001 output contains NO `always_ff`
- Rendered Verilog-2001 output contains `always @(posedge`
- Rendered Verilog-2001 output contains `reg active_q` (or similar reg declaration)
- Rendered Verilog-2001 output contains `wire bool_result`
- Rendered SystemVerilog output (verilog_mode=False) is byte-for-byte identical to current output
</acceptance_criteria>
</task>

<task id="6.2.3">
<title>Convert `concat_delay.sv.j2` to support Verilog-2001</title>
<read_first>
- templates/concat_delay.sv.j2 (current template content)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-PATTERNS.md (Verilog-2001 conversion patterns, zero literal section)
</read_first>
<action>
Add Verilog-2001 guards for:
1. Port declarations: `input logic` → `input`; `output logic` → `output`
2. Internal signals: `logic [CNT_WIDTH-1:0] count_q` → `reg [CNT_WIDTH-1:0] count_q`; `logic running_q` → `reg running_q`; `logic attempt_fired_q` → `reg attempt_fired_q`
3. Sequential block: `always_ff @(...)` → `always @(...)`
4. Zero literal: `count_q <= '0;` → `count_q <= 0;` (in both the reset and start branches)

The `##0` path has only `attempt_fired_q` as reg; the other signals are `assign`-driven (wire).
</action>
<acceptance_criteria>
- Template renders without error when `verilog_mode=True`
- Rendered Verilog-2001 output contains NO `logic` keyword
- Rendered Verilog-2001 output contains NO `always_ff`
- Rendered Verilog-2001 output contains NO `'0` literal
- Rendered Verilog-2001 output contains `reg [CNT_WIDTH-1:0] count_q` (in non-##0 path)
- Rendered SystemVerilog output (verilog_mode=False) is byte-for-byte identical to current output
</acceptance_criteria>
</task>

<task id="6.2.4">
<title>Convert `overlap_bitvec.sv.j2` and `nonoverlap.sv.j2` to support Verilog-2001</title>
<read_first>
- templates/overlap_bitvec.sv.j2 (current template content)
- templates/nonoverlap.sv.j2 (current template content)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-PATTERNS.md (conversion matrix)
</read_first>
<action>
For both templates, add Verilog-2001 guards:
1. Port declarations: `input logic` → `input`; `output logic` → `output`
2. Internal reg signals (in always_ff): `logic [BV_WIDTH-1:0] bv_q` → `reg [BV_WIDTH-1:0] bv_q`; `logic overflow_flag_q` → `reg overflow_flag_q`; `logic attempt_fired_q` → `reg attempt_fired_q`
3. Internal wire signals (in assign): `logic ant_pass_w` → `wire ant_pass_w`, etc.
4. Sequential block: `always_ff @(...)` → `always @(...)`
5. Zero literal: `bv_q <= '0;` → `bv_q <= 0;`

Both templates follow the same structure (child instances + shift register + assign outputs).
</action>
<acceptance_criteria>
- Both templates render without error when `verilog_mode=True`
- Rendered Verilog-2001 output from both contains NO `logic`, `always_ff`, or `'0`
- Rendered Verilog-2001 contains `always @(posedge` in the sequential block
- Rendered SystemVerilog output (verilog_mode=False) is byte-for-byte identical to current output for both templates
</acceptance_criteria>
</task>

<task id="6.2.5">
<title>Convert signal function templates (`rose`, `fell`, `stable`, `past`) to support Verilog-2001</title>
<read_first>
- templates/rose.sv.j2 (current template content)
- templates/fell.sv.j2 (current template content)
- templates/stable.sv.j2 (current template content)
- templates/past.sv.j2 (current template content)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-PATTERNS.md (conversion matrix)
</read_first>
<action>
For all four templates, add Verilog-2001 guards:
1. Port declarations: `input logic` → `input`; `output logic` → `output`
2. Internal reg signals: `sig_prev_q`, `attempt_fired_q`, `shift_q` → `reg`
3. Internal wire signals: `rose_detect`, `fell_detect`, `stable_detect`, `pass_internal`, `fail_internal`, `past_value` → `wire`
4. Sequential block: `always_ff @(...)` → `always @(...)`
5. `past.sv.j2` only: `shift_q <= '0;` → `shift_q <= 0;`

`rose`, `fell`, `stable` have no `'0` literals (use `1'b0` which is valid in both SV and Verilog-2001).
</action>
<acceptance_criteria>
- All four templates render without error when `verilog_mode=True`
- Rendered output from all four contains NO `logic`, `always_ff`, or `'0`
- `past.sv.j2` Verilog-2001 output has no `'0` (uses `0` instead)
- Rendered SystemVerilog output (verilog_mode=False) is byte-for-byte identical for all four templates
</acceptance_criteria>
</task>

<task id="6.2.6">
<title>Convert `rep_consecutive.sv.j2`, `seq_concat_top.sv.j2`, `disable_iff_top.sv.j2` to support Verilog-2001</title>
<read_first>
- templates/rep_consecutive.sv.j2 (current template content)
- templates/seq_concat_top.sv.j2 (current template content)
- templates/disable_iff_top.sv.j2 (current template content)
- .planning/phases/06-cli-polish-verilog-2001-integration-testing/06-PATTERNS.md (conversion matrix)
</read_first>
<action>
For `rep_consecutive.sv.j2`:
1. Port declarations: `input logic` → `input`; `output logic` → `output`
2. Internal regs: `count_q`, `running_q`, `attempt_fired_q` → `reg`
3. Sequential block: `always_ff` → `always @(...)`
4. Zero literal: `count_q <= '0;` → `count_q <= 0;`

For `seq_concat_top.sv.j2` (wire-only, no registers):
1. Port declarations: `input logic` → `input`; `output logic` → `output`
2. Internal signals: all are `wire` (driven by child instance ports or `assign`)
3. No `always_ff` or `'0` to convert

For `disable_iff_top.sv.j2` (wire-only, no registers):
1. Port declarations: `input logic` → `input`; `output logic` → `output`
2. Internal signals: `cond_result`, `effective_disable` → `wire`
3. No `always_ff` or `'0` to convert
</action>
<acceptance_criteria>
- All three templates render without error when `verilog_mode=True`
- Rendered output from all three contains NO `logic`, `always_ff`, or `'0`
- `seq_concat_top` and `disable_iff_top` Verilog-2001 output contains NO `reg` keyword (wire-only)
- `rep_consecutive` Verilog-2001 output contains `reg` for counter signals
- Rendered SystemVerilog output (verilog_mode=False) is byte-for-byte identical for all three templates
</acceptance_criteria>
</task>

<task id="6.2.7">
<title>Write Verilog-2001 mode tests</title>
<read_first>
- tests/test_golden_parity.py (pipeline helper pattern, parametrized test pattern)
- tests/test_emitter.py (emit() invocation patterns)
- src/sva2rtl/emitter.py (emit/emit_all signatures from task 6.2.1)
- tests/fixtures/ (list of available JSON fixtures)
</read_first>
<action>
Create `tests/test_verilog_mode.py` with:

1. `_run_pipeline_verilog(fixture_name: str) -> dict[str, str]` — helper running normalize→compose→emit_all(verilog_mode=True)
2. `test_verilog_mode_no_logic_keyword` — parametrized over all fixture files; asserts `"logic"` not in any emitted module text
3. `test_verilog_mode_no_always_ff` — parametrized; asserts `"always_ff"` not in output
4. `test_verilog_mode_no_tick_zero` — parametrized; asserts `"<= '0"` not in output
5. `test_verilog_mode_has_always_posedge` — for fixtures that produce registered output; asserts `"always @(posedge"` or `"always @(negedge"` present
6. `test_verilog_mode_sv_unchanged` — parametrized; asserts `emit(checker, verilog_mode=False)` produces same output as before (no regression)
7. `test_verilog_mode_wire_for_assign_signals` — for bool_expr fixture; asserts `"wire bool_result"` in output
8. `test_verilog_mode_reg_for_sequential_signals` — for bool_expr fixture; asserts `"reg active_q"` or similar pattern

Use fixture files: `bool_simple.json`, `bool_labeled.json`, `unsupported_delay.json` (which is actually a concat test), and any others available in `tests/fixtures/`.
</action>
<acceptance_criteria>
- `tests/test_verilog_mode.py` exists with at least 8 test functions
- `uv run pytest tests/test_verilog_mode.py -v` exits 0 (all pass)
- Tests verify NO `logic`, NO `always_ff`, NO `'0` in Verilog-2001 output
- Tests verify SystemVerilog mode output is unchanged (golden parity)
- `uv run ruff check tests/test_verilog_mode.py` exits 0
</acceptance_criteria>
</task>

## Verification

```bash
uv run mypy --strict src/sva2rtl/emitter.py
uv run pytest tests/test_verilog_mode.py tests/test_golden_parity.py tests/test_emitter.py -v
uv run ruff check src/ tests/
# Golden parity (ensures SV mode unbroken):
uv run pytest tests/test_golden_parity.py -v
```

## must_haves

- `verilog_mode` parameter threaded through `emit()` / `emit_all()` API (OUT-05 wiring)
- All 11 RTL templates produce output with NO `logic`, `always_ff`, or `'0` when `verilog_mode=True` (OUT-05)
- SystemVerilog output (default mode) is byte-for-byte identical to pre-change output (no regression)
- Verilog-2001 output uses `reg` for sequential signals and `wire` for combinational signals
- `always_ff @(...)` becomes `always @(...)` in Verilog-2001 mode
