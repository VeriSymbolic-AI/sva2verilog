# Plan 3.1: Consecutive Repetition `[*N]` and `[*M:N]`

---
wave: 1
depends_on: []
files_modified:
  - src/sva2rtl/ir.py
  - src/sva2rtl/ast_importer.py
  - src/sva2rtl/composer.py
  - src/sva2rtl/behavioral_oracle.py
  - templates/rep_consecutive.sv.j2
  - tests/fixtures/rep_fixed.json
  - tests/fixtures/rep_range.json
  - tests/test_repetition.py
  - tests/golden/sva_rep_fixed.sv
  - tests/golden/sva_rep_range.sv
autonomous: true
requirements:
  - OP-05
---

## Summary

Deliver end-to-end consecutive repetition (`[*N]` and `[*M:N]`) from AST import through IR, composer, template, to behavioral oracle and tests. Uses counter-based FSM architecture reusing the same counter width formula as `concat_delay`. Rejects unbounded `[*0:$]` with SVA-E002 error.

## Vertical Slice

`a[*3]` in SVA input file -> slang JSON -> `SeqRepetition` IR node -> `rep_consecutive` CheckerNode -> `rep_consecutive.sv.j2` template -> compilable SV monitor with correct pass/fail semantics. Behavioral oracle validates cycle-by-cycle correctness.

<threat_model>
- **File path injection:** N/A - no user-supplied file paths used in template generation
- **Integer overflow:** Counter width is computed from `rep_max`; bounded by Python int. Template uses parameterized `CNT_WIDTH` — no overflow possible for v1 range values.
- **Denial of service:** Large `rep_max` values (e.g., 2^31) could produce impractical RTL. Mitigated by counter encoding (log2 bits) — even rep_max=1M uses only 20-bit counter.
- **Silent miscompile:** Unbounded `[*0:$]` rejected with SVA-E002 error, not silently compiled to incorrect hardware.
- **Severity:** All LOW. No high-severity threats identified.
</threat_model>

## Tasks

<task id="3.1.1">
<title>Add SeqRepetition IR node to ir.py</title>
<read_first>
- src/sva2rtl/ir.py
</read_first>
<action>
Add a new frozen dataclass `SeqRepetition(SVANode)` after the `SeqConcat` class (around line 76). Fields: `expr: SVANode` (the expression being repeated), `rep_min: int` (minimum repetition count), `rep_max: int` (maximum repetition count). Follow the exact same pattern as `SeqConcat` — frozen=True, source_loc inherited from SVANode base.
</action>
<acceptance_criteria>
- `ir.py` contains `class SeqRepetition(SVANode):` with `frozen=True`
- `SeqRepetition` has fields `expr: SVANode`, `rep_min: int`, `rep_max: int`
- `SeqRepetition` is hashable: `hash(SeqRepetition(expr=BoolExpr(text="a", source_loc=loc), rep_min=2, rep_max=5, source_loc=loc))` succeeds
- `mypy --strict src/sva2rtl/ir.py` exits 0
</acceptance_criteria>
</task>

<task id="3.1.2">
<title>Add AST importer dispatch for consecutive repetition</title>
<read_first>
- src/sva2rtl/ast_importer.py
- src/sva2rtl/ir.py
- .planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-RESEARCH.md (Section 1.1)
</read_first>
<action>
1. Remove `"SequenceRepetition"` from `UNSUPPORTED_KINDS_PHASE1` dict (line 49-51).
2. Add `SeqRepetition` to the import from `sva2rtl.ir`.
3. In `_import_concurrent_assertion`, add a new match case BEFORE the default case: `case "SimpleAssertionExpr"` when the node has a `"repetition"` field with `"kind": "Consecutive"` — call a new `_build_seq_repetition(expr_node, source_loc)` builder.
4. Also add the same case in `_dispatch_expr_to_ir` so repetition works as child of other sequences.
5. Implement `_build_seq_repetition(node, source_loc) -> SeqRepetition`:
   - Extract `repetition.min` as `rep_min` (int)
   - Extract `repetition.max` — if value is `"$"`, raise `SvaCompileError` with message containing "SVA-E002" and "unbounded repetition"
   - Otherwise cast to int as `rep_max`
   - Fixed repetition: when only `min == max`, both set to N
   - Build inner expression via `_dispatch_expr_to_ir(node.get("expr", {}))`
   - Return `SeqRepetition(expr=inner, rep_min=rep_min, rep_max=rep_max, source_loc=source_loc)`
6. Add `_reconstruct_rep_text(node: SeqRepetition) -> str` that returns `"{inner_text} [*{min}:{max}]"` or `"{inner_text} [*{N}]"` for fixed.
</action>
<acceptance_criteria>
- `UNSUPPORTED_KINDS_PHASE1` dict is empty `{}`
- `_build_seq_repetition` exists and returns `SeqRepetition`
- Calling `import_assertion` on a fixture JSON with `"repetition": {"kind": "Consecutive", "min": 3, "max": 3}` returns a `SeqRepetition` node with `rep_min=3, rep_max=3`
- Fixture with `"max": "$"` raises `SvaCompileError` with "SVA-E002" in the message
- `mypy --strict src/sva2rtl/ast_importer.py` exits 0
</acceptance_criteria>
</task>

<task id="3.1.3">
<title>Add composer support for SeqRepetition</title>
<read_first>
- src/sva2rtl/composer.py
- src/sva2rtl/ir.py
</read_first>
<action>
1. Add `SeqRepetition` to the import from `sva2rtl.ir`.
2. Add a new match case in `compose()` function: `case SeqRepetition():` -> call `_compose_repetition(node, clock, label, original_text)`.
3. Implement `_compose_repetition`:
   - Compute `cnt_width = max(1, math.ceil(math.log2(node.rep_max + 1))) if node.rep_max > 0 else 1`
   - Derive `module_name` via `module_name_from_label(label, original_text)`
   - Extract `observed_signals` from `node.expr` if it's a `BoolExpr` (using `extract_signals(node.expr.text)`)
   - Extract the inner expression text: `node.expr.text` if BoolExpr, else `"<expr>"`
   - Build params dict with keys: `module_name`, `rep_min` (str), `rep_max` (str), `cnt_width` (str), `signal_expr` (inner expression text), `clock_signal`, `clock_edge`, `source_loc`, `sva2rtl_version`, `original_text`
   - Return `CheckerNode(template_name="rep_consecutive", module_name=module_name, params=params, observed_signals=observed, source_loc=node.source_loc, children=())`
</action>
<acceptance_criteria>
- `compose()` accepts a `SeqRepetition` node without raising `UnsupportedConstruct`
- Returned CheckerNode has `template_name="rep_consecutive"`
- `params["rep_min"]` and `params["rep_max"]` are string representations of the repetition bounds
- `params["cnt_width"]` equals `"2"` for rep_max=3 (ceil(log2(4))=2)
- `mypy --strict src/sva2rtl/composer.py` exits 0
</acceptance_criteria>
</task>

<task id="3.1.4">
<title>Create rep_consecutive.sv.j2 template</title>
<read_first>
- templates/concat_delay.sv.j2
- templates/bool_expr.sv.j2
</read_first>
<action>
Create `templates/rep_consecutive.sv.j2`. Structure:
- Header comment block (same pattern: sva2rtl_version, source_loc, original_text)
- Module declaration with parameter `CNT_WIDTH = {{ cnt_width }}`
- Ports: `clk` ({{ clock_signal }}), `rst_n`, `start`, observed_signals loop (input logic {{ port_name }}), `disable_i`, then outputs: `active`, `pass`, `fail`, `attempt_fired`, `disabled_o`
- Internal logic: counter `count_q[CNT_WIDTH-1:0]`, `running_q`, `attempt_fired_q`
- Signal evaluation: `assign sig_eval = ({{ signal_expr }});`
- `always_ff` block with reset condition `(!rst_n | disable_i)`:
  - Reset: all to 0
  - Else: sticky attempt_fired; on `start && sig_eval`: set running, count=1; on `start && !sig_eval`: nothing (immediate fail path); while `running_q && sig_eval`: increment counter, stop at rep_max; while `running_q && !sig_eval`: clear running (broken)
- Output assigns with disable gating:
  - `pass_internal = running_q && sig_eval && (count_q >= CNT_WIDTH'd{rep_min}) && (count_q <= CNT_WIDTH'd{rep_max})`
  - `fail_internal = running_q && !sig_eval && (count_q < CNT_WIDTH'd{rep_min})`
  - `active_internal = running_q`
  - Gate all with `disable_i ? 1'b0 : *_internal`
  - `disabled_o = disable_i`
</action>
<acceptance_criteria>
- File `templates/rep_consecutive.sv.j2` exists
- Template renders without Jinja2 errors when given params: `module_name`, `cnt_width`, `rep_min`, `rep_max`, `signal_expr`, `clock_signal`, `clock_edge`, `source_loc`, `sva2rtl_version`, `original_text`, `observed_signals`, `children`
- Rendered output contains `module sva_rep_check` (or whatever module_name is passed)
- Rendered output contains `input logic disable_i` and `output logic disabled_o`
- Rendered output contains `parameter CNT_WIDTH`
- Rendered output contains counter logic with `count_q` and `running_q`
- `endmodule` is the last non-empty line
</acceptance_criteria>
</task>

<task id="3.1.5">
<title>Add behavioral oracle for rep_consecutive</title>
<read_first>
- src/sva2rtl/behavioral_oracle.py
</read_first>
<action>
1. Add `"rep_consecutive"` to `_valid_kinds` set.
2. Add oracle state in `__init__`: `self._rep_count: int = 0`, `self._rep_running: bool = False`.
3. Add to `reset()`: reset `_rep_count` to 0 and `_rep_running` to False.
4. Extend `tick()` dispatch: `elif self._kind == "rep_consecutive": return self._tick_rep_consecutive(signals)`
5. Implement `_tick_rep_consecutive(self, signals: dict[str, bool]) -> dict[str, bool]`:
   - Extract `start = signals.get("start", False)` and `sig = signals.get("sig", False)`
   - Extract `rep_min = int(self._params.get("rep_min", 1))`, `rep_max = int(self._params.get("rep_max", 1))`
   - Logic: if start and sig: begin counting (count=1, running=True); if running and sig: increment count (up to rep_max then stop); if running and not sig: broken (running=False)
   - pass = running and sig and count >= rep_min and count <= rep_max
   - fail = running and not sig and count < rep_min
   - active = running
   - Return dict with keys: "active", "pass", "fail", "overflow" (always False)
</action>
<acceptance_criteria>
- `SVABehavioralSim("rep_consecutive", {"rep_min": 3, "rep_max": 3})` creates successfully
- A 3-cycle trace `[start+sig, sig, sig]` produces `pass=True` on tick 3
- A 2-cycle trace `[start+sig, not-sig]` produces `fail=True` on tick 2
- `mypy --strict src/sva2rtl/behavioral_oracle.py` exits 0
</acceptance_criteria>
</task>

<task id="3.1.6">
<title>Create test fixtures and tests for consecutive repetition</title>
<read_first>
- tests/test_sequential.py
- tests/test_behavioral_oracle.py
- tests/fixtures/delay_fixed.json
- src/sva2rtl/ast_importer.py
- src/sva2rtl/composer.py
</read_first>
<action>
1. Create `tests/fixtures/rep_fixed.json`: Slang-style AST JSON with `"kind": "SimpleAssertionExpr"` containing `"repetition": {"kind": "Consecutive", "min": 3, "max": 3}` and inner expr as NamedValue "a". Wrap in full ConcurrentAssertion/PropertySpec/clocking structure matching existing fixture patterns.
2. Create `tests/fixtures/rep_range.json`: Same structure with `"min": 2, "max": 5`.
3. Create `tests/test_repetition.py` with:
   - `test_ir_node_creation()`: construct SeqRepetition, assert frozen, assert fields
   - `test_import_rep_fixed()`: load rep_fixed.json, call import_assertion, assert returns SeqRepetition with rep_min=3, rep_max=3
   - `test_import_rep_range()`: load rep_range.json, assert rep_min=2, rep_max=5
   - `test_import_unbounded_rejects()`: fixture with max="$", assert raises SvaCompileError with "SVA-E002"
   - `test_compose_rep_fixed()`: import + compose, assert CheckerNode.template_name == "rep_consecutive"
   - `test_emit_rep_fixed()`: full pipeline through emit_all, assert output contains `module` and `endmodule`
   - `test_oracle_rep_exact_3()`: behavioral oracle with rep_min=3, rep_max=3; verify pass on exactly 3 consecutive true
   - `test_oracle_rep_fail_early()`: verify fail when signal drops before rep_min
   - `test_oracle_rep_range_2_5()`: verify pass at counts 2, 3, 4, 5; fail before 2
4. Create golden files after first successful run: `tests/golden/sva_rep_fixed.sv`, `tests/golden/sva_rep_range.sv`
</action>
<acceptance_criteria>
- `pytest tests/test_repetition.py -v` exits 0 with all tests passing
- At least 8 test functions exist in `test_repetition.py`
- Unbounded repetition test asserts `SvaCompileError` with "SVA-E002" in message
- Golden file `tests/golden/sva_rep_fixed.sv` contains `parameter CNT_WIDTH = 2` (ceil(log2(3+1))=2)
- `mypy --strict tests/test_repetition.py` exits 0
</acceptance_criteria>
</task>

## Verification

```bash
# All tests pass
pytest tests/test_repetition.py -v

# Type checking
mypy --strict src/sva2rtl/ir.py src/sva2rtl/ast_importer.py src/sva2rtl/composer.py src/sva2rtl/behavioral_oracle.py

# Linting
ruff check src/sva2rtl/ tests/test_repetition.py

# Existing tests still pass (no regression)
pytest tests/ -v --ignore=tests/test_repetition.py
```

## must_haves

- [ ] `SeqRepetition` IR node exists and is frozen/hashable
- [ ] AST importer handles `SimpleAssertionExpr` with consecutive repetition
- [ ] Unbounded `[*0:$]` rejected with SVA-E002
- [ ] Composer produces CheckerNode with `template_name="rep_consecutive"`
- [ ] Template renders compilable SV with counter-based FSM
- [ ] Behavioral oracle correctly models [*N]/[*M:N] semantics
- [ ] All new tests pass; no regressions in existing tests
