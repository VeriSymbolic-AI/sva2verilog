---
wave: 1
depends_on: []
files_modified:
  - src/sva2rtl/ast_importer.py
  - src/sva2rtl/composer.py
  - src/sva2rtl/emitter.py
  - src/sva2rtl/cli.py
  - templates/concat_delay.sv.j2
  - tests/fixtures/delay_fixed.json
  - tests/fixtures/delay_range.json
  - tests/test_ast_importer.py
  - tests/test_composer.py
  - tests/test_emitter.py
  - tests/golden/delay_fixed_3.sv
  - tests/golden/delay_range_2_5.sv
requirements:
  - OP-01
  - OP-02
autonomous: true
---

# Plan 2.1: Unified Delay Template — `##N` and `##[M:N]`

## Goal

Deliver end-to-end compilation of `##N` (fixed delay) and `##[M:N]` (range delay) SVA sequences into counter-encoded synthesizable RTL monitors. A single unified template handles both cases via window comparator, per decision D-01/D-02. The pipeline ingests a slang JSON AST containing `SequenceConcat`, builds hierarchical `CheckerNode` trees with delay children, emits multiple `.sv` files (one per module), and produces correct, compilable SystemVerilog.

## Vertical Slice

Input: `assert property (@(posedge clk) a ##3 b)` or `a ##[2:5] b`
Output: Flat directory with `sva_<name>.sv` (top wrapper) + `sva_delay_<M>_<N>.sv` (counter sub-module)
Proof: Golden file match + `iverilog output/*.sv` compiles clean

---

## Tasks

<task id="2.1.1">
<title>Create unified delay counter Jinja2 template</title>
<read_first>
- templates/bool_expr.sv.j2
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-01 through D-04)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 1: concat_delay.sv.j2)
</read_first>
<action>
Create `templates/concat_delay.sv.j2`. This template renders a standalone counter-based delay module with:
- Header comment block matching bool_expr.sv.j2 pattern (version, source_loc, original_text)
- Module port interface: `clk, rst_n, start` inputs; `active, pass, fail, attempt_fired` outputs (same standard interface)
- `parameter CNT_WIDTH = {{ cnt_width }}` declaration
- Counter register: `logic [CNT_WIDTH-1:0] count_q`
- State register: `logic running_q` (tracks whether counting is active)
- `always_ff @({{ clock_edge }} {{ clock_signal }})` block with sync reset
- Counter logic: on `start`, reset count to 0 and set running; increment each cycle while running; stop when count reaches `delay_max`
- Window comparator output: `assign pass = running_q && (count_q >= {{ delay_min }}) && (count_q <= {{ delay_max }})`
- `active` HIGH from start until count reaches delay_max
- `attempt_fired` sticky logic (same as bool_expr.sv.j2)
- `fail` output always 1'b0 for delay modules (delay cannot fail, only pass or not yet)
- Template parameters expected: module_name, clock_signal, clock_edge, delay_min, delay_max, cnt_width, source_loc, sva2rtl_version, original_text
- Special case: when delay_min == 0, pass is HIGH immediately on the start cycle (combinational pass-through for ##0 semantics)
</action>
<acceptance_criteria>
- File `templates/concat_delay.sv.j2` exists
- Template contains `parameter CNT_WIDTH` declaration
- Template contains `(count_q >= {{ delay_min }}) && (count_q <= {{ delay_max }})` window comparator logic
- Template contains `always_ff @({{ clock_edge }} {{ clock_signal }})` block
- Template contains standard port interface: input logic clk/rst_n/start, output logic active/pass/fail/attempt_fired
- Template contains `if (!rst_n)` synchronous reset block setting all registers to 0
- Template contains `endmodule` as final code line
- Template renders without Jinja2 errors when given params: module_name="sva_delay_2_5", clock_signal="clk", clock_edge="posedge", delay_min="2", delay_max="5", cnt_width="3", source_loc="test.sv:1:1", sva2rtl_version="0.1.0", original_text="##[2:5]"
</acceptance_criteria>
</task>

<task id="2.1.2">
<title>Extend ast_importer to handle SequenceConcat nodes</title>
<read_first>
- src/sva2rtl/ast_importer.py
- tests/fixtures/unsupported_delay.json
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 4: ast_importer.py)
- src/sva2rtl/ir.py (SeqConcat definition, lines 62-75)
</read_first>
<action>
Modify `src/sva2rtl/ast_importer.py`:
1. Remove `"SequenceConcat"` from `UNSUPPORTED_KINDS_PHASE1` dict (line 50). Keep `"SequenceRepetition"` entry.
2. Add `SeqConcat` to the import from `sva2rtl.ir` (line 24).
3. In `_import_concurrent_assertion()` (line 276-297): replace the unconditional `text = expr_to_sv(expr_node)` / `ir_node = BoolExpr(...)` with a match dispatch on `expr_node.get("kind")`:
   - case `"SequenceConcat"`: call new helper `_build_seq_concat(expr_node, source_loc)` which returns `SeqConcat`
   - default case: existing BoolExpr path
4. Add helper `_build_seq_concat(node: dict[str, Any], source_loc: SourceLoc) -> SeqConcat`:
   - Iterates `node["elements"]` list
   - For each element: extracts `element["sequence"]` → recursively builds `SVANode` via new `_dispatch_expr_to_ir(seq_node)` helper
   - Extracts `int(element.get("min", "0"))` and `int(element.get("max", "0"))` as delay tuple
   - Returns `SeqConcat(elements=tuple(elements), delays=tuple(delays), source_loc=source_loc)`
5. Add helper `_dispatch_expr_to_ir(node: dict[str, Any]) -> SVANode`:
   - For `"SequenceExpr"` kind: unwrap to inner expr and recurse
   - For `"NamedValue"` / `"BinaryOp"` / etc: call `expr_to_sv(node)` and wrap in `BoolExpr`
   - For `"SequenceConcat"` kind: call `_build_seq_concat` recursively
   - Extract source_loc from the node being dispatched
6. Reconstruct `original_text` for SeqConcat: join element texts with delay annotations (e.g. "a ##1 b")
</action>
<acceptance_criteria>
- `"SequenceConcat"` is NOT in `UNSUPPORTED_KINDS_PHASE1`
- `"SequenceRepetition"` IS still in `UNSUPPORTED_KINDS_PHASE1`
- `import_assertion()` on `tests/fixtures/unsupported_delay.json` returns a `SeqConcat` IR node (no longer raises UnsupportedConstruct)
- The returned `SeqConcat` has `elements` tuple of length 2 and `delays` tuple containing `(1, 1)`
- `SeqConcat.elements[0]` is a `BoolExpr` with text containing "a"
- `SeqConcat.elements[1]` is a `BoolExpr` with text containing "b"
- `SeqConcat.source_loc.file` equals "test_delay.sv"
- `mypy --strict src/sva2rtl/ast_importer.py` exits 0
</acceptance_criteria>
</task>

<task id="2.1.3">
<title>Extend composer to build hierarchical CheckerNode trees for SeqConcat</title>
<read_first>
- src/sva2rtl/composer.py
- src/sva2rtl/ir.py (SeqConcat, CheckerNode definitions)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 5: composer.py)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-01, D-04, D-08, D-09)
</read_first>
<action>
Modify `src/sva2rtl/composer.py`:
1. Add imports: `import math`, add `SeqConcat, PropImplication` to the import from `sva2rtl.ir`
2. Refactor `compose()` function: replace the single `if not isinstance(node, BoolExpr)` check with a `match node:` dispatch:
   - `case BoolExpr()`: call new `_compose_bool_expr(node, clock, label, original_text)` (extract current logic into this private helper)
   - `case SeqConcat()`: call new `_compose_seq_concat(node, clock, label, original_text)`
   - `case _`: raise `UnsupportedConstruct` with construct_name=type(node).__name__
3. Add `_compose_bool_expr()`: move the existing BoolExpr logic from compose() here, unchanged
4. Add `_compose_seq_concat(node, clock, label, original_text) -> CheckerNode`:
   - Build list of children: for each element in node.elements, recursively call `compose(elem, clock, None, original_text)` to get a BoolExpr CheckerNode
   - For each delay in node.delays, call `_make_delay_node(delay_min, delay_max, clock, node.source_loc)` to get a delay CheckerNode
   - Interleave: children = [elem0, delay0, elem1, delay1, ..., elemN] (elements and delays alternate)
   - Collect all observed_signals from children via `_collect_signals(children)`
   - Build top-level CheckerNode with template_name="seq_concat_top", module_name from label, children tuple, collected signals
5. Add `_make_delay_node(delay_min: int, delay_max: int, clock: ClockSpec, source_loc: SourceLoc) -> CheckerNode`:
   - Compute cnt_width = `max(1, math.ceil(math.log2(delay_max + 1)))` if delay_max > 0 else 1
   - Module name = `f"sva_delay_{delay_min}_{delay_max}"`
   - params dict with keys: module_name, delay_min (str), delay_max (str), cnt_width (str), clock_signal, clock_edge, source_loc, sva2rtl_version, original_text
   - template_name = "concat_delay"
   - observed_signals = () (delay modules have no DUT signal inputs)
   - children = ()
6. Add `_collect_signals(children: list[CheckerNode]) -> tuple[tuple[str, str], ...]`:
   - Iterates all children, deduplicates observed_signals, returns tuple
</action>
<acceptance_criteria>
- `compose(SeqConcat(...), clock, label, text)` returns a `CheckerNode` (does not raise)
- The returned CheckerNode has `children` tuple of length 3 for `a ##1 b` (elem_a, delay_1_1, elem_b)
- `children[1].template_name == "concat_delay"`
- `children[1].params["delay_min"] == "1"` and `children[1].params["delay_max"] == "1"`
- `children[1].params["cnt_width"] == "1"`
- `children[1].module_name == "sva_delay_1_1"`
- `children[0].template_name == "bool_expr"` (antecedent element)
- `children[2].template_name == "bool_expr"` (consequent element)
- For `##[2:5]`: delay node has `params["cnt_width"] == "3"` (ceil(log2(6))=3)
- `compose(BoolExpr(...), clock, label, text)` still works unchanged (backward compatibility)
- `mypy --strict src/sva2rtl/composer.py` exits 0
</acceptance_criteria>
</task>

<task id="2.1.4">
<title>Extend emitter for multi-file hierarchical output</title>
<read_first>
- src/sva2rtl/emitter.py
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 6: emitter.py)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-08, D-09, D-10)
</read_first>
<action>
Modify `src/sva2rtl/emitter.py`:
1. Add new public function `emit_all(checker: CheckerNode, template_dir: Path | None = None) -> dict[str, str]`:
   - Creates Jinja2 environment
   - Calls `_emit_recursive(checker, env, results)` with empty dict
   - Returns dict mapping module_name -> rendered SV text
2. Add `_emit_recursive(checker: CheckerNode, env: Environment, results: dict[str, str]) -> None`:
   - Depth-first: emit all children first
   - Skip if `checker.module_name` already in results (deduplication for CSE)
   - Build context dict from checker.params, add `observed_signals` and `children` keys
   - Render template and store in results
3. Modify existing `emit()` to also pass `children` into the template context (add `ctx["children"] = checker.children`). This maintains backward compatibility: bool_expr.sv.j2 template ignores the children variable since it doesn't reference it.
4. Add new public function `write_output_dir(modules: dict[str, str], output_dir: Path) -> None`:
   - Creates output_dir with parents=True, exist_ok=True
   - Writes each module to `output_dir / f"{module_name}.sv"`
   - UTF-8 encoding
5. Create `templates/seq_concat_top.sv.j2`:
   - Top-level wrapper module that instantiates children with token-passing wiring
   - Standard port interface (clk, rst_n, start, observed signals, active, pass, fail, attempt_fired)
   - Internal wires: wire children's pass→next child's start in sequence
   - First child gets parent's `start`; last child's `pass` drives parent's `pass`
   - `active` = OR of all children's active signals
   - `fail` = 1'b0 (sequence chains cannot fail, only pass or timeout)
   - `attempt_fired` = sticky, set on first start
   - Uses `{% for child in children %}` to generate instantiation code
</action>
<acceptance_criteria>
- Function `emit_all` exists in `src/sva2rtl/emitter.py` and is importable
- `emit_all(checker_with_children)` returns a dict with keys for each unique module_name in the tree
- `emit(checker_without_children)` still returns a string (backward compatible, Phase 1 tests pass)
- `write_output_dir` exists, creates directory, writes one .sv file per module
- File `templates/seq_concat_top.sv.j2` exists
- `seq_concat_top.sv.j2` template contains child instantiation loop using `{% for child in children %}`
- `seq_concat_top.sv.j2` contains standard port interface: clk, rst_n, start, active, pass, fail, attempt_fired
- `mypy --strict src/sva2rtl/emitter.py` exits 0
</acceptance_criteria>
</task>

<task id="2.1.5">
<title>Update CLI for multi-file output</title>
<read_first>
- src/sva2rtl/cli.py
- src/sva2rtl/emitter.py (after task 2.1.4 modifications)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 8: cli.py)
</read_first>
<action>
Modify `src/sva2rtl/cli.py`:
1. Add `emit_all, write_output_dir` to the import from `sva2rtl.emitter`
2. Update pipeline logic in `main()` after `checker_node = compose(...)`:
   - If `checker_node.children` is non-empty (hierarchical output):
     - Call `modules = emit_all(checker_node)`
     - Determine output_dir: if `--output` provided, use it as directory path; else use current directory "."
     - Call `write_output_dir(modules, Path(output_dir))`
   - Else (leaf node, backward-compatible):
     - Existing `sv_text = emit(checker_node)` + `write_output(sv_text, ...)` path unchanged
3. Update `--output` help text to indicate it is used as directory for hierarchical monitors
</action>
<acceptance_criteria>
- `sva2rtl` CLI with a `##N` input file writes multiple .sv files to the output directory
- `sva2rtl` CLI with a boolean-only input file still writes a single file (backward compatible)
- Exit code 0 on successful compilation of delay sequences
- `mypy --strict src/sva2rtl/cli.py` exits 0
</acceptance_criteria>
</task>

<task id="2.1.6">
<title>Create test fixtures and golden files for delay operators</title>
<read_first>
- tests/fixtures/unsupported_delay.json (existing fixture to adapt)
- tests/golden/bool_labeled.sv (golden file format reference)
- templates/concat_delay.sv.j2 (after task 2.1.1)
- templates/seq_concat_top.sv.j2 (after task 2.1.4)
</read_first>
<action>
Create test fixtures and golden reference files:
1. `tests/fixtures/delay_fixed.json`: slang AST JSON for `assert property (@(posedge clk) a ##3 b)`:
   - Reuse the structure from unsupported_delay.json but change min/max to "3"/"3"
   - SequenceConcat with 2 elements (NamedValue "a", NamedValue "b"), delay (3,3)
2. `tests/fixtures/delay_range.json`: slang AST JSON for `assert property (@(posedge clk) a ##[2:5] b)`:
   - SequenceConcat with 2 elements, delay (2,5)
3. `tests/golden/delay_fixed_3.sv`: Expected generated output for the top-level wrapper module of `a ##3 b`
   - Render the seq_concat_top.sv.j2 template manually with correct parameters
   - Module name: `sva_prop_<hash8>` (compute from "a ##3 b" text)
   - Contains instantiation of child delay module `sva_delay_3_3` and two bool_expr children
4. `tests/golden/delay_range_2_5.sv`: Expected generated output for `a ##[2:5] b` top wrapper
   - Contains instantiation of `sva_delay_2_5` child
5. `tests/golden/sva_delay_3_3.sv`: Expected generated output for the delay counter sub-module (##3)
   - Rendered from concat_delay.sv.j2 with delay_min=3, delay_max=3, cnt_width=2
6. `tests/golden/sva_delay_2_5.sv`: Expected generated output for the delay counter sub-module (##[2:5])
   - Rendered from concat_delay.sv.j2 with delay_min=2, delay_max=5, cnt_width=3
</action>
<acceptance_criteria>
- File `tests/fixtures/delay_fixed.json` exists and is valid JSON with `"kind": "SequenceConcat"` and delays of (3,3)
- File `tests/fixtures/delay_range.json` exists and is valid JSON with delays of (2,5)
- File `tests/golden/delay_fixed_3.sv` exists and contains `module sva_` and `endmodule`
- File `tests/golden/delay_range_2_5.sv` exists and contains `module sva_` and `endmodule`
- File `tests/golden/sva_delay_3_3.sv` exists and contains `parameter CNT_WIDTH` and `endmodule`
- File `tests/golden/sva_delay_2_5.sv` exists and contains `parameter CNT_WIDTH` and `endmodule`
- All golden .sv files end with a newline character
</acceptance_criteria>
</task>

<task id="2.1.7">
<title>Unit tests for delay operator pipeline</title>
<read_first>
- tests/test_ast_importer.py (existing test patterns)
- tests/test_composer.py (existing test patterns)
- tests/test_emitter.py (existing golden match test pattern)
- tests/fixtures/delay_fixed.json (after task 2.1.6)
- tests/fixtures/delay_range.json (after task 2.1.6)
</read_first>
<action>
Update existing test files and create new integration test:

1. Modify `tests/test_ast_importer.py`:
   - CHANGE `test_import_assertion_unsupported()` and `test_import_assertion_unsupported_construct_name()`: these currently test that unsupported_delay.json raises UnsupportedConstruct. Update them to instead test that SequenceConcat is now HANDLED (returns SeqConcat). Alternatively, rename and add new tests.
   - ADD `test_import_delay_fixed_returns_seq_concat()`: loads delay_fixed.json, asserts isinstance(node, SeqConcat)
   - ADD `test_import_delay_fixed_elements_count()`: asserts len(node.elements) == 2
   - ADD `test_import_delay_fixed_delays()`: asserts node.delays == ((3, 3),)
   - ADD `test_import_delay_range_delays()`: loads delay_range.json, asserts node.delays == ((2, 5),)
   - CHANGE `test_unsupported_kinds_table_has_sequence_concat()`: remove this test (SequenceConcat is no longer unsupported)

2. Modify `tests/test_composer.py`:
   - CHANGE `test_compose_unsupported_raises_unsupported_construct()` and `test_compose_unsupported_carries_source_loc()`: change from testing SeqConcat raises to testing it succeeds (or add new test and use a different unsupported type)
   - ADD `test_compose_seq_concat_returns_checker_node()`: compose(SeqConcat(elements=(BoolExpr("a"), BoolExpr("b")), delays=((3,3),)), ...) returns CheckerNode
   - ADD `test_compose_seq_concat_has_children()`: returned node has len(children) == 3
   - ADD `test_compose_seq_concat_delay_child_template()`: children[1].template_name == "concat_delay"
   - ADD `test_compose_seq_concat_delay_params()`: children[1].params["delay_min"] == "3", params["delay_max"] == "3"
   - ADD `test_compose_seq_concat_cnt_width()`: for delay (2,5): params["cnt_width"] == "3"

3. Modify `tests/test_emitter.py`:
   - ADD `test_emit_all_returns_dict()`: emit_all(checker_with_children) returns dict
   - ADD `test_emit_all_contains_all_module_names()`: dict keys contain delay sub-module name
   - ADD `test_emit_delay_golden_match()`: emit_all output for sva_delay_3_3 matches golden/sva_delay_3_3.sv
   - ADD `test_emit_backward_compatible()`: emit(bool_expr_checker) still works (existing tests already cover this — just ensure they still pass)
</action>
<acceptance_criteria>
- `pytest tests/test_ast_importer.py` exits 0 with all tests passing
- `pytest tests/test_composer.py` exits 0 with all tests passing
- `pytest tests/test_emitter.py` exits 0 with all tests passing
- No test references `"SequenceConcat" in UNSUPPORTED_KINDS_PHASE1` expecting True
- Tests exist that assert `isinstance(node, SeqConcat)` for delay_fixed.json import
- Tests exist that assert `children[1].template_name == "concat_delay"` for composed SeqConcat
- `mypy --strict tests/` exits 0
</acceptance_criteria>
</task>

---

## Threat Model

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Counter overflow in delay module (count_q wraps around for large N) | Medium | cnt_width is ceil(log2(N+1)) — always sufficient bits to hold max value. Acceptance test verifies cnt_width=7 for ##100. |
| Template injection via module_name (user-controlled label in SV output) | Low | module_name_from_label() already sanitizes with regex `[^a-zA-Z0-9_]` → `_`. No new attack surface. |
| Path traversal via --output flag (write files outside intended directory) | Low | CLI validates path is under working directory or uses Path resolution. Standard click path handling. |
| Denial of service via enormous delay value (##[0:2147483647]) | Medium | cnt_width computation uses math.log2 — produces a reasonable counter width (31 bits). No state expansion. Counter encoding by design prevents this. |
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

# Golden file match (deterministic output)
python -c "
from sva2rtl.emitter import emit_all
from sva2rtl.composer import compose
from sva2rtl.ast_importer import import_assertion
import json
ast = json.loads(open('tests/fixtures/delay_fixed.json').read())
node, clock, text, label = import_assertion(ast)
checker = compose(node, clock, label, text)
modules = emit_all(checker)
print('Modules:', list(modules.keys()))
assert 'sva_delay_3_3' in modules
"
```

---

## Must-Haves (Goal-Backward Verification)

- [ ] `##N` with N=1,3,8 compiles to counter-encoded delay module (OP-01)
- [ ] `##[M:N]` with [0:1],[2:5],[0:15] compiles to window-comparator counter module (OP-02)
- [ ] Single unified template handles both ##N and ##[M:N] (D-01/D-02)
- [ ] Hierarchical multi-file output: one .sv per module (D-08/D-09/D-10)
- [ ] Counter bit-width = ceil(log2(max+1)) (area-efficient encoding)
- [ ] Pipeline runs end-to-end: slang JSON AST -> SeqConcat IR -> CheckerNode tree -> .sv files
- [ ] Backward compatibility: boolean-only properties still compile identically
- [ ] All Phase 1 tests continue to pass
