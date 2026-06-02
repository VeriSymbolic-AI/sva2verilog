# Phase 2: Core Sequential Operators — `##N`, `##[M:N]`, `|->`, `|=>` - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers the backbone of >90% of real SVA assertions: fixed delays (`##N`), range delays (`##[M:N]`), overlapping implication (`|->`), and non-overlapping implication (`|=>`). Concurrent overlapping threads are tracked correctly via bit-vector method. Debug outputs (`attempt_fired`, `overflow_flag`) make correctness verifiable. Golden file integration tests and stress tests ship with the operators.

</domain>

<decisions>
## Implementation Decisions

### Delay Implementation (`##N` and `##[M:N]`)
- **D-01:** `##N` always uses counter encoding (never shift register). Same implementation as `##[M:N]` where M=N. Uniform codegen, always area-efficient. For `##1` this is a 1-bit counter (1 FF + compare). For `##100` this is 7 FFs instead of 100.
- **D-02:** Single unified delay template (`concat_delay.sv.j2`) handles both `##N` (as `##[N:N]`) and `##[M:N]`. Window comparator `(count >= M) && (count <= N)` trivially becomes `(count == N)` for fixed delays — synthesizer optimizes the gate.
- **D-03:** The delay module's `pass` output stays HIGH for the entire M..N window (all valid cycles). For `##[2:5]`, `pass` goes high at cycle 2 and remains high through cycle 5. For `##N`, `pass` is naturally a single-cycle pulse (window width = 1). This directly feeds the token-passing `start` of the next stage.
- **D-04:** Concurrency tracking lives in the `|->` bit-vector module, NOT in the delay module. The delay module is purely "start -> count -> window match -> pass" — it sees one active sequence at a time. The implication module manages multiple concurrent threads.

### Overflow Behavior (`|->` Bit-Vector Saturation)
- **D-05:** Overflow is a hard error: `fail` fires immediately on the overflow cycle AND `overflow_flag` latches high (sticky). Monitor HALTS — no more `pass`/`fail`/`active` signals after overflow. Only `rst_n` restores operation. No silent degradation, no confusing post-overflow results.
- **D-06:** Bit-vector width is auto-determined from max consequent length, but user-overridable via a generate parameter: `parameter BV_WIDTH = <consequent_length>`. Users can increase via bind override: `sva_my_check #(.BV_WIDTH(16)) u_check(...)`.
- **D-07:** `overflow_flag` is truly sticky — only cleared by `rst_n`. No `clear_overflow` input. Once set, stays high permanently until system reset.

### Module Output Topology
- **D-08:** Hierarchical sub-modules — each operator template generates its own SV module. For `a |-> ##[2:5] b`: `sva_delay_2_5` (counter + window), `sva_bitvec_impl_my_check` (thread tracking + overflow/halt), `sva_my_check` (top wrapper, standard interface, instantiates children).
- **D-09:** Module boundary = one module per operator template. Maximum composability, each component independently testable, enables Phase 5 CSE naturally (identical delay counters become shared instances).
- **D-10:** One .sv file per module, flat output directory. `sva2rtl input.sv --output ./output/` produces all .sv files in one flat directory. `iverilog output/*.sv` just works.

### Claude's Discretion
- Sub-module naming convention for generated delay/bitvec modules (encode parameters into name)
- Internal port interface between sub-modules (standard token-passing: start/pass/active/fail between parent and children)
- Counter reset behavior on `rst_n` (sync reset to zero, matching Phase 1 pattern)
- `##0` zero-delay semantics (combinational pass-through, no counter needed)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Algorithm
- `.planning/ROADMAP.md` Phase 2 section — Plan breakdown (2.1-2.5), success criteria, requirements mapping
- `.planning/REQUIREMENTS.md` — OP-01 through OP-04, OUT-06, TEST-02/05/06 requirement details
- `.planning/PROJECT.md` §Key Decisions — Token-passing architecture, bit-vector method, counter encoding rationale

### Existing Implementation (Phase 1 patterns to follow)
- `src/sva2rtl/ir.py` — `SeqConcat`, `PropImplication`, `CheckerNode` (with `children` tuple) already defined
- `src/sva2rtl/composer.py` — `compose()` pattern, `module_name_from_label()`, `extract_signals()` to extend
- `src/sva2rtl/emitter.py` — Jinja2 FileSystemLoader pattern, `emit()` renders `{template_name}.sv.j2`
- `src/sva2rtl/ast_importer.py` — `UNSUPPORTED_KINDS_PHASE1` dict to remove; dispatch on `SequenceConcat`, implication ops
- `templates/bool_expr.sv.j2` — Established pattern: registered outputs, sync reset, standard interface

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `CheckerNode.children: tuple[CheckerNode, ...]` — already supports hierarchical composition, children tuple ready for sub-module instantiation
- `SeqConcat(elements, delays)` IR node — already defined with `(min, max)` delay tuples, ready for Phase 2 use
- `PropImplication(antecedent, consequent, overlapping)` IR node — already defined with overlap flag
- `module_name_from_label()` — naming convention established, extend for sub-module names
- `extract_signals()` — signal extraction from expressions, reuse for antecedent/consequent signal lists
- `_make_env()` — Jinja2 environment setup, same loader for new templates

### Established Patterns
- **Registered outputs:** all monitor outputs use `always_ff` with sync reset (OUT-02) — new templates follow same pattern
- **Standard interface:** every module exposes `clk, rst_n, start, pass, fail, active, attempt_fired` — new sub-modules follow this contract
- **Template parameterization:** `params: dict[str, str]` passed to Jinja2 render context — extend for counter width, delay values
- **Error dispatch pattern:** `_check_unsupported()` + `UNSUPPORTED_KINDS_PHASE1` — remove entries as Phase 2 handles them
- **`SourceLoc` threading:** every IR node carries source location — maintain through new dispatch paths

### Integration Points
- `ast_importer.py` dispatch: remove `SequenceConcat` and implication ops from `UNSUPPORTED_KINDS_PHASE1`, add new dispatch cases in `expr_to_sv()` and `_import_concurrent_assertion()`
- `composer.py` `compose()`: extend `isinstance` check to handle `SeqConcat` and `PropImplication`, build hierarchical `CheckerNode` tree with children
- `emitter.py` `emit()`: needs to recursively emit children (each child → its own module file) plus the top-level wrapper
- `templates/` directory: add `concat_delay.sv.j2`, `overlap_bitvec.sv.j2`, `nonoverlap.sv.j2` (or unified implication template)

</code_context>

<specifics>
## Specific Ideas

- The unified delay template should use `(count >= M) && (count <= N)` as the window condition — synthesizers naturally optimize `M==N` to equality
- `parameter BV_WIDTH = <N>` at module top makes the bit-vector user-tunable without changing generated code
- Overflow halt state: freeze the bit-vector register, gate `active`/`pass`/`fail` outputs to 0, only `overflow_flag` remains high
- Token-passing wiring: `pass` of antecedent checker → `start` of delay module; `pass` of delay module → `start` of consequent checker

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 2-Core Sequential Operators*
*Context gathered: 2026-05-25*
