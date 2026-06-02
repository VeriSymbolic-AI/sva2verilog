# Phase 3: Remaining Tier 1 Operators + Named Sequences + Simulation Validation - Context

**Gathered:** 2026-05-26
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase delivers full Tier 1 SVA coverage: consecutive repetition (`[*N]`/`[*M:N]`), all signal functions (`$rose`, `$fell`, `$stable`, `$past`), `disable iff` with correct async semantics, named sequence/property expansion with CSE tagging, `bind` statement generation, and a dual-layer simulation validation oracle (Python behavioral + Icarus RTL). Every generated monitor is cross-checked cycle-exactly against ground truth.

</domain>

<decisions>
## Implementation Decisions

### Named Sequence/Property Expansion (PARSE-03)
- **D-01:** Named sequences are expanded inline at each use site (not shared sub-modules). Each property gets its own copy of the hardware. Simpler codegen with no multi-fanout wiring complexity.
- **D-02:** Expanded subtrees are tagged in the CheckerNode tree with their source declaration name, so Phase 5 CSE can identify and merge identical instances without re-analysis.
- **D-03:** Expansion is fully recursive — nested named references are resolved until only primitive operators remain. Cycle detection rejects self-referencing sequences with a clear error (SVA-E0xx).
- **D-04:** Named property declarations (`property p_name = ...`) follow the same inline expansion + CSE tagging pattern as named sequences.

### Simulation Oracle Architecture (TEST-03, TEST-04)
- **D-05:** Dual oracle validation: Python behavioral model for fast cycle-by-cycle checks (no simulator dependency) + Icarus Verilog co-simulation for RTL-level ground truth.
- **D-06:** Stimulus approach is golden + random hybrid: hand-crafted golden cases for known corner cases (boundary cycles, edge conditions) + Hypothesis property-based random traces for fuzz discovery.
- **D-07:** Simulation tests use `@pytest.mark.simulation` marker and gracefully skip when `iverilog` is not installed locally. CI environment explicitly installs Icarus and runs both suites (hard requirement in CI).
- **D-08:** Comparison is cycle-exact: pass/fail output signals are compared cycle-by-cycle between Python oracle and Icarus RTL simulation. Any single-cycle mismatch = test failure. Python oracle must model the same registered-output delay as the RTL.

### `disable iff` Semantics (OP-10)
- **D-09:** Full async state clear — `disable iff` forces ALL internal FFs (counters, bit-vectors, repetition FSMs) to their reset values combinationally within the same cycle. No stale state, no spurious transitions, no power waste while disabled.
- **D-10:** `disable` is always-present in the standard port interface on ALL sub-modules. When no `disable iff` clause exists, it's tied to `1'b0`. Uniform interface — no conditional template logic.
- **D-11:** While disabled: all outputs forced to 0 (pass=0, fail=0, active=0, attempt_fired=0) PLUS a new `disabled` output indicator goes high. Users can distinguish "idle" from "disabled by reset/abort."
- **D-12:** Standard interface updated: `clk, rst_n, start, pass, fail, active, attempt_fired, disable, disabled`. All existing Phase 2 templates must be updated to include `disable`/`disabled` ports.

### `bind` Generation (OUT-04)
- **D-13:** One bind file per property — `sva2rtl input.sv` produces `output/sva_my_check.sv` (monitor) + `output/sva_my_check_bind.sv` (bind statement). Simple 1:1 mapping.
- **D-14:** Target DUT module is inferred from slang AST context (the module containing the assertion). No extra CLI flag needed.
- **D-15:** Bind uses named port connections with explicit mapping: `.clk(clk), .rst_n(rst_n), .sig_a(a), .sig_b(b)`. Monitor port names match signal names used in the SVA expression.

### Claude's Discretion
- Named sequence/property resolution scope: follow what slang's `--ast-json` provides. If slang pre-resolves cross-file references, support them; if not, restrict to same-compilation-unit.
- Sub-module naming convention for repetition/signal-function modules (encode parameters into name, matching Phase 2 pattern)
- Internal wiring for the `disable` signal through the module hierarchy (top-level gates or per-FF async clear — implementation detail)
- `$past(sig, N)` handling of non-literal N (likely reject with unsupported-construct error for v1)
- `[*0:$]` unbounded repetition rejection with clear SVA-E002 error code
- Python oracle class structure and API surface (extend existing `behavioral_oracle.py`)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Algorithm
- `.planning/ROADMAP.md` Phase 3 section — Plan breakdown (3.1-3.4), success criteria, requirements mapping
- `.planning/REQUIREMENTS.md` — OP-05 through OP-10, PARSE-03, OUT-04, TEST-03/04 requirement details
- `.planning/PROJECT.md` §Key Decisions — Token-passing architecture, counter encoding rationale
- `.planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md` — Phase 2 decisions (counter encoding D-01/D-02, module topology D-08/D-09/D-10, overflow behavior D-05/D-07, token-passing wiring)

### Existing Implementation (Phase 1-2 patterns to follow)
- `src/sva2rtl/ir.py` — IR node hierarchy: `SeqConcat`, `PropImplication`, `BoolExpr`, `SourceLoc`
- `src/sva2rtl/ast_importer.py` — `UNSUPPORTED_KINDS_PHASE1` dict (remove `SequenceRepetition`), dispatch pattern to extend
- `src/sva2rtl/composer.py` — `compose()` pattern, `module_name_from_label()`, hierarchical CheckerNode building
- `src/sva2rtl/emitter.py` — Jinja2 FileSystemLoader, recursive child emission pattern
- `src/sva2rtl/behavioral_oracle.py` — Existing oracle infrastructure to extend for Phase 3 operators
- `templates/concat_delay.sv.j2` — Counter-based delay template (pattern for `[*N]` template)
- `templates/overlap_bitvec.sv.j2` — Bit-vector template (pattern for registered outputs + standard interface)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `behavioral_oracle.py` — already exists, extend with cycle-by-cycle evaluation for new operators
- `concat_delay.sv.j2` — counter+window pattern directly applicable to `[*M:N]` consecutive repetition
- `CheckerNode.children: tuple[CheckerNode, ...]` — hierarchical composition ready for named sequence subtrees
- `extract_signals()` in composer — signal extraction reusable for bind port inference
- `module_name_from_label()` — naming convention for generated bind file names

### Established Patterns
- **Registered outputs:** all monitor outputs use `always_ff` with sync reset — new templates (rose, fell, stable, past, rep) follow same pattern
- **Standard interface:** every module exposes the standard port set — Phase 3 extends it with `disable`/`disabled`
- **Counter encoding:** bounded ranges use counter + comparator (concat_delay pattern) — `[*M:N]` reuses this
- **Template parameterization:** `params: dict[str, str]` passed to Jinja2 — extend for repetition count, signal function parameters
- **Error dispatch:** `UNSUPPORTED_KINDS_PHASE1` → remove `SequenceRepetition`, add new unsupported kinds if any remain

### Integration Points
- `ast_importer.py`: add dispatch for `SequenceRepetition`, `$rose/$fell/$stable/$past` system functions, `disable iff`, named sequence/property resolution
- `composer.py`: extend to build CheckerNode tree for new operators, tag CSE candidates by declaration name
- `emitter.py`: new templates (rep_consecutive, rose, fell, stable, past, disable_iff), update all existing templates to include `disable`/`disabled` ports
- `ir.py`: may need new IR nodes for signal functions (`SignalFunc` or similar) and `disable iff` (`DisableIff`)
- `templates/` directory: add 5+ new templates, update existing ones for disable port

</code_context>

<specifics>
## Specific Ideas

- Counter-based FSM for `[*M:N]` should follow the exact same pattern as `concat_delay.sv.j2` — counter + window comparator `(count >= M) && (count <= N)`
- `$rose(sig)` = 1 FF + `(sig & ~sig_prev)` — exactly 1 FF of hardware cost
- `$fell(sig)` = 1 FF + `(~sig & sig_prev)` — exactly 1 FF of hardware cost
- `$stable(sig)` = 1 FF + XNOR comparator `(sig == sig_prev)`
- `$past(sig, N)` = N-stage shift register pipeline
- `disable` signal should use async clear pattern: `always_ff @(posedge clk or posedge disable)` for state registers
- CSE tag on CheckerNode could be a simple `cse_origin: str | None` field — None means unique, non-None names the source declaration
- Bind file should include a comment header with the original SVA text (matching OUT-08 pattern from Phase 1)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 3-Remaining Tier 1 Operators + Named Sequences + Simulation Validation*
*Context gathered: 2026-05-26*
