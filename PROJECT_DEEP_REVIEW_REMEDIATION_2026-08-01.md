# sva2rtl Deep Review Remediation — 2026-08-01

## Purpose and evidence boundary

This document closes the actionable fix order from
`PROJECT_DEEP_REVIEW_2026-08-01.md` without rewriting the original audit.
"Closed" below means the reproduced unsafe behavior is prevented and covered
by a local regression. It does not promote a construct to `Fully supported`.

The validation in this document is local evidence for the final working tree on
2026-08-01. It is not same-commit GitHub CI, nightly, or Full Formal evidence.
`SUPPORT_MATRIX.md` remains the authority for construct-level support, and no
row is promoted by this remediation alone.

## Finding disposition

| ID | Disposition | Remediation and remaining boundary |
|---|---|---|
| F-01 | Closed, fail-closed outside the implemented subset | Structured slang widths now reach boolean IR, emitted ports, simulation, and Formal harnesses. Vector operands in NFA paths that cannot preserve width metadata are rejected rather than scalarized. |
| F-02 | Closed for safety | Conflicting generated module identities raise a compilation error instead of silently overwriting output. Scope-aware duplicate-label support remains a future capability; the current behavior is deliberately fail-closed. |
| F-03 | Closed | Reserved monitor-port names receive deterministic `dut_*` aliases with an explicit generated-port-to-DUT-signal mapping. Structured boolean semantics use the same aliases. |
| F-04 | Closed for the local Formal runner | Proof/BMC and required reachability covers run as separate SBY tasks. A failed or timed-out required cover returns `UNKNOWN`/failure even when the primary assertion task passes. |
| F-05 | Closed for emitted template families | Multi-clock support templates and helper functions use the Verilog-2001 compatibility path; local `iverilog -g2001` compilation and Verilator 1364-2001 lint regressions pass. |
| F-06 | Mitigated, protocol work remains | Multi-clock CDC emission is rejected by default. `--experimental-multiclock` is an explicit prototype opt-in and documentation states that the level synchronizer can miss or coalesce events. A handshake/toggle event-transfer protocol is not implemented. |
| F-07 | Closed | Hierarchical or multi-property output requires a directory, leaf output can target a file, existing files fail by default, `--force` is explicit, and writes use temporary-file replacement. |
| F-08 | Closed | All reviewed `import_assertion` tuple consumers now use `(node, clock, text, label)` and the critical tests/tools are included in strict mypy. |
| F-09 | Closed for disappearance budgets | CI, generated RTL, Python 3.14, Verilator, and Full Formal shards now enforce reviewed minimum-pass and maximum-skip budgets. Named bounded-liveness xfail remains explicit. |
| F-10 | Focused closure only | New regressions cover vectors, reserved names, collisions, output safety, V2001, cover reachability, and CDC default rejection. Full mutation gates pass, but surviving and uncovered mutants remain validation debt. |
| F-11 | Open | Structured real-project slang compilation context (filelists, include paths, defines, libraries, tops, parameter overrides) was outside the approved fix order and is still missing. |
| F-12 | Documentation closed; publication external | README now states source-available BSL terms accurately and uses repository installation because no PyPI publication was verified. Publishing a package remains authorization- and credential-dependent. |
| F-13 | Closed for default artifacts | Generated source comments retain only the source basename, preventing absolute local path disclosure and improving reproducibility. |
| F-14 | Open | Importer, composer, CLI, and oracle complexity remains. Refactoring requires a separate semantics-preserving change with mutation protection. |

## Additional defect found during full validation

Reserved-name aliasing exposed an independent-reference defect in `disable
iff`: generated RTL correctly evaluated `(!dut_rst_n)`, while the behavioral
oracle inferred negation from the first text character and was confused by
outer parentheses. Compiler output now carries a serialized structured disable
condition and the oracle evaluates that structure. The legacy text path remains
only for hand-built checker compatibility. Focused Icarus and Verilator
cross-checks pass after the fix.

## Local validation evidence

| Gate | Result |
|---|---|
| Full Icarus suite | 1505 passed, 1 explicit skip, 1 strict xfail |
| Full Verilator simulation selection | 170 passed, 2 explicit skips; the slow differential skip was executed separately below |
| Full Formal selection | 126 passed, 1 strict bounded-liveness xfail |
| Nightly differential equivalent | Icarus fast 16/16 and slow 1/1; Verilator fast 16/16 and slow 1/1 |
| Aggregate branch coverage | 86.36%, above 82%; aggregate and all configured critical-module floors passed |
| Python AST mutation | `bool_semantics` 16/16; `behavioral_oracle` 118/131; `composer` 44/51; `ast_importer` 93/109; every module exceeded the 85% gate |
| RTL template mutation | 12/12 reviewed mutants killed |
| Python 3.14 compatibility | 1278 passed, 1 strict xfail, 228 deselected by the package-job selector |
| Distribution smoke | wheel and sdist built; isolated install and source compilation passed |
| Static quality | Ruff passed; strict mypy passed for production and critical Formal/generated-RTL helpers; `git diff --check` passed |
| Local tool boundary | Icarus 12.0; Verilator 5.028; Yosys 0.66; SBY 0.65; Z3 4.15.0 |

The explicit full-suite skip is the absence of promoted differential-failure
fixtures. The strict xfail records the known bounded-liveness k-induction
boundary. The Verilator-only second skip is an Icarus-specific Verilog-2001
integration check; the slow Verilator differential was separately selected and
passed.

## Residual risk and next evidence gates

1. **Same-commit remote evidence is still required.** After this remediation is
   committed and pushed, GitHub CI, differential nightly, and Full Formal must
   all pass on that exact commit before any support claim is upgraded.
2. **CDC remains experimental.** Implement an acknowledged event-transfer
   protocol with explicit source/destination rate, backpressure, reset, and
   overflow semantics before removing the opt-in gate.
3. **Mutation is above threshold, not complete.** The four Python modules have
   36 surviving scored mutants and 33 uncovered candidates in total. Prioritize
   NFA branching, importer statement-shape dispatch, and composite-oracle state
   retention before raising the mutation threshold.
4. **Real-project frontend context is absent.** Filelists, includes, defines,
   libraries, tops, and parameter overrides need a structured, non-shell API
   and fixture-backed integration tests.
5. **Complexity remains a change-risk multiplier.** Refactor only behind
   behavioral, differential, Formal, and mutation gates; do not combine the
   refactor with semantic expansion.

## Stop conditions for trust promotion

Do not promote a support row or describe this build as production-qualified if
any of the following is true:

- the executable commit differs from the CI/nightly/Full Formal commit;
- a required cover is unreachable, times out, or reports anything other than
  PASS;
- a vector/NFA width cannot be represented and is not rejected;
- multi-clock output is used without the explicit experimental boundary;
- a pass/skip floor disappears or a strict xfail changes without review.
