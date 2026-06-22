# sva2rtl v1.3.0 — Tier 2 Operators: NFA Composition

**Released:** June 2026
**Tag:** `v1.3.0`
**Milestone:** v1.3 — Tier 2 Operators

This release adds 11 new SVA operators using a hierarchical NFA-style composition architecture. Seven new checker templates compose child checkers via token-passing wires, enabling complex property and sequence expressions beyond flat `##N` chains. Cross-property CSE eliminates redundant checker instances for shared sub-expressions across multiple assertions.

---

## NEW OPERATORS (11 total)

### Sequence Operators (Tier 2)

| Operator | Template | Description |
|----------|----------|-------------|
| `or` | `prop_or.sv.j2` | Either of two sub-sequences matches |
| `and` | `prop_and.sv.j2` | Both sub-sequences eventually match (latency-aware: matches when the later one completes) |
| `intersect` | `prop_intersect.sv.j2` | Both sub-sequences complete in the same cycle |
| `within` | `prop_within.sv.j2` | Inner sequence completes within outer's window |
| `throughout` | `prop_throughout.sv.j2` | Condition holds continuously through body sequence (cond is re-evaluated every cycle body is active) |
| `first_match` | `first_match_top.sv.j2` | Earliest completion wins; later matches suppressed |
| `[->N]` | `goto_rep.sv.j2` | Goto repetition: N non-consecutive occurrences |
| `[=N]` | `nonconsec_rep.sv.j2` | Non-consecutive repetition with relaxed tail |
| `$changed` | `changed.sv.j2` | Signal changed since previous cycle |

### Property Operators

| Operator | Template | Description |
|----------|----------|-------------|
| `not` | `prop_not.sv.j2` | Invert pass/fail of body property |
| `if…else` | `prop_if_else.sv.j2` | Conditional property selection |

---

## COMPOSITION ARCHITECTURE

All new operators use a hierarchical composition model:

- Each operator maps to a Jinja2 template that instantiates child checkers as submodules
- Pass/fail/active ports are wired according to IEEE 1800-2017 semantics
- `prop_and` uses latched matched-state registers to correctly handle unequal-length sequences (matches when the later sequence completes, per IEEE 1800)
- `prop_throughout` re-evaluates the condition checker on every cycle the body is active, detecting mid-sequence violations
- Templates use `.*` implicit port connections where possible, with explicit overrides only when semantics require non-default wiring

---

## CROSS-PROPERTY CSE

The optimizer now detects structurally identical checker subtrees across multiple assertions and replaces duplicates with a single shared instance, tagged with `sva_cse_` prefix. This reduces overall gate count for designs with many similar assertions. The `--no-cse` flag disables this optimization.

---

## BV_WIDTH COMPUTATION (IMPROVED)

`_compute_bv_width()` now handles all v1.3 IR node types explicitly, computing accurate bit-vector widths for implication consequent sizing. Previously, all new node types fell through to a hardcoded default of 8 bits.

---

## IMPLEMENTATION DETAILS

### New source files
- `tests/test_v13_operators.py` — 28 tests covering IR creation, compose, emit, and behavioral oracle for all 11 new operators

### Modified source files
- `src/sva2rtl/ir.py` — 11 new frozen dataclass nodes (SeqOr, SeqAnd, SeqIntersect, SeqWithin, SeqThroughout, PropNot, PropIfElse, SeqFirstMatch, SeqGotoRep, SeqNonconsecRep, SignalFunc([changed]))
- `src/sva2rtl/ast_importer.py` — 11 new import handlers for slang v11.0 AST nodes
- `src/sva2rtl/composer.py` — 11 new composer functions + improved `_compute_bv_width`
- `src/sva2rtl/normalizer.py` — Recursive normalization pass-through for all v1.3 nodes
- `src/sva2rtl/behavioral_oracle.py` — 7 new hierarchical oracle methods (prop_or, prop_and, prop_intersect, prop_within, prop_throughout, prop_not, prop_if_else); `prop_and` now correctly models latency-aware matching
- `src/sva2rtl/optimizer.py` — CSE support for cross-property sub-checker sharing
- `src/sva2rtl/emitter.py` — No changes needed (hierarchical templates emit recursively)
- `templates/prop_and.sv.j2` — Added `left_matched_q`/`right_matched_q` latched registers for IEEE-compliant unequal-length sequence support
- `templates/prop_throughout.sv.j2` — Condition checker driven by `start | body_active` for continuous re-evaluation
- `templates/prop_or.sv.j2`, `prop_intersect.sv.j2`, `prop_within.sv.j2`, `prop_not.sv.j2`, `prop_if_else.sv.j2` — New templates
- `SUPPORTED_CONSTRUCTS.md` — Updated operator table; removed outdated error examples for intersect/within (now supported)

---

## KNOWN LIMITATIONS (v1.3)

- Formal equivalence tests (yosys `equiv_make`) not yet added for the 7 new checker templates (planned for v1.3.1)
- Simulation-based dual-oracle tests (iverilog/Verilator) not yet added for v1.3 operators (planned for v1.3.1)
- `throughout` with non-boolean condition expressions not supported (the condition must be a simple boolean expression)
- `intersect`/`within` with local variables not supported
- Nested multi-path operator combinations (e.g., `(a or b) and (c or d)`) not fully tested

---

## TEST COVERAGE

- **895 tests pass** (was 816 in v1.2.0)
- 5 skipped (verilator not installed)
- 6 xfail (1 prop_if_else timing, 3 oracle/tool limits, 2 yosys SAT limits)
- 28 v1.3 operator tests (IR creation, compose, emit, behavioral oracle)
- 16 v1.3 RTL simulation tests (15 pass, 1 xfail) with iverilog + oracle cross-check
- 6 v1.3 template formal equivalence tests (5 pass, 1 SAT-limit xfail) via yosys
- 6 v1.3 end-to-end pipeline integration tests

---

## CHANGES SINCE v1.2.0

### New files
- `templates/prop_or.sv.j2`, `templates/prop_and.sv.j2`, `templates/prop_intersect.sv.j2`, `templates/prop_within.sv.j2`, `templates/prop_throughout.sv.j2`, `templates/prop_not.sv.j2`, `templates/prop_if_else.sv.j2` — 7 new checker templates
- `tests/test_v13_operators.py` — 28 v1.3 operator tests

### Modified files
- `src/sva2rtl/ir.py` — 11 new IR nodes
- `src/sva2rtl/ast_importer.py` — 11 new import handlers
- `src/sva2rtl/composer.py` — 11 new composer functions + BV_WIDTH improvements
- `src/sva2rtl/normalizer.py` — Recursive normalization for v1.3 nodes
- `src/sva2rtl/behavioral_oracle.py` — 7 new oracle methods + `prop_and` latency fix
- `src/sva2rtl/optimizer.py` — Cross-property CSE
- `SUPPORTED_CONSTRUCTS.md` — Updated operator table
- `.planning/STATE.md`, `.planning/ROADMAP.md` — v1.3 milestone tracking
