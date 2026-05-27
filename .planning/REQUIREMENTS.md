# Requirements: sva2rtl

**Defined:** 2026-05-25
**Core Value:** Turn any SVA property into a correct, area-efficient synthesizable hardware monitor

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Parsing & Frontend

- [x] **PARSE-01**: Tool invokes slang CLI with --ast-json and parses the resulting JSON into internal SVA IR ✅ Phase 1
- [x] **PARSE-02**: AST importer dispatches on all SVA-relevant slang node kinds (SequenceConcatExpr, ImplicationPropertyExpr, SequenceRepetitionExpr, etc.) ✅ Phase 1
- [x] **PARSE-03**: Named sequence and property declarations are resolved and expanded inline ✅ Phase 3
- [x] **PARSE-04**: Clock event (@(posedge clk)) is extracted and threaded through the IR ✅ Phase 1
- [x] **PARSE-05**: Source location (file:line:col) is preserved from slang AST through the entire pipeline ✅ Phase 1

### Tier 1 SVA Operators

- [x] **OP-01**: Fixed delay `##N` compiles to shift register or counter template ✅ Phase 2
- [x] **OP-02**: Range delay `##[M:N]` compiles to counter with window comparator (counter encoding, not state expansion) ✅ Phase 2
- [x] **OP-03**: Overlapping implication `|->` handles multiple simultaneous threads via bit-vector method ✅ Phase 2
- [x] **OP-04**: Non-overlapping implication `|=>` starts consequent one cycle after antecedent match ✅ Phase 2
- [x] **OP-05**: Consecutive repetition `[*N]` and `[*M:N]` compile to counted FSM ✅ Phase 3
- [x] **OP-06**: `$rose(sig)` compiles to edge-detect flip-flop (1 FF + AND-NOT) ✅ Phase 3
- [x] **OP-07**: `$fell(sig)` compiles to edge-detect flip-flop (1 FF + AND) ✅ Phase 3
- [x] **OP-08**: `$stable(sig)` compiles to 1 FF + XNOR comparator ✅ Phase 3
- [x] **OP-09**: `$past(sig, N)` compiles to N-stage shift register pipeline ✅ Phase 3
- [x] **OP-10**: `disable iff (expr)` generates asynchronous combinational gate on all monitor state and outputs ✅ Phase 3

### RTL Output

- [x] **OUT-01**: Generated SystemVerilog monitor module with standard interface: clk, rst_n, start, pass, fail, active ✅ Phase 1
- [x] **OUT-02**: All monitor outputs are registered (no combinational glitches on pass/fail) ✅ Phase 1
- [x] **OUT-03**: Every flip-flop has synchronous reset to idle state ✅ Phase 1
- [x] **OUT-04**: bind statement file generated for non-invasive DUT attachment ✅ Phase 3
- [ ] **OUT-05**: `--verilog` flag emits Verilog-2001 compatible output (wire/reg, always @(posedge))
- [x] **OUT-06**: Debug outputs: `attempt_fired` (antecedent triggered at least once), `overflow_flag` (pending threads exceeded capacity) ✅ Phase 2
- [x] **OUT-07**: Generated module names derived from property label (not generic monitor_0/1/2) ✅ Phase 1
- [x] **OUT-08**: Original SVA property text emitted as comment at top of generated module ✅ Phase 1

### Internal Pipeline

- [ ] **PIPE-01**: IR normalization pass rewrites exotic forms to canonical primitives (|=> to ##1 |->; flatten chains; range canonicalization)
- [ ] **PIPE-02**: Composition engine walks normalized IR and builds CheckerNode tree with token-passing signal wiring
- [ ] **PIPE-03**: CSE optimization: structural hash on CheckerNode, identical subtrees share hardware instances
- [ ] **PIPE-04**: Counter merging: range counters with same parameters share single counter module
- [ ] **PIPE-05**: Dead-state elimination: prune unreachable nodes from CheckerNode tree

### CLI & Developer Experience

- [ ] **CLI-01**: Single entry point `sva2rtl <input.sv>` with --output, --property, --verilog, --slang-path flags
- [ ] **CLI-02**: `--dump-ast` prints slang JSON AST and exits
- [ ] **CLI-03**: `--dump-ir` prints normalized SVA IR tree and exits
- [ ] **CLI-04**: `--dump-tree` prints CheckerNode tree and exits
- [x] **CLI-05**: Exit code 0 (success), 1 (compile error), 2 (unsupported construct), 3 (slang not found) ✅ Phase 1
- [x] **CLI-06**: Unsupported constructs produce clear named error with suggestion (never silent miscompile) ✅ Phase 1

### Quality & Testing

- [x] **TEST-01**: Unit tests per module (ir, ast_importer, normalizer, composer, optimizer, emitter) ✅ Phase 1
- [x] **TEST-02**: Golden file integration tests: input.sv + expected.sv pairs for each supported operator ✅ Phase 2
- [x] **TEST-03**: Simulation validation: generated monitors pass Verilator/Icarus compile and behavioral tests ✅ Phase 3
- [x] **TEST-04**: End-to-end oracle tests: SVA property -> generated monitor -> simulate with stimulus -> compare pass/fail against behavioral SVA assertion ✅ Phase 3
- [x] **TEST-05**: Concurrent-attempt stress tests: antecedent fires every cycle for 2x consequent length ✅ Phase 2
- [x] **TEST-06**: Boundary tests for every bounded operator: test at N-1, N, M, M+1 cycle boundaries ✅ Phase 2

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Tier 2 Operators

- **OP-11**: `throughout` — condition holds every tick during sequence evaluation
- **OP-12**: `first_match` — FSM termination on first accepting path
- **OP-13**: Sequence `and` / `or` — parallel FSM with join/select logic
- **OP-14**: Go-to repetition `[->N]` — non-consecutive counted match
- **OP-15**: Non-consecutive repetition `[=N]` — count occurrences without requiring adjacency
- **OP-16**: `intersect` — parallel FSM with synchronized start AND end
- **OP-17**: `within` — bounded containment checker

### Advanced Features

- **ADV-01**: Multi-clock domain support (per-sequence clock annotation)
- **ADV-02**: Local variables in sequences (register capture at FSM transition)
- **ADV-03**: Coverage instrumentation (cover property -> cover_hit output)
- **ADV-04**: Area/timing estimation report (FF count, LUT depth per assertion)
- **ADV-05**: FSM Graphviz visualization (--dump-fsm dot)
- **ADV-06**: Formal equivalence checking hook (SymbiYosys .sby config)
- **ADV-07**: Library/programmatic API (Python import, not just CLI)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Custom SystemVerilog parser | slang v11.0 handles this perfectly; writing parser is 12-24 months wasted |
| Formal verification engine | Use SymbiYosys/JasperGold; this tool generates monitors, not proofs |
| GUI / Visual property editor | Terminal-first; target users are CLI engineers |
| PSL (IEEE 1850) support | Different standard, different parser; SVA covers target audience |
| LLM-assisted SVA generation | Orthogonal product; this tool is a great TARGET for LLM output |
| Simulation-only constructs ($display, $fatal, dynamic delays) | Detect and reject; not synthesizable |
| Unbounded repetition [*] / [$] | No finite hardware representation; reject with error |
| Strong/liveness properties (s_eventually) | Requires simulation-end signal; safety-only for v1 |
| Approximate/sampling monitoring | Exact formal semantics is the value proposition |
| EDA vendor plugin wrappers | Users use this alongside vendors, not as plugin |

## Traceability

| Requirement | Phase | Phase Name | Status |
|-------------|-------|------------|--------|
| PARSE-01 | Phase 1 | Foundation | Pending |
| PARSE-02 | Phase 1 | Foundation | Pending |
| PARSE-03 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| PARSE-04 | Phase 1 | Foundation | Pending |
| PARSE-05 | Phase 1 | Foundation | Pending |
| OP-01 | Phase 2 | Core Sequential Operators | Pending |
| OP-02 | Phase 2 | Core Sequential Operators | Pending |
| OP-03 | Phase 2 | Core Sequential Operators | Pending |
| OP-04 | Phase 2 | Core Sequential Operators | Pending |
| OP-05 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| OP-06 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| OP-07 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| OP-08 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| OP-09 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| OP-10 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| OUT-01 | Phase 1 | Foundation | Pending |
| OUT-02 | Phase 1 | Foundation | Pending |
| OUT-03 | Phase 1 | Foundation | Pending |
| OUT-04 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| OUT-05 | Phase 6 | CLI Polish + Verilog-2001 | Pending |
| OUT-06 | Phase 2 | Core Sequential Operators | Pending |
| OUT-07 | Phase 1 | Foundation | Pending |
| OUT-08 | Phase 1 | Foundation | Pending |
| PIPE-01 | Phase 4 | Normalization + Composition Engine | Pending |
| PIPE-02 | Phase 4 | Normalization + Composition Engine | Pending |
| PIPE-03 | Phase 5 | Optimization Passes | Pending |
| PIPE-04 | Phase 5 | Optimization Passes | Pending |
| PIPE-05 | Phase 5 | Optimization Passes | Pending |
| CLI-01 | Phase 6 | CLI Polish + Verilog-2001 | Pending |
| CLI-02 | Phase 6 | CLI Polish + Verilog-2001 | Pending |
| CLI-03 | Phase 6 | CLI Polish + Verilog-2001 | Pending |
| CLI-04 | Phase 6 | CLI Polish + Verilog-2001 | Pending |
| CLI-05 | Phase 1 | Foundation | Pending |
| CLI-06 | Phase 1 | Foundation | Pending |
| TEST-01 | Phase 1 | Foundation | Pending |
| TEST-02 | Phase 2 | Core Sequential Operators | Pending |
| TEST-03 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| TEST-04 | Phase 3 | Remaining Tier 1 + Sim Validation | Pending |
| TEST-05 | Phase 2 | Core Sequential Operators | Pending |
| TEST-06 | Phase 2 | Core Sequential Operators | Pending |

**Coverage:**
- v1 requirements: 40 total
- Mapped to phases: 40
- Unmapped: 0 ✓

**Requirements per phase:**
- Phase 1 (Foundation): 12 — PARSE-01/02/04/05, OUT-01/02/03/07/08, CLI-05/06, TEST-01
- Phase 2 (Core Sequential Operators): 8 — OP-01/02/03/04, OUT-06, TEST-02/05/06
- Phase 3 (Remaining Tier 1 + Sim Validation): 10 — OP-05–10, PARSE-03, OUT-04, TEST-03/04
- Phase 4 (Normalization + Composition Engine): 2 — PIPE-01/02
- Phase 5 (Optimization Passes): 3 — PIPE-03/04/05
- Phase 6 (CLI Polish + Verilog-2001): 5 — CLI-01/02/03/04, OUT-05

---
*Requirements defined: 2026-05-25*
*Last updated: 2026-05-25 — traceability updated after roadmap creation (phase assignments revised: PARSE-03→Ph3, OP-05–10→Ph3, OUT-01–03/07/08→Ph1, OUT-06→Ph2, OUT-05→Ph6, CLI-05/06→Ph1, TEST-02/05/06→Ph2; count corrected to 40)*
