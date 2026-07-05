# sva2rtl v1.4.0 Release Notes

**Release date:** 2026-06-30
**Type:** Feature release — bounded liveness operators (Part A)

v1.4.0 adds the first family of **temporal/liveness operators** to sva2rtl:
bounded eventually, bounded always, and the weak until forms. Every new operator
is proven correct **non-circularly** — each generated monitor is checked by a
SymbiYosys bounded model check against an independently authored IEEE-1800
reference monitor (never derived from the implementation), upholding the RISK-01
verification-independence discipline established in v1.3.1.

This release also folds in the v1.3.2 → v1.4 Part 0 verification-hardening
campaign (the `##N` inter-element spacing fix and single-cycle implication timing
fix) and a repo-wide lint cleanup (ruff 0 across `src/`, `tests/`, `tools/`).

## Summary

| Area | Change |
|------|--------|
| Version | Bumped `pyproject.toml` and `__init__.py` to `1.4.0` |
| `s_eventually [m:n]` / `eventually [m:n]` | Bounded existential liveness — pass at first in-window hit, fail at deadline if never satisfied |
| `always [m:n]` / `s_always [m:n]` | Bounded universal liveness (dual) — fail at first in-window violation, pass at deadline if all held |
| `until` / `until_with` | Weak until safety properties — pass when discharged, fail when the left operand drops |
| Honesty-first rejections | Unbounded liveness (`s_eventually a`, unbounded `always a`) and strong `s_until` / `s_until_with` rejected with source-located errors |
| Verification | 24 non-circular SymbiYosys BMC miters (eventually ×10, always ×10, until ×4) + 14 iverilog sim cross-checks + 22 frontend unit tests + 13 edge-case tests |
| Part 0 (folded in) | BUG-DELAY-01 `##N` spacing fix; BUG-IMPL-01 single-cycle implication timing fix |
| Lint | ruff debt cleared repo-wide (54 → 0 in `src/`; `tests/` + `tools/` also 0) |
| Tests | 970 passed, 4 skipped, 5 xfailed |

## Details

### Bounded eventually — `s_eventually [m:n]` / `eventually [m:n]`

A deadline-bounded existential obligation: armed at the evaluation (`start`)
cycle, the boolean operand must hold at some offset `k ∈ [m,n]`. The generated
monitor (`templates/s_eventually.sv.j2`) uses an offset counter, a satisfied
latch, and a deadline-fail, with registered outputs (pass at `start+k*+1` where
`k*` is the first in-window holding offset; fail at `start+n+1` if none). The weak
and strong forms collapse to the same synthesizable monitor over a finite window.

### Bounded always — `always [m:n]` / `s_always [m:n]`

The universal dual: the operand must hold at *every* in-window offset. The
monitor (`templates/s_always.sv.j2`) uses an offset counter, a violation latch,
and a deadline-pass (fail at `start+k_viol+1` for the first violating offset;
pass at `start+n+1` if all held). Fail fires exactly once on the first violation.

### Weak until — `until` / `until_with`

Standard SVA `until` has no `[m:n]` range; the synthesizability split is between
the **weak** forms (safety properties — no liveness obligation, fully supported)
and the **strong** forms (`s_until` / `s_until_with`, which require the
right-hand side to eventually hold — an unbounded eventual obligation, rejected).
The weak monitor (`templates/until.sv.j2`) is a counter-free safety FSM. For
`until`, pass fires when `b` first holds, fail when `a` drops before `b`. For
`until_with`, `a` must also hold at the `b` cycle. An undecided attempt stays
pending, faithfully modelling the weak (no-liveness) semantics.

### Non-circular formal verification (RISK-01)

Each operator's generated monitor is proven equivalent to an **independently
authored** IEEE-1800 reference monitor via SymbiYosys BMC (depth 20), comparing
both `pass` and `fail` outputs. The references use deliberately distinct
structures (eventually/always: an 8-bit offset counter rather than the monitor's
`cnt_q == k-1` encoding; until: a two-register `started`/`decided` live window
rather than the monitor's single `running_q`). During development the eventually
proof caught a genuine semantic bug in the first reference draft (the deadline
fail must be gated by "not already satisfied"), confirming the reference is a
real independent oracle rather than a mirror of the implementation.

### Honesty-first rejections

Constructs that are not synthesizable on finite state, or not yet supported,
raise `UnsupportedConstruct` with a source location and a remediation hint rather
than silently miscompiling: unbounded `s_eventually a` / unbounded `always a`,
strong `s_until` / `s_until_with`, non-boolean operands (sequence/property
operands are deferred to the v1.5 NFA engine), inverted bounds (`m > n`), and
liveness operators nested under an implication consequent.

## Known limitations carried forward

- Liveness operands are restricted to boolean expressions; sequence/property
  operands are deferred to the v1.5 NFA composition engine.
- Liveness operators nested under an implication consequent are rejected (v1.5).
- `intersect` / `within` with boolean operands: oracle does not evaluate operand
  values (RISK-02) — recorded as strict xfail; fixed by v1.5.
- Multi-clock properties (Part B) are deferred to v1.4.1.

## Test status

970 passed, 4 skipped (verilator not installed), 5 xfailed. ruff: 0 errors across
`src/`, `tests/`, `tools/`. All bounded-liveness operators carry independent
SymbiYosys BMC equivalence proofs.
