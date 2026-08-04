---
status: resolved
trigger: "Fix the review-blocking multidimensional packed signal width bug that can return a false PROVEN result."
created: 2026-08-04
updated: 2026-08-04
---

# Debug Session: Multidimensional Packed False PROVEN

## Symptoms

- Expected behavior: formal interface validation must preserve the exact elaborated width and signedness, or reject unsupported types before creating a proof bundle or Yosys input.
- Actual behavior: `logic [1:0][3:0]` is parsed as width 2 instead of width 8; both property and DUT appear to match, the bind truncates the signal, and a false property can return `PROVEN`.
- Error messages: no diagnostic is emitted; the evidence contract reports `MATCHED`, the solver reports `PROVEN`, and cover reports `REACHED`.
- Timeline: discovered during the 2026-08-04 post-commit merge review of local commit `12d9f3d`.
- Reproduction: drive an 8-bit multidimensional packed DUT output with `8'h04`, assert `always (data == 8'h00)` using the same declared type, and run `sva2rtl-formal`; the generated bind declares only `[1:0] data` and returns `PROVEN`.

## Current Focus

- hypothesis: the unanchored single-range type parser accepts the first packed dimension and ignores all trailing dimensions or type syntax
- test: add parser and real-solver regressions that forbid a multidimensional packed signal from becoming a silently flattened/truncated proof model
- expecting: the input is either represented at its exact total packed width or rejected before output creation; it must never return `PROVEN` through truncation
- next_action: resolved; preserve the strict type grammar until shape-aware multidimensional semantics have independent qualification
- reasoning_checkpoint: matching two independently wrong width calculations does not establish an exact DUT/property interface contract
- tdd_checkpoint: true

## Evidence

- timestamp: 2026-08-04T15:03:15+08:00
  observation: slang emits `logic[1:0][3:0]`, while `parse_slang_integral_type` returns `(2, False)`
- timestamp: 2026-08-04T15:03:15+08:00
  observation: the generated interface contract records `data` as width 2 and status MATCHED
- timestamp: 2026-08-04T15:03:15+08:00
  observation: an actually false 8-bit property returns PROVEN with REACHED cover after bind truncation

## Eliminated

- hypothesis: the existing scalar-property versus vector-DUT mismatch regression covers this case
  reason: both sides declare the same multidimensional type, so both reuse the same incorrect first-dimension width

## Resolution

- root_cause: `_named_value_type` used an unanchored range search, accepted only
  the first dimension of `logic[1:0][3:0]`, and let property and DUT interface
  extraction agree on the same incorrect two-bit width.
- fix: integral type parsing now uses anchored grammars for scalar types and one
  fixed packed dimension. Multi-dimensional packed, unpacked-array, aggregate,
  and trailing syntax fails closed before proof-bundle/Yosys-input creation. The
  CLI still writes a source-isolated `UNSUPPORTED` evidence bundle, whose
  diagnostic recommends a reviewed one-dimensional alias.
- verification: the original false property now returns UNSUPPORTED with no
  solver input; an unrelated complex DUT port no longer expands a scalar
  property contract; 11 focused regressions, 1733-test default suite, 214-test
  Full Formal selection, 174-test Verilator selection, both fixed and rotating
  differential sweeps, 133 generated-RTL checks, 86.99% aggregate coverage,
  334/334 covered Python mutants, 12/12 RTL-template mutants, Python 3.14,
  distribution smoke, and privacy/static gates passed. Local Full Formal retains
  two explicit missing-Super-Prove skips plus one expected k-induction xfail.
- files_changed: `src/sva2rtl/ast_importer.py`,
  `src/sva2rtl/formal_flow.py`, `tests/test_ast_importer.py`,
  `tests/test_formal_advanced_safety.py`, and public evidence/boundary docs.
