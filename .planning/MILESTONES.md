# Milestones

## v1.0 MVP — SVA→RTL Compiler (Shipped: 2026-06-01)

**Phases completed:** 6 phases, 21 plans, 87 tasks
**Tag:** `v1.0`
**Codebase:** ~4.0K LOC src + ~10.7K LOC tests + ~1.2K LOC Jinja2 templates
**Timeline:** 2026-05-25 → 2026-06-01 (8 days)
**Tests at ship:** 736 passed, 17 skipped (slang-only tests)

### Delivered

A working open-source SVA→synthesizable-RTL compiler. `sva2rtl <file.sv>` parses SystemVerilog Assertions via slang, normalizes a frozen-dataclass IR, composes a token-passing CheckerNode tree, runs an optimization pipeline (constant fold + concat merge + CSE + counter merge + dead-node elimination), and emits SystemVerilog or Verilog-2001 monitor modules with the standard `(clk, rst_n, start, pass, fail, active)` interface. CI matrix on Ubuntu/macOS × Py 3.12/3.13 with iverilog and slang prebuilt binaries.

### Key Accomplishments

- **Phase 1 — Foundation:** Frozen-dataclass SVA IR (BoolExpr, SeqConcat, PropImplication, SourceLoc, ClockSpec, CheckerNode) + slang subprocess wrapper + AST importer + click CLI + Jinja2 emitter; bool_expr golden tests; precise exit codes (0/1/2/3).
- **Phase 2 — Core Sequential Operators:** `##N` shift-register/counter, `##[M:N]` counter+window, `|->` bit-vector overlap, `|=>` non-overlap implication; oracle-validated against iverilog.
- **Phase 3 — Tier 1 Operators + Sim Validation:** `[*N]` counted FSM, `$rose`/`$fell`/`$stable`/`$past` edge-detect FFs, `disable iff` async gating, named-sequence inlining, full simulation oracle harness (65 sim tests).
- **Phase 4 — Normalization + Composition Engine:** Pure IR normalize() pass + token-passing CheckerNode tree composition + SHA-256 structural hash for CSE; 478 tests pass with zero golden regressions.
- **Phase 5 — Optimization Passes:** `constant_fold`, `concat_merge`, `cse`, `counter_merge`, `dead_node` to fixed point; `--no-optimize` flag; 540 tests pass.
- **Phase 6 — CLI Polish + Verilog-2001 + CI:** `--dump-ast`/`--dump-ir`/`--dump-tree`/`--property`/`--verilog`/`--version` flags + multi-property pipeline + Verilog-2001 templates with `verilog_mode` Jinja2 guards (iverilog -g2001 clean) + GitHub Actions CI matrix + `pyproject` v1.0.0 release metadata; 736 tests pass.

### Requirements Coverage

40/40 v1 requirements satisfied. See [milestones/v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md) for full traceability.

### Audit Result

`tech_debt` — no blockers. See [milestones/v1.0-MILESTONE-AUDIT.md](milestones/v1.0-MILESTONE-AUDIT.md):
- 14/14 cross-phase integration seams clean
- E2E pipeline verified end-to-end
- Known deferred debt: 24 advisory code-review findings on Phase 06, Phase 03 H-01..H-04 carry-forward (now duplicated in Verilog-2001 template branches), version mismatch (`__init__.py` 0.1.0 vs `pyproject` 1.0.0), and missing Nyquist VALIDATION.md sweeps for all 6 phases. All deferred to v1.1.

### Known Deferred Items

- **Phase 03 carry-forward (H-01..H-04):** `_DECLARATIONS` global not reset between assertions, `rep_consecutive` silent miss, `attempt_fired_q` cleared by `disable_i` (now duplicated across both Verilog-2001 template branches in 11 templates), `_collect_signals` discarding `sig_name`.
- **Phase 06 review HIGH:** multi-property `--dump-tree` drops `unoptimized_checker`; `--property` cannot match unlabeled assertions; `--output` file-vs-directory ambiguous; `--verilog` silently ignored by `--dump-*`; Verilog-2001 always-block bodies duplicated 22× across 11 templates.
- **Nyquist coverage:** No VALIDATION.md exists in any phase. Run `/gsd:validate-phase {N}` retroactively in v1.1.

---
