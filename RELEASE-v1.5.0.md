# sva2rtl v1.5.0 Release Notes

**Release date:** 2026-07-01
**Type:** Quality release — RISK-02 closure + honesty-boundary rejection

v1.5.0 delivers two focused improvements to the composed sequence operators
(`intersect`, `within`, `throughout`): (1) fixes **RISK-02**, closing the
long-standing value-level oracle gap that let `a intersect b` /
`a within b` pass vacuously for boolean operands; (2) closes the
**silent-wrong multi-cycle composition** path, where sequences like
`(a ##2 b) intersect (c[*3])` previously compiled to a monitor whose
IEEE-correct answer only appeared by accident. The full NFA composition
engine (nested composition, multi-cycle implication consequent, sby BMC
per-operator proofs) is now scheduled as v1.5.1.

## Summary

| Area | Change |
|------|--------|
| Version | Bumped `1.4.1` → `1.5.0` |
| RISK-02 | 2 strict xfails flipped to real green pass; RTL was already correct, oracle now aligned |
| Honesty boundary | Multi-cycle operands to `intersect` / `within` / `throughout` rejected at compile time with actionable message |
| Oracle helper | `_eval_bool_leaf(cond_node, signals)` — RISK-01-independent boolean-atom evaluator |
| Composer helper | `_reject_non_boolean_composition(op_name, positions, source_loc)` — silent-wrong path shield |
| Spike infrastructure | `tools/audit/probe_nfa_ast.py`, `tools/audit/probe_nfa_prototype.py`, `.gsd/milestones/v1.5/spike-notes.md` — NFA product-construction algorithm + Python prototype validated on 4 hand-derived vectors |
| Tests | 1005 passed (was 982) / 4 skipped / **2 xfailed** (was 4) / 0 failed |
| Ruff | 0 errors repo-wide |
| Goldens | 62 single-clock goldens — version-line bump only, otherwise byte-identical |

## What v1.5.0 fixes

### RISK-02 — vacuous intersect / within pass for boolean operands

**Symptom (pre-v1.5):** The behavioral oracle modelled every `bool_expr`
leaf as a `delay_fixed(0,0)` that always passes when started, so composed
operators like `a intersect b` reported `pass = left_pass & right_pass = 1
& 1 = 1` regardless of the actual values of `a` and `b`. The v1.3.1 team
recorded this honestly as two `pytest.mark.xfail(strict=True)` baseline
tests rather than hide it.

**Fix.** New helper `_eval_bool_leaf(cond_node, signals) -> bool` in
`behavioral_oracle.py` — hand-authored from IEEE 1800 §16.9.7 / §16.9.10
semantics for single-cycle boolean sequences (AND across `observed_signals`).
The `_tick_prop_intersect` and `_tick_prop_within` pass outputs are now
gated by `_eval_bool_leaf` on their two operands. Non-`bool_expr` children
see `_eval_bool_leaf → True` conservatively; the compile-time rejection
below prevents those from arising in practice.

**Impact.**
- `test_intersect_baseline_both_true` and `test_within_baseline_inner_inside_outer`
  in `tests/test_v13_independent_baseline.py` — the `@pytest.mark.xfail`
  decorators are gone and both tests now PASS (real green, not xpass).
- Eight new exhaustive gate tests in `tests/test_v15_risk02_gate.py`:
  `intersect` full TT/TF/FT/FF truth table + four `within` shape variants
  (inner+outer / inner-only / outer-only / neither) — all hand-derived
  from IEEE-1800 per RISK-01, all pass.
- RTL was **already correct** for boolean operands (`bool_expr.sv.j2`
  registers `pass_q <= start & bool_result`), so no template touches
  and no golden diffs beyond the version-line bump.

### Silent-wrong multi-cycle composition — closed at compile time

**Symptom (pre-v1.5):** `(a ##2 b) intersect (c[*3])` compiled to
`prop_intersect(seq_concat, rep_consecutive)` and emitted RTL whose
`_body_pass = left_pass & right_pass` fires only when the two
sub-sequences happen to complete on the same cycle. IEEE 1800 §16.9.7
requires "same start AND same completion cycle" tracking across all
matching threads — the token-passing composition cannot express that.
Users could unknowingly ship a wrong monitor.

**Fix.** New guard `_reject_non_boolean_composition(op_name, positions,
source_loc)` in `composer.py`. Every operand of `_compose_intersect`,
`_compose_within`, `_compose_throughout` is now checked against
`_is_boolean_leaf` (`isinstance(operand, BoolExpr)`). Any non-boolean
operand raises `UnsupportedConstruct` naming the offending position and
IR type, pointing at the v1.5.1 NFA engine, and describing the
split-property workaround.

**Impact.**
- 13 rejection tests in `tests/test_v15_g2a_reject.py`:
  - intersect × 3 (seq-concat-left, repetition-right, both-multi-cycle)
  - within × 2 (seq-concat-inner, repetition-outer)
  - throughout × 1 (multi-cycle body)
  - nested × 2 (`(a intersect b) within c`, `(a intersect b) intersect c`)
  - misc shapes × 3 (SeqOr, SeqGotoRep, SeqNonconsecRep as operands)
  - error-quality × 2 (workaround hint present, source_loc threaded
    per pitfall P5.1)
- All 992 pre-v1.5 tests continue to pass. Zero regression on the
  boolean-operand path.

## v1.5.1 preview — full NFA composition engine

v1.5.0 deliberately stops after the honesty layer. The remaining v1.5
milestones become **v1.5.1**:

- `templates/nfa_generic.sv.j2` — parametric one-hot NFA template
  (K state count, TRANSITIONS matrix, ACCEPT mask, NFA_KIND selector,
  THREAD_SLOTS reserved for G3), registered `pass_q`/`fail_q` outputs,
  `yosys check -assert` clean.
- `NfaCompose` IR node (`states`, `transitions`,
  `accept: frozenset[int]`, `nfa_kind: Literal["sequence", "property"]`,
  `observed_signals`, `source_loc`).
- Composer NFA branches: `_compose_intersect_nfa` /
  `_compose_within_nfa` / `_compose_throughout_nfa` with product
  construction bottom-up (nested lowering).
- Behavioral oracle rule-based thread simulator `_tick_nfa_generic`.
- Three independent IEEE-1800 reference monitors in `formal_equiv.py`.
- 12 sby BMC non-circular miters (4 per operator) — noted risk:
  YosysHQ AppNote-109 flags intersect/within/throughout as
  not-FPV-friendly; convergence at 10-cycle horizon TBD in v1.5.1
  spike, with a fallback to iverilog-only cross-check documented.
- Multi-cycle implication consequent unlock
  (`a |-> b ##N c`, `a |-> b[*N]`, `a |-> (b ##[M:N] c)`) — removes
  `composer.py` `bv_width > 1` hard-reject.
- Five nested composition end-to-end cases (NFA-07).
- Compile-time K ≤ 32 state budget enforcement (D3).

The v1.5.0 honesty boundary is the necessary precondition for v1.5.1:
users can no longer inadvertently rely on the silent-wrong path while
the NFA engine is in flight.

## Technical highlights

- **Zero RTL template changes:** goldens are byte-identical modulo the
  single-line `sva2rtl 1.4.1` → `sva2rtl 1.5.0` version bump. All 62
  goldens verified via `test_golden_parity`.
- **Boundary discipline maintained:** each of the three commits touched
  only its scoped file set:
  - `d0c8732 (G0)` — `tools/audit/probe_nfa_*.py`, `uv.lock`
  - `1194818 (G1)` — `behavioral_oracle.py`,
    `test_v13_independent_baseline.py`, `test_v15_risk02_gate.py`
  - `d8b1957 (G2a)` — `composer.py`, `test_v15_g2a_reject.py`
- **G0 spike infrastructure retained:** the Python NFA prototype
  (`tools/audit/probe_nfa_prototype.py`) validates the product
  construction algorithm on 4 hand-derived vectors, with max
  K = 16 across all NFA-07 target patterns (well within the K ≤ 32
  budget). The spike-notes document is the north star for v1.5.1.
- **Execute-time replans documented:** two `STEER` decisions recorded
  in `.gsd/milestones/v1.5/v1.5-ROADMAP.md`:
  1. G1 light-path (skip full NfaCompose IR bridge, do direct
     `_eval_bool_leaf` gate — saves ~300 LOC of transient scaffolding)
  2. G2 split into G2a (this release) + G2b (v1.5.1)

## Suite delta

| Metric | v1.4.1 | v1.5.0 | Delta |
|--------|--------|--------|-------|
| passed | 982 | 1005 | +23 |
| skipped | 4 | 4 | 0 |
| xfailed | 4 | 2 | **-2 (RISK-02 flipped)** |
| ruff errors | 0 | 0 | 0 |
| golden files | 62 | 62 | 0 (version-line only) |

## Commits (v1.5.0 = 4a181bd..d8b1957 minus v1.4.2 patch)

- `d0c8732` — `chore(v1.5): NFA spike + Python prototype (G0)`
- `1194818` — `feat(v1.5): RISK-02 xfail flip via boolean-leaf operand truth (G1)`
- `d8b1957` — `feat(v1.5): honesty-boundary rejection for multi-cycle intersect/within/throughout (G2a)`
- **(this release closeout)** — `release(v1.5.0): RISK-02 closure + honesty boundary + version bump`
