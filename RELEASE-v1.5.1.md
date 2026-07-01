# Release v1.5.1 — NFA Composition Engine

## Summary

v1.5.1 ships the NFA composition engine, closing all v1.5 risk items
(RISK-02, BUG-IMPL-01, silent-wrong multi-cycle composition). The engine
uses one-hot state encoding, product construction (Boule & Zilic MBAC),
and multi-thread slot allocation to compose SVA sequence operators for
intersect, within, throughout, and multi-cycle implication consequents.

## New Features (v1.5.1 vs v1.5.0)

### Multi-cycle operand support (P1)
- `intersect` / `within` / `throughout` now accept `SeqConcat` (fixed
  delays) and `SeqRepetition` (fixed count) operands.
  Example: `(a ##2 b) intersect (c[*3])`, `a within (c[*3])`,
  `en throughout (a ##2 b)`.
- Total NFA states K x T ≤ 32 (compile-time enforced).

### Multi-cycle implication consequent (P2)
- `|->` and `|=>` with multi-cycle consequents:
  `a |-> b ##2 c`, `a |-> b[*3]`, `a |-> b ##1 c ##2 d`.
- Antecedent evaluated combinationally (no registered pipeline misalignment).
- Multi-thread (T ≤ 4) handles overlapping ant matches.
- Closes BUG-IMPL-01 (confirmed correctness defect in legacy bv_q path).

### Nested composition (P3)
- Recursive NFA lifting: inner intersect/within/throughout compose first,
  then feed into parent product construction.
  Example: `(a intersect b) within c`, `(a intersect b) intersect c`,
  `en throughout (a intersect b)`.

## Verification

| Layer | Count | Operators |
|-------|-------|-----------|
| Unit (oracle) | 38 | intersect / within / throughout / implication |
| iverilog dual-oracle sim | 18 | all 4 operators |
| sby BMC miters (non-circular) | 24 | all 4 operators, independent shift-register references |
| K budget boundary tests | 4 | K ≤ 32 enforcement |

Total suite: **1073 passed, 4 skipped, 2 xfailed, 0 failed**.

## Architecture

- **nfa_generic.sv.j2**: one-hot state NFA, single and multi-thread modes
- **implication_nfa.sv.j2**: wrapper template for implication with NFA consequent
- **composer.py**: product construction (intersect/within/throughout), recursive
  NFA lifting, serialise/deserialise for nested composition
- **behavioral_oracle.py**: rule-based thread simulator (RISK-01 independent)
- **formal_equiv.py**: miter harness for sby BMC proofs

## Breaking Changes

None from v1.5.0. The single-cycle implication path (`overlap_bitvec`/
`nonoverlap` templates), single-cycle intersect/within/throughout
(`prop_*` templates), and all boolean golden outputs remain byte-identical.

## Dependencies

- Python 3.11+
- slang v11 (AST parsing)
- Jinja2 (template rendering)
- iverilog (simulation)
- SymbiYosys + yices (formal verification)

## Commit List

- `a0fad01` NFA engine base + multi-cycle intersect
- `aa7e380` multi-cycle within + throughout via NFA
- `267f12b` 12 dual-oracle iverilog sim tests
- `60621ae` 12 sby BMC miters for NFA operators
- `a75cc3f` multi-cycle implication consequent via NFA
- P2 slice 2: 6 iverilog sim + 6 sby BMC for implication
- P3: nested composition + K budget + docs
