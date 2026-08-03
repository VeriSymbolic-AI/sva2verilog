# Supported SVA Constructs — sva2rtl v1.7.1 current main

This file explains supported syntax, semantics, and generated template shapes.
Exact support status, subset boundaries, and verification evidence are governed
by [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md). Treat the tiers below as implemented
syntax groups, not as full-evidence claims.

## Formal Evidence Note

Phase 10 adds focused formal harness evidence for the existing language subset:
representative `arbitrary_start`, `arbitrary_disable`, `reset_recovery`,
full-contract, cover-probe, and k-induction slices are recorded in
`SUPPORT_MATRIX.md`. These are evidence-strength upgrades for named constructs
and modes, not a blanket claim that every supported operator has full-contract
or arbitrary-start proof coverage. Phase 11 adds local Yosys generated-RTL smoke
coverage and CI routing for generated-module Verilator lint. Verilator 5.028 is
installed locally and the generated strict-lint gate passes; same-commit remote
lint evidence remains pending until this worktree is pushed. Phase 12 adds
bounded source-level differential testing against an independent test-local
Python reference under both Icarus and Verilator, with slow randomized breadth
kept opt-in. Complex NFA/liveness proof expansion remains separate validation
work; mutation and coverage release metrics are tracked in
`INDUSTRIAL_VALIDATION_GAPS.md`.

## Tier 1 Operators (Implemented Core Subset)

| Operator | Category | Description | Example SVA | Generated Template |
|----------|----------|-------------|-------------|-------------------|
| `##N` | Delay | Fixed cycle delay | `a ##2 b` | Bounded counter/window |
| `##[M:N]` | Delay | Bounded delay range | `a ##[1:3] b` | Counter with [M,N] window comparator |
| <code>\|-></code> | Implication | Overlapping implication, including multi-cycle consequent | <code>req \|-> ack</code> | Antecedent match triggers consequent check |
| <code>\|=></code> | Implication | Non-overlapping implication, including multi-cycle consequent | <code>req \|=> ack</code> | Antecedent match triggers consequent check (next cycle) |

> **v1.5.1 (P2).** Multi-cycle sequence consequents (e.g. `a |-> b ##2 c`,
> `a |-> b[*3]`, `a |-> b ##1 c ##2 d`) are now supported via the NFA
> composition engine. The antecedent is evaluated combinationally and gates the
> consequent NFA start. Multi-thread slots (T ≤ 4) handle overlapping ant matches.
> Single-cycle consequents continue to use the formally-proven overlap_bitvec/
> nonoverlap path (byte-identical to v1.5.0). Ranged delays in the consequent
> (`a |-> b ##[2:5] c`) are now supported via NFA engine (v1.7 LANG-03)
> property.
| `[*N]` | Repetition | Exact consecutive repetition | `a[*3]` | Counter counts N consecutive matches |
| `[*M:N]` | Repetition | Bounded consecutive repetition | `a[*1:4]` | Counter with [M,N] range check |
| `$rose()` | Sampled value | Rising edge (0-to-1 transition) | `$rose(sig)` | Edge detector: `sig & ~sig_prev` |
| `$fell()` | Sampled value | Falling edge (1-to-0 transition) | `$fell(sig)` | Edge detector: `~sig & sig_prev` |
| `$stable()` | Sampled value | No value change | `$stable(sig)` | Comparator: `sig == sig_prev` |
| `$past(sig, N)` | Sampled value | Value N cycles ago | `$past(data, 2)` | Shift register delay line (N stages) |
| `$changed()` | Sampled value | Signal changed since previous cycle | `$changed(sig)` | Comparator: `sig != sig_prev` |
| `disable iff` | Control | Disable condition sampled by the generated synchronous monitor | `disable iff (rst) prop` | Output gating plus synchronous state clear |
| Named sequences | Structure | Reusable sequence definitions | `sequence s; a ##1 b; endsequence` | Submodule instantiation |

## Tier 2 Operators (v1.3 + v1.5.1 — Implemented Complex Subset)

| Operator | Category | Description | Example SVA | Generated Template |
|----------|----------|-------------|-------------|-------------------|
| `[->N]` | Repetition | Goto repetition (N non-consecutive occurrences); one start pulse arms the full attempt | `a[->3]` | Armed counter with liveness tracking, locking pass register |
| `[=N]` | Repetition | Non-consecutive repetition (relaxed tail); one start pulse arms the full attempt | `a[=2]` | Armed counter with relaxed completion check |
| `first_match` | Sequence | Earliest completion wins | `first_match(a ##[1:3] b)` | Wrapper with locked_q to suppress later matches |
| `and` | Sequence | Both sequences match (same start) | `s1 and s2` | AND of two sub-checker pass signals |
| `or` | Sequence | Either sequence matches | `s1 or s2` | OR of two sub-checker pass signals |
| `intersect` | Sequence | Both sequences complete simultaneously | `s1 intersect s2` | AND of pass signals with active intersection |
| `within` | Sequence | Inner sequence within outer's window | `s1 within s2` | Inner pass AND outer active check |
| `throughout` | Sequence | Condition holds throughout sequence | `en throughout s1` | Fail if condition fails while body active |
| `not` | Property | Invert pass/fail | `not (prop)` | Swap pass and fail outputs |
| `if...else` | Property | Conditional property selection | `if (cond) p1 else p2` | MUX between true/false branch checkers |

## Tier 3 Operators (v1.4 Part A — Bounded Liveness)

Bounded-liveness operators carry an explicit cycle window `[m:n]`, which gives
the pass/fail monitor a hard deadline and a finite resource budget. Unbounded
forms have no finite PASS deadline and are therefore rejected by the monitor
composer. Selected unbounded shapes are nevertheless imported into formal-only
IR and handled by `sva2rtl-formal`; they never enter RTL-monitor composition.

| Operator | Category | Description | Example SVA | Generated Template |
|----------|----------|-------------|-------------|-------------------|
| `s_eventually [m:n]` | Liveness | Boolean operand must hold at some offset `k ∈ [m,n]` from start; PASS at first in-window hit, FAIL at deadline `n` if never satisfied | `s_eventually [1:3] a` | `s_eventually` — offset counter + satisfied latch + deadline-fail (pass@start+k*+1, fail@start+n+1) |
| `eventually [m:n]` | Liveness | Weak bounded form; collapses to the same synthesizable monitor as the strong form over a finite window | `eventually [0:4] a` | `s_eventually` (shared) |
| `always [m:n]` | Liveness | Universal dual: boolean operand must hold at EVERY offset `k ∈ [m,n]`; FAIL at first in-window violation, PASS at deadline `n` if all held | `always [1:3] a` | `s_always` — offset counter + violation latch + deadline-pass (fail@start+k_viol+1, pass@start+n+1) |
| `s_always [m:n]` | Liveness | Strong bounded form; collapses to the same synthesizable monitor as the weak form over a finite window | `s_always [0:4] a` | `s_always` (shared) |
| `until` | Safety | Weak until: `a` holds until `b`; PASS when `b` first holds, FAIL when `a` drops before `b` (`b` not required to ever hold) | `a until b` | `until` — safety FSM (no counter); pass@b, fail@(~a & ~b) |
| `until_with` | Safety | Weak until-with: `a` must also hold at the `b` cycle; PASS when `a & b`, FAIL when `a` drops | `a until_with b` | `until` (with_ flag) |

Notes for v1.4 Part A:
- The operand must reduce to a **boolean expression** (like `throughout`'s
  condition). Sequence/property operands are rejected (deferred to the v1.5 NFA
  engine).
- Equivalence is established **non-circularly**: the generated monitor is proven
  by SymbiYosys BMC against an independent IEEE-1800 reference monitor authored
  from `∃ k ∈ [m,n] : a(t0+k)` semantics (not derived from the implementation).
- Unbounded `s_eventually a`, `a |-> s_eventually b`,
  `a |=> s_eventually b`, `a s_until b`, and `a s_until_with b` with Boolean
  operands are formal-only. The monitor composer rejects them; the formal CLI
  lowers them to Yosys `$live` plus any required safety obligation.
- The formal-only live result is `PROVEN` only after a real SymbiYosys
  `mode live` / Super Prove pass and required cover reachability. Missing
  Super Prove is `UNKNOWN`; bounded BMC is never promoted to a liveness proof.
- Unbounded `always`, nested liveness shapes, and other unbounded forms remain
  outside the implemented formal frontend.
- Weak `until` / `until_with` are safety properties (no liveness obligation) and
  are implemented in the finite-state monitor subset. Strong `s_until` /
  `s_until_with` are formal-only and split into weak-until safety plus eventual
  discharge.

## Composition Model

sva2rtl uses token-passing composition between generated operator modules:

- Each operator is compiled to a hardware template
- Templates are composed by connecting token ports (start/match/fail)
- NFA implication consequents have explicit bounded thread slots (T ≤ 4).
- Most standalone counter/operator templates hold one active state machine;
  callers must not infer unlimited overlapping-attempt support from the `start`
  port. Row-specific evidence in `SUPPORT_MATRIX.md` governs this boundary.
- Counter encoding replaces one-hot shift registers for range operators (area optimization)

### Token Flow

```
start → [Operator Template] → match (pass downstream)
                            → fail  (report violation)
                            → active (evaluation in progress)
```

## Operator Details

### Delay: `##N` (Fixed)

Generates a bounded counter. A token enters on `start`, and the window output
opens at the counter value corresponding to exactly N source-sample cycles.

### Delay: `##[M:N]` (Range)

Generates a counter with window comparator. Token can exit on any cycle between M and N (inclusive).

```systemverilog
// ##[1:3] generates:
logic [1:0] cnt;
logic counting;
always_ff @(posedge clk or negedge rst_n)
    if (!rst_n)       begin cnt <= '0; counting <= 1'b0; end
    else if (token_in) begin cnt <= '0; counting <= 1'b1; end
    else if (counting) cnt <= cnt + 1'b1;
assign token_out = counting && (cnt >= 2'd1) && (cnt <= 2'd3) && cond_match;
```

### Implication: `|->` (Overlapping)

Antecedent match triggers consequent evaluation in the same cycle.

### Implication: `|=>` (Non-overlapping)

Equivalent to `|-> ##1`. Antecedent match triggers consequent evaluation on the next cycle.

### Repetition: `[*N]` (Exact)

Counter-based template. Counts N consecutive matches of the operand.

### Repetition: `[*M:N]` (Range)

Counter with range check. Reports match when count is within [M, N] and operand ceases to hold (or reaches N).

### Sampled Value Functions

| Function | Implementation |
|----------|---------------|
| `$rose(sig)` | `sig & ~sig_d1` |
| `$fell(sig)` | `~sig & sig_d1` |
| `$stable(sig)` | `sig == sig_d1` |
| `$changed(sig)` | `sig != sig_d1` |
| `$past(sig, N)` | N-stage shift register on `sig` |

All sampled value functions register the signal with a one-cycle delay (`sig_d1`).
The v1 contract accepts one plain, scalar identifier only. Packed vectors,
selects / compound expressions, optional clocking or gating arguments, and
non-positive `$past` depths are rejected explicitly instead of being silently
scalarized or emitted as invalid ports. DUT signals whose names overlap the
public monitor interface are assigned deterministic `dut_*` port aliases.

### `disable iff`

Generates an enable gate around the entire monitor. When the disable condition is active:
- No new attempts are started
- Active attempts are terminated without generating pass/fail
- `disabled_o` is asserted

## Known Limitations and Historical Fixes

### Cycle-delay spacing (BUG-DELAY-01, RESOLVED v1.4)

The cycle-delay operators `##N` / `##[M:N]` recognize the correct absolute
inter-element spacing: the generated monitor for `a ##N b` samples `b` exactly
`N` cycles after `a` (and `a ##[M:N] b` accepts the window `[M, N]`). This is
proven non-circularly (FPV) in `tests/test_formal_sva_equiv.py`
(`TestDelaySvaEquiv`, parametrized over `##1`, `##3`, `##[1:3]`, `##[2:5]`).

> A prior release shipped a `+2` absolute-spacing defect in the token-passing
> `concat_delay` (b sampled at `a+(N+2)`), hidden by an isomorphic oracle and a
> circular equivalence test. It was found and fixed in v1.4; see
> `.planning/BUG-delay-spacing.md`.

> **Fusion (`##0`).** `a ##0 b` with two BoolExpr operands is automatically
> rewritten to `(a) && (b)` in the normalizer (v1.7 LANG-01). The registered-leaf
> pipeline no longer emits non-standard RTL for `##0`. Non-BoolExpr `##0` forms
> (e.g. `a ##0 (b[*3])`) are rejected at compile time with a suggestion.

### Semantic boundary: intersect / within / throughout (v1.5 update)

**v1.5.0 changes.** Two distinct boundary issues affecting the composed
sequence operators `intersect`, `within`, `throughout` have been addressed:

1. **RISK-02 (value-level oracle correctness for boolean operands) — FIXED.**
   The behavioral oracle previously modelled a boolean expression as
   always-passing (a `delay_fixed(0,0)` leaf), so `a intersect b` and
   `a within b` verified vacuously true. v1.5 introduces
   `_eval_bool_leaf(cond_node, signals)` — an independent RISK-01
   boolean-atom evaluator that ANDs across `observed_signals` — and gates
   the pass output of `_tick_prop_intersect` / `_tick_prop_within` by it.
   The two strict-xfail baseline tests in
   `tests/test_v13_independent_baseline.py` (`test_intersect_baseline_both_true`,
   `test_within_baseline_inner_inside_outer`) are now real green pass.
   Eight exhaustive gate tests in `tests/test_v15_risk02_gate.py` cover the
   intersect TT/TF/FT/FF truth table and four within shape variants.
   The RTL was already correct for boolean operands (`bool_expr.sv.j2`
   evaluates `pass_q <= start & bool_result`); v1.5 aligned the oracle
   with the RTL, closing RISK-01 independence for this case.

2. **Silent-wrong multi-cycle composition — REJECTED.** Previously,
   `(a ##2 b) intersect (c[*3])` silently compiled to
   `prop_intersect(seq_concat, rep_consecutive)`, whose RTL
   `left_pass & right_pass` matches IEEE 1800 §16.9.7 semantics only when
   the two sub-sequences happen to complete on the same cycle by accident.
   v1.5 closes this silent-wrong path with a compile-time
   `UnsupportedConstruct` in `_compose_intersect / _compose_within /
   _compose_throughout` whenever any operand is not a `BoolExpr` leaf.
   The error names the offending operand position and IR type, mentions
   the v1.5.1 NFA composition engine, and describes the split-property
   workaround. Thirteen rejection tests in `tests/test_v15_g2a_reject.py`
   cover intersect, within, throughout, nested composition, SeqOr /
   SeqGotoRep / SeqNonconsecRep operands, and error-message quality
   (source_loc, workaround hint).

**v1.5.1 changes — NFA composition engine fully deployed.**

The NFA composition engine (one-hot state encoding, product construction,
multi-thread slot allocation) now supports:

- **Multi-cycle operands** for `intersect`, `within`, `throughout`:
  `SeqConcat` (fixed delays), `SeqRepetition` (fixed count). Total states
  K ≤ 32 per composition (compile-time enforced).
- **Multi-cycle implication consequents**: `|->` / `|=>` with
  `SeqConcat` / `SeqRepetition` consequents (up to 7-state, 4-thread).
- **Nested composition**: `(a intersect b) within c`,
  `(a intersect b) intersect c`, `en throughout (a intersect b)` — all
  combinations of intersect/within/throughout nested up to the K ≤ 32
  budget.
- **Independent verification**: 24 sby BMC miters across all operators
  prove equivalence against shift-register reference monitors (structurally
  distinct from one-hot NFA). 18 dual-oracle iverilog simulations match
  cycle-for-cycle. Behavioral oracle uses rule-based thread simulator
  (RISK-01 independent). Phase 10 does not promote the complex NFA composition
  family to full-contract or k-induction proof; those boundaries remain governed
  by `SUPPORT_MATRIX.md`.

**Now supported (v1.7 LANG-02..04):** SeqOr, ranged delays, ranged repetition,
SeqGotoRep, SeqNonconsecRep inside intersections/within/throughout via the NFA
engine. The only remaining rejection is K-state budget exceedance (>32).

### Fixed-count `[->N]` / `[=N]` boundary

`[->N]` and `[=N]` are supported for fixed positive counts. Ranged
goto/non-consecutive repetition such as `a[->2:4]` or `a[=1:3]` is recognized
and rejected with `SVA-E002`; use a fixed count until ranged count NFA
semantics are implemented. Fixed-count goto/nonconsecutive are now NFA-liftable
(v1.7 LANG-04).

### Unsupported / Deliberately Rejected Operators

The following operators remain unsupported or deliberately rejected:

| Operator | Category | Status |
|----------|----------|--------|
| `nexttime` | Temporal | Not supported |
| `eventually`/`s_eventually` (bounded `[m:n]`) | Liveness | **Supported** (v1.4 Part A) |
| `eventually`/`s_eventually` (unbounded Boolean/root implication shapes) | Liveness | Formal-only with open live backend; monitor generation rejected |
| `always [m:n]` / `s_always [m:n]` (bounded) | Liveness | **Supported** (v1.4 Part A) |
| `until` / `until_with` (weak) | Safety | **Supported** (v1.4 Part A) |
| `s_until` / `s_until_with` (strong Boolean operands) | Liveness | Formal-only safety + eventual-discharge proof; monitor generation rejected |
| `always` (unbounded) | Temporal | Rejected — legal streaming safety form, but not implemented by v1 |
| `[->M:N]` / `[=M:N]` where `M < N` | Repetition | Rejected — v1 supports fixed counts only |
| `intersect`/`within` with local variables | Sequence | Not supported |
| Nested multi-path operators | Sequence | Supported when operands are NFA-liftable and K ≤ 32 |
| Multi-clock properties | Clocking | Trusted/prototype boundary for path-one split-and-synchronize forms |

### Structural Limitations

| Limitation | Description |
|------------|-------------|
| Multi-clock path-one only | The compiler accepts `##1` clock-change sequences and non-overlap cross-clock implication through a trusted 2-DFF level synchronizer; event delivery, full CDC/metastability proof, and multi-path cross-clock composition are excluded |
| Unbounded repetition `[*]` | Open-ended match/resource semantics are outside the bounded v1 contract |
| Unbounded delay `##[0:$]` | No finite deadline under the current pass/fail monitor contract |
| Local variables | SVA local variables in sequences are not supported |
| Recursive properties | Not supported |
| Non-scalar sampled operands | Packed vectors, arrays, selects, and compound expressions are not supported in sampled value functions |
| Optional sampled arguments | Optional clocking/gating arguments are outside the scalar v1 sampled-value contract |
| `$countones`, `$onehot` | System functions beyond $rose/$fell/$stable/$past not supported |

### Multi-clock support (v1.4.1 Part B — Path One: trusted 2-DFF synchronizer)

With explicit `--experimental-multiclock` opt-in, the compiler accepts a bounded
multi-clock subset using a split-and-synchronize compilation approach (Gawanmeh
& Tahar, 2009): each `@(clk_i)` sub-sequence is compiled to
a single-clock checker in its own clock domain, reusing the full Tier 1/2/3
generation pipeline. Cross-domain `##1` boundaries are connected through a
2-DFF level synchronizer (`templates/sync_2dff.sv.j2`, TRUSTED COMPONENT).
The default emission path rejects these forms after composition. The opt-in is
accepted syntax and generated structure, not a claim of reliable cross-domain
event delivery or CDC sign-off.

**Supported subset** (equals the SVA standard's allowed multi-clock forms):
- `@(posedge clk1) seq1 ##1 @(posedge clk2) seq2` (multi-clock sequence)
- `@(posedge clk1) antecedent |=> @(posedge clk2) consequent` (multi-clock impl.)
- multi-stage chains of the above (`@(clk1) ... ##1 @(clk2) ... ##1 @(clk3) ...`)

**Permanently excluded** (with reasons):
- `##N (N != 1)` or `##[M:N]` across a clock change — forbidden by IEEE 1800
- multi-clock `intersect`/`within`/`throughout` — require same-start same-clock
- overlapping implication `|->` across different clocks — race risk
- full multi-clock formal equivalence — industry-wide limitation (DVCon 2024)

**Trusted component:** The 2-DFF synchronizer has NOT been verified against
metastability via formal methods. Per-domain sub-checkers retain the full
verification stack (iverilog+Verilator sim, behavioral oracle, SymbiYosys
formal equivalence). Cross-clock timing assumptions should be validated on FPGA
prototypes or in post-silicon testing.

It is also a **level synchronizer, not an acknowledged pulse transfer**.
Generated one-cycle tokens may be missed when the destination clock is slower
or unfavorably phased, and multiple events may coalesce. The compiler currently
does not enforce a minimum token width or event-rate bound. The multi-clock
subset therefore remains a trusted/prototype boundary until a handshake or
toggle protocol and asynchronous clock-ratio tests close event delivery.

See `.planning/DESIGN-multiclock-risk-D.md` for the full design and references.

## Error Codes

| Code | Severity | Description | Resolution |
|------|----------|-------------|------------|
| SVA-E001 | Error | Unsupported SVA operator encountered | Use only Tier 1/2/3 operators listed above |
| SVA-E002 | Error | Repetition form is unbounded or outside the supported finite-state subset | Replace unbounded `[*]`/`[+]` with bounded `[*M:N]`; replace ranged `[->M:N]`/`[=M:N]` with fixed `[->N]`/`[=N]` |
| SVA-E003 | Error | Multi-clock property detected (cross-clock `##N` N≠1, multi-clock intersect/within/throughout, overlapping `|->` cross-clock) | Use allowed multi-clock forms (`##1`, `|=>`) |
| SVA-E004 | Error | Failed to parse SVA input (slang error) | Check syntax; ensure slang can parse the input |
| SVA-E005 | Error | `--property` matched no assertion (label, index, or line not found) | Use a valid label name, 1-based index, or `@N` source-line number |

### Error Output Format

```
sva2rtl: error SVA-E001: unsupported operator 'nexttime' at input.sv:12:5
  |
12|     nexttime a
  |     ^^^^^^^^
  = note: 'nexttime' is not synthesizable in the supported finite-state subset
  = help: see SUPPORTED_CONSTRUCTS.md for the list of supported operators
```

## Unsupported Constructs with Clear Errors

The following constructs are recognized by the parser but produce clear error messages directing users to alternatives or workarounds:

| Construct | Error Code | Suggested Workaround |
|-----------|-----------|---------------------|
| `[*]` (unbounded) | SVA-E002 | Use `[*1:MAX]` with explicit bound |
| `[+]` (unbounded) | SVA-E002 | Use `[*1:MAX]` with explicit bound |
| `[->M:N]` / `[=M:N]` where `M < N` | SVA-E002 | Use fixed `[->N]` / `[=N]`, or split into explicit properties |
| `##[0:$]` | SVA-E002 | Use `##[0:MAX]` with explicit bound |
| Unsupported multi-clock forms (`##N` where N≠1, cross-clock `intersect`, overlapping cross-clock `|->`) | SVA-E003 | Use allowed path-one forms (`##1`, `|=>`) or split into single-clock properties |
| `nexttime` / unbounded `always` / unsupported nested liveness | SVA-E001 | Outside the implemented unbounded frontend; decompose with a checked relation or use another supporting frontend |
| unbounded `s_eventually` / strong `s_until` in the documented Boolean shapes | — | Use `sva2rtl-formal`; synthesizable monitor generation remains intentionally rejected |
| bounded `eventually`/`s_eventually [m:n]` | — | Supported since v1.4 Part A |

## Validation

All generated monitors are validated against behavioral simulation:

1. **Functional correctness**: Monitor output matches expected pass/fail for exhaustive input traces
2. **Reset behavior**: Clean state after assertion of `rst_n`
3. **Concurrent attempts**: Multiple overlapping evaluations produce correct independent results
4. **Boundary conditions**: Edge cases (zero-delay, max-range, immediate match/fail)

Test suite uses Icarus Verilog and Verilator for simulation-based validation.
Phase 11 also adds generated-RTL tool gates: representative emitted monitors run
through a Yosys synthesis-oriented smoke flow, and a separate Verilator
`--lint-only -Wall` gate is configured for CI. These gates prove tool
acceptance of generated RTL; they do not replace simulation, formal, or CDC
evidence.

Phase 12 adds bounded source-level differential tests: Hypothesis-backed
generated SVA source cases are compiled through the normal pipeline, driven with
bounded stimulus, and compared against the independent Python oracle and Icarus
RTL simulation. Verilator differential runs where Verilator is installed; a
local Verilator skip is non-evidence. Broader randomized sweeps are behind the
`differential_slow` marker.
