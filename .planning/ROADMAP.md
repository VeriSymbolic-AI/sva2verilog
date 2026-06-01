# Roadmap: sva2rtl

## Milestones

- ✅ **v1.0 MVP** — SVA→RTL Compiler — Phases 1-6 (shipped 2026-06-01) — see [.planning/milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
- 📋 **v1.1** (planning) — hardening + Phase 03 H-01..H-04 carry-forward + Phase 06 review HIGH defects + Nyquist coverage

## Phases

<details>
<summary>✅ v1.0 MVP — SVA→RTL Compiler (Phases 1-6) — SHIPPED 2026-06-01</summary>

- [x] Phase 1: Foundation — IR + Slang Frontend + Boolean Assert → SV Monitor (5/5 plans) — completed 2026-05-25
- [x] Phase 2: Core Sequential Operators — `##N`, `##[M:N]`, `|->`, `|=>` (3/3 plans) — completed 2026-05-26
- [x] Phase 3: Remaining Tier 1 Operators + Named Sequences + Simulation Validation (4/4 plans) — completed 2026-05-27
- [x] Phase 4: Normalization + Composition Engine (3/3 plans) — completed 2026-05-28
- [x] Phase 5: Optimization Passes (3/3 plans) — completed 2026-05-28
- [x] Phase 6: CLI Polish + Verilog-2001 + Integration Testing (3/3 plans) — completed 2026-06-01

</details>

### 📋 v1.1 (Planning)

Hardening cycle before public release. To be defined via `/gsd:new-milestone`.

Likely scope (from v1.0 milestone audit):
- Phase 03 H-01..H-04 carry-forward (`_DECLARATIONS` global reset, `rep_consecutive` silent miss, `attempt_fired_q` cleared by `disable_i`, `_collect_signals` dropping `sig_name`)
- Phase 06 code-review HIGH defects (multi-property `--dump-tree`, `--property` unlabeled-assertion match, `--output` file-vs-directory ambiguity, `--verilog` ignored by `--dump-*`, Verilog-2001 template body duplication)
- Version sync (`__init__.py` → 1.0.0)
- Nyquist coverage sweeps for all 6 phases
- Tier 2 SVA operators (per v2 backlog)

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 5/5 | Complete | 2026-05-25 |
| 2. Core Sequential Operators | v1.0 | 3/3 | Complete | 2026-05-26 |
| 3. Remaining Tier 1 + Sim Validation | v1.0 | 4/4 | Complete | 2026-05-27 |
| 4. Normalization + Composition Engine | v1.0 | 3/3 | Complete | 2026-05-28 |
| 5. Optimization Passes | v1.0 | 3/3 | Complete | 2026-05-28 |
| 6. CLI Polish + Verilog-2001 + Integration Testing | v1.0 | 3/3 | Complete | 2026-06-01 |

---

*v1.0 archived: 2026-06-01 — see `.planning/MILESTONES.md` and `.planning/milestones/v1.0-*` for full historical detail.*
