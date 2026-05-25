# Project Research Summary

**Project:** SVA-to-RTL Compiler (Python-based)
**Domain:** Compiler / EDA tooling — SystemVerilog Assertions → synthesizable RTL monitors
**Researched:** 2026-05-25
**Confidence:** HIGH

## Executive Summary

This project is a source-to-source compiler that translates IEEE 1800-2017 SystemVerilog Assertions (SVA) into synthesizable RTL hardware monitors. The tool occupies a well-defined niche: it does not simulate or formally verify properties, but instead generates standalone `always_ff`-based FSM modules that can be `bind`-instantiated into any DUT to do runtime assertion checking in silicon or gate-level simulation. Expert implementations (TIMA Lab, existing academic tools) converge on a token-passing architecture — each in-flight sequence match is represented as a token flowing through a composed checker network, entirely avoiding the NFA→DFA subset-construction state explosion that plagues naive implementations.

The recommended approach is a strict 9-stage pipeline: slang CLI as the parsing frontend (JSON AST), frozen-dataclass SVA IR, a rewrite-based normalizer, a Composer that builds a `CheckerNode` tree via token-passing composition, lightweight optimizer passes, and a Jinja2 template emitter. This layering enforces clean separation between semantic concerns and RTL generation, making operator coverage incremental and testable at each stage. The `automata-lib` library handles NFA/DFA where needed (small subgraphs ≤ 8 states), while larger sequences use token-passing directly.

The dominant risk class is **silent semantic incorrectness**: vacuous satisfaction (a monitor that passes without ever firing), bit-vector overflow when many threads are simultaneously active, and the `throughout`/`intersect` boundary cases. All three are easy to get wrong with tests that pass — the antidote is a first-class `attempt_fired` debug output baked in from Phase 1, mandatory concurrent-attempt stress tests, and behavioral SVA simulation used as an oracle throughout development.

---

## Key Findings

### Recommended Stack

The stack is entirely Python 3.12+ with `uv` as the package manager. The critical frontend choice is `slang v11.0` (the only production-quality open-source SV parser) invoked via subprocess with `--ast-json` — this produces a stable, version-insulated JSON AST rather than binding directly to pyslang's Python API. Internal IR uses frozen dataclasses throughout; Python 3.12's `match`/`case` structural pattern matching aligns naturally with `node["kind"]` dispatch. Jinja2 templates give RTL engineers readable, reviewable output with clean whitespace control.

See [STACK.md](STACK.md) for full rationale and explicit "What NOT to use" decisions.

**Core technologies:**
- **Python 3.12+**: Runtime — `match`/`case` for AST dispatch; all dependencies support it
- **slang v11.0 (`--ast-json`)**: SVA frontend — only spec-compliant SV parser, MIT license, JSON isolates against API churn
- **frozen dataclasses**: IR modeling — structural hashing for CSE, immutable for safe sharing across passes
- **automata-lib 9.0.0**: NFA/DFA engine — `NFA.to_dfa()` + `DFA.minify()` for small subgraphs
- **networkx 3.6.1**: Graph algorithms — cycle detection, SCC, topological sort of RTL modules
- **Jinja2 3.1.6**: RTL code generation — template inheritance, whitespace control, custom `sv_width` filters
- **click 8.x**: CLI framework — composable subcommands, clean option declarations
- **pytest 9.x + hypothesis 6.x**: Testing — property-based testing generates edge-case SVA structures; shrinking finds minimal reproducers
- **ruff + mypy (strict)**: Code quality — ruff replaces Black + Flake8 + isort; strict mypy catches missing match cases at analysis time

---

### Expected Features

See [FEATURES.md](FEATURES.md) for full operator tables, the dependency chain diagram, and the priority matrix.

**Must have (table stakes — v1 required):**
- Boolean expressions, `$rose`/`$fell`/`$stable`, `$past(sig, n)` — basic signal checks
- Fixed delay `##n` and range delay `##[n:m]` — core sequence operators
- Consecutive repetition `[*n]` / `[*n:m]` — counter + FSM
- Overlapping (`|->`) and non-overlapping (`|=>`) implication — the primary assertion form
- `disable iff (reset_expr)` — synchronous clear on monitors
- Named `sequence` / `property` definitions — modular reuse
- Synthesizable RTL output: no `initial` blocks, no `$display`, standard `clk/rst_n/pass/fail` port interface
- `bind`-based wrapper generation with auto-inferred port connections
- Error reporting with `file:line:col` attribution; non-zero exit on error; never silent miscompile
- CLI with `--output`, `--verilog`, `--property`, exit codes for CI integration

**Should have (competitive differentiators — v1 stretch / v2):**
- Tier 2 operators: go-to repetition `[->n]`, non-consecutive `[=n]`, `first_match`, `intersect`, `within`, `throughout`
- Optimization passes: dead-state pruning (quick win), counter merging, CSE across monitors, area estimation report
- Developer experience: `--dump-ast`, `--dump-ir`, `--dump-tree`, FSM Graphviz visualization, verbose synthesis report
- `attempt_fired` / `overflow_flag` / `pending_count` debug output ports
- Coverage instrumentation (`cover property` → `cover_hit` output)

**Defer (v2+):**
- Local variables in sequences — capture-at-match registers; VERY HIGH complexity, strongest differentiator
- Multi-clock domain support — per-sequence clock annotation, CDC-safe sampling warnings
- LTL strong operators (`strong(seq)`) — liveness in hardware is architecturally unsound for safety monitors; v3+

---

### Architecture Approach

The compiler follows a strict left-to-right pipeline with clean component boundaries: `Frontend` (slang subprocess) → `ASTImporter` (JSON → SVA IR) → `Normalizer` (canonical rewrites per Patent US7810056B2) → `Composer` (IR → `CheckerNode` tree via token-passing per Patent US10726182B2) → `Optimizer` (CSE, counter merge, dead-node prune) → `Emitter` (Jinja2 → RTL text) → `CLI`. No component reaches backward into a prior stage's representation. The fundamental design choice — token-passing rather than NFA determinization — is made at the Composer/Optimizer boundary and must be settled in Phase 1, as it determines the entire template library interface (`start`/`active`/`pass`/`fail` token ports on every checker module).

See [ARCHITECTURE.md](ARCHITECTURE.md) for full module specs, IR node type definitions, template directory layout, and the 9-stage build order.

**Major components:**
1. **Frontend + ASTImporter** (`frontend.py`, `ast_importer.py`) — slang subprocess invocation and JSON → typed SVA IR; slang schema knowledge isolated here entirely
2. **SVA IR** (`ir.py`) — frozen dataclass tree: `BoolExpr`, `SeqConcat`, `SeqRep`, `PropImplication`, etc.; basis for all downstream passes
3. **Normalizer** (`normalizer.py`) — bottom-up rewrite: desugar `|=>`, flatten concat chains, expand small fixed repetitions, normalize boolean constants
4. **Composer** (`composer.py`) — walks normalized IR, selects templates, wires token-passing signals (`pass` of antecedent → `start` of consequent)
5. **Operator Template Library** (`templates/`) — Jinja2 `.sv.j2` files per operator; standard `clk/rst_n/start/active/pass/fail` interface on all modules
6. **Optimizer** (`optimizer.py`) — constant fold, concat merge, counter share, CSE (structural hash dedup), dead-node prune
7. **Emitter** (`emitter.py`) — DFS collect unique `CheckerNode`s, emit children-before-parents, SV vs Verilog-2001 guards
8. **CLI** (`cli.py`) — click entry point; `--dump-*` debug modes, `--optimize`, `--slang-path`, `--multi-file`

---

### Critical Pitfalls

See [PITFALLS.md](PITFALLS.md) for the full danger matrix, per-pitfall prevention recipes, and the "silent killers" summary.

1. **Vacuous satisfaction (P1.1)** — `A |-> B` passes because A never fires; monitor reports "pass" having checked nothing. _Avoid:_ emit first-class `attempt_fired` output from Phase 1; every test asserts it went high; document "meaningful pass = `fail==0 AND attempt_fired==1`."

2. **NFA→DFA state explosion (P4.1)** — subset construction on an N-state NFA produces up to 2^N DFA states. _Avoid:_ use token-passing architecture for all sequences; only DFA-convert NFAs with ≤ 8 states. This is the core architectural decision and must be settled pre-Phase 1.

3. **Bit-vector overflow / silent thread drop (P1.3)** — antecedent firing every cycle overflows the active-thread bit-vector; oldest threads silently dropped, producing false negatives. _Avoid:_ parameterize bit-width to `max_consequent_length` at compile time; emit sticky `overflow_flag` output; mandatory concurrent-attempt stress tests.

4. **Token duplication missing at `or` nodes (P8.2)** — at sequence disjunction, tokens must be _duplicated_ into both branches, not moved. Missing duplication leaves one branch permanently unchecked. _Avoid:_ formal token-passing spec before implementation; token-count invariant checker; test each branch in isolation.

5. **Source location not threaded through IR (P5.1)** — errors referencing generated RTL line numbers instead of original SVA source. Retrofitting after the fact is extremely painful. _Avoid:_ `SourceLoc(file, line, col)` is a first-class field on IR nodes from Phase 1.

6. **`throughout` / `intersect` semantics (P1.4, P1.5)** — `throughout` must check its condition _every cycle_, not just start/end; `intersect` requires same start AND same end, not same-start-only. _Avoid:_ dedicated templates with explicit cycle-level AND semantics; synchronized product NFA for `intersect`.

7. **`disable iff` is asynchronous (P1.6)** — treating it as synchronous reset leaves a one-cycle window of spurious failure. _Avoid:_ gate all outputs combinationally with disable condition; async clear on FFs.

---

## Implications for Roadmap

Based on the architecture's 9-stage build order, the feature dependency chain, and pitfall phases:

### Phase 1: Foundation — IR, Ingestion, Normalizer, Template Interface

**Rationale:** All downstream work depends on a correct IR and a stable token-passing interface contract. The most dangerous pitfalls (vacuous satisfaction, source location, strong/weak scope decision) must be settled here — they cannot be retrofitted.
**Delivers:** `ir.py`, `errors.py`, `checker_node.py` (with `attempt_fired` port from day one); `frontend.py` + `ast_importer.py` tested against JSON fixtures; `normalizer.py` with pure IR→IR tests; minimal `bool_expr` + `concat_fixed` templates + emitter skeleton to validate the interface cheaply before writing the Composer.
**Addresses:** §1.1 (boolean exprs), §1.2 (single-clock semantics), §1.5 (error reporting with source location)
**Avoids:** P5.1 (source location), P1.8 (strong/weak scope), P8.1 (slang AST node enumeration), P8.4 (implicit clocking)

### Phase 2: Core Sequential Operators + Composition

**Rationale:** `##n`, `##[n:m]`, and implication (`|->`/`|=>`) are the backbone of >90% of real SVA assertions. Getting composition correct (token-passing wiring, `|->` vs `|=>` cycle offset) is load-bearing for everything else.
**Delivers:** `composer.py`; templates for `concat_fixed`, `concat_range`, `overlap_bitvec`, `nonoverlap`; golden test suite with `attempt_fired` assertions and concurrent-attempt stress tests; basic CLI (`--output`, `--verilog`, exit codes).
**Uses:** slang JSON fixtures, frozen IR, Jinja2 templates
**Implements:** token-passing composition, implication wiring protocol
**Avoids:** P1.2 (|->vs|=> off-by-one), P1.3 (bit-vector width parameterization), P2.1 (combinational loops), P2.3 (counter bit-width), P2.4 (reset on every FF), P3.1 (concurrent-attempt tests), P3.4 (boundary tests)

### Phase 3: Repetition Operators + Named Sequences + bind Generation

**Rationale:** Consecutive repetition `[*n:m]` unlocks counter-based templates needed for almost all temporal patterns. Named `sequence`/`property` support enables composition of larger designs. `bind` generation completes the integration story.
**Delivers:** `rep_consecutive.sv.j2`, `rep_goto.sv.j2`, `rep_nonconsec.sv.j2`; named sequence/property instantiation; `checker_top.sv.j2` `bind` wrapper with auto-port inference; `disable iff` (async clear template); `$rose`/`$fell`/`$stable`/`$past` templates.
**Addresses:** §1.1 full operator table, §1.4 (bind generation)
**Avoids:** P1.4 (`throughout` every-tick), P1.6 (`disable iff` async), P4.2 (unbounded rep compile error)

### Phase 4: Optimization Passes

**Rationale:** Optimization requires a complete, correct `CheckerNode` tree — it cannot proceed until Phase 3 has full operator coverage. Dead-state pruning and counter merging are quick wins with high area impact.
**Delivers:** `optimizer.py` with `ConstantFoldPass`, `ConcatMergePass`, `CounterMergePass`, `CSEPass`, `DeadNodePass`; before/after tree tests; golden parity checks (optimization must not change observable behavior).
**Uses:** structural hash deduplication on frozen dataclass IR
**Avoids:** P1.5 (`intersect` product explosion managed via state-count budget), P4.3 (nesting depth limits)

### Phase 5: Tier 2 Operators + Developer Experience

**Rationale:** Tier 2 operators (`intersect`, `within`, `throughout`, `first_match`) are differentiators but depend on a working FSM composition foundation. Debug outputs make the tool usable for operator adoption.
**Delivers:** `seq_intersect.sv.j2`, `throughout.sv.j2`, `within.sv.j2`, `first_match.sv.j2`; `--dump-ast`, `--dump-ir`, `--dump-tree` CLI modes; FSM Graphviz DOT visualization; verbose synthesis report; `pending_count`/`overflow_flag` debug outputs.
**Addresses:** §2.1 Tier 2 operators, §2.3 developer experience
**Avoids:** P1.5 (`intersect` same-start-AND-end via synchronized product NFA)

### Phase 6: Simulation Validation + CI Hardening

**Rationale:** Behavioral correctness against a real SV simulator (Icarus/Verilator) is the final oracle. Gate-level sim catches sim-vs-synthesis mismatches that unit tests cannot.
**Delivers:** `tests/simulation/` suite; Yosys + iverilog CI step; `(* keep *)` pragmas on state registers; `SUPPORTED_CONSTRUCTS.md`; named error codes (SVA-E001, etc.).
**Addresses:** §1.3 synthesizable RTL guarantee
**Avoids:** P3.3 (sim-vs-synthesis mismatch), P3.5 (vacuity not tested), P8.5 (non-idiomatic RTL)

### Phase 7: V2 — Local Variables + Multi-Clock + Coverage

**Rationale:** These features require architectural extensions (capture registers latched at FSM transition points; per-sequence clock annotation) that are cleanest to add after the single-clock core is stable and validated.
**Delivers:** Local variable capture registers; multi-clock implication with CDC-safe sampling warnings; `cover property` → `cover_hit` output; UVM-compatible coverage event output.
**Addresses:** §2.4, §2.5, §2.6

---

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** The token-passing interface contract (`start`/`active`/`pass`/`fail`) must be validated with simple templates before building the Composer — cheaper to find interface bugs on `bool_expr` than after writing all composition logic.
- **Phase 3 before Phase 4:** Optimizer requires a complete operator set; partial optimization of an incomplete tree produces misleading area estimates and golden mismatches.
- **Phase 5 after Phase 4:** Tier 2 operators like `intersect` produce large `CheckerNode` trees; the optimizer must be working before these are useful in practice.
- **Phase 6 late:** Simulation infrastructure requires Icarus/Verilator in CI, which adds environment complexity; doing it after the core is correct avoids simulator noise masking real IR bugs.
- **Phase 7 deferred:** Local variables require per-FSM-state register labeling that touches the entire Composer/template contract; the cleanest addition path is after single-clock is production-stable.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2:** Bit-vector width calculation for multi-thread implication — needs exact formula validated against LRM examples
- **Phase 3:** `disable iff` async semantics — async clear vs. synchronous reset behavior differs between synthesis tools; needs vendor validation
- **Phase 5:** `intersect` synchronized product NFA state budget — M×N blowup threshold needs empirical tuning
- **Phase 7:** Local variable capture — no open-source reference implementation found; will need LRM §16.11 deep-dive

Phases with standard patterns (skip research-phase):
- **Phase 1:** Frozen dataclass IR + slang JSON parsing — well-documented, established pattern
- **Phase 4:** Optimizer passes — standard compiler optimization literature (constant folding, CSE) applies directly
- **Phase 6:** pytest + Icarus/Verilator CI integration — well-documented toolchain

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All libraries verified on PyPI/GitHub with current releases; slang v11.0 confirmed May 2026 |
| Features | HIGH | Grounded in IEEE 1800-2017 LRM and existing SVA→RTL academic literature |
| Architecture | HIGH | Token-passing design validated by TIMA Lab patents (US10726182B2, US7810056B2) |
| Pitfalls | HIGH | Derived from LRM semantics, hardware synthesis rules, and known failure modes in existing tools |

**Overall confidence:** HIGH

### Gaps to Address

- **slang JSON schema completeness:** All SVA node `kind` strings need enumeration before writing `ast_importer.py`. Mitigate by writing a slang node-kind inventory script against real SVA test files in Phase 1.
- **`disable iff` synthesis portability:** Async clear behavior differs across FPGA vs. ASIC synthesis. Mitigate by offering both synchronous and asynchronous reset modes via template parameter, validated in Phase 6 against Yosys.
- **Local variable semantics edge cases:** IEEE 1800-2017 §16.11 has ambiguous wording on multi-match scenarios. Mitigate by deferring to Phase 7 and using SystemVerilog simulation as the oracle.
- **automata-lib performance ceiling:** For Tier 2 operators with large NFAs, automata-lib may be too slow. Mitigate by the token-passing architectural choice (DFA conversion only for NFAs ≤ 8 states); replace with a custom implementation if profiling shows a bottleneck.

---

## Sources

### Primary (HIGH confidence)
- **MikePopoloski/slang** (GitHub + PyPI `pyslang 9.1.0`) — SVA/SV parsing, `--ast-json` schema, v11.0 release notes
- **IEEE 1800-2017 LRM** — SVA operator semantics (§16), sequence and property definitions
- **Patent US10726182B2** (TIMA Lab) — token-passing checker composition architecture
- **Patent US7810056B2** — SVA normalization rewrite rules
- **caleb531/automata** (GitHub, v9.0.0) — NFA/DFA API, `NFA.to_dfa()`, `DFA.minify()`
- **astral-sh/ruff** — ruff 0.15.x release notes confirming Black/Flake8/isort replacement

### Secondary (MEDIUM confidence)
- **sahadipayan/SVA_to_RTL** (GitHub) — existing open-source reference for operator coverage and test patterns
- **SymbiYosys docs** — scope boundary: formal verification vs. runtime monitoring
- **Design-Reuse.com synthesizable assertion article** — synthesizable RTL output conventions

### Tertiary (LOW confidence)
- **networkx 3.6.1 changelog** — graph algorithm applicability to DFA state graphs (inferred, not benchmarked)
- **Community consensus on click vs. typer** — click recommended for compiler CLI weight; needs validation if command surface grows significantly

---
*Research completed: 2026-05-25*
*Ready for roadmap: yes*
