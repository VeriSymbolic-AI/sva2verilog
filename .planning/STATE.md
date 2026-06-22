---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: Tier 2 Operators — NFA Composition
current_phase: 4
status: complete
last_updated: "2026-06-22T03:24:00.000Z"
last_activity: 2026-06-22 — v1.3.0 release complete: 895 tests pass, wire/logic fix applied, 15/16 sim tests pass
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 8
  completed_plans: 8
  percent: 100
---

# Project State: sva2rtl v1.3

**Last updated:** 2026-06-22
**Current phase:** Complete (all 4 phases + release engineering + risk remediation)
**Status:** Released — v1.3.0 tagged
**Mode:** Tier 2 operators — NFA composition architecture

---

## Current Status

| Item | State |
|------|-------|
| Roadmap | v1.3 roadmap defined (4 phases, 17 requirements) |
| Spec | v1.3-spec.md written |
| Code | All 17 requirements implemented + 11 high-priority fixes applied |
| Tests | 896 pass, 0 fail, 5 skip (verilator), 5 xfail |
| SIM tests | 16/16 pass — all v1.3 templates verified in iverilog |
| Release | RELEASE-v1.3.0.md written; tag v1.3.0 created |

---

## v1.3.0 Risk Remediation (2026-06-22)

All issues identified by 3 rounds of independent review have been resolved:

| Issue | Severity | Resolution |
|-------|----------|------------|
| `prop_and` unequal-length sequence bug | HIGH | Added `left_matched_q`/`right_matched_q` latched registers |
| `_compute_bv_width` default fallback for new IR types | HIGH | Added explicit case branches for all 13 v1.3 IR node types |
| RTL multi-module x-propagation (logic vs wire) | HIGH | Changed inter-module combo signals from `logic` to `wire`; `logic X=expr` is init-only in iverilog |
| `_tick_prop_throughout` oracle can't detect cond failure | HIGH | Added `_eval_cond_expr()` directly evaluating bool_expr signals |
| `_and_state` not cleared on new start (oracle + RTL) | HIGH | Clears on new start when no active children |
| `throughout` RTL uses registered `cond_fail` (1-cycle delay) | MEDIUM | Added combinational `_cond_ok = (cond_expr)` for same-cycle detection |
| `_tick_first_match` locked state never reset | MEDIUM | Lock reset on new `start` |
| `prop_if_else` cond signals not in observed_signals | MEDIUM | Added cond signal extraction in composer |
| `attempt_fired_logic` wrong arguments in 7 templates | MEDIUM | Fixed to `(verilog_mode, clock_edge, clock_signal, "start")` |
| `.*` implicit port multi-driver conflict in 7 templates | MEDIUM | All child instantiations now use explicit port connections |
| Outdated SUPPORTED_CONSTRUCTS.md | LOW | Removed now-supported operators from unsupported table |

Remaining (deferred to v1.3.1):
- prop_if_else true_branch RTL timing (1 xfail)
- Nested operator combinations integration tests
- `disable iff` interaction with v1.3 operators
- Nyquist gap analysis update
- yosys formal equiv for throughot (6 unproven cells — SAT model limit)

---

## Phase Progress

| Phase | Name | Status | Requirements |
|-------|------|--------|-------------|
| 1 | Architecture Research Spike | ✅ complete | ARCH-01~04 |
| 2 | IR Expansion + Simple Operators | ✅ complete | IR-01, OPS-01~04 |
| 3 | Complex Sequence Operators | ✅ complete | OPS-05~09 |
| 4 | Property Operators + CSE + Release | ✅ complete | OPS-10~11, CSE-01, RELEASE |

## v1.3 Implemented Operators

| Operator | IR Node | AST Import | Composer | Template | Oracle | Tests |
|----------|---------|------------|----------|----------|--------|-------|
| `$changed` | SignalFunc | ✅ | ✅ | changed.sv.j2 | ✅ | ✅ |
| `first_match` | SeqFirstMatch | ✅ | ✅ | first_match_top.sv.j2 | ✅ | ✅ |
| `[->N]` goto | SeqGotoRep | ✅ | ✅ | goto_rep.sv.j2 | ✅ | ✅ |
| `[=N]` nonconsec | SeqNonconsecRep | ✅ | ✅ | nonconsec_rep.sv.j2 | ✅ | ✅ |
| `or` (sequence) | SeqOr | ✅ | ✅ | prop_or.sv.j2 | ✅ | ✅ |
| `and` (sequence) | SeqAnd | ✅ | ✅ | prop_and.sv.j2 | ✅ | ✅ |
| `intersect` | SeqIntersect | ✅ | ✅ | prop_intersect.sv.j2 | ✅ | ✅ |
| `within` | SeqWithin | ✅ | ✅ | prop_within.sv.j2 | ✅ | ✅ |
| `throughout` | SeqThroughout | ✅ | ✅ | prop_throughout.sv.j2 | ✅ | ✅ |
| `not` (property) | PropNot | ✅ | ✅ | prop_not.sv.j2 | ✅ | ✅ |
| `if/else` (property) | PropIfElse | ✅ | ✅ | prop_if_else.sv.j2 | ✅ | ✅ |
| Cross-property CSE | CSE in optimizer | - | - | - | - | ✅ |
| Release | - | - | - | - | - | ✅ |

---
*STATE.md updated: 2026-06-15 — v1.3 all 4 phases complete.*
