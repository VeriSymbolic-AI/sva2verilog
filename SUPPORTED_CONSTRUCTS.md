# Supported SVA Constructs — sva2rtl v1.3.1

## Tier 1 Operators (Fully Supported)

| Operator | Category | Description | Example SVA | Generated Template |
|----------|----------|-------------|-------------|-------------------|
| `##N` | Delay | Fixed cycle delay | `a ##2 b` | Shift register (N flip-flops) |
| `##[M:N]` | Delay | Bounded delay range | `a ##[1:3] b` | Counter with [M,N] window comparator |
| <code>\|-></code> | Implication | Overlapping implication, **single-cycle consequent only** | <code>req \|-> ack</code> | Antecedent match triggers consequent check (same cycle) |
| <code>\|=></code> | Implication | Non-overlapping implication, **single-cycle consequent only** | <code>req \|=> ack</code> | Antecedent match triggers consequent check (next cycle) |

> **Implication consequent restriction (v1.3.2).** The consequent of `|->` / `|=>`
> must be a **single-cycle** expression: a boolean expression or a sampled-value
> function (`$rose`/`$fell`/`$stable`/`$past`/`$changed`). These single-cycle
> forms are formally proven equivalent to IEEE-1800 semantics
> (`tests/test_formal_sva_equiv.py`). A **multi-cycle sequence consequent**
> (e.g. `a |-> b ##2 c`, `a |-> b[*3]`, `a |-> (b ##[2:5] c)`) is **rejected at
> compile time** (error SVA-E002): its legacy implementation is a confirmed
> correctness defect (BUG-IMPL-01) and a correct version requires the v1.5 NFA
> composition engine. Workaround: move the sequence into the **antecedent**
> (e.g. `(b ##2 c) |-> d`), or split into separate properties whose consequent
> is single-cycle.
| `[*N]` | Repetition | Exact consecutive repetition | `a[*3]` | Counter counts N consecutive matches |
| `[*M:N]` | Repetition | Bounded consecutive repetition | `a[*1:4]` | Counter with [M,N] range check |
| `$rose()` | Sampled value | Rising edge (0-to-1 transition) | `$rose(sig)` | Edge detector: `sig & ~sig_prev` |
| `$fell()` | Sampled value | Falling edge (1-to-0 transition) | `$fell(sig)` | Edge detector: `~sig & sig_prev` |
| `$stable()` | Sampled value | No value change | `$stable(sig)` | Comparator: `sig == sig_prev` |
| `$past(sig, N)` | Sampled value | Value N cycles ago | `$past(data, 2)` | Shift register delay line (N stages) |
| `$changed()` | Sampled value | Signal changed since previous cycle | `$changed(sig)` | Comparator: `sig != sig_prev` |
| `disable iff` | Control | Asynchronous disable condition | `disable iff (rst) prop` | Gating logic on monitor enable |
| Named sequences | Structure | Reusable sequence definitions | `sequence s; a ##1 b; endsequence` | Submodule instantiation |

## Tier 2 Operators (v1.3 — Fully Supported)

| Operator | Category | Description | Example SVA | Generated Template |
|----------|----------|-------------|-------------|-------------------|
| `[->N]` | Repetition | Goto repetition (N non-consecutive occurrences) | `a[->3]` | Counter with liveness tracking, locking pass register |
| `[=N]` | Repetition | Non-consecutive repetition (relaxed tail) | `a[=2]` | Counter with relaxed completion check |
| `first_match` | Sequence | Earliest completion wins | `first_match(a ##[1:3] b)` | Wrapper with locked_q to suppress later matches |
| `and` | Sequence | Both sequences match (same start) | `s1 and s2` | AND of two sub-checker pass signals |
| `or` | Sequence | Either sequence matches | `s1 or s2` | OR of two sub-checker pass signals |
| `intersect` | Sequence | Both sequences complete simultaneously | `s1 intersect s2` | AND of pass signals with active intersection |
| `within` | Sequence | Inner sequence within outer's window | `s1 within s2` | Inner pass AND outer active check |
| `throughout` | Sequence | Condition holds throughout sequence | `en throughout s1` | Fail if condition fails while body active |
| `not` | Property | Invert pass/fail | `not (prop)` | Swap pass and fail outputs |
| `if...else` | Property | Conditional property selection | `if (cond) p1 else p2` | MUX between true/false branch checkers |

## Tier 3 Operators (v1.4 Part A — Bounded Liveness)

Bounded-liveness operators carry an explicit cycle window `[m:n]`, which makes
them synthesizable on finite state (the obligation has a hard deadline). The
**unbounded** forms are rejected at compile time — they are not synthesizable on
finite state.

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
- Unbounded `s_eventually a` / `always a` / `s_until` / `s_until_with` (which
  require an eventual or unbounded obligation) raise `UnsupportedConstruct` with a
  source location and a remediation hint.
- Weak `until` / `until_with` are safety properties (no liveness obligation) and
  are fully supported; the strong `s_until` / `s_until_with` forms are rejected.

## Composition Model

sva2rtl uses token-passing composition to handle concurrent property evaluations:

- Each operator is compiled to a hardware template
- Templates are composed by connecting token ports (start/match/fail)
- Multiple overlapping attempts are tracked simultaneously via token replication
- Counter encoding replaces one-hot shift registers for range operators (area optimization)

### Token Flow

```
start → [Operator Template] → match (pass downstream)
                            → fail  (report violation)
                            → active (evaluation in progress)
```

## Operator Details

### Delay: `##N` (Fixed)

Generates an N-stage shift register. Token enters on `start`, exits on `match` after exactly N clock cycles.

```systemverilog
// ##2 generates:
logic [1:0] delay_sr;
always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) delay_sr <= '0;
    else        delay_sr <= {delay_sr[0], token_in};
assign token_out = delay_sr[1];
```

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

### `disable iff`

Generates an enable gate around the entire monitor. When the disable condition is active:
- No new attempts are started
- Active attempts are terminated without generating pass/fail
- `disabled_o` is asserted

## Known Limitations (v1.3.1)

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

> **Fusion limitation (`##0`).** `a ##0 b` (and any ranged delay whose lower
> bound is 0) requires sampling two operands in the SAME cycle, which the
> registered-leaf token-passing pipeline cannot express; `##0` retains a 1-cycle
> separation. Use `a && b` for true same-cycle conjunction. This is a structural
> limitation slated for the v1.5 NFA engine.

### Semantic boundary: intersect / within with boolean operands

The composed operators `intersect` and `within` are verified correct only for
the single-completion-time sub-sequence case. With **boolean operands**, the
behavioral oracle currently does not evaluate the operand values (it models a
boolean expression as always-passing for timing purposes), so the value-level
semantics of `a intersect b` / `a within b` are NOT independently guaranteed in
this release. This boundary is recorded honestly as strict-xfail baseline tests
in `tests/test_v13_independent_baseline.py`. The fix is the unified timing+data
oracle planned for the v1.5 NFA composition engine. Use `throughout` (which does
evaluate its condition) where value-level correctness is required, or wait for
v1.5 for fully value-aware intersect/within.

### RTL simulation: multi-module x-propagation

The iverilog simulation tests for v1.3 composed operator templates (prop_or,
prop_and, prop_intersect, prop_within, prop_throughout, prop_not, prop_if_else)
are skipped in this release due to a known x-propagation issue in multi-module
iverilog simulations.  Behavioral oracle tests provide full functional coverage.
A fix is targeted for v1.3.1.

### Unsupported Operators (planned for v1.4)

The following temporal operators are not yet supported:

| Operator | Category | Status |
|----------|----------|--------|
| `nexttime` | Temporal | Not supported |
| `eventually`/`s_eventually` (bounded `[m:n]`) | Liveness | **Supported** (v1.4 Part A) |
| `eventually`/`s_eventually` (unbounded) | Liveness | Rejected — not synthesizable on finite state |
| `always [m:n]` / `s_always [m:n]` (bounded) | Liveness | **Supported** (v1.4 Part A) |
| `until` / `until_with` (weak) | Safety | **Supported** (v1.4 Part A) |
| `s_until` / `s_until_with` (strong) | Liveness | Rejected — requires unbounded eventual obligation |
| `always` (unbounded) | Temporal | Rejected — not synthesizable on finite state |
| `intersect`/`within` with local variables | Sequence | Not supported |
| Nested multi-path operators | Sequence | Not supported (single-level only) |
| Multi-clock properties | Clocking | Not supported (planned v1.4.1 Part B) |

### Structural Limitations

| Limitation | Description |
|------------|-------------|
| Multi-clock properties | Only single-clock-domain properties are supported |
| Unbounded repetition `[*]` | Requires infinite state; not synthesizable |
| Unbounded delay `##[0:$]` | Requires infinite state; not synthesizable |
| Local variables | SVA local variables in sequences are not supported |
| Recursive properties | Not supported |
| Multi-dimensional signals | Array signals not supported in sampled value functions |
| `$countones`, `$onehot` | System functions beyond $rose/$fell/$stable/$past not supported |

### Multi-clock support (v1.4.1 Part B — Path One: trusted 2-DFF synchronizer)

Multi-clock properties are supported using a split-and-synchronize compilation
approach (Gawanmeh & Tahar, 2009): each `@(clk_i)` sub-sequence is compiled to
a single-clock checker in its own clock domain, reusing the full Tier 1/2/3
generation pipeline. Cross-domain `##1` boundaries are connected through a
standard 2-DFF synchronizer (`templates/sync_2dff.sv.j2`, TRUSTED COMPONENT).

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

See `.planning/DESIGN-multiclock-risk-D.md` for the full design and references.

## Error Codes

| Code | Severity | Description | Resolution |
|------|----------|-------------|------------|
| SVA-E001 | Error | Unsupported SVA operator encountered | Use only Tier 1/2/3 operators listed above |
| SVA-E002 | Error | Unbounded repetition is not synthesizable | Replace `[*]` or `[+]` with bounded `[*M:N]` |
| SVA-E003 | Error | Multi-clock property detected (cross-clock `##N` N≠1, multi-clock intersect/within/throughout, overlapping `|->` cross-clock) | Use allowed multi-clock forms (`##1`, `|=>`) |
| SVA-E004 | Error | Failed to parse SVA input (slang error) | Check syntax; ensure slang can parse the input |
| SVA-E005 | Error | `--property` matched no assertion (label, index, or line not found) | Use a valid label name, 1-based index, or `@N` source-line number |

### Error Output Format

```
sva2rtl: error SVA-E001: unsupported operator 'nexttime' at input.sv:12:5
  |
12|     nexttime a
  |     ^^^^^^^^
  = note: 'nexttime' is a Tier 3 operator not supported in v1.3.0
  = help: see SUPPORTED_CONSTRUCTS.md for the list of supported operators
```

## Unsupported Constructs with Clear Errors

The following constructs are recognized by the parser but produce clear error messages directing users to alternatives or workarounds:

| Construct | Error Code | Suggested Workaround |
|-----------|-----------|---------------------|
| `[*]` (unbounded) | SVA-E002 | Use `[*1:MAX]` with explicit bound |
| `[+]` (unbounded) | SVA-E002 | Use `[*1:MAX]` with explicit bound |
| `##[0:$]` | SVA-E002 | Use `##[0:MAX]` with explicit bound |
| Multi-clock `@(posedge clk2)` | SVA-E003 | Split into separate single-clock properties |
| `nexttime` / unbounded `always` / unbounded `eventually` / `s_until` | SVA-E001 | Unbounded liveness not synthesizable; use bounded `[m:n]` forms |
| bounded `eventually`/`s_eventually [m:n]` | — | Supported since v1.4 Part A |

## Validation

All generated monitors are validated against behavioral simulation:

1. **Functional correctness**: Monitor output matches expected pass/fail for exhaustive input traces
2. **Reset behavior**: Clean state after assertion of `rst_n`
3. **Concurrent attempts**: Multiple overlapping evaluations produce correct independent results
4. **Boundary conditions**: Edge cases (zero-delay, max-range, immediate match/fail)

Test suite uses Icarus Verilog and Verilator for simulation-based validation.
