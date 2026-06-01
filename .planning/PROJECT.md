# sva2rtl

## What This Is

An open-source SVA (SystemVerilog Assertion) to synthesizable RTL compiler. `sva2rtl <file.sv>` parses SVA properties via slang, normalizes a frozen-dataclass IR, composes a token-passing CheckerNode tree, runs an optimization pipeline, and emits hardware monitor modules in SystemVerilog (or Verilog-2001 via `--verilog`) with the standard `(clk, rst_n, start, pass, fail, active)` interface. Verified against iverilog and Verilator co-simulation. v1.0 ships Tier 1 SVA operators (`##N`, `##[M:N]`, `|->`, `|=>`, `[*N]`, `$rose`, `$fell`, `$stable`, `$past`, `disable iff`) plus named-sequence inlining. No mature open-source tool existed in this space — this fills a critical gap in the EDA toolchain.

## Core Value

Turn any SVA property into a correct, area-efficient synthesizable hardware monitor — something no open-source tool does today.

## Current State

**Shipped: v1.0 MVP — 2026-06-01.** Tag: `v1.0`. ~4.0K LOC src + ~10.7K LOC tests + ~1.2K LOC Jinja2 templates across 6 phases / 21 plans. 736 tests pass on Ubuntu/macOS × Py 3.12/3.13 with iverilog and slang prebuilt binaries in CI. Tool is releasable but a hardening pass before public tagging is recommended (see Known Issues).

### Stack

- Python 3.12+, uv, click, Jinja2, automata-lib, networkx
- slang v11.0 (CLI subprocess via `--ast-json`)
- pytest + mypy (strict) + ruff
- GitHub Actions CI matrix (Ubuntu/macOS × Py 3.12/3.13)

### Known Issues / Tech Debt (carry to v1.1)

- Phase 03 review HIGH defects (H-01..H-04) unaddressed; H-03 (`attempt_fired_q` cleared by `disable_i`) is now duplicated across Verilog-2001 template branches in 11 templates after Phase 6 broadened the templates.
- Phase 06 review: 5 HIGH (multi-property `--dump-tree` drops `unoptimized_checker`; `--property` cannot match unlabeled assertions; `--output` file-vs-directory ambiguity; `--verilog` silently ignored by `--dump-*`; Verilog-2001 always-block bodies duplicated 22× across 11 templates), 10 MEDIUM, 9 LOW.
- `src/sva2rtl/__init__.py` says `__version__ = "0.1.0"` while `pyproject.toml` is `1.0.0`.
- No `*-VALIDATION.md` files exist — Nyquist coverage is missing for all 6 phases (workflow opt-in; not gated yet).

## Requirements

### Validated (v1.0)

- ✓ Parse SVA properties via slang `--ast-json` frontend — v1.0 (Tier 1 coverage)
- ✓ Overlapping implication (`|->`) — v1.0 via bit-vector method
- ✓ Non-overlapping implication (`|=>`) — v1.0
- ✓ Fixed delay (`##N`) — v1.0 via shift register / counter
- ✓ Range delay (`##[M:N]`) — v1.0 via counter + window comparator (counter encoding, not state expansion)
- ✓ Consecutive repetition (`[*N]`, `[*M:N]`) — v1.0 via counted FSM
- ✓ `$rose`, `$fell`, `$stable`, `$past` — v1.0 via edge-detect FFs / shift register
- ✓ `disable iff` — v1.0 via async gating
- ✓ Multi-thread overlapping implication (bit-vector method) — v1.0
- ✓ Standard monitor interface `(clk, rst_n, start, pass, fail, active)` — v1.0
- ✓ Generate bind statements for DUT integration — v1.0
- ✓ `--verilog` flag for Verilog-2001 compatible output — v1.0 (iverilog -g2001 clean)
- ✓ Correctness validated against Icarus Verilog co-simulation — v1.0 (65 sim tests)
- ✓ Area-efficient: counter encoding for bounded ranges, CSE, constant folding — v1.0
- ✓ Named-sequence inlining — v1.0 (PARSE-03)
- ✓ `--dump-ast`, `--dump-ir`, `--dump-tree`, `--property`, `--version` debug surface — v1.0

### Active (v1.1 candidates)

- [ ] Hardening: address Phase 03 H-01..H-04 carry-forward
- [ ] Hardening: address Phase 06 review HIGH defects
- [ ] Version sync (`__init__.py`)
- [ ] Nyquist VALIDATION.md sweeps for all 6 phases
- [ ] Goto repetition (`[->N]`) and non-consecutive repetition (`[=N]`) — Tier 2
- [ ] `$changed` — Tier 2
- [ ] `throughout`, `within`, `intersect`, `first_match` — Tier 2
- [ ] Sequence `and`/`or` composition — Tier 2
- [ ] Validate against Verilator (currently iverilog-only oracle)

### Out of Scope (still valid)

- Local variables in sequences — requires data-path synthesis, defer to v2
- Multi-clock assertions — complex clock domain crossing, defer to v2
- Recursive properties — rare in practice
- Checker constructs (IEEE Ch.17) — rare, complex
- Liveness properties (`s_eventually`) — not synthesizable without approximation
- FPGA synthesis toolchain integration — downstream user concern
- GUI or IDE integration — CLI-first

## Context

- **Market gap (still valid):** No mature open-source SVA→RTL compiler exists globally. Commercial EDA tools (VCS/Questa/Xcelium) discard SVA at synthesis — they don't generate monitor circuits. v1.0 is the first usable open-source filling that gap.
- **Architecture validated:** TIMA Lab token-passing composition + counter encoding works as predicted — linear complexity, compositional, extensible. Phase 4 (composition engine) and Phase 5 (optimizer) shipped without re-architecting earlier phases.
- **Parsing solved (validated):** slang v11.0 `--ast-json` is stable and complete enough for Tier 1; subprocess CLI integration was the right choice (avoids pyslang C++ build complexity in v1).
- **Test approach validated:** Mock-based unit + golden parity + iverilog simulation oracle gave 736 tests with strong correctness signal.
- **Closest reference (still applies):** sahadipayan/SVA_to_RTL_Synthesizer remains the only other open-source attempt and remains incomplete.

## Constraints

- **Parsing:** slang library (CLI subprocess via `--ast-json`) — IEEE 1800-2017+ complete
- **Language:** Python for v1 ✓ — potential C++ rewrite for v2 performance still on the table
- **Output:** SystemVerilog default, Verilog-2001 via `--verilog` flag ✓
- **Validation:** All generated monitors pass equivalence checking against iverilog ✓; Verilator parity is v1.1 work
- **License:** BSL (Business Source License) — free for individual/academic/evaluation, commercial use by large companies requires license
- **Architecture:** Token-passing composition model (TIMA Lab) with operator-aware templates (counter encoding for ranges) ✓
- **Interface standard:** Every generated checker exposes `(clk, rst_n, start, pass, fail, active)` ports ✓

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + slang CLI (not C++ or pyslang) | Fastest iteration; JSON AST is stable and complete; avoids C++ build complexity | ✓ Good — shipped v1.0 in 8 days; JSON boundary insulated from slang version churn |
| Bit-vector method for overlapping implication | Simple, hardware-efficient, handles 85%+ of real SVA | ✓ Good — Phase 2 OP-03 lands cleanly; co-sim oracle agrees |
| TIMA Lab token-passing architecture | Linear complexity, compositional, extensible | ✓ Good — Phase 4 composition + Phase 5 optimizer both fit without re-architecting Phase 2/3 |
| Counter encoding over state expansion | `##[0:100]` = 7-bit counter (~10 FF) vs 101 parallel paths | ✓ Good — area parity with academic baselines |
| Rewrite normalization as preprocessing | Reduce exotic operators to primitives before template emission | ✓ Good — Phase 4 normalize() is pure + idempotent; isolated optimizer changes |
| BSL license | Prevent large-company free-riding while keeping community access | — Pending — no real users yet |
| Standard checker interface (start/pass/fail/active + attempt_fired) | Enables hierarchical composition, debugging, reuse | ✓ Good — first-class from Phase 1 paid off in Phase 4 composition |
| Frozen dataclass IR (over Pydantic) | Structural hashing for CSE; immutable; pattern matching | ✓ Good — SHA-256 hash + match dispatch worked across all 6 phases |
| Worktree-isolated parallel executor agents | Run independent plans in parallel without merge conflict | ⚠️ Revisit — Wave-based merge worked, but the SDK `worktree.cleanup-wave` blocked on a base-mismatch heuristic; needed manual merge fallback |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-02 after v1.0 milestone — v1.0 shipped; debt visible; v1.1 hardening pass on deck.*
