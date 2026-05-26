---
wave: 2
depends_on:
  - PLAN-2.1
files_modified:
  - src/sva2rtl/ast_importer.py
  - src/sva2rtl/composer.py
  - templates/overlap_bitvec.sv.j2
  - templates/nonoverlap.sv.j2
  - tests/fixtures/implication_overlap.json
  - tests/fixtures/implication_nonoverlap.json
  - tests/golden/overlap_impl.sv
  - tests/golden/nonoverlap_impl.sv
  - tests/golden/sva_bitvec_impl.sv
  - tests/test_ast_importer.py
  - tests/test_composer.py
  - tests/test_emitter.py
requirements:
  - OP-03
  - OP-04
  - OUT-06
autonomous: true
---

# Plan 2.2: Overlapping (`|->`) and Non-Overlapping (`|=>`) Implication with Bit-Vector Thread Tracking

## Goal

Deliver end-to-end compilation of overlapping implication (`|->`) and non-overlapping implication (`|=>`) into synthesizable RTL with bit-vector concurrent thread tracking. The bit-vector module manages multiple simultaneous active threads, implements overflow detection with hard-halt semantics (D-05), and exposes `overflow_flag` as a sticky debug output. `|=>` is implemented as `|->` with a 1-cycle delay child (reusing the `concat_delay` template from Plan 2.1).

## Vertical Slice

Input: `assert property (@(posedge clk) a |-> ##[2:5] b)` or `a |=> b`
Output: Flat directory with top wrapper + bit-vector implication module + delay child + bool_expr children
Proof: Golden file match + overflow_flag latches on saturation + `iverilog output/*.sv` compiles clean

---

## Tasks

<task id="2.2.1">
<title>Extend ast_importer to handle implication operators</title>
<read_first>
- src/sva2rtl/ast_importer.py (current state after Plan 2.1)
- src/sva2rtl/ir.py (PropImplication definition, lines 78-87)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 4: ast_importer.py, implication dispatch)
- tests/fixtures/unsupported_delay.json (structure reference for creating new fixtures)
</read_first>
<action>
Modify `src/sva2rtl/ast_importer.py`:
1. Remove `"OverlappedImplication"` and `"NonOverlappedImplication"` from `_UNSUPPORTED_BINARY_OPS` dict (lines 55-58). This dict should become empty or be removed entirely.
2. Add `PropImplication` to the import from `sva2rtl.ir`.
3. In `_import_concurrent_assertion()`: extend the match dispatch (added in Plan 2.1) to handle implication:
   - case `"BinaryPropertyExpr"` where `expr_node.get("op")` is `"OverlappedImplication"` or `"NonOverlappedImplication"`:
     - Call new helper `_build_prop_implication(expr_node, source_loc)` which returns `PropImplication`
4. In `expr_to_sv()` BinaryOp case (line 138-143): remove the check against `_UNSUPPORTED_BINARY_OPS` (since it's now empty/removed). Or if dict is kept empty, the check becomes a no-op naturally.
5. Add helper `_build_prop_implication(node: dict[str, Any], source_loc: SourceLoc) -> PropImplication`:
   - Extract `node["left"]` → antecedent: dispatch via `_dispatch_expr_to_ir(node["left"])` (reuse from Plan 2.1)
   - Extract `node["right"]` → consequent: dispatch via `_dispatch_expr_to_ir(node["right"])`
   - Determine `overlapping = (node.get("op") == "OverlappedImplication")`
   - Return `PropImplication(antecedent=ant, consequent=con, overlapping=overlapping, source_loc=source_loc)`
6. Also handle the case where the BinaryPropertyExpr wraps a SequenceConcat consequent (e.g., `a |-> ##[2:5] b`) — the consequent side may be a SequenceConcat which _dispatch_expr_to_ir already handles from Plan 2.1.
</action>
<acceptance_criteria>
- `_UNSUPPORTED_BINARY_OPS` dict is empty or removed entirely
- `import_assertion()` on a fixture with `"op": "OverlappedImplication"` returns a `PropImplication` node
- `PropImplication.overlapping` is `True` for `|->`
- `PropImplication.overlapping` is `False` for `|=>`
- `PropImplication.antecedent` is a `BoolExpr` for simple antecedent
- `PropImplication.consequent` can be either `BoolExpr` or `SeqConcat` depending on the property
- `mypy --strict src/sva2rtl/ast_importer.py` exits 0
- `expr_to_sv()` no longer raises UnsupportedConstruct for OverlappedImplication/NonOverlappedImplication (those are now handled at the property level, not the expression level)
</acceptance_criteria>
</task>

<task id="2.2.2">
<title>Create overlapping implication bit-vector template</title>
<read_first>
- templates/concat_delay.sv.j2 (after Plan 2.1 — pattern reference)
- templates/bool_expr.sv.j2 (standard interface reference)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-05, D-06, D-07)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 2: overlap_bitvec.sv.j2)
</read_first>
<action>
Create `templates/overlap_bitvec.sv.j2`. This template renders the top-level overlapping implication monitor with bit-vector thread tracking:

Module interface:
- Standard inputs: `clk, rst_n, start` + all observed_signals from children
- Standard outputs: `active, pass, fail, attempt_fired`
- Additional debug output: `overflow_flag`
- `parameter BV_WIDTH = {{ bv_width }}`

Internal architecture:
- Instantiate antecedent child (first in children list): wire parent `start` → ant child `start`
- Instantiate consequent child (second in children list): wire from bit-vector logic → con child `start`
- Bit-vector register `logic [BV_WIDTH-1:0] bv_q`: each bit represents one active thread
- On antecedent `pass`: attempt to insert a new bit at position 0 (thread start)
- Each cycle: shift bv_q right by 1 (threads age)
- Consequent evaluation: when a bit reaches the end of the shift register, check consequent `pass`
- Overflow detection: if antecedent passes AND all BV_WIDTH bits are occupied, set `overflow_flag` sticky, assert `fail`, enter HALT state
- HALT state: freeze bv_q, gate active/pass/fail to 0, overflow_flag stays high (D-05)
- `overflow_flag` only cleared by rst_n (D-07)
- `pass` output: consequent pass AND corresponding thread bit is set
- `fail` output: thread bit expires (reaches end) AND consequent did not pass, OR overflow
- `active` output: any bit in bv_q is set
- `attempt_fired`: sticky, set when antecedent first passes

Child instantiation pattern (from template):
- Use `{{ children[0].module_name }}` for antecedent instance
- Use `{{ children[1].module_name }}` for consequent instance (may itself have children for ##[M:N])
- Wire internal signals: `ant_pass_w`, `con_pass_w`, `con_start_w`
</action>
<acceptance_criteria>
- File `templates/overlap_bitvec.sv.j2` exists
- Template contains `parameter BV_WIDTH = {{ bv_width }}`
- Template contains `logic [BV_WIDTH-1:0] bv_q` bit-vector register
- Template contains overflow detection logic with `overflow_flag` output
- Template contains HALT state logic that freezes outputs when overflow_flag is set
- Template contains `always_ff @({{ clock_edge }} {{ clock_signal }})` block
- Template contains `if (!rst_n)` synchronous reset clearing bv_q and overflow_flag
- Template contains at least two child module instantiations (antecedent + consequent)
- Template contains standard output ports: active, pass, fail, attempt_fired, overflow_flag
- Template contains `endmodule` as final code line
</acceptance_criteria>
</task>

<task id="2.2.3">
<title>Create non-overlapping implication template</title>
<read_first>
- templates/overlap_bitvec.sv.j2 (after task 2.2.2 — sibling template)
- templates/concat_delay.sv.j2 (delay module reused for 1-cycle offset)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-08, D-09)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 3: nonoverlap.sv.j2)
</read_first>
<action>
Create `templates/nonoverlap.sv.j2`. This template implements `|=>` as `|->` with a 1-cycle delay inserted between antecedent match and consequent start.

Two implementation approaches (choose the sub-module approach per D-08/D-09):
- The template is structurally identical to `overlap_bitvec.sv.j2` but with the antecedent pass signal routed through a 1-cycle delay register before entering the bit-vector logic. This means the bit-vector thread tracking starts one cycle after antecedent match.

Implementation:
- Same module interface as overlap_bitvec.sv.j2 (including overflow_flag)
- Same `parameter BV_WIDTH = {{ bv_width }}`
- Internal 1-cycle pipeline register: `logic ant_pass_delayed_q` — registered version of antecedent pass
- The delayed antecedent pass is what inserts bits into the bit-vector (not the raw antecedent pass)
- All other logic (bv_q shifting, overflow, halt, consequent checking) is identical to overlap template
- Alternative: simply include the overlap template's logic but use `ant_pass_delayed_q` instead of `ant_pass_w` as the bit insertion signal

Note: The composer will handle the difference — `|=>` composer creates the same structure as `|->` but marks the template as "nonoverlap". Both templates share the same bit-vector tracking architecture.
</action>
<acceptance_criteria>
- File `templates/nonoverlap.sv.j2` exists
- Template contains `parameter BV_WIDTH = {{ bv_width }}`
- Template contains a 1-cycle delay register for the antecedent pass signal (e.g., `ant_pass_delayed_q`)
- Template contains bit-vector register `logic [BV_WIDTH-1:0] bv_q`
- Template contains overflow detection and halt logic (same as overlap)
- Template contains standard port interface including `overflow_flag` output
- Template contains `always_ff` block with synchronous reset
- Template contains `endmodule`
- The behavioral difference from overlap_bitvec: consequent evaluation starts 1 cycle later than antecedent match
</acceptance_criteria>
</task>

<task id="2.2.4">
<title>Extend composer to handle PropImplication</title>
<read_first>
- src/sva2rtl/composer.py (current state after Plan 2.1)
- src/sva2rtl/ir.py (PropImplication definition)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 5: _compose_implication)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-05, D-06)
</read_first>
<action>
Modify `src/sva2rtl/composer.py`:
1. Add `PropImplication` to the match dispatch in `compose()`:
   - `case PropImplication()`: call `_compose_implication(node, clock, label, original_text)`
2. Add `_compose_implication(node: PropImplication, clock: ClockSpec, label: str | None, original_text: str) -> CheckerNode`:
   - Recursively compose antecedent: `ant_checker = compose(node.antecedent, clock, None, original_text)`
   - Recursively compose consequent: `con_checker = compose(node.consequent, clock, None, original_text)`
   - Select template: `"overlap_bitvec"` if `node.overlapping` else `"nonoverlap"`
   - Compute `bv_width = _estimate_bv_width(node.consequent)` (default heuristic)
   - Build module_name from label
   - Collect observed_signals from both children
   - Build params dict with keys: module_name, bv_width (str), clock_signal, clock_edge, source_loc, sva2rtl_version, original_text
   - Return CheckerNode with template, params, children=(ant_checker, con_checker)
3. Add `_estimate_bv_width(consequent: SVANode) -> int`:
   - For `BoolExpr`: return 1 (single-cycle consequent, 1 thread at a time)
   - For `SeqConcat`: compute max delay from delays tuple: `sum of all delay_max values + len(elements)`. This is the max number of concurrent threads.
   - Default: return 8 (safe default for unknown structures)
   - Minimum: always at least 1
</action>
<acceptance_criteria>
- `compose(PropImplication(ant=BoolExpr("a"), con=BoolExpr("b"), overlapping=True), clock, label, text)` returns a CheckerNode
- Returned node has `template_name == "overlap_bitvec"` for overlapping=True
- Returned node has `template_name == "nonoverlap"` for overlapping=False
- Returned node has `children` tuple of length 2 (antecedent, consequent)
- `children[0]` is the antecedent checker (BoolExpr template)
- `children[1]` is the consequent checker (BoolExpr or seq_concat_top template)
- `params["bv_width"]` is a string representation of an integer >= 1
- For `a |-> ##[2:5] b`: bv_width should account for the 5-cycle consequent window
- `compose(PropImplication(...))` does NOT raise UnsupportedConstruct
- `mypy --strict src/sva2rtl/composer.py` exits 0
</acceptance_criteria>
</task>

<task id="2.2.5">
<title>Create test fixtures and golden files for implication operators</title>
<read_first>
- tests/fixtures/delay_fixed.json (structure reference from Plan 2.1)
- tests/fixtures/unsupported_delay.json (base JSON structure)
- tests/golden/sva_delay_3_3.sv (golden format reference from Plan 2.1)
- templates/overlap_bitvec.sv.j2 (after task 2.2.2)
- templates/nonoverlap.sv.j2 (after task 2.2.3)
</read_first>
<action>
Create test fixtures and golden reference files:

1. `tests/fixtures/implication_overlap.json`: slang AST JSON for `assert property (@(posedge clk) a |-> b)`:
   - Top-level: BinaryPropertyExpr with op="OverlappedImplication"
   - Left (antecedent): SequenceExpr wrapping NamedValue "a"
   - Right (consequent): SequenceExpr wrapping NamedValue "b"
   - Full JSON structure following the same patterns as bool_simple.json (Instance > InstanceBody > ConcurrentAssertion > PropertySpec with clocking)

2. `tests/fixtures/implication_nonoverlap.json`: slang AST JSON for `assert property (@(posedge clk) a |=> b)`:
   - Same structure but op="NonOverlappedImplication"

3. `tests/golden/overlap_impl.sv`: Expected generated output for top-level `a |-> b` monitor:
   - Render overlap_bitvec.sv.j2 with bv_width=1, instantiating two bool_expr children
   - Contains overflow_flag output port
   - Module name: use labeled fixture (e.g., label "impl_check" → "sva_impl_check")

4. `tests/golden/nonoverlap_impl.sv`: Expected generated output for `a |=> b` monitor:
   - Render nonoverlap.sv.j2 with bv_width=1
   - Contains the 1-cycle delay register for antecedent pass

5. `tests/golden/sva_bitvec_impl.sv`: Expected generated bit-vector implication sub-module for a more complex case (e.g., `a |-> ##[2:5] b`)
   - Shows bit-vector with bv_width > 1
</action>
<acceptance_criteria>
- File `tests/fixtures/implication_overlap.json` exists, is valid JSON, contains `"op": "OverlappedImplication"`
- File `tests/fixtures/implication_nonoverlap.json` exists, is valid JSON, contains `"op": "NonOverlappedImplication"`
- File `tests/golden/overlap_impl.sv` exists, contains `overflow_flag`, `module sva_`, `endmodule`
- File `tests/golden/nonoverlap_impl.sv` exists, contains `overflow_flag`, `module sva_`, `endmodule`
- All golden .sv files end with a newline character
- All JSON fixtures have proper `"design"` top-level key with Instance/InstanceBody/ConcurrentAssertion nesting
</acceptance_criteria>
</task>

<task id="2.2.6">
<title>Unit tests for implication operator pipeline</title>
<read_first>
- tests/test_ast_importer.py (current state after Plan 2.1)
- tests/test_composer.py (current state after Plan 2.1)
- tests/test_emitter.py (current state after Plan 2.1)
- tests/fixtures/implication_overlap.json (after task 2.2.5)
- tests/fixtures/implication_nonoverlap.json (after task 2.2.5)
</read_first>
<action>
Add tests to existing test files:

1. `tests/test_ast_importer.py` additions:
   - `test_import_implication_overlap_returns_prop_implication()`: loads implication_overlap.json, asserts isinstance(node, PropImplication) and node.overlapping is True
   - `test_import_implication_nonoverlap_returns_prop_implication()`: loads implication_nonoverlap.json, asserts node.overlapping is False
   - `test_import_implication_antecedent_is_bool_expr()`: assert isinstance(node.antecedent, BoolExpr)
   - `test_import_implication_consequent_is_bool_expr()`: assert isinstance(node.consequent, BoolExpr)
   - Remove or update any test that asserts OverlappedImplication is in _UNSUPPORTED_BINARY_OPS

2. `tests/test_composer.py` additions:
   - `test_compose_implication_overlap_returns_checker()`: compose(PropImplication(overlapping=True, ...), ...) returns CheckerNode
   - `test_compose_implication_overlap_template_name()`: assert template_name == "overlap_bitvec"
   - `test_compose_implication_nonoverlap_template_name()`: assert template_name == "nonoverlap"
   - `test_compose_implication_children_count()`: assert len(children) == 2
   - `test_compose_implication_bv_width_param()`: assert "bv_width" in params and int(params["bv_width"]) >= 1
   - `test_compose_implication_with_delay_consequent()`: compose PropImplication where consequent is SeqConcat, verify children[1] has its own children

3. `tests/test_emitter.py` additions:
   - `test_emit_overlap_bitvec_contains_overflow()`: emit() of overlap_bitvec checker contains "overflow_flag"
   - `test_emit_overlap_bitvec_contains_bv_register()`: contains "bv_q"
   - `test_emit_nonoverlap_contains_delay_register()`: contains "ant_pass_delayed"
   - `test_emit_all_implication_module_count()`: emit_all for a |-> ##[2:5] b returns dict with >= 3 modules
</action>
<acceptance_criteria>
- `pytest tests/test_ast_importer.py` exits 0
- `pytest tests/test_composer.py` exits 0
- `pytest tests/test_emitter.py` exits 0
- Tests verify PropImplication with overlapping=True returns template "overlap_bitvec"
- Tests verify PropImplication with overlapping=False returns template "nonoverlap"
- Tests verify overflow_flag appears in emitted output for implication templates
- Tests verify bv_width parameter is present and >= 1
- `mypy --strict tests/` exits 0
</acceptance_criteria>
</task>

---

## Threat Model

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Silent thread drop when bv_q overflows (data loss) | High | D-05: overflow is a HARD ERROR — fail fires immediately + overflow_flag sticky + HALT state. No silent degradation. Covered by TEST-05 stress tests in Plan 2.3. |
| Bit-vector width too small for workload (false overflow) | Medium | D-06: BV_WIDTH is auto-sized from consequent length AND user-overridable via parameter. Tests verify auto-sizing heuristic. |
| Off-by-one in |=> vs |-> (consequent starts wrong cycle) | High | Dedicated golden tests for both operators with identical inputs — outputs differ by exactly 1 cycle. Plan 2.3 boundary tests verify. |
| Antecedent/consequent signal collision in generated wiring | Low | _collect_signals deduplicates. Children have unique instance names derived from module_name. |
| Template injection via property text in comments | Low | original_text is placed in SV comment only. SV comments cannot affect synthesis. |
</threat_model>

---

## Verification

```bash
# All unit tests pass
pytest tests/test_ast_importer.py tests/test_composer.py tests/test_emitter.py -v

# Type checking
mypy --strict src/sva2rtl/

# Lint
ruff check src/ tests/

# End-to-end implication compilation
python -c "
from sva2rtl.emitter import emit_all
from sva2rtl.composer import compose
from sva2rtl.ast_importer import import_assertion
import json
ast = json.loads(open('tests/fixtures/implication_overlap.json').read())
node, clock, text, label = import_assertion(ast)
checker = compose(node, clock, label, text)
modules = emit_all(checker)
print('Modules:', list(modules.keys()))
assert any('overflow_flag' in sv for sv in modules.values())
"
```

---

## Must-Haves (Goal-Backward Verification)

- [ ] `|->` compiles to bit-vector thread tracking module (OP-03)
- [ ] `|=>` compiles to same architecture with 1-cycle delay offset (OP-04)
- [ ] `overflow_flag` output exists and is sticky (OUT-06)
- [ ] Overflow = hard fail + halt (D-05) — no silent thread drop
- [ ] BV_WIDTH parameter is auto-sized and overridable (D-06)
- [ ] Antecedent and consequent are independently composed as children (D-08/D-09)
- [ ] PropImplication IR nodes are correctly imported from slang JSON AST
- [ ] Pipeline runs end-to-end: JSON → PropImplication → CheckerNode → .sv files
- [ ] Phase 1 + Plan 2.1 tests still pass (no regressions)
