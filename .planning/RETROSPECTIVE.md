# Retrospective — sva2rtl

A living document. Each milestone adds a new section. Cross-milestone trends accumulate at the bottom.

---

## Milestone: v1.0 — MVP — SVA→RTL Compiler

**Shipped:** 2026-06-01
**Phases:** 6 | **Plans:** 21 | **Tasks:** 87
**Codebase at ship:** ~4.0K LOC src + ~10.7K LOC tests + ~1.2K LOC Jinja2 templates
**Tests at ship:** 736 passed, 17 skipped (slang-only)
**Timeline:** 2026-05-25 → 2026-06-01 (8 days)

### What Was Built

- **Phase 1 — Foundation:** Frozen-dataclass SVA IR, slang `--ast-json` subprocess wrapper, JSON→IR translator with source-location threading, click CLI with precise exit codes (0/1/2/3), Jinja2 emitter, bool_expr golden tests.
- **Phase 2 — Core Sequential Operators:** `##N`, `##[M:N]`, `|->` (bit-vector), `|=>` operators with iverilog oracle validation.
- **Phase 3 — Tier 1 Operators + Sim Validation:** `[*N]` counted FSM, `$rose`/`$fell`/`$stable`/`$past` edge-detect FFs, `disable iff` async gating, named-sequence inlining, simulation oracle harness (65 sim tests).
- **Phase 4 — Normalization + Composition Engine:** Pure `normalize()` IR pass + token-passing CheckerNode tree + SHA-256 structural hash; 478 tests with zero golden regressions.
- **Phase 5 — Optimization Passes:** `constant_fold`, `concat_merge`, `cse`, `counter_merge`, `dead_node` to fixed point; `--no-optimize` flag.
- **Phase 6 — CLI Polish + Verilog-2001 + Integration Testing:** `--dump-ast`/`--dump-ir`/`--dump-tree`/`--property`/`--verilog`/`--version` flags; multi-property pipeline; Verilog-2001 templates with `verilog_mode` Jinja2 guards (iverilog -g2001 clean across 24 emitted modules); GitHub Actions CI matrix; pyproject.toml v1.0.0 release metadata.

### What Worked

- **Vertical-MVP slicing.** Every phase produced a working end-to-end pipeline. Phase 1 already compiled boolean assertions all the way to RTL — later phases extended without rewriting. Cross-phase integration audit found 14/14 seams clean.
- **Frozen-dataclass IR + match/case dispatch.** Structural hashing for CSE fell out for free; pattern-matching on `kind` made every visitor read like a spec. Zero hash collisions across 540 tests.
- **TIMA Lab token-passing composition.** Linear complexity held up; Phase 4's composition engine + Phase 5's optimizer slotted in without disturbing Phase 2/3 operator templates.
- **slang CLI subprocess (not pyslang).** JSON `--ast-json` gave us a stable schema boundary. We never had to touch pyslang's C++ build during v1.
- **Mock-based CLI tests + iverilog simulation oracle.** Mock layer kept unit tests slang-independent (still pass without slang installed); simulation oracle layer caught real RTL bugs that golden-text comparison alone would have missed.
- **Counter encoding over state expansion.** `##[0:100]` is 7-bit counter (~10 FF) instead of 101 parallel paths. Hard architectural commitment paid off in test_golden_parity stability.
- **GSD wave-based parallel execution.** Phase 6 ran two non-overlapping plans (CLI flags + Verilog-2001 templates) in parallel git worktrees, then a sequential third plan (integration tests). Total wall-clock cut roughly in half.

### What Was Inefficient

- **Plan filename drift.** Phase 6 plans were initially `PLAN-6.1.md` / `PLAN-6.2.md` / `PLAN-6.3.md` — the SDK's phase-plan-index expected `01-PLAN.md` / `02-PLAN.md` / `03-PLAN.md`. Required a rename + frontmatter-position fix mid-execution. Cost ~10 minutes of manual git-mv + edit.
- **`gsd-sdk worktree.cleanup-wave` was overly strict.** It rejected merging worktree branches whose merge-base was the expected base because the worktree's HEAD had moved past that base. Required falling back to manual `git merge` — fine, but the SDK helper should've recognized that case as safe.
- **Code review surfaced ~30 advisory findings post-ship.** Most are real (5 HIGH that affect UX), and Phase 6's Verilog-2001 broadening *duplicated* the Phase 03 H-03 defect (`attempt_fired_q` cleared by `disable_i`) across 22 template branches. Earlier code-review checkpoints (per-plan, not just per-phase) would have prevented the multiplication.
- **Nyquist coverage zero.** `workflow.nyquist_validation: true` is on, but no `*-VALIDATION.md` was ever generated for any phase. Need to bake `/gsd:validate-phase` into the per-phase chain or accept it as retroactive cleanup.
- **MILESTONES.md auto-extracted accomplishment lines included markdown noise** (literal `Plan`, `Phase:`, `Status: COMPLETE` rows from SUMMARY.md headings). Hand-rewrote after archival.

### Patterns Established

- **Frontmatter-first plan files.** YAML frontmatter at the top, title H1 after — this is what `gsd-sdk phase-plan-index` parses, and the title-first variant silently loses `wave:` and `depends_on:`.
- **Frozen dataclasses + match/case > Pydantic for compiler IR.** Faster, hashable, less ceremony.
- **Standard monitor port contract `(clk, rst_n, start, pass, fail, active)` (+ `attempt_fired` debug)** baked from Phase 1, never broken.
- **Two-track validation:** golden-file regression tests for byte-for-byte stability; iverilog simulation oracle for behavior. Both required; either alone is insufficient.
- **`verilog_mode` Jinja2 guard pattern.** One template, two output modes — keeps SV-by-default unchanged. Cost is body duplication; acceptable for v1, due for refactor in v1.1.
- **Wave-grouped parallel execution with files_modified disjointness check.** Plans whose `files_modified` lists are disjoint can run in parallel git worktrees; same-wave overlap forces sequential.

### Key Lessons

1. **Establish the IR + interface contract on a trivial input first.** Phase 1's bool-only end-to-end pipeline made everything else cheap.
2. **JSON AST boundary > in-process binding.** Schema is more stable than the binding library API.
3. **Counter encoding is non-negotiable for bounded ranges.** Two-line decision in Phase 0 saved 10× area on `##[0:N]`.
4. **Verilog-2001 retrofit through Jinja2 guards is cheap to ship but expensive to maintain.** Each future template change is 2× edits. Plan the dedup refactor (`{% include %}` shared body) into v1.1.
5. **Code-review high-severity findings duplicate when broadened.** Catch them at the phase boundary, not the milestone boundary — H-03 went from 11 instances to 22 because Phase 6 doubled the templates before Phase 3's review was addressed.
6. **The SDK helpers (`worktree.cleanup-wave`, `phase.complete`) are useful but not always trustworthy as black boxes.** Always verify the file system state matches what the helper claims to have done.

### Cost Observations

- Model mix: predominantly Sonnet (executor + verifier defaults); some Opus for review/integration check on Phase 6.
- Sessions: 1 long milestone + several focused phase sessions.
- Notable: 8-day calendar time to ship a non-trivial compiler in a domain with no comparable open-source reference.

---

## Cross-Milestone Trends

(Will accumulate as additional milestones ship.)

| Trend | v1.0 | Direction |
|-------|------|-----------|
| Test count at ship | 736 | — |
| Test:src LOC ratio | 2.7× | — |
| Tests per plan (avg) | 35 | — |
| Code-review HIGH findings carried forward | 9 (5 from Ph6 + 4 from Ph3) | Watch in v1.1 |
| Nyquist VALIDATION.md coverage | 0/6 phases | Action: retroactively close in v1.1 |
| Time per phase (calendar) | ~1.3 days | — |

---

*Retrospective started: 2026-06-02. Living document — append at each milestone close.*
