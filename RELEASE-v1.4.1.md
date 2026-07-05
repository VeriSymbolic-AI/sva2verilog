# sva2rtl v1.4.1 Release Notes

**Release date:** 2026-07-01
**Type:** Feature release — multi-clock path-one

v1.4.1 adds **multi-clock SVA support** (restricted subset = SVA standard's full
multi-clock set) using a split-and-synchronize compilation approach (Gawanmeh &
Tahar, 2009). Each `@(clk_i)` sub-sequence compiles to a single-clock sub-checker
reusing the full Tier 1/2/3 pipeline; cross-clock `##1` boundaries are connected
by a standard 2-DFF synchronizer treated as a trusted base component.

## Summary

| Area | Change |
|------|--------|
| Version | Bumped to `1.4.1` |
| Multi-clock sequence | `@(clk1) a ##1 @(clk2) b` — per-domain checkers + 2-DFF sync |
| Multi-clock implication | `@(clk1) a |=> @(clk2) b` — antecedent sync→consequent |
| Multi-stage chaining | 3+ clock domains transitively composed |
| Architecture | IR `ClockedSeq` for clock-domain boundaries; composer splits by domain; `mc_seq_top` multi-clock emitter with per-domain clock ports |
| 2-DFF synchronizer | `sync_2dff.sv.j2` trusted component (structural checks, no formal metastability proof) |
| Blacklist | Overlapping `|->` cross-clock, multi-clock intersect/within/throughout, `##N` (N≠1) cross-clock — all cleanly rejected |
| Incidental fix | Enabled live-slang `|->`/`|=>` via v11 `Binary` implication arm (stale xfail removed) |
| Tests | 982 passed, 4 skipped, 4 xfailed; ruff 0 |

## Multi-clock support

**Whitelist (= SVA standard's full multi-clock set):**

| Mode | SVA | Description |
|------|-----|-------------|
| Sequence | `@(clk1) a ##1 @(clk2) b` | Per-domain sub-checkers, 2-DFF sync on token |
| Implication | `@(clk1) a \|=> @(clk2) b` | Antecedent→sync→consequent |
| Multi-stage | `@(clk1) ... ##1 @(clk2) ... ##1 @(clk3) ...` | Transitive domain composition |

**Verification boundary:** Per-domain sub-checkers retain the full verification
stack (iverilog+Verilator, behavioral oracle, SymbiYosys formal equivalence). The
cross-clock 2-DFF synchronizer is verified by structural checks (instantiated,
wired correctly, 2 dst-clock latency). Full multi-clock formal equivalence is NOT
attempted (industry-wide limitation, DVCon 2024).

**Trusted component:** The `sync_2dff` template carries explicit warning comments.
No metastability formal proof is provided. FPGA prototype or post-silicon
validation is recommended for timing closure.

## Technical highlights

- **Single-clock byte-identical:** The refactored `compose()` dispatcher preserves
  exact golden-parity for all 62 single-clock goldens.
- **Incidental fix:** Added the v11 `Binary` implication kind to the top-level
  dispatcher — live-slang `|->`/`|=>` now work without a fixture. A stale `xfail`
  in `test_formal_passes` was removed as a result.
- **Delay extraction fix:** Multi-clock SeqConcat stores the cross-boundary `##1`
  on the Clocking element (not the previous element); `_build_seq_concat` now
  correctly reads it.

## Known limitations (carried forward)

- Liveness operators nested under implication consequent — rejected (v1.5).
- `intersect`/`within` with boolean operands — RISK-02 oracle boundary.
- Multi-clock formal equivalence — permanently excluded (see above).
- Multi-clock LFSR metastability injection — deferred to v1.4.2 (Path Two).

## Test status

982 passed, 4 skipped, 4 xfailed. ruff 0 errors across `src/` / `tests/` / `tools/`.
