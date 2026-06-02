---
phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor
plan: "02"
subsystem: frontend
tags: [slang, ast-json, subprocess, json-fixture, sva-ir, ast-importer]

requires:
  - phase: 01-plan-01
    provides: ir.py (BoolExpr, ClockSpec, SourceLoc, SVANode), errors.py (SlangNotFound, SvaCompileError, UnsupportedConstruct)

provides:
  - frontend.py — invoke_slang() subprocess wrapper with temp-file JSON capture
  - ast_importer.py — JSON-to-SVA-IR translator (import_assertion, expr_to_sv, extract_source_loc)
  - tests/fixtures/bool_simple.json — slang AST fixture for BinaryPropertyExpr(And)
  - tests/fixtures/bool_labeled.json — fixture with labeled assertion block
  - tests/fixtures/bool_complex.json — fixture with UnaryPropertyExpr(Not) + nested binary
  - tests/fixtures/unsupported_delay.json — SequenceConcat fixture for unsupported-construct tests

affects: [plan-03-emitter, plan-04-cli, plan-05-tests]

tech-stack:
  added: []
  patterns:
    - "slang invoked via subprocess list-form (never shell=True), JSON written to temp file"
    - "expr_to_sv recursive descent with exhaustive match/case + default UnsupportedConstruct"
    - "SourceLoc extracted from every JSON node visited (P5.1 prevention)"
    - "UNSUPPORTED_KINDS_PHASE1 dict for centralized Phase 2+ rejection"

key-files:
  created:
    - src/sva2rtl/frontend.py
    - src/sva2rtl/ast_importer.py
    - tests/test_frontend.py
    - tests/test_ast_importer.py
    - tests/fixtures/bool_simple.json
    - tests/fixtures/bool_labeled.json
    - tests/fixtures/bool_complex.json
    - tests/fixtures/unsupported_delay.json
  modified: []

key-decisions:
  - "JSON written to temp file (not stdout): slang prepends non-JSON status lines to stdout that break json.loads()"
  - "expr_to_sv wraps every binary node in parentheses to prevent precedence bugs in generated RTL (P8.2)"
  - "Clock extracted from PropertySpec.clocking field, not guessed from module ports (P8.4)"
  - "Default match case raises UnsupportedConstruct — never silent skip (P8.1)"
  - "Block label extraction: split 'ADDRESS label_name' on first space, take index 1"

patterns-established:
  - "Fixture JSON mirrors actual slang --ast-json schema with source location fields on every node"
  - "Frontend tests use unittest.mock.patch on subprocess.run and builtins.open"
  - "AST importer tests load actual fixture JSON files from tests/fixtures/"

requirements-completed: [PARSE-01, PARSE-02, PARSE-04, CLI-06]

duration: 25min
completed: 2026-05-25
---

# Phase 1 Plan 02: Slang Frontend + AST Importer Summary

**slang subprocess wrapper (frontend.py) + JSON-to-BoolExpr IR translator (ast_importer.py) with source-location threading, exhaustive match dispatch, and 29 passing unit tests**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-05-25T00:00:00Z
- **Completed:** 2026-05-25T00:25:00Z
- **Tasks:** 4
- **Files modified:** 8

## Accomplishments

- `invoke_slang()` runs slang as a subprocess (list args, never shell), writes JSON to a temp file, handles FileNotFoundError → SlangNotFound (exit 3) and non-zero exit → SvaCompileError (exit 1)
- `import_assertion()` walks the slang AST dict, extracts ClockSpec from PropertySpec.clocking, reconstructs `BoolExpr.text` via `expr_to_sv()`, returns label and source location
- `expr_to_sv()` handles all Phase 1 expression kinds: BinaryPropertyExpr, UnaryPropertyExpr, SequenceExpr, BinaryOp, UnaryOp, NamedValue, IntegerLiteral — with parenthesized binary output and exhaustive default-raise
- Four fixture JSON files covering simple/labeled/complex boolean and unsupported SequenceConcat
- 29 unit tests — all passing; mypy --strict zero errors; ruff zero violations

## Task Commits

1. **Task 1: frontend.py slang subprocess wrapper** — `9f4c6c7` (feat)
2. **Task 2: JSON test fixtures** — `a7ffdb7` (test)
3. **Task 3: ast_importer.py JSON→IR translator** — `882741f` (feat)
4. **Task 4: unit tests** — `64bc58b` (test)

## Files Created/Modified

- `src/sva2rtl/frontend.py` — invoke_slang() with temp-file JSON capture and error mapping
- `src/sva2rtl/ast_importer.py` — import_assertion(), expr_to_sv(), extract_source_loc(), _check_unsupported()
- `tests/test_frontend.py` — 5 tests covering error paths, no-shell invariant, timeout
- `tests/test_ast_importer.py` — 24 tests covering expr_to_sv node kinds, fixture round-trips, source loc extraction
- `tests/fixtures/bool_simple.json` — `assert property (@(posedge clk) a && b)` AST
- `tests/fixtures/bool_labeled.json` — labeled assertion `my_check: assert property (...)`
- `tests/fixtures/bool_complex.json` — `((a && b) || (!c))` with UnaryPropertyExpr(Not)
- `tests/fixtures/unsupported_delay.json` — SequenceConcat node for UnsupportedConstruct tests

## Decisions Made

- Write slang JSON to a temp file (not stdout): slang prefixes stdout with build status text that breaks `json.loads()`
- `expr_to_sv` wraps all binary nodes in parentheses unconditionally — prevents precedence bugs in generated RTL
- Clock extracted from `PropertySpec.clocking.event` (SignalEvent.edge + NamedValue.symbol), never from module port names
- Default `case _:` in `expr_to_sv` raises `UnsupportedConstruct` — no silent skips that could produce wrong RTL

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## Next Phase Readiness

- `import_assertion(ast)` delivers `(BoolExpr, ClockSpec, text, label)` — exactly what Plan 03 (emitter) needs
- All PARSE-01, PARSE-02, PARSE-04 requirements satisfied
- CLI-06 (unsupported construct with source location) fully implemented
- Ready for Plan 1.3: template emitter + bool_expr.sv.j2

---
*Phase: 01-foundation-ir-slang-frontend-boolean-assert-sv-monitor*
*Completed: 2026-05-25*
