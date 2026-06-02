---
wave: 1
depends_on: []
files_modified:
  - src/sva2rtl/ir.py
  - src/sva2rtl/ast_importer.py
  - src/sva2rtl/composer.py
  - src/sva2rtl/behavioral_oracle.py
  - templates/rose.sv.j2
  - templates/fell.sv.j2
  - templates/stable.sv.j2
  - templates/past.sv.j2
  - tests/fixtures/rose.json
  - tests/fixtures/fell.json
  - tests/fixtures/stable.json
  - tests/fixtures/past.json
  - tests/test_signal_functions.py
  - tests/golden/sva_rose.sv
  - tests/golden/sva_fell.sv
  - tests/golden/sva_stable.sv
  - tests/golden/sva_past.sv
autonomous: true
requirements:
  - OP-06
  - OP-07
  - OP-08
  - OP-09
---

# Plan 3.2: Signal Function Operators (`$rose`, `$fell`, `$stable`, `$past`)

## Summary

Deliver all four signal function operators (`$rose`, `$fell`, `$stable`, `$past`) end-to-end: AST import, IR node (`SignalFunc`), composer, four Jinja2 templates, behavioral oracle, and unit tests. Each function generates minimal hardware: 1 FF for rose/fell/stable, N FFs for past(sig, N).

## Vertical Slice

`$rose(sig)` in SVA -> slang `CallExpression` JSON -> `SignalFunc("rose", "sig", depth=1)` IR node -> CheckerNode(template_name="rose") -> `rose.sv.j2` template -> SV module with 1 FF + edge detect logic. Same pattern for fell/stable/past.

<threat_model>
- **Integer overflow in $past depth:** `$past(sig, N)` with very large N creates N FFs. Mitigated: emit warning for N > 32 (not error). Counter width is bounded.
- **Non-literal N in $past:** Non-compile-time N rejected with unsupported construct error, preventing runtime-dependent hardware.
- **Silent miscompile:** Unknown system function names raise `UnsupportedConstruct` — never silently skipped.
- **Severity:** All LOW. No high-severity threats identified.
</threat_model>

## Tasks

<task id="3.2.1">
<title>Add SignalFunc IR node to ir.py</title>
<read_first>
- src/sva2rtl/ir.py
</read_first>
<action>
Add a new frozen dataclass `SignalFunc(SVANode)` after the `SeqRepetition` class (or after SeqConcat if 3.1 hasn't been applied yet). Fields: `func_name: str` (one of "rose", "fell", "stable", "past"), `signal: str` (the signal name), `depth: int = 1` (pipeline depth for $past; 1 is default, ignored for rose/fell/stable). Follow same pattern as BoolExpr — frozen=True, source_loc from SVANode.
</action>
<acceptance_criteria>
- `ir.py` contains `class SignalFunc(SVANode):` with `frozen=True`
- `SignalFunc` has fields `func_name: str`, `signal: str`, `depth: int`
- `depth` has default value `1`
- Instance is hashable: `hash(SignalFunc(func_name="rose", signal="sig", depth=1, source_loc=loc))` succeeds
- `mypy --strict src/sva2rtl/ir.py` exits 0
</acceptance_criteria>
</task>

<task id="3.2.2">
<title>Add AST importer dispatch for system function calls</title>
<read_first>
- src/sva2rtl/ast_importer.py
- src/sva2rtl/ir.py
- .planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-RESEARCH.md (Section 1.2)
</read_first>
<action>
1. Add `SignalFunc` to the import from `sva2rtl.ir`.
2. In `expr_to_sv()`, add a new match case for `"CallExpression"` BEFORE the default `case _:`:
   - Extract `subroutineName` field
   - If name is in `{"$rose", "$fell", "$stable", "$past"}`: call `_build_signal_func(node, source_loc)` and return a placeholder text (e.g., the function call text reconstructed)
   - Otherwise: raise `UnsupportedConstruct` for unknown system functions
3. In `_dispatch_expr_to_ir()`, add a match case for `"CallExpression"` that checks `subroutineName` is a supported signal function, then returns a `SignalFunc` IR node directly.
4. Similarly in `_import_concurrent_assertion`, add a match case for when `expr_node` is a `CallExpression` with a supported system function name.
5. Implement `_build_signal_func(node: dict, source_loc: SourceLoc) -> SignalFunc`:
   - Extract `subroutineName` → strip "$" prefix for `func_name` ("$rose" -> "rose")
   - Extract first argument's signal name via the `arguments[0]` NamedValue symbol field
   - For `$past`: extract second argument as integer depth (default 1 if absent); reject non-IntegerLiteral second arg with UnsupportedConstruct
   - Return `SignalFunc(func_name=func_name, signal=signal, depth=depth, source_loc=source_loc)`
6. Add `_reconstruct_signal_func_text(node: SignalFunc) -> str` returning e.g. `"$rose(sig)"` or `"$past(sig, 3)"`.
</action>
<acceptance_criteria>
- `_build_signal_func` exists and returns `SignalFunc`
- `import_assertion` on a fixture with `"subroutineName": "$rose"` returns a `SignalFunc(func_name="rose", signal="sig", depth=1)`
- `import_assertion` on a fixture with `"subroutineName": "$past"` and two arguments returns `SignalFunc(func_name="past", signal="sig", depth=3)`
- Unknown system function (e.g., `$countones`) raises `UnsupportedConstruct`
- `mypy --strict src/sva2rtl/ast_importer.py` exits 0
</acceptance_criteria>
</task>

<task id="3.2.3">
<title>Add composer support for SignalFunc</title>
<read_first>
- src/sva2rtl/composer.py
- src/sva2rtl/ir.py
</read_first>
<action>
1. Add `SignalFunc` to the import from `sva2rtl.ir`.
2. Add a new match case in `compose()`: `case SignalFunc():` -> call `_compose_signal_func(node, clock, label, original_text)`.
3. Implement `_compose_signal_func`:
   - Derive `module_name` via `module_name_from_label(label, original_text)`
   - `observed_signals = ((node.signal, node.signal),)` — single observed signal
   - `template_name = node.func_name` — maps directly to template file name ("rose", "fell", "stable", "past")
   - Build params dict with keys: `module_name`, `signal_name` (node.signal), `depth` (str(node.depth)), `clock_signal`, `clock_edge`, `source_loc`, `sva2rtl_version`, `original_text`
   - Return `CheckerNode(template_name=template_name, module_name=module_name, params=params, observed_signals=observed_signals, source_loc=node.source_loc, children=())`
</action>
<acceptance_criteria>
- `compose()` accepts a `SignalFunc` node without raising `UnsupportedConstruct`
- For `SignalFunc(func_name="rose", ...)` returned CheckerNode has `template_name="rose"`
- For `SignalFunc(func_name="past", ..., depth=3)` params contains `"depth": "3"`
- `observed_signals` is a tuple with one entry `(signal_name, signal_name)`
- `mypy --strict src/sva2rtl/composer.py` exits 0
</acceptance_criteria>
</task>

<task id="3.2.4">
<title>Create rose.sv.j2, fell.sv.j2, stable.sv.j2 templates</title>
<read_first>
- templates/bool_expr.sv.j2
- templates/concat_delay.sv.j2
</read_first>
<action>
Create three templates with the same base structure but different detection logic:

**templates/rose.sv.j2:**
- Header comment (sva2rtl_version, source_loc, original_text)
- Module: ports = clk ({{ clock_signal }}), rst_n, start, {{ signal_name }}, disable_i, then outputs active, pass, fail, attempt_fired, disabled_o
- Internal: `sig_prev_q` FF — `always_ff` with reset `(!rst_n | disable_i)` resets to 0, else captures {{ signal_name }}
- Detection: `assign rose_detect = {{ signal_name }} & ~sig_prev_q;`
- Registered outputs: attempt_fired_q sticky, pass_internal = start & rose_detect, fail_internal = start & ~rose_detect, active_internal = start
- Disable gating: pass/fail/active gated by disable_i; disabled_o = disable_i

**templates/fell.sv.j2:** Same structure, detection = `~{{ signal_name }} & sig_prev_q`

**templates/stable.sv.j2:** Same structure, detection = `({{ signal_name }} == sig_prev_q)` (XNOR)
</action>
<acceptance_criteria>
- Files `templates/rose.sv.j2`, `templates/fell.sv.j2`, `templates/stable.sv.j2` exist
- Each renders without Jinja2 errors with params: module_name, signal_name, clock_signal, clock_edge, source_loc, sva2rtl_version, original_text, observed_signals (empty tuple), children (empty tuple)
- `rose.sv.j2` rendered output contains `assign rose_detect = sig & ~sig_prev_q;` (for signal_name=sig)
- `fell.sv.j2` rendered output contains `~sig & sig_prev_q`
- `stable.sv.j2` rendered output contains `sig == sig_prev_q`
- All three contain `input logic disable_i` and `output logic disabled_o`
- All three contain exactly one `always_ff` block with `sig_prev_q`
</acceptance_criteria>
</task>

<task id="3.2.5">
<title>Create past.sv.j2 template</title>
<read_first>
- templates/concat_delay.sv.j2
- templates/rose.sv.j2
</read_first>
<action>
Create `templates/past.sv.j2`:
- Header comment block (standard pattern)
- Module with parameter `DEPTH = {{ depth }}`
- Ports: clk ({{ clock_signal }}), rst_n, start, {{ signal_name }}, disable_i, outputs: active, pass, fail, attempt_fired, disabled_o
- N-stage shift register: `logic [DEPTH-1:0] shift_q;`
- `always_ff` with reset condition `(!rst_n | disable_i)`: reset shift_q to '0; else `shift_q <= {shift_q[DEPTH-2:0], {{ signal_name }}};`
- Past value output: `logic past_value; assign past_value = shift_q[DEPTH-1];`
- For standalone use as a property checker: `assign pass_internal = start & past_value; assign fail_internal = start & ~past_value;`
- Standard registered attempt_fired_q pattern
- Disable gating on all outputs
- Note: when DEPTH=1, use simpler single-FF form (Jinja2 conditional: `{% if depth == "1" %}` use single reg instead of shift)
</action>
<acceptance_criteria>
- File `templates/past.sv.j2` exists
- Template renders without Jinja2 errors with params: module_name, signal_name, depth, clock_signal, clock_edge, source_loc, sva2rtl_version, original_text, observed_signals, children
- Rendered output with depth="3" contains `parameter DEPTH = 3`
- Rendered output contains `shift_q` and shift register logic
- Rendered output contains `input logic disable_i` and `output logic disabled_o`
- `endmodule` is the last non-empty line
</acceptance_criteria>
</task>

<task id="3.2.6">
<title>Add behavioral oracle for rose, fell, stable, past</title>
<read_first>
- src/sva2rtl/behavioral_oracle.py
</read_first>
<action>
1. Add `"rose"`, `"fell"`, `"stable"`, `"past"` to `_valid_kinds` set.
2. Add oracle state in `__init__`: `self._sig_prev: bool = False`, `self._past_shift: list[bool] = [False] * int(params.get("depth", 1))`.
3. Add to `reset()`: reset `_sig_prev` to False, `_past_shift` to all-False list.
4. Extend `tick()` dispatch with elif branches for each new kind.
5. Implement `_tick_rose(signals)`: sig = signals["sig"]; detect = sig and not self._sig_prev; self._sig_prev = sig; return pass=start&detect, fail=start&~detect, active=start
6. Implement `_tick_fell(signals)`: detect = not sig and self._sig_prev; same pattern
7. Implement `_tick_stable(signals)`: detect = (sig == self._sig_prev); same pattern
8. Implement `_tick_past(signals)`: past_val = self._past_shift[-1]; shift right (insert sig at [0], drop [-1]); return pass=start&past_val, fail=start&~past_val, active=start
</action>
<acceptance_criteria>
- `SVABehavioralSim("rose", {})` creates successfully
- Rose trace [sig=0, sig=1, sig=1, sig=0]: tick 2 with start=True has pass=True (0->1 transition detected at tick 2); tick 3 with start=True has pass=False (1->1 no edge)
- Fell trace [sig=1, sig=0]: tick 2 with start=True has pass=True
- Stable trace [sig=1, sig=1]: tick 2 with start=True has pass=True; [sig=1, sig=0] tick 2 has fail=True
- Past(depth=2) trace [sig=1, sig=0, sig=1]: tick 3 past_value reflects sig from 2 cycles ago (True)
- `mypy --strict src/sva2rtl/behavioral_oracle.py` exits 0
</acceptance_criteria>
</task>

<task id="3.2.7">
<title>Create test fixtures and tests for signal functions</title>
<read_first>
- tests/test_sequential.py
- tests/test_behavioral_oracle.py
- tests/fixtures/delay_fixed.json
- src/sva2rtl/ast_importer.py
</read_first>
<action>
1. Create `tests/fixtures/rose.json`: ConcurrentAssertion with PropertySpec containing a CallExpression with subroutineName "$rose", arguments: [NamedValue for "sig"]. Full clocking structure.
2. Create `tests/fixtures/fell.json`: Same with "$fell".
3. Create `tests/fixtures/stable.json`: Same with "$stable".
4. Create `tests/fixtures/past.json`: CallExpression with "$past", arguments: [NamedValue "sig", IntegerLiteral 3].
5. Create `tests/test_signal_functions.py` with test functions:
   - `test_ir_signal_func_creation()`: construct all 4 variants, assert frozen/hashable
   - `test_import_rose()`: load rose.json, assert SignalFunc(func_name="rose", signal="sig")
   - `test_import_fell()`: load fell.json, assert SignalFunc(func_name="fell", signal="sig")
   - `test_import_stable()`: load stable.json, assert SignalFunc(func_name="stable", signal="sig")
   - `test_import_past()`: load past.json, assert SignalFunc(func_name="past", signal="sig", depth=3)
   - `test_compose_rose()`: full compose, assert template_name="rose"
   - `test_compose_past()`: full compose, assert params["depth"]=="3"
   - `test_emit_rose()`: full pipeline emit_all, assert output contains `rose_detect`
   - `test_emit_past()`: full pipeline emit_all, assert output contains `shift_q`
   - `test_oracle_rose_edge()`: behavioral oracle, 0->1 = pass, 1->1 = no pass
   - `test_oracle_fell_edge()`: 1->0 = pass, 0->0 = no pass
   - `test_oracle_stable_no_change()`: same value = pass
   - `test_oracle_past_depth_3()`: value appears 3 cycles later in output
6. Generate golden files: `tests/golden/sva_rose.sv`, `tests/golden/sva_fell.sv`, `tests/golden/sva_stable.sv`, `tests/golden/sva_past.sv`
</action>
<acceptance_criteria>
- `pytest tests/test_signal_functions.py -v` exits 0 with all tests passing
- At least 12 test functions exist
- Golden file `tests/golden/sva_rose.sv` contains `sig_prev_q` and `rose_detect`
- Golden file `tests/golden/sva_past.sv` contains `parameter DEPTH = 3`
- `mypy --strict tests/test_signal_functions.py` exits 0
</acceptance_criteria>
</task>

## Verification

```bash
# All tests pass
pytest tests/test_signal_functions.py -v

# Type checking
mypy --strict src/sva2rtl/ir.py src/sva2rtl/ast_importer.py src/sva2rtl/composer.py src/sva2rtl/behavioral_oracle.py

# Linting
ruff check src/sva2rtl/ tests/test_signal_functions.py

# No regressions
pytest tests/ -v --ignore=tests/test_signal_functions.py
```

## must_haves

- [ ] `SignalFunc` IR node exists and is frozen/hashable
- [ ] AST importer dispatches `CallExpression` with `$rose/$fell/$stable/$past`
- [ ] Non-literal `$past(sig, N)` depth rejected as unsupported
- [ ] Composer maps each func_name to its corresponding template
- [ ] 4 templates render correct detection logic (AND-NOT, AND, XNOR, shift register)
- [ ] All templates include `disable_i`/`disabled_o` ports
- [ ] Behavioral oracle correctly models all 4 signal functions
- [ ] All new tests pass; no regressions
