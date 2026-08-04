---
status: resolved
trigger: "Fix exact-SHA CI failures after all Icarus tests passed."
created: 2026-08-04
updated: 2026-08-04
---

# Debug Session: CI Python Matrix and Skip Budget

## Symptoms

- All four Icarus jobs completed their test step successfully, but the outcome
  gate rejected `1509 passed, 228 skipped` against a stale 185-skip cap.
- Forty-four formal tests used the explicit full-toolchain skip reason, but that
  reason was absent from the ordinary CI allowlist.
- A nominal Python 3.13 job installed 3.13 and then `uv sync` selected the
  repository-default Python 3.12 interpreter, so the matrix label overstated
  the interpreter actually exercised.

## Root Cause

The ordinary Icarus gate had not been updated when real-solver formal tests were
added. Separately, the matrix installed its selected Python but did not pass that
selection to `uv sync`, allowing `.python-version` to choose 3.12.

## Resolution

- Raise the ordinary Icarus pass floor from 1325 to 1500 and set the current
  explicit skip ceiling to 228.
- Allow only the enumerated missing-full-formal-toolchain skip reasons for the
  shared solver stack, liveness cover stack, no-op AIG preparation, and local
  safety stack. The 228 ceiling remains exact, and Full Formal retains zero
  toolchain skips, so this does not replace solver execution.
- Set `UV_PYTHON` for the complete matrix job, sync with
  `--python ${{ matrix.python }}`, and lock both requirements with a workflow
  regression test. This keeps later `uv run` steps from returning to the
  repository-default interpreter.

## Verification

Focused workflow tests, both explicit Python 3.12 and 3.13 environments, the
complete local gates, and replacement exact-SHA remote CI/nightly/Full Formal
must pass before release qualification.
