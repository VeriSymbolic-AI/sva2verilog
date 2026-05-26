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

Deliver end-to-end compilation of overlapping implication (`|->`) and non-overlapping implication (`|=>`) into synthesizable RTL with bit-vector concurrent thread tracking. The bit-vector module manages multiple simultaneous active threads, implements overflow detection with hard-halt semantics (D-05), and exposes `overflow_flag` as a sticky debug output. `|=>` is implemented with its own dedicated `nonoverlap.sv.j2` template using a 1-cycle `ant_pass_delayed_q` register (NOT decomposed to `##1 |->`).

## Key Design Decisions

- **[REVIEW FIX] BV_WIDTH auto-computation algorithm (HIGH concern #1):**
  `BV_WIDTH = max(max_delay_in_consequent + 1, 1)` where `max_delay_in_consequent` = sum of all `delay_max` values in the consequent sequence chain. For a `BoolExpr` consequent (single-cycle), max_delay=0 so BV_WIDTH=1. For `SeqConcat` with delays `[(2,5)]`, max_delay=5 so BV_WIDTH=6. For `SeqConcat` with delays `[(2,5),(1,3)]` (multi-element), max_delay=5+3=8 so BV_WIDTH=9. This ensures enough bit positions to track all possible concurrent threads when the antecedent fires every cycle.

- **[REVIEW FIX] Hard-halt overflow semantics (HIGH concern #2):**
  On overflow: (1) set `overflow_flag` sticky HIGH, (2) FREEZE the entire bit-vector register (no new threads accepted, no existing threads advance — `bv_q` holds its value), (3) gate `active`, `pass`, and `fail` outputs to 0, (4) only `rst_n` clears the overflow state and restores operation. This is option (b) — simplest RTL, matches D-05 exactly. The `fail` output pulses HIGH for exactly ONE cycle on the overflow event itself, then is gated to 0 while halted.

- **[REVIEW FIX] Bit-vector is a SHIFT REGISTER, not a counter array (MEDIUM concern #7):**
  Design note: The bit-vector (`bv_q`) is a shift register where each bit POSITION represents "a thread started exactly N cycles ago." Shifting right by 1 each cycle = all threads aging by one cycle. Setting bit[0] = new thread started this cycle. No per-thread counters are needed — the bit position IS the elapsed time counter. This is the key insight that makes the implementation O(BV_WIDTH) flip-flops rather than O(BV_WIDTH * COUNTER_WIDTH). When bit[K] is set, it means a thread is K cycles old.

- **[REVIEW FIX] `|=>` strategy (MEDIUM concern #11):**
  `|=>` uses its own dedicated `nonoverlap.sv.j2` template with a 1-cycle `ant_pass_delayed_q` register. It is NOT decomposed to `##1 |->` at the IR level. The template structure is identical to `overlap_bitvec.sv.j2` except that `ant_pass_delayed_q` (registered version of antecedent pass) drives bit insertion instead of raw `ant_pass_w`. Phase 4 normalization will later prove equivalence between `|=>` and `##1 |->` but for Phase 2 they are separate templates for clarity and testability.

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
   - Extract `node["left"]` -> antecedent: dispatch via `_dispatch_expr_to_ir(node["left"])` (reuse from Plan 2.1)
   - Extract `node["right"]` -> consequent: dispatch via `_dispatch_expr_to_ir(node["right"])`
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
<title>[REVIEW FIX] Create overlapping implication bit-vector template with hard-halt and shift register</title>
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

[REVIEW FIX] Internal architecture — SHIFT REGISTER design (not counter array):
- Bit-vector register `logic [BV_WIDTH-1:0] bv_q`: each bit POSITION represents a thread's age in cycles
- bit[0] = thread started THIS cycle; bit[K] = thread started K cycles ago
- On antecedent `pass` AND NOT overflow: set bit[0] = 1 (new thread enters)
- Each cycle (when not halted): shift bv_q right by 1 (all threads age by one cycle)
- Consequent evaluation: when bit[BV_WIDTH-1] is set (thread has aged to max), check consequent `pass`
- `pass` output: `bv_q[BV_WIDTH-1] && con_pass_w` (oldest thread AND consequent satisfied)
- `fail` output: `bv_q[BV_WIDTH-1] && !con_pass_w` (oldest thread AND consequent NOT satisfied), OR overflow event

[REVIEW FIX] Overflow hard-halt semantics (HIGH concern #2):
- Overflow condition: `ant_pass_w && (bv_q == {BV_WIDTH{1'b1}})` (antecedent fires AND all bits occupied)
- On overflow cycle: `fail` pulses HIGH for 1 cycle, `overflow_flag` latches HIGH
- HALT behavior: once `overflow_flag` is set:
  - `bv_q` is FROZEN (no shifting, no new bits inserted)
  - `active` output gated to 1'b0
  - `pass` output gated to 1'b0
  - `fail` output gated to 1'b0
- Only `rst_n` clears `overflow_flag` and restores operation (D-07)

Child instantiation:
- Instantiate antecedent child (first in children list): wire parent `start` -> ant child `start`
- Instantiate consequent child (second in children list): wire `con_start_w` -> con child `start`
- Wire internal signals: `ant_pass_w`, `con_pass_w`, `con_start_w`
- `attempt_fired`: sticky, set when antecedent first passes

Template parameters expected: module_name, bv_width, clock_signal, clock_edge, source_loc, sva2rtl_version, original_text, children (list), observed_signals
</action>
<acceptance_criteria>
- File `templates/overlap_bitvec.sv.j2` exists
- Template contains `parameter BV_WIDTH = {{ bv_width }}`
- Template contains `logic [BV_WIDTH-1:0] bv_q` bit-vector register
- Template contains right-shift logic: `bv_q <= {ant_pass_w, bv_q[BV_WIDTH-1:1]}` or equivalent shift-right with new bit insertion at MSB/LSB
- Template contains overflow detection logic with `overflow_flag` output
- [REVIEW FIX] Template contains HALT state logic that FREEZES bv_q when overflow_flag is set (no shift, no insert)
- [REVIEW FIX] Template gates active/pass/fail to 0 when overflow_flag is set
- Template contains `always_ff @({{ clock_edge }} {{ clock_signal }})` block
- Template contains `if (!rst_n)` synchronous reset clearing bv_q and overflow_flag
- Template contains at least two child module instantiations (antecedent + consequent)
- Template contains standard output ports: active, pass, fail, attempt_fired, overflow_flag
- Template contains `endmodule` as final code line
</acceptance_criteria>
</task>

<task id="2.2.3">
<title>[REVIEW FIX] Create non-overlapping implication template with dedicated ant_pass_delayed_q register</title>
<read_first>
- templates/overlap_bitvec.sv.j2 (after task 2.2.2 — sibling template)
- templates/concat_delay.sv.j2 (delay module reused for 1-cycle offset)
- .planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md (decisions D-08, D-09)
- .planning/phases/02-core-sequential-operators-n-m-n/02-PATTERNS.md (section 3: nonoverlap.sv.j2)
</read_first>
<action>
Create `templates/nonoverlap.sv.j2`. This template implements `|=>` with its own dedicated 1-cycle delay register.

[REVIEW FIX] Strategy confirmation (MEDIUM concern #11):
- `|=>` uses its OWN `nonoverlap.sv.j2` template — NOT decomposed to `##1 |->` at IR level
- The template is structurally identical to `overlap_bitvec.sv.j2` with ONE key difference:
  - Instead of `ant_pass_w` directly inserting bits into bv_q, a registered `ant_pass_delayed_q` does
  - `ant_pass_delayed_q` is a 1-cycle flip-flop that captures `ant_pass_w`
  - This register delays the bit-vector insertion by exactly 1 cycle
- Phase 4 normalization will later prove `|=>` equivalent to `##1 |->` but they remain separate templates for Phase 2

Implementation:
- Same module interface as overlap_bitvec.sv.j2 (including overflow_flag, BV_WIDTH parameter)
- Internal 1-cycle pipeline register: `logic ant_pass_delayed_q`
- In `always_ff`: `ant_pass_delayed_q <= ant_pass_w` (with sync reset to 0)
- Bit insertion uses `ant_pass_delayed_q` instead of `ant_pass_w`: `bv_q <= {ant_pass_delayed_q, bv_q[BV_WIDTH-1:1]}`
- Overflow detection uses `ant_pass_delayed_q` (overflow on delayed signal, matching insertion)
- All other logic (bv_q shifting, overflow halt, consequent checking, output gating) identical to overlap template
- Same HALT semantics: freeze bv_q, gate outputs, only rst_n clears
</action>
<acceptance_criteria>
- File `templates/nonoverlap.sv.j2` exists
- Template contains `parameter BV_WIDTH = {{ bv_width }}`
- [REVIEW FIX] Template contains `logic ant_pass_delayed_q` register declaration
- [REVIEW FIX] Template contains `ant_pass_delayed_q <= ant_pass_w` in always_ff block (1-cycle delay)
- [REVIEW FIX] Template uses `ant_pass_delayed_q` (NOT `ant_pass_w`) for bit-vector insertion
- Template contains bit-vector register `logic [BV_WIDTH-1:0] bv_q`
- Template contains overflow detection and halt logic (same as overlap)
- Template contains standard port interface including `overflow_flag` output
- Template contains `always_ff` block with synchronous reset
- Template contains `endmodule`
- The behavioral difference from overlap_bitvec: consequent evaluation starts 1 cycle later than antecedent match
</acceptance_criteria>
</task>

<task id="2.2.4">
<title>[REVIEW FIX] Extend composer to handle PropImplication with formal BV_WIDTH algorithm</title>
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
   - [REVIEW FIX] Compute bv_width using formal algorithm: `bv_width = _compute_bv_width(node.consequent)`
   - Build module_name from label
   - Collect observed_signals from both children
   - Build params dict with keys: module_name, bv_width (str), clock_signal, clock_edge, source_loc, sva2rtl_version, original_text
   - Return CheckerNode with template, params, children=(ant_checker, con_checker)

3. [REVIEW FIX] Add `_compute_bv_width(consequent: SVANode) -> int` (HIGH concern #1):
   Formal algorithm: `BV_WIDTH = max(max_delay_in_consequent + 1, 1)`
   Where `max_delay_in_consequent` is computed as:
   - For `BoolExpr`: max_delay = 0, so BV_WIDTH = 1 (single-cycle consequent)
   - For `SeqConcat`: max_delay = sum of all delay_max values in the delays tuple
     - Example: delays=((2,5),) -> max_delay=5 -> BV_WIDTH=6
     - Example: delays=((2,5),(1,3)) -> max_delay=5+3=8 -> BV_WIDTH=9
   - Default for unknown types: return 8 (safe default)
   - Minimum: always at least 1
   
   Implementation:
   ```python
   def _compute_bv_width(consequent: SVANode) -> int:
       """Compute BV_WIDTH = max(max_delay_in_consequent + 1, 1).
       
       max_delay = sum of all delay_max values in the consequent chain.
       Each bit position in the shift register represents one cycle of
       thread age, so we need enough positions for the longest possible
       consequent evaluation window.
       """
       match consequent:
           case BoolExpr():
               return 1  # single-cycle: max_delay=0, width=1
           case SeqConcat():
               max_delay = sum(d_max for _, d_max in consequent.delays)
               return max(max_delay + 1, 1)
           case _:
               return 8  # safe default for unknown structures
   ```
</action>
<acceptance_criteria>
- `compose(PropImplication(ant=BoolExpr("a"), con=BoolExpr("b"), overlapping=True), clock, label, text)` returns a CheckerNode
- Returned node has `template_name == "overlap_bitvec"` for overlapping=True
- Returned node has `template_name == "nonoverlap"` for overlapping=False
- Returned node has `children` tuple of length 2 (antecedent, consequent)
- `children[0]` is the antecedent checker (BoolExpr template)
- `children[1]` is the consequent checker (BoolExpr or seq_concat_top template)
- [REVIEW FIX] For `a |-> b` (BoolExpr consequent): `params["bv_width"] == "1"`
- [REVIEW FIX] For `a |-> ##[2:5] b` (SeqConcat consequent with delays=((2,5),)): `params["bv_width"] == "6"`
- [REVIEW FIX] For `a |-> ##2 b ##3 c` (SeqConcat with delays=((2,2),(3,3))): `params["bv_width"] == "6"` (max_delay=2+3=5, width=6)
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
   - Module name: use labeled fixture (e.g., label "impl_check" -> "sva_impl_check")

4. `tests/golden/nonoverlap_impl.sv`: Expected generated output for `a |=> b` monitor:
   - Render nonoverlap.sv.j2 with bv_width=1
   - Contains the 1-cycle delay register for antecedent pass (ant_pass_delayed_q)

5. `tests/golden/sva_bitvec_impl.sv`: Expected generated bit-vector implication sub-module for a more complex case (e.g., `a |-> ##[2:5] b`)
   - Shows bit-vector with bv_width=6 (max_delay=5, width=5+1=6)
</action>
<acceptance_criteria>
- File `tests/fixtures/implication_overlap.json` exists, is valid JSON, contains `"op": "OverlappedImplication"`
- File `tests/fixtures/implication_nonoverlap.json` exists, is valid JSON, contains `"op": "NonOverlappedImplication"`
- File `tests/golden/overlap_impl.sv` exists, contains `overflow_flag`, `module sva_`, `endmodule`
- File `tests/golden/nonoverlap_impl.sv` exists, contains `overflow_flag`, `ant_pass_delayed`, `module sva_`, `endmodule`
- All golden .sv files end with a newline character
- All JSON fixtures have proper `"design"` top-level key with Instance/InstanceBody/ConcurrentAssertion nesting
</acceptance_criteria>
</task>

<task id="2.2.6">
<title>[REVIEW FIX] Unit tests for implication pipeline with BV_WIDTH algorithm verification</title>
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
   - [REVIEW FIX] `test_compose_implication_bv_width_bool_consequent()`: assert params["bv_width"] == "1" for BoolExpr consequent
   - [REVIEW FIX] `test_compose_implication_bv_width_delay_consequent()`: assert params["bv_width"] == "6" for SeqConcat consequent with delays=((2,5),)
   - [REVIEW FIX] `test_compose_implication_bv_width_multi_delay()`: assert params["bv_width"] == "6" for SeqConcat with delays=((2,2),(3,3)) (max_delay=5, width=6)
   - `test_compose_implication_with_delay_consequent()`: compose PropImplication where consequent is SeqConcat, verify children[1] has its own children

3. `tests/test_emitter.py` additions:
   - `test_emit_overlap_bitvec_contains_overflow()`: emit() of overlap_bitvec checker contains "overflow_flag"
   - `test_emit_overlap_bitvec_contains_bv_register()`: contains "bv_q"
   - [REVIEW FIX] `test_emit_overlap_bitvec_contains_halt_gating()`: contains logic that gates outputs to 0 when overflow_flag is set
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
- [REVIEW FIX] Tests verify bv_width=1 for BoolExpr consequent
- [REVIEW FIX] Tests verify bv_width=6 for SeqConcat consequent with max_delay=5
- [REVIEW FIX] Tests verify halt gating logic in emitted output
- `mypy --strict tests/` exits 0
</acceptance_criteria>
</task>

---

## Threat Model

<threat_model>
| Threat | Severity | Mitigation |
|--------|----------|------------|
| Silent thread drop when bv_q overflows (data loss) | High | D-05: overflow is a HARD ERROR — fail fires immediately + overflow_flag sticky + HALT state (freeze all). No silent degradation. Covered by TEST-05 stress tests in Plan 2.3. |
| Bit-vector width too small for workload (false overflow) | Medium | [REVIEW FIX] BV_WIDTH formally computed as max(sum_of_delay_max + 1, 1). Auto-sizing covers all cases where antecedent fires every cycle. User-overridable via parameter for edge cases. |
| Off-by-one in |=> vs |-> (consequent starts wrong cycle) | High | [REVIEW FIX] |=> has dedicated template with explicit ant_pass_delayed_q register. Golden tests verify 1-cycle offset. Not relying on decomposition. |
| Antecedent/consequent signal collision in generated wiring | Low | _collect_signals deduplicates. Children have unique instance names derived from module_name. |
| Template injection via property text in comments | Low | original_text is placed in SV comment only. SV comments cannot affect synthesis. |
| [REVIEW FIX] Overflow with existing threads still in-flight (data corruption) | High | Hard-halt FREEZES entire state — no threads advance, no threads lost. On reset, clean restart. No partial state corruption possible. |
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
- [ ] [REVIEW FIX] BV_WIDTH computed formally: `max(sum_of_delay_max + 1, 1)` — not a guess
- [ ] [REVIEW FIX] BV_WIDTH=1 for BoolExpr consequent, BV_WIDTH=6 for delays=((2,5),) consequent
- [ ] [REVIEW FIX] Hard-halt FREEZES bv_q, gates active/pass/fail to 0, only rst_n clears
- [ ] [REVIEW FIX] `|=>` uses dedicated nonoverlap.sv.j2 with ant_pass_delayed_q register (not ##1 |-> decomposition)
- [ ] [REVIEW FIX] Bit-vector is shift register: bit position = thread age, shift right = all threads age
- [ ] BV_WIDTH parameter is auto-sized and overridable (D-06)
- [ ] Antecedent and consequent are independently composed as children (D-08/D-09)
- [ ] PropImplication IR nodes are correctly imported from slang JSON AST
- [ ] Pipeline runs end-to-end: JSON -> PropImplication -> CheckerNode -> .sv files
- [ ] Phase 1 + Plan 2.1 tests still pass (no regressions)
