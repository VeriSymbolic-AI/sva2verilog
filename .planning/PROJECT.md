# sva2rtl

## What This Is

An open-source SVA (SystemVerilog Assertion) to synthesizable RTL compiler. It takes SVA properties/sequences as input and generates hardware monitor modules in SystemVerilog (with Verilog-2001 compatibility flag) that can be simulated with Verilator/Icarus or synthesized to FPGA. No mature open-source tool exists in this space globally — this fills a critical gap in the EDA toolchain.

## Core Value

Turn any SVA property into a correct, area-efficient synthesizable hardware monitor — something no open-source tool does today.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Parse SVA properties via slang --ast-json frontend (full IEEE 1800-2017 coverage)
- [ ] Support overlapping implication (|->), non-overlapping implication (|=>)
- [ ] Support fixed delay (##N) via shift register / counter templates
- [ ] Support range delay (##[M:N]) via counter + window comparator
- [ ] Support consecutive repetition ([*N], [*M:N])
- [ ] Support goto repetition ([->N]) and non-consecutive repetition ([=N])
- [ ] Support $rose, $fell, $stable, $past, $changed
- [ ] Support disable iff (abort/reset semantics)
- [ ] Support throughout (condition hold during sequence)
- [ ] Support within (bounded containment)
- [ ] Support intersect (parallel sequences, synchronized completion)
- [ ] Support first_match (early termination)
- [ ] Support sequence and/or composition
- [ ] Handle overlapping implication with multiple concurrent threads (bit-vector method)
- [ ] Generate SystemVerilog monitor modules with standard interface (clk, rst_n, start, pass, fail, active)
- [ ] Generate bind statements for DUT integration
- [ ] Provide --verilog flag for Verilog-2001 compatible output
- [ ] Validate correctness against Icarus Verilog and Verilator simulation
- [ ] Area-efficient output: counter encoding for bounded ranges (not state expansion)

### Out of Scope

- Local variables in sequences — requires data-path synthesis, defer to v2
- Multi-clock assertions — complex clock domain crossing, defer to v2
- Recursive properties — rare in practice
- Checker constructs (IEEE Ch.17) — rare, complex
- Liveness properties (s_eventually) — not synthesizable to safety monitors without approximation
- FPGA synthesis toolchain integration — downstream user concern
- GUI or IDE integration — CLI-first

## Context

- **Market gap**: No mature open-source SVA->RTL compiler exists globally. Commercial EDA tools (VCS/Questa/Xcelium) discard SVA at synthesis — they don't generate monitor circuits.
- **Closest reference**: sahadipayan/SVA_to_RTL_Synthesizer (6 stars, 3 files, only basic conditionals — not usable)
- **Parsing solved**: slang v11.0 (MIT, C++20) provides complete IEEE 1800-2017 SVA parsing with --ast-json output
- **Algorithm landscape**: TIMA Lab (token-passing, linear complexity), US Patent 10726182 (operator templates), US Patent 7810056 (rewrite normalization) — all provide validated algorithmic foundations
- **PyABV (2025)**: Proved <1.5% area overhead is achievable for hardware monitors
- **RLVR value**: This compiler serves as fallback for yosys-slang gaps, enabling 100% SVA reward signal coverage in AI training pipelines

## Constraints

- **Parsing**: Must use slang library (not re-implement parser) — slang is MIT, IEEE 1800-2017+ complete
- **Language**: Python for v1 (rapid iteration), potential C++ rewrite for v2 performance
- **Output**: SystemVerilog default, Verilog-2001 via --verilog flag
- **Validation**: All generated monitors must pass equivalence checking against behavioral simulation (Icarus/Verilator)
- **License**: BSL (Business Source License) — free for individual/academic/evaluation, commercial use by large companies requires license
- **Architecture**: Token-passing composition model (TIMA Lab) with operator-aware templates (counter encoding for ranges)
- **Interface standard**: Every generated checker exposes (clk, rst_n, start, pass, fail, active) ports

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + slang CLI (not C++ or pyslang) | Fastest iteration; JSON AST is stable and complete; avoids C++ build complexity | — Pending |
| Bit-vector method for overlapping implication | Simple, hardware-efficient, handles 85%+ of real SVA; NFA/DFA layered on top for Phase B/C | — Pending |
| TIMA Lab token-passing architecture | Linear complexity (O(n) area), compositional, extensible, proven in academic literature | — Pending |
| Counter encoding over state expansion | `##[0:100]` = 7-bit counter (~10 FF) vs 101 parallel paths (101 FF) — critical for practical area | — Pending |
| Rewrite normalization as preprocessing | Reduce exotic operators to primitives before template emission (Patent 7810056) | — Pending |
| BSL license | Prevent large-company free-riding while keeping community access; successful precedent (MariaDB, HashiCorp) | — Pending |
| Standard checker interface (start/match/fail/active) | Enables hierarchical composition, debugging, and reuse across all operator templates | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? -> Move to Out of Scope with reason
2. Requirements validated? -> Move to Validated with phase reference
3. New requirements emerged? -> Add to Active
4. Decisions to log? -> Add to Key Decisions
5. "What This Is" still accurate? -> Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-25 after initialization*
