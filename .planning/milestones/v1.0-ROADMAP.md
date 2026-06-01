# Roadmap: sva2rtl

**Mode:** mvp
**Granularity:** standard (6 phases, 3–5 plans each)
**Created:** 2026-05-25
**Requirements mapped:** 40 / 40 ✓

---

## How to Read This Roadmap

Each phase is a **vertical MVP slice** — it produces something that works end-to-end from a real SVA input file to a compilable, behaviorally correct RTL monitor. No phase produces a partially-working pipeline. Later phases extend earlier ones without breaking them.

**Plans** within each phase are concrete, independently testable deliverables that together complete the phase's slice.

---

## Phase 1: Foundation — IR + Slang Frontend + Boolean Assert → SV Monitor

**Mode:** mvp
**Delivers:** `sva2rtl bool_assert.sv` works end-to-end — the entire compiler pipeline exists, handles boolean assertions, and produces a valid, compilable SV monitor with the standard interface.
**Unlocks:** every subsequent phase (all downstream work depends on stable IR, token-passing interface contract, and slang ingestion)
**Progress:** 5/5 plans complete ✅ — Phase 1 COMPLETE

### Why This Slice

The most dangerous pitfalls (vacuous satisfaction, missing source location, silent miscompile) must be caught before any operator templates are written. Building the pipeline skeleton on the simplest possible input — a pure boolean property — validates the interface contract cheaply. The `attempt_fired` debug port must be first-class from day one; retrofitting it after ten operators are implemented is extremely painful.

### Plans

| # | Plan | Key Deliverables |
|---|------|-----------------|
| 1.1 | Project skeleton + SVA IR | `ir.py` (frozen dataclasses: `BoolExpr`, `SeqConcat`, `PropImplication`, `SourceLoc`), `errors.py` (error types + named codes), `checker_node.py` (CheckerNode with `start`/`active`/`pass`/`fail`/`attempt_fired` port contract) | ✅ 2026-05-25 |
| 1.2 | Slang frontend + AST importer | `frontend.py` (slang subprocess invocation, `--ast-json` capture), `ast_importer.py` (JSON → IR dispatch for boolean expressions + clock event extraction + source location threading) | ✅ 2026-05-25 |
| 1.3 | Template emitter + bool_expr template | `emitter.py` skeleton, `templates/bool_expr.sv.j2` (1-FF registered output, synchronous reset, standard port interface), `templates/checker_top.sv.j2` stub, Jinja2 pipeline wired end-to-end | ✅ 2026-05-25 |
| 1.4 | CLI entry point + error handling | `cli.py` (click), `--output` flag, exit codes (0/1/2/3), unsupported-construct error with source location, slang-not-found detection with install hint | ✅ 2026-05-25 |
| 1.5 | Unit test framework + Phase 1 tests | pytest + ruff + mypy (strict) configured; tests for `ir.py`, `ast_importer.py` (JSON fixture-based), `emitter.py` (bool_expr golden output); slang node-kind inventory script | ✅ 2026-05-25 |

### Requirements

PARSE-01, PARSE-02, PARSE-04, PARSE-05, OUT-01, OUT-02, OUT-03, OUT-07, OUT-08, CLI-05, CLI-06, TEST-01

### Success Criteria

1. `sva2rtl bool.sv` (containing `assert property (@(posedge clk) a && b)`) produces a `.sv` file that compiles clean under `iverilog` with no warnings.
2. The generated monitor exposes exactly `clk, rst_n, start, pass, fail, active, attempt_fired` ports; `attempt_fired` goes high in simulation on the first cycle the boolean fires.
3. Providing an SVA file containing `##1` (an unsupported-in-Phase-1 operator) exits with code 2, names the unsupported construct, and prints the source file/line/col — no silent miscompile, no crash.
4. Running `sva2rtl` when slang is not installed exits with code 3 and prints an actionable install message.
5. All unit tests pass; mypy --strict reports zero errors across the codebase.

---

## Phase 2: Core Sequential Operators — `##N`, `##[M:N]`, `|->`, `|=>`

**Mode:** mvp
**Delivers:** The backbone of >90% of real SVA assertions compiles end-to-end. Concurrent overlapping threads are tracked correctly via bit-vector method. Debug outputs make correctness verifiable.
**Unlocks:** Phase 3 operators (all depend on the implication wiring protocol established here)

### Why This Slice

`##N`, `##[M:N]`, and overlapping implication (`|->`) are the three most common SVA constructs. Getting the bit-vector thread-tracking model and the `|->` vs `|=>` one-cycle offset correct now prevents cascading errors in every subsequent operator. Concurrent-attempt stress tests and boundary tests must ship with the operators — not as future work.

### Plans

| # | Plan | Key Deliverables |
|---|------|-----------------|
| 2.1 | Fixed delay `##N` | `templates/concat_fixed.sv.j2` (N-stage shift register, parameterized width), golden test for `##1`, `##3`, `##8` |
| 2.2 | Range delay `##[M:N]` | `templates/concat_range.sv.j2` (counter + window comparator, `ceil(log2(N+1))`-bit counter, counter encoding — not state expansion), golden tests for `##[0:1]`, `##[2:5]`, `##[0:15]` |
| 2.3 | Overlapping implication `|->` (bit-vector) | `templates/overlap_bitvec.sv.j2` (bit-vector active-thread register, width = max_consequent_length, `overflow_flag` sticky output), golden tests |
| 2.4 | Non-overlapping implication `|=>` | `templates/nonoverlap.sv.j2` (1-cycle registered start → `|->` consequent wiring), full `|->` / `|=>` paired golden tests |
| 2.5 | Debug outputs + test suites | OUT-06 (`attempt_fired`, `overflow_flag`) verified in every golden test; golden file integration test harness (TEST-02); concurrent-attempt stress tests antecedent fires every cycle for 2× consequent length (TEST-05); boundary tests at N−1, N, M, M+1 (TEST-06) |

### Requirements

OP-01, OP-02, OP-03, OP-04, OUT-06, TEST-02, TEST-05, TEST-06

### Success Criteria

1. `sva2rtl delay.sv` (containing `@(posedge clk) a |-> ##[2:5] b`) produces a monitor where `fail` fires at exactly cycle 2, 3, 4, or 5 after a failing condition, never at cycle 1 or 6.
2. A `|->` monitor with antecedent firing every cycle for 20 cycles tracks all 20 concurrent threads independently; `fail` fires on the correct subset without false negatives or false positives.
3. `overflow_flag` latches high when concurrent active threads exceed the bit-vector width; it never silently drops threads without flagging the overflow.
4. All golden files for Phase 2 operators reproduce byte-for-byte across repeated runs (deterministic codegen).

---

## Phase 3: Remaining Tier 1 Operators + Named Sequences + Simulation Validation

**Mode:** mvp
**Delivers:** Full Tier 1 SVA coverage: consecutive repetition, all `$`-functions, `disable iff`, named sequences/properties, `bind` generation, and behavioral simulation oracle validation. Every generated monitor is cross-checked against Icarus Verilog.
**Unlocks:** Phase 4 normalization (requires complete operator set to normalize over) and production use

### Why This Slice

Consecutive repetition `[*N]` and the `$`-functions (`$rose`, `$fell`, `$stable`, `$past`) appear in the majority of real SVA testbenches. `disable iff` is safety-critical (reset behavior must be asynchronous — one of the most common misimplementation sites). Named sequences enable modular reuse. Simulation validation is the correctness oracle that catches semantic errors invisible to unit tests.

### Plans

| # | Plan | Key Deliverables |
|---|------|-----------------|
| 3.1 | ✅ Consecutive repetition `[*N]` and `[*M:N]` | `templates/rep_consecutive.sv.j2` (counter-based FSM, parameterized M/N, counted FSM with window accept), golden tests for `[*1]`, `[*3]`, `[*2:5]`, `[*0:$]` rejects with SVA-E002 |
| 3.2 | ✅ Signal function operators | `templates/rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2`, `past.sv.j2` (edge-detect FF, XNOR comparator, N-stage pipeline); unit tests asserting exactly 1 FF for `$rose`/`$fell`/`$stable`, N FFs for `$past(sig, N)` |
| 3.3 | ✅ `disable iff` + named sequence/property expansion | `templates/disable_iff_top.sv.j2` (async combinational output gate, effective_disable = disable_i | cond_result); `ast_importer.py` inline expansion of named `sequence`/`property` declarations (PARSE-03); `emit_bind()` + `templates/bind.sv.j2` (OUT-04); `disable_i`/`disabled_o` added to all 9 templates; module-naming collision bug fixed in `_compose_implication` |
| 3.4 | ✅ Simulation validation harness | `tests/simulation/` suite; Icarus Verilog behavioral oracle: each generated monitor simulated with stimulus → `pass`/`fail` compared against behavioral SVA reference; end-to-end oracle tests for all Tier 1 operators (TEST-03, TEST-04) |

### Requirements

OP-05, OP-06, OP-07, OP-08, OP-09, OP-10, PARSE-03, OUT-04, TEST-03, TEST-04

### Success Criteria

1. `$rose(sig)` monitor fires `pass` exactly 1 cycle after a 0→1 transition and never fires on a sustained-high signal; `$fell` fires exactly 1 cycle after 1→0; both verified in simulation.
2. `disable iff (rst_n)` monitor clears all active state within the same combinational cycle as the reset signal, with no 1-cycle spurious-failure window — verified via simulation stimulus toggling reset mid-sequence.
3. A named `sequence s = a ##2 b` used in two separate properties generates the monitor once (not twice), and both properties instantiate the shared sequence correctly.
4. All Tier 1 operator monitors pass the Icarus Verilog behavioral oracle: simulated `pass`/`fail` outputs match ground-truth behavioral SVA assertion evaluation for all golden test cases.
5. Generated `bind` statement compiles and connects to a reference DUT module without port-name mismatches.

---

## Phase 4: Normalization + Composition Engine

**Mode:** mvp
**Delivers:** A proper token-passing composition engine (TIMA Lab architecture) with a normalization preprocessing pass. Complex multi-operator chains that were handled ad-hoc in Phase 2–3 now route through the canonical architecture. `--dump-tree` becomes the debugging window into composition.
**Progress:** 3/3 plans complete ✅
**Unlocks:** Phase 5 optimization (optimizer requires a well-formed CheckerNode tree from the composition engine); reliable handling of deeply nested/composite SVA patterns

### Why This Slice

Phases 2–3 wire templates directly (workable for isolated operators). Phase 4 introduces the proper normalization→composition pipeline that handles complex composed patterns correctly, prevents subtle off-by-one errors in operator chaining, and gives the optimizer a stable tree to work with. All Phase 1–3 golden files must regenerate identically — normalization is transparent for simple cases, additive for complex ones.

### Plans

| # | Plan | Key Deliverables |
|---|------|-----------------|
| 4.1 | IR normalization pass | `normalizer.py`: bottom-up rewrites — `|=>` → `##1 |->` desugaring; flatten `SeqConcat` chains; canonicalize `##[N:N]` → `##N`; expand small fixed repetitions `[*N]` where N ≤ 3; normalize boolean constants; pure IR→IR (no side effects), fully tested | ✅ 2026-05-28 |
| 4.2 | Composition engine (token-passing) | `composer.py`: walks normalized IR, selects operator templates, wires `pass(antecedent)` → `start(consequent)` token signals; builds `CheckerNode` tree with stable structural hashes; replaces ad-hoc direct wiring from Phase 2–3 | ✅ 2026-05-28 |
| 4.3 | Integration + regression validation | Complex compositions tested: `a |-> ##[1:3] (b [*2:4] ##1 c)`; `--dump-tree` prints CheckerNode tree with token-passing wiring; all Phase 1–3 golden files regenerate byte-for-byte; all simulation oracle tests still pass | ✅ 2026-05-28 |

### Requirements

PIPE-01, PIPE-02

### Success Criteria

1. `a |=> ##[1:3] b` compiles via normalization (`|=>` → `##1 |->`) and produces the same behavioral output as the Phase 2 direct implementation; verified by simulation oracle.
2. A deeply nested assertion `a |-> (b ##[2:4] (c [*2:3] ##1 d))` compiles without error, and `--dump-tree` shows a well-formed CheckerNode tree with correct token-passing wiring.
3. All Phase 1–3 golden files regenerate byte-for-byte after the composition engine replaces direct wiring (normalization is transparent for simple inputs).
4. All Phase 3 simulation oracle tests pass without modification, confirming the new architecture is behaviorally equivalent.

---

## Phase 5: Optimization Passes

**Mode:** mvp
**Delivers:** Area-efficient output. Identical subexpressions share hardware (CSE). Repeated counters with the same parameters share a single module instance. Unreachable FSM states are pruned. Optimization is provably semantics-preserving via before/after oracle parity.
**Unlocks:** Phase 6 (optimization correctness is proven before the integration test suite locks in expected outputs)

### Why This Slice

Without optimization, every `##[2:5]` in a complex property instantiates its own counter even when the parameters are identical; CSE across a large monitor can reduce area by 30–50%. Dead-state pruning removes unreachable nodes that would synthesize to unnecessary flip-flops. Critically, optimization must be proven semantics-preserving before the integration test suite treats optimized output as the ground truth.

### Plans

| # | Plan | Key Deliverables |
|---|------|-----------------|
| 5.1 | Constant folding + concat merging | `optimizer.py` framework with pass protocol; `ConstantFoldPass` (propagate literal true/false); `ConcatMergePass` (merge adjacent `##N ##M` → `##(N+M)`); before/after tree comparison tests |
| 5.2 | CSE + counter merging | `CSEPass` (structural hash on frozen dataclass CheckerNode, deduplicate identical subtrees — identical subtrees become one instance with fanout wiring); `CounterMergePass` (range counters with same M/N parameters share single counter module) (PIPE-03, PIPE-04) |
| 5.3 | Dead-state elimination + parity tests | `DeadNodePass` (topological sort + reachability from root; prune unreachable CheckerNodes) (PIPE-05); full parity suite: for each golden test, optimized output must produce identical simulation traces as unoptimized; `--dump-tree` shows node count before/after |

### Requirements

PIPE-03, PIPE-04, PIPE-05

### Success Criteria

1. A property with two identical `##[2:5]` subsequences produces a single shared counter instance in the generated RTL — visible in `--dump-tree` and confirmed in the emitted module list.
2. `--dump-tree` reports reduced node count after optimization vs. before for a complex multi-operator property.
3. All Phase 1–4 simulation oracle tests pass unmodified on optimized output (optimization does not change observable `pass`/`fail`/`attempt_fired` behavior).
4. Dead-state nodes (unreachable FSM states introduced by over-approximation in repetition templates) are not present in the emitted output.

---

## Phase 6: CLI Polish + Verilog-2001 + Integration Testing

**Mode:** mvp
**Delivers:** Production-ready CLI with full debug modes, Verilog-2001 output for Icarus/broad-compatibility targets, and a locked integration test suite covering all 40 v1 requirements. The tool is releasable.
**Unlocks:** v1 release; user adoption; v2 planning

### Why This Slice

The core compiler is correct and optimized after Phase 5, but the developer experience is unpolished. `--dump-ast`, `--dump-ir`, and `--dump-tree` are essential debugging tools for users writing complex SVA. Verilog-2001 output is required for Icarus-only environments. The integration test suite, once locked against optimized output, becomes the regression guard for all future work.

### Plans

| # | Plan | Key Deliverables |
|---|------|-----------------|
| 6.1 | Full CLI flag implementation | `--dump-ast` (prints slang JSON, exits 0); `--dump-ir` (prints normalized SVA IR tree, exits 0); `--dump-tree` (prints CheckerNode tree, exits 0); `--property <name>` (compile single named property); `--slang-path <path>` (override slang binary location) (CLI-01 through CLI-04) |
| 6.2 | Verilog-2001 output mode | `--verilog` flag; Jinja2 template guards replacing `logic` → `wire`/`reg`, `always_ff` → `always @(posedge clk)`, `always_comb` → `assign`; all templates updated; `iverilog -g2001` compile verified in CI (OUT-05) |
| 6.3 | Integration test suite + CI hardening | End-to-end integration tests for all 40 v1 requirements locked against optimized golden output; Icarus Verilog in CI matrix (Ubuntu + macOS); `SUPPORTED_CONSTRUCTS.md` listing all v1 operators with examples; named error code table (SVA-E001 through SVA-Exx) |
| 6.4 | Release polish | Version stamp, `--version` flag; `pyproject.toml` package metadata; `uv` lock file committed; README with quick-start install + usage; all `--dump-*` outputs human-readable with clear section headers |

### Requirements

CLI-01, CLI-02, CLI-03, CLI-04, OUT-05

### Success Criteria

1. `sva2rtl --verilog prop.sv` produces output that compiles clean with `iverilog -g2001` with zero warnings for all supported operator classes.
2. `sva2rtl --dump-ir prop.sv` prints a human-readable normalized SVA IR tree (indented, node kinds labeled) and exits 0 without emitting any RTL.
3. `sva2rtl --dump-tree prop.sv` prints the optimized CheckerNode composition tree with token-passing wiring annotations and exits 0.
4. All 40 v1 requirements have a passing test in CI — unit tests, golden file tests, and simulation oracle tests — on both Ubuntu and macOS runners with Icarus Verilog.

---

## Requirement Coverage Matrix

| Requirement | Phase | Group |
|-------------|-------|-------|
| PARSE-01 | 1 | Parsing & Frontend |
| PARSE-02 | 1 | Parsing & Frontend |
| PARSE-03 | 3 | Parsing & Frontend |
| PARSE-04 | 1 | Parsing & Frontend |
| PARSE-05 | 1 | Parsing & Frontend |
| OP-01 | 2 | Tier 1 Operators |
| OP-02 | 2 | Tier 1 Operators |
| OP-03 | 2 | Tier 1 Operators |
| OP-04 | 2 | Tier 1 Operators |
| OP-05 | 3 | Tier 1 Operators |
| OP-06 | 3 | Tier 1 Operators |
| OP-07 | 3 | Tier 1 Operators |
| OP-08 | 3 | Tier 1 Operators |
| OP-09 | 3 | Tier 1 Operators |
| OP-10 | 3 | Tier 1 Operators |
| OUT-01 | 1 | RTL Output |
| OUT-02 | 1 | RTL Output |
| OUT-03 | 1 | RTL Output |
| OUT-04 | 3 | RTL Output |
| OUT-05 | 6 | RTL Output |
| OUT-06 | 2 | RTL Output |
| OUT-07 | 1 | RTL Output |
| OUT-08 | 1 | RTL Output |
| PIPE-01 | 4 | Internal Pipeline |
| PIPE-02 | 4 | Internal Pipeline |
| PIPE-03 | 5 | Internal Pipeline |
| PIPE-04 | 5 | Internal Pipeline |
| PIPE-05 | 5 | Internal Pipeline |
| CLI-01 | 6 | CLI & DX |
| CLI-02 | 6 | CLI & DX |
| CLI-03 | 6 | CLI & DX |
| CLI-04 | 6 | CLI & DX |
| CLI-05 | 1 | CLI & DX |
| CLI-06 | 1 | CLI & DX |
| TEST-01 | 1 | Quality & Testing |
| TEST-02 | 2 | Quality & Testing |
| TEST-03 | 3 | Quality & Testing |
| TEST-04 | 3 | Quality & Testing |
| TEST-05 | 2 | Quality & Testing |
| TEST-06 | 2 | Quality & Testing |

**Total: 40 / 40 mapped. 0 unmapped. ✓**

---

## Phase Dependencies

```
Phase 1 (Foundation)
    └── Phase 2 (Core Operators)
            └── Phase 3 (Remaining Tier 1 + Sim Validation)
                    └── Phase 4 (Normalization + Composition Engine)
                            └── Phase 5 (Optimization Passes)
                                    └── Phase 6 (CLI Polish + Verilog-2001)
```

Each phase is strictly sequential — no parallelism, because each phase's outputs are inputs to the next.

---

## v2 Preview (Out of Scope for This Roadmap)

The following are tracked in REQUIREMENTS.md as v2 and are **not** in this roadmap:
- Tier 2 operators: `throughout`, `first_match`, `and`/`or`, `[->N]`, `[=N]`, `intersect`, `within`
- Multi-clock domain support
- Local variables in sequences
- Coverage instrumentation (`cover property`)
- Area/timing estimation report
- FSM Graphviz visualization
- Formal equivalence checking hook (SymbiYosys)
- Library/programmatic API

---

*Roadmap created: 2026-05-25*
*Last updated: 2026-05-28 after Plan 4.1 completion — normalizer.py with [*1] identity removal, SeqConcat flattening, PropImplication preservation (D-05); 17 new tests; 470 tests pass (10 skip); PIPE-01 partially satisfied*
