---
phase: 06-cli-polish-verilog-2001-integration-testing
plan: 02
subsystem: rtl-emitter
tags: [verilog-2001, jinja2, templates, emitter, iverilog, OUT-05]

# Dependency graph
requires:
  - phase: 01
    provides: emitter scaffold + bool_expr template
  - phase: 02
    provides: concat_delay / overlap_bitvec / nonoverlap templates
  - phase: 03
    provides: rose / fell / stable / past / rep_consecutive / disable_iff_top templates
  - phase: 04
    provides: seq_concat_top template + composition engine
provides:
  - verilog_mode keyword-only parameter on emit() / emit_all() / _emit_recursive() / emit_bind()
  - Jinja2 {% if verilog_mode %} guards on all 11 RTL templates (every template that emits a module)
  - Verilog-2001 emission rules: input/output drop logic, internal logic → reg or wire by context, always_ff → always @(...), '0 → 0
  - tests/test_verilog_mode.py with 121 parametrized assertions across 16 fixtures
affects: [06.1-cli, 06.3-integration-tests, release, ci]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single-source-of-truth template guards: one .sv.j2 file emits both SV and Verilog-2001 via {% if verilog_mode %}"
    - "Output ports stay typeless in Verilog-2001 (driven by assign, so wire-default is correct)"
    - "Multi-bit '0 → 0 (auto-sizing); 1'b0 untouched (valid in both standards)"

key-files:
  created:
    - tests/test_verilog_mode.py
  modified:
    - src/sva2rtl/emitter.py
    - templates/bool_expr.sv.j2
    - templates/concat_delay.sv.j2
    - templates/overlap_bitvec.sv.j2
    - templates/nonoverlap.sv.j2
    - templates/rose.sv.j2
    - templates/fell.sv.j2
    - templates/stable.sv.j2
    - templates/past.sv.j2
    - templates/rep_consecutive.sv.j2
    - templates/seq_concat_top.sv.j2
    - templates/disable_iff_top.sv.j2

key-decisions:
  - "Apply Verilog-2001 conversion via Jinja2 conditional guards rather than maintaining a parallel template set — single source of truth, lower drift risk"
  - "Replace '0 with bare 0 instead of {WIDTH{1'b0}} — Verilog-2001 zero-extends 0 across <= assignments and matches the LHS reg width without producing iverilog -g2001 warnings"
  - "Outputs stay as `output X` (no `output reg`) because every output in every template is `assign`-driven from an internal *_q register"
  - "verilog_mode is keyword-only (* in signature) to make miscall obvious at the call site"

patterns-established:
  - "Verilog-2001 conversion matrix: ports drop type, internal regs use `reg`, internal assign-driven signals use `wire`, always_ff → always @(...)"
  - "Test parametrization across all 16 representative fixtures rather than per-operator handcrafted cases — catches keyword leakage everywhere"

requirements-completed:
  - OUT-05

# Metrics
duration: pre-merged-in-base
completed: 2026-06-01
---

# Phase 06, Plan 02: Verilog-2001 Output Mode Summary

**Verilog-2001 emission threaded through emit()/emit_all()/_emit_recursive()/emit_bind() with Jinja2 {% if verilog_mode %} guards on all 11 RTL templates; 121 assertions verify zero `logic`/`always_ff`/`'0` leakage and that SV mode is byte-for-byte unchanged.**

## Performance

- **Duration:** Already merged into the worktree base (`6b2ef28`); no new task commits required from this executor
- **Started:** 2026-06-01 (orchestration sweep)
- **Completed:** 2026-06-01
- **Tasks:** 7 (all 7 plan tasks satisfied in upstream commit `08c6ff0`)
- **Files modified:** 12 (emitter + 11 templates) + 1 created (tests/test_verilog_mode.py)

## Accomplishments

- `verilog_mode: bool = False` keyword-only parameter threaded through `emit()`, `emit_all()`, `_emit_recursive()`, and `emit_bind()` (Task 6.2.1)
- All 11 module-emitting templates accept `verilog_mode` and produce iverilog-`-g2001`-clean output:
  - `bool_expr` (3 guards), `concat_delay` (3), `overlap_bitvec` (4), `nonoverlap` (4), `rose` (4), `fell` (4), `stable` (4), `past` (7), `rep_consecutive` (4), `seq_concat_top` (2), `disable_iff_top` (3) (Tasks 6.2.2 – 6.2.6)
- `tests/test_verilog_mode.py` adds 121 parametrized assertions over 16 fixtures verifying:
  - No `logic` token outside comments
  - No `always_ff`
  - No tick-zero (`'0`) literal
  - At least one `always @(posedge|negedge ...)` block in every fixture with sequential logic
  - Default-mode (verilog_mode=False) output is byte-for-byte identical to the no-kwarg invocation (golden parity)
  - `wire` declarations exist for assign-driven internals; `reg` declarations exist for sequential internals
  - Output ports carry no `logic` qualifier; input ports carry no `logic` qualifier (Task 6.2.7)

## Task Commits

The 7-task plan was executed atomically in a single upstream commit on the canonical branch — that commit is part of this worktree's base ancestry and was not re-created here:

1. **Tasks 6.2.1 – 6.2.7 (combined)** — `08c6ff0` (`feat(emitter): add Verilog-2001 output mode (--verilog flag)`)
   - 13 files / +725 lines: emitter.py + 11 templates + tests/test_verilog_mode.py

**Plan metadata commit:** This SUMMARY.md is the only artifact this executor adds; STATE.md / ROADMAP.md remain untouched per orchestrator protocol.

## Files Created/Modified

- `src/sva2rtl/emitter.py` — added `verilog_mode: bool = False` keyword-only param to `emit`, `emit_all`, `_emit_recursive`, `emit_bind`; added `ctx["verilog_mode"] = verilog_mode` in all three context builders
- `templates/bool_expr.sv.j2` — guards for ports, `wire bool_result`, `reg active_q/pass_q/fail_q/attempt_fired_q`, `always @(...)`
- `templates/concat_delay.sv.j2` — guards for ports, `reg [CNT_WIDTH-1:0] count_q`, `reg running_q/attempt_fired_q`, `always @(...)`, `count_q <= 0`
- `templates/overlap_bitvec.sv.j2` — port guards, reg/wire split for `bv_q/overflow_flag_q/attempt_fired_q` vs `ant_pass_w/con_pass_w/...`, zero-literal fix
- `templates/nonoverlap.sv.j2` — same pattern as overlap_bitvec
- `templates/rose.sv.j2`, `fell.sv.j2`, `stable.sv.j2` — port guards, `reg sig_prev_q/attempt_fired_q`, `wire *_detect/_internal`, `always @(...)`
- `templates/past.sv.j2` — port guards, conditional reg/wire split for both depth==1 and depth>1 paths, `shift_q <= 0`
- `templates/rep_consecutive.sv.j2` — port guards, `reg count_q/running_q/attempt_fired_q`, `always @(...)`, zero-literal fix
- `templates/seq_concat_top.sv.j2` — port guards only (wire-only top, no registers)
- `templates/disable_iff_top.sv.j2` — port guards, `wire cond_result/effective_disable`
- `tests/test_verilog_mode.py` (NEW) — 121 parametrized assertions exceeding the plan's 8-test target

## Decisions Made

- **Conditional guards over duplicate templates:** Phase 06 CONTEXT D-01 mandates a single source of truth; chose `{% if verilog_mode %}` blocks within each .sv.j2 rather than a parallel `templates_v2001/` tree to prevent SV-vs-Verilog-2001 drift.
- **`'0 → 0` (not `{WIDTH{1'b0}}`):** Verilog-2001 zero-extends `0` to LHS reg width on `<=` assignments without warnings under `iverilog -g2001`, and is the most readable conversion. `1'b0` is left untouched in both modes.
- **Outputs stay typeless:** Every output port in every template is `assign`-driven from an internal `_q` register, so `output X` (wire-default) is sufficient — no `output reg` is needed anywhere.

## Deviations from Plan

**None — the upstream commit fulfills every acceptance criterion in tasks 6.2.1 through 6.2.7 byte-for-byte.**

The only nominal deviation is collapsing — the seven plan tasks were committed as one upstream commit (`08c6ff0`) rather than seven sequential commits. Because that commit is part of this worktree's base ancestry, no atomic re-commit is feasible without rewriting history. The acceptance criteria are all met:

- emit/emit_all/_emit_recursive/emit_bind signatures include `*, verilog_mode: bool = False` ✅
- `mypy --strict src/sva2rtl/emitter.py` exits 0 ✅
- All 11 templates render without error in Verilog-2001 mode and contain no `logic`/`always_ff`/`'0` ✅
- SystemVerilog-mode output is byte-for-byte identical to pre-change output (golden parity passes — `tests/test_golden_parity.py` 16/16 PASS) ✅
- `tests/test_verilog_mode.py` PASS (121/121) ✅
- `tests/test_emitter.py` PASS ✅
- `uv run ruff check src/ tests/` clean ✅

## Issues Encountered

- **Cold uv environment timed out fetching hatchling from PyPI** (network constraint in the sandbox). Worked around by using the pre-built `/Users/allenenli/Documents/formal_sva_rtl/.venv` interpreter directly with `PYTHONPATH=src` for verification — same Python 3.12 + same pinned package set that `uv sync` would install.

## Verification Run

```
PYTHONPATH=src .venv/bin/python -m pytest tests/test_verilog_mode.py tests/test_golden_parity.py tests/test_emitter.py -q
→ 192 passed in 0.93s

PYTHONPATH=src .venv/bin/python -m mypy --strict src/sva2rtl/emitter.py
→ Success: no issues found in 1 source file

PYTHONPATH=src .venv/bin/python -m ruff check src/ tests/
→ All checks passed!

iverilog -g2001 compile sweep on emitted Verilog-2001 from 9 representative fixtures
(bool_simple, rose, past, rep_fixed, delay_fixed, implication_overlap,
 implication_nonoverlap, implication_bitvec, disable_iff)
→ 24 emitted .v files compile clean (no warnings, no errors)
```

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **OUT-05 satisfied** — `--verilog` flag (Plan 6.1) can rely on `emit(..., verilog_mode=True)` and `emit_all(..., verilog_mode=True)`
- **Plan 6.3 (integration tests) ready to consume** — `_run_pipeline_verilog()` helper in `tests/test_verilog_mode.py` is the canonical pattern integration tests should reuse for `--verilog` end-to-end coverage
- **No blockers** — emitter API is stable and backward-compatible (default `verilog_mode=False` matches all pre-Phase-6 callers)

---
*Phase: 06-cli-polish-verilog-2001-integration-testing*
*Plan: 02 — Verilog-2001 Output Mode*
*Completed: 2026-06-01*
