# Plan 3.3: `disable iff` + Interface Update + Named Sequences + Bind Generation

---
wave: 2
depends_on:
  - PLAN-3.1
  - PLAN-3.2
files_modified:
  - src/sva2rtl/ir.py
  - src/sva2rtl/ast_importer.py
  - src/sva2rtl/composer.py
  - src/sva2rtl/emitter.py
  - templates/bool_expr.sv.j2
  - templates/concat_delay.sv.j2
  - templates/overlap_bitvec.sv.j2
  - templates/nonoverlap.sv.j2
  - templates/seq_concat_top.sv.j2
  - templates/rep_consecutive.sv.j2
  - templates/rose.sv.j2
  - templates/fell.sv.j2
  - templates/stable.sv.j2
  - templates/past.sv.j2
  - templates/disable_iff_top.sv.j2
  - templates/bind.sv.j2
  - tests/fixtures/disable_iff.json
  - tests/fixtures/named_seq.json
  - tests/test_disable_iff.py
  - tests/test_named_sequences.py
  - tests/test_bind.py
  - tests/golden/bool_labeled.sv
  - tests/golden/bool_simple.sv
  - tests/golden/nonoverlap_impl.sv
  - tests/golden/overlap_impl.sv
  - tests/golden/sva_bitvec_impl.sv
  - tests/golden/sva_delay_0_0.sv
  - tests/golden/sva_delay_1_1.sv
  - tests/golden/sva_delay_2_2.sv
  - tests/golden/sva_delay_2_5.sv
  - tests/golden/sva_delay_3_3.sv
autonomous: true
requirements:
  - OP-10
  - PARSE-03
  - OUT-04
---

## Summary

Three related deliverables in one plan: (1) Update ALL existing templates with `disable_i`/`disabled_o` ports + regenerate golden files; (2) Implement `disable iff` with async combinational output gating and synchronous state clear; (3) Named sequence/property inline expansion with CSE tagging; (4) Bind statement generation. This plan is wave 2 because the interface update must happen after 3.1/3.2 templates exist.

## Vertical Slice

`disable iff (rst) a |-> ##2 b` -> DisableIff IR wrapping PropImplication -> `disable_iff_top` CheckerNode wrapping body checker -> template gates outputs and clears state. Named sequence `sequence s = a ##2 b; property p = s;` -> inline expansion at use site with `cse_origin` tag. Bind statement `bind dut_module sva_check u_check (...)` generated alongside monitor.

<threat_model>
- **Spurious failure during disable:** If disable takes effect synchronously with 1-cycle delay, a failing check could emit a spurious `fail=1` for 1 cycle before the disable suppresses it. Mitigated: combinational output gating ensures same-cycle suppression.
- **Stale state after disable de-assertion:** State cleared via `effective_rst = !rst_n | disable_i` in always_ff. When disable de-asserts, state is already zero — no stale threads resume. Verified by simulation oracle tests.
- **Circular named sequence reference:** Mitigated by visited-set cycle detection during recursive expansion; raises SVA-E003 error.
- **Bind port name mismatch:** Port names derived from same `extract_signals()` used in monitor generation — guaranteed to match.
- **Severity:** MEDIUM (disable iff correctness is safety-critical for reset behavior). Mitigated by dedicated oracle test verifying no-spurious-failure-on-disable-cycle.
</threat_model>

## Tasks

<task id="3.3.1">
<title>Update ALL existing templates with disable_i/disabled_o ports</title>
<read_first>
- templates/bool_expr.sv.j2
- templates/concat_delay.sv.j2
- templates/overlap_bitvec.sv.j2
- templates/nonoverlap.sv.j2
- templates/seq_concat_top.sv.j2
</read_first>
<action>
Update all 5 existing templates with uniform changes:

**Port additions** (add after last input before outputs):
- Add `input  logic disable_i,` after the last input port (after observed_signals loop or after `start`)
- Add `output logic disabled_o` as the last output port

**Reset condition change** (in every `always_ff` block):
- Change `if (!rst_n)` to `if (!rst_n | disable_i)`

**Output gating** (change assign statements):
- For `bool_expr.sv.j2`: rename pass_q/fail_q/active_q assignments to internal names, add gating assigns: `assign pass = disable_i ? 1'b0 : pass_q;` etc.
- For `concat_delay.sv.j2`: gate `pass`, `active`, `fail` assigns with `disable_i ? 1'b0 :`
- For `overlap_bitvec.sv.j2` and `nonoverlap.sv.j2`: gate `active`, `pass`, `fail` assigns; add `assign disabled_o = disable_i;`
- For `seq_concat_top.sv.j2`: pass `disable_i` to all child instantiations (add `.disable_i(disable_i),` and `.disabled_o()` in each child port map); gate top-level outputs

**Child instantiation updates** (in wrapper templates: overlap_bitvec, nonoverlap, seq_concat_top):
- Add `.disable_i (disable_i),` port connection to each child instantiation
- Add `.disabled_o ()` port connection to each child instantiation

**disabled_o assignment** in all templates:
- `assign disabled_o = disable_i;`
</action>
<acceptance_criteria>
- All 5 templates contain `input  logic disable_i`
- All 5 templates contain `output logic disabled_o`
- All 5 templates contain `assign disabled_o = disable_i;`
- `bool_expr.sv.j2` uses `disable_i ? 1'b0 :` gating on pass/fail/active outputs
- `seq_concat_top.sv.j2` child instantiations contain `.disable_i (disable_i),`
- `overlap_bitvec.sv.j2` child instantiations contain `.disable_i (disable_i),`
- Templates render without Jinja2 errors with existing test params plus `disable_i` in context
</acceptance_criteria>
</task>

<task id="3.3.2">
<title>Regenerate all Phase 1-2 golden files and fix tests</title>
<read_first>
- tests/test_sequential.py
- tests/test_emitter.py
- tests/test_integration.py
- tests/test_pipeline_e2e.py
- tests/golden/bool_labeled.sv
- tests/golden/sva_delay_1_1.sv
</read_first>
<action>
1. Run the full pipeline for each existing fixture to regenerate golden files that now include `disable_i`/`disabled_o` ports.
2. Regenerate ALL golden files in `tests/golden/` by running the compile pipeline for each fixture JSON file.
3. Update any test assertions that check for specific port lists or exact string matches that would break with the new ports.
4. Ensure the composer passes `disable_i` port connections by default (for child instantiations in wrapper templates, already handled by template changes).
5. Run `pytest tests/` — all existing tests must pass with regenerated golden files.
6. Also update the Plan 3.1 and 3.2 golden files if they already exist (rep_consecutive, rose, fell, stable, past already have disable_i from their template creation).
</action>
<acceptance_criteria>
- `pytest tests/ -v` exits 0 (all existing tests pass)
- All golden files in `tests/golden/` contain `disable_i` and `disabled_o`
- `tests/golden/bool_labeled.sv` contains `input  logic disable_i` and `output logic disabled_o`
- No test references the old port list without disable_i/disabled_o
- `ruff check tests/` exits 0
</acceptance_criteria>
</task>

<task id="3.3.3">
<title>Add DisableIff IR node and AST importer dispatch</title>
<read_first>
- src/sva2rtl/ir.py
- src/sva2rtl/ast_importer.py
- .planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-RESEARCH.md (Section 1.3)
</read_first>
<action>
1. Add `DisableIff(SVANode)` frozen dataclass to `ir.py`: fields `condition: str` (disable condition expression text), `body: SVANode` (the property being disabled).
2. Add `DisableIff` to imports in `ast_importer.py`.
3. In `_import_concurrent_assertion`: check if `expr_node` kind is `"DisableIff"` — if so, extract condition via `expr_to_sv(node["condition"])`, extract body by recursing on `node["expr"]`, wrap in `DisableIff(condition=cond_text, body=body_ir, source_loc=source_loc)`.
4. Also handle the case where `DisableIff` wraps the entire PropertySpec.expr — the JSON structure places it as the outermost node around the property body.
5. Add `_build_disable_iff(node: dict, source_loc: SourceLoc) -> DisableIff` builder function.
6. Add `_reconstruct_disable_text(node: DisableIff) -> str` returning `"disable iff ({condition}) {body_text}"`.
</action>
<acceptance_criteria>
- `ir.py` contains `class DisableIff(SVANode):` with `frozen=True`
- `DisableIff` has fields `condition: str`, `body: SVANode`
- `import_assertion` on a fixture with `"kind": "DisableIff"` wrapping an assertion returns a `DisableIff` node
- `DisableIff.condition` contains the textual representation of the disable condition
- `mypy --strict src/sva2rtl/ir.py src/sva2rtl/ast_importer.py` exits 0
</acceptance_criteria>
</task>

<task id="3.3.4">
<title>Add composer and template for disable_iff_top</title>
<read_first>
- src/sva2rtl/composer.py
- templates/seq_concat_top.sv.j2
- src/sva2rtl/ir.py
</read_first>
<action>
1. Add `DisableIff` to imports in `composer.py`.
2. Add match case in `compose()`: `case DisableIff():` -> `_compose_disable_iff(node, clock, label, original_text)`.
3. Implement `_compose_disable_iff`:
   - Derive module_name from label
   - Recursively compose the body: `body_checker = compose(node.body, clock, None, original_text)`
   - Extract observed_signals: combine signals from condition expression (`extract_signals(node.condition)`) with body_checker.observed_signals, deduplicated
   - params: module_name, disable_expr (node.condition), clock_signal, clock_edge, source_loc, sva2rtl_version, original_text
   - Return CheckerNode(template_name="disable_iff_top", children=(body_checker,), ...)
4. Create `templates/disable_iff_top.sv.j2`:
   - Standard header comment
   - Module ports: clk, rst_n, start, observed_signals loop, outputs (active, pass, fail, attempt_fired, disabled_o) — no `disable_i` input on this module since IT IS the disable source
   - Combinational disable condition: `assign disable_cond = ({{ disable_expr }});`
   - Child body instantiation: pass `disable_cond` as `.disable_i(disable_cond)`, wire `.start(start & ~disable_cond)` (suppress start while disabled)
   - Wire body outputs to top outputs directly (body already gates with disable_i internally)
   - `assign disabled_o = disable_cond;`
</action>
<acceptance_criteria>
- `compose()` accepts `DisableIff` node and returns CheckerNode with `template_name="disable_iff_top"`
- `children` tuple has exactly 1 element (the body checker)
- Template `templates/disable_iff_top.sv.j2` exists and renders without errors
- Rendered output contains `assign disable_cond = ` with the disable expression
- Rendered output instantiates the body child with `.disable_i (disable_cond)`
- Rendered output does NOT have a `disable_i` input port itself (it's the source)
- `mypy --strict src/sva2rtl/composer.py` exits 0
</acceptance_criteria>
</task>

<task id="3.3.5">
<title>Implement named sequence/property inline expansion (PARSE-03)</title>
<read_first>
- src/sva2rtl/ast_importer.py
- src/sva2rtl/ir.py
- .planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-RESEARCH.md (Section 5)
- .planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-CONTEXT.md (D-01 through D-04)
</read_first>
<action>
1. Add `cse_origin: str | None = None` field to `CheckerNode` in `ir.py` (after `children` field). Update `__hash__` and `__eq__` to include `cse_origin`.
2. In `ast_importer.py`, add logic to detect named sequence/property references in the slang JSON:
   - Before processing the main assertion, scan the AST members for sequence/property declarations (nodes with `"kind": "Sequence"` or `"kind": "Property"` at the module body level). Store in a `declarations: dict[str, dict]` mapping name -> body node.
   - When encountering a `"SequenceInstance"` or named reference node during dispatch, call `_expand_named_sequence(node, declarations, visited_set, source_loc)`.
3. Implement `_expand_named_sequence`:
   - Extract the sequence name from the node
   - Cycle detection: if name in visited set, raise `SvaCompileError` with message "SVA-E003: circular sequence reference: {name}"
   - Add name to visited set
   - Look up body in declarations dict
   - Recursively dispatch the body through `_dispatch_expr_to_ir`
   - Remove name from visited set
   - Return the expanded IR node
4. In `compose()`, when constructing a CheckerNode from an expanded named sequence, set `cse_origin=declaration_name` on the resulting CheckerNode (passed through compose via a new optional parameter or set post-construction).
5. Alternative simpler approach: if slang pre-resolves named sequences (body already inlined), just detect the pattern and tag the cse_origin. Create a test fixture to verify slang's behavior.
</action>
<acceptance_criteria>
- `CheckerNode` has field `cse_origin: str | None` with default `None`
- `CheckerNode.__hash__` includes `cse_origin` in its hash tuple
- Named sequence fixture JSON (where slang provides a reference) is correctly expanded to primitive operators
- Circular sequence reference raises `SvaCompileError` with "SVA-E003" in message
- Expanded CheckerNode from a named sequence has `cse_origin` set to the declaration name
- `mypy --strict src/sva2rtl/ir.py src/sva2rtl/ast_importer.py` exits 0
</acceptance_criteria>
</task>

<task id="3.3.6">
<title>Implement bind statement generation (OUT-04)</title>
<read_first>
- src/sva2rtl/emitter.py
- src/sva2rtl/ir.py
- .planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-RESEARCH.md (Section 6)
</read_first>
<action>
1. Create `templates/bind.sv.j2`:
   - Header comment: `// Generated by sva2rtl {{ sva2rtl_version }}`
   - Comment: `// Bind file for property: {{ module_name }}`
   - Comment: `// Source: {{ source_loc }}`
   - `bind {{ dut_module }} {{ module_name }} u_{{ module_name }} (`
   - Port connections: `.{{ clock_signal }}({{ clock_signal }}),` `.rst_n(rst_n),` `.start(1'b1),` `.disable_i(1'b0),`
   - Loop over observed_signals: `.{{ port_name }}({{ sig_name }}),`
   - Unconnected outputs: `.active(), .pass(), .fail(), .attempt_fired(), .disabled_o()`
   - `);`
2. Add `emit_bind()` function to `emitter.py`:
   - Signature: `def emit_bind(checker: CheckerNode, dut_module: str, template_dir: Path | None = None) -> str`
   - Uses same `_make_env()` pattern
   - Renders `bind.sv.j2` with context: checker.params + observed_signals + dut_module + module_name
3. Update `ast_importer.py` to extract the DUT module name from the AST:
   - During `_find_assertion_in_members` traversal, capture the Instance/InstanceBody name
   - Return it as part of the import result (extend the return tuple or add a separate function)
   - Alternatively: add a `extract_dut_module(ast: dict) -> str` public function
</action>
<acceptance_criteria>
- File `templates/bind.sv.j2` exists
- `emit_bind(checker, "my_dut")` returns a string containing `bind my_dut sva_my_check u_sva_my_check (`
- Bind output contains `.start     (1'b1),` (always-on by default)
- Bind output contains `.disable_i (1'b0),` (no disable by default)
- Bind output lists all observed_signals with named port connections
- `emitter.py` contains function `emit_bind` with type annotations
- `mypy --strict src/sva2rtl/emitter.py` exits 0
</acceptance_criteria>
</task>

<task id="3.3.7">
<title>Create tests for disable iff, named sequences, and bind</title>
<read_first>
- tests/test_sequential.py
- tests/test_emitter.py
- src/sva2rtl/ast_importer.py
- src/sva2rtl/composer.py
- src/sva2rtl/emitter.py
</read_first>
<action>
1. Create `tests/fixtures/disable_iff.json`: ConcurrentAssertion with PropertySpec containing a DisableIff node wrapping a BoolExpr or simple assertion. Condition is a NamedValue "rst".
2. Create `tests/fixtures/named_seq.json`: AST with a named sequence declaration and a property that references it.
3. Create `tests/test_disable_iff.py`:
   - `test_ir_disable_iff_creation()`: construct DisableIff, assert frozen
   - `test_import_disable_iff()`: load fixture, assert returns DisableIff with condition text and body
   - `test_compose_disable_iff()`: compose, assert template_name="disable_iff_top", children has 1 element
   - `test_emit_disable_iff()`: full emit_all, assert output contains `disable_cond` and `disable_i`
   - `test_disable_gates_outputs()`: rendered output contains ternary gating on pass/fail/active
4. Create `tests/test_named_sequences.py`:
   - `test_cse_origin_field()`: CheckerNode with cse_origin is hashable and comparable
   - `test_named_seq_expansion()`: fixture with named sequence ref expands inline
   - `test_circular_ref_rejected()`: mock circular reference raises SvaCompileError with "SVA-E003"
5. Create `tests/test_bind.py`:
   - `test_emit_bind_basic()`: emit_bind produces valid bind statement text
   - `test_bind_port_connections()`: all observed_signals appear as port connections
   - `test_bind_default_start()`: output contains `.start     (1'b1)`
   - `test_bind_default_disable()`: output contains `.disable_i (1'b0)`
   - `test_bind_dut_module_name()`: `bind <dut_name>` matches the provided dut_module arg
</action>
<acceptance_criteria>
- `pytest tests/test_disable_iff.py tests/test_named_sequences.py tests/test_bind.py -v` exits 0
- At least 5 tests in test_disable_iff.py, 3 in test_named_sequences.py, 4 in test_bind.py
- Circular reference test verifies "SVA-E003" in error message
- All existing tests still pass: `pytest tests/ -v` exits 0
- `mypy --strict tests/test_disable_iff.py tests/test_named_sequences.py tests/test_bind.py` exits 0
</acceptance_criteria>
</task>

## Verification

```bash
# All tests pass (including updated golden files)
pytest tests/ -v

# Type checking (all modified files)
mypy --strict src/sva2rtl/

# Linting
ruff check src/sva2rtl/ tests/

# Verify templates render (spot check)
python -c "from sva2rtl.emitter import _make_env; e=_make_env(); print(e.get_template('disable_iff_top.sv.j2'))"
```

## must_haves

- [ ] ALL existing templates updated with `disable_i`/`disabled_o` ports
- [ ] All Phase 1-2 golden files regenerated and tests pass
- [ ] `DisableIff` IR node exists; AST importer handles `DisableIff` JSON kind
- [ ] `disable_iff_top.sv.j2` template gates outputs combinationally on disable cycle
- [ ] Named sequences expanded inline with `cse_origin` tag for Phase 5 CSE
- [ ] Circular sequence reference rejected with SVA-E003
- [ ] `emit_bind()` function generates valid SystemVerilog bind statements
- [ ] `bind.sv.j2` template produces correct port connections
- [ ] No regressions in any existing test
