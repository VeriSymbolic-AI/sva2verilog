# Supported SVA Constructs — sva2rtl v1.3.0

## Tier 1 Operators (Fully Supported)

| Operator | Category | Description | Example SVA | Generated Template |
|----------|----------|-------------|-------------|-------------------|
| `##N` | Delay | Fixed cycle delay | `a ##2 b` | Shift register (N flip-flops) |
| `##[M:N]` | Delay | Bounded delay range | `a ##[1:3] b` | Counter with [M,N] window comparator |
| <code>\|-></code> | Implication | Overlapping implication | <code>req \|-> ack</code> | Antecedent match triggers consequent check (same cycle) |
| <code>\|=></code> | Implication | Non-overlapping implication | <code>req \|=> ack</code> | Antecedent match triggers consequent check (next cycle) |
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

## Known Limitations (v1.3.0)

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
| `always` | Temporal | Not supported |
| `eventually` | Temporal | Not supported |
| `until` | Temporal | Not supported |
| `intersect`/`within` with local variables | Sequence | Not supported |
| Nested multi-path operators | Sequence | Not supported (single-level only) |
| Multi-clock properties | Clocking | Not supported |

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

## Error Codes

| Code | Severity | Description | Resolution |
|------|----------|-------------|------------|
| SVA-E001 | Error | Unsupported SVA operator encountered | Use only Tier 1 operators listed above |
| SVA-E002 | Error | Unbounded repetition is not synthesizable | Replace `[*]` or `[+]` with bounded `[*M:N]` |
| SVA-E003 | Error | Multi-clock property detected | Rewrite using single clock domain |
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
| `nexttime` / `always` / `eventually` / `until` | SVA-E001 | Tier 3 operators; planned for v1.4 |

## Validation

All generated monitors are validated against behavioral simulation:

1. **Functional correctness**: Monitor output matches expected pass/fail for exhaustive input traces
2. **Reset behavior**: Clean state after assertion of `rst_n`
3. **Concurrent attempts**: Multiple overlapping evaluations produce correct independent results
4. **Boundary conditions**: Edge cases (zero-delay, max-range, immediate match/fail)

Test suite uses Icarus Verilog and Verilator for simulation-based validation.
