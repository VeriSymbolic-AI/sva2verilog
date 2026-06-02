# Plan 02 Execution Summary — Implication Operators (|-> and |=>)

**Phase:** 02-core-sequential-operators-n-m-n  
**Plan:** 02 — Implication operators `|->` and `|=>`  
**Status:** COMPLETE  
**Commits:** ad87b90, c334f80, 4b622b2, db1f67e, 4fdec23, b92d997

---

## What Was Built

Implemented full end-to-end support for SVA implication operators (`|->` and `|=>`),
from JSON AST parsing through IR construction, Jinja2 template emission, and test coverage.

### Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 2.2.1 | `ast_importer.py` — parse `OverlappedImplication` and `NonOverlappedImplication` into `PropImplication` IR node | `ad87b90` |
| 2.2.2 | `templates/overlap_bitvec.sv.j2` — shift-register bit-vector template for `\|->` | `c334f80` |
| 2.2.3 | `templates/nonoverlap.sv.j2` — dedicated template for `\|=>` with `ant_pass_delayed_q` | `4b622b2` |
| 2.2.4 | `composer.py` — `_compose_implication()` with formal BV_WIDTH algorithm, children composition | `db1f67e` |
| 2.2.5 | Golden files for all three implication fixtures (overlap, nonoverlap, bitvec) generated via pipeline | `4fdec23` |
| 2.2.6 | Unit tests for import/compose/emit stages; fix stale `test_compose_unsupported_type_raises` | `b92d997` |

---

## Architecture Decisions

### BV_WIDTH Algorithm
`bv_width = max(sum_of_consequent_delay_max_values + 1, 1)`

- `BoolExpr` consequent → `bv_width = 1` (single-cycle check)
- `SeqConcat` consequent with `delays=((2,5),)` → `bv_width = 6` (max=5, +1)
- `SeqConcat` with `delays=((2,2),(3,3))` → `bv_width = 6` (max=2+3=5, +1)

Rationale: the bit-vector must hold one bit per possible thread age, from age 0 (just
started) to age `max_delay` (longest possible completion cycle). Width = max_delay + 1.

### Hard-Halt Overflow Semantics
When `bv_q[BV_WIDTH-1]` is set and a new token would be inserted, `overflow_flag` latches HIGH.
On overflow: `active`, `pass`, `fail` all gate to `1'b0`; `bv_q` freezes. Only `!rst_n` clears.
This prevents false positives/negatives from unbounded thread accumulation.

### Non-Overlapping (`|=>`) Register
`nonoverlap.sv.j2` inserts new antecedent-pass tokens with a 1-cycle delay using a dedicated
`ant_pass_delayed_q` register, implementing the `|=>` one-step shift before consequent matching.

### Module Naming
Antecedent and consequent sub-checkers use `label=None` with different `original_text` values
extracted from their respective IR nodes to ensure distinct SHA-256 module names. The top-level
implication wrapper uses the assertion label when provided.

---

## Test Coverage Added

- **`test_ast_importer.py`**: 12 new tests covering `PropImplication` round-trip parsing for
  overlap, non-overlap, and bitvec fixtures; antecedent/consequent text and type assertions
- **`test_composer.py`**: 14 new tests including BV_WIDTH computation for 3 cases, template
  selection, child structure; fixed stale `test_compose_unsupported_type_raises` (now uses
  a locally-defined `_UnknownNode` stub instead of `PropImplication`)
- **`test_emitter.py`**: 11 spot-check tests + 3 parametrized golden-match tests

**Final test count: 200 passed, 5 skipped** (5 skips are intentional hypothesis-related skips).

---

## Files Created / Modified

```
src/sva2rtl/ast_importer.py        — PropImplication parsing (2.2.1)
templates/overlap_bitvec.sv.j2     — |-> BV template (2.2.2)
templates/nonoverlap.sv.j2         — |=> template (2.2.3)
src/sva2rtl/composer.py            — _compose_implication() (2.2.4)
tests/fixtures/implication_overlap.json     — |-> a b fixture (2.2.5)
tests/fixtures/implication_nonoverlap.json  — |=> a b fixture (2.2.5)
tests/fixtures/implication_bitvec.json      — |-> a ##[2:5] b fixture (2.2.5)
tests/golden/overlap_impl.sv       — generated golden (2.2.5)
tests/golden/nonoverlap_impl.sv    — generated golden (2.2.5)
tests/golden/sva_bitvec_impl.sv    — generated golden (2.2.5)
tests/test_ast_importer.py         — new PropImplication tests (2.2.6)
tests/test_composer.py             — new tests + stale test fix (2.2.6)
tests/test_emitter.py              — new tests + golden match (2.2.6)
```
