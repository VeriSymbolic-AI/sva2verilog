# sva2rtl Final Local Review — 2026-08-04

## Decision

The local candidate is suitable for an anonymous Git commit. The ten reviewed
false-assurance and evidence-safety defects are closed by fail-closed behavior,
focused regressions, and the complete local gate set below.

This is **not** a production or release qualification. The resulting commit
still requires exact-SHA remote CI, nightly differential/mutation, and Full
Formal success. Local macOS cannot execute the Super Prove liveness engine.

## Reviewed findings and disposition

| ID | Severity | Reproduced defect | Closure | Remaining boundary |
|---|---|---|---|---|
| P24-F01 | Critical | A scalar property could be connected to a vector DUT signal and return `PROVEN` instead of reporting an interface error | DUT and property interfaces now use one slang integral-type interpretation; observed signals require exact width and signedness, while clock, reset, and fairness inputs must be scalar | Only supported packed integral types enter this path; unknown or incompatible forms reject |
| P24-F02 | High | A decomposition certificate trusted hand-authored `PROVEN` JSON and did not provide replayable proof objects for an unsupported original | Schema-v2 certificates bind the original, DUT sources, subproperties, relation property, manifests, logs, and deterministic replay commands by hash; the aggregate route never sends the unsupported original to Yosys | The relation property is a reviewed, human-authored semantic model; the tool proves that model but does not automatically derive its adequacy from the unsupported original |
| P24-F03 | High | The same file could be supplied as DUT and property input, allowing source assertions to enter the DUT proof compilation | Same-file, hard-link, and symlink aliases reject; DUT elaboration rejects concurrent assert/assume/cover constructs; the manifest records a hashed interface contract | Assertion-bearing DUT sources must be separated or sanitized before use |
| P24-F04 | Critical | `--force` could recursively delete an arbitrary non-evidence directory | Replacement is limited to a non-root directory carrying the exact sva2rtl evidence marker; inputs, their ancestors, the home directory, the working directory, and filesystem root reject | A user must choose a dedicated output directory; general-purpose deletion is intentionally unavailable |
| P24-F05 | Medium | `result.json` was not cryptographically bound to its manifest, inputs, checker, replay commands, or solver logs | Result schema v2 records the relevant hashes and replay commands; every declared manifest artifact is rehashed immediately before execution; proof and cover logs are also bound and revalidated | SHA-256 binding detects changed evidence but does not establish independence of the underlying solver or semantic model |
| P24-F06 | Critical | Proof bundles with the same DUT source hashes but a different selected top or environment could satisfy a decomposition certificate | Every relation and member proof manifest must match the aggregate top, clock, reset, prove mode, attempt model, logic profile, and ordered fairness assumptions; checker identity is also manifest-bound | Deliberately different proof environments require an explicit relation model rather than silent reuse |
| P24-F07 | Critical | Immediate procedural `assume`, `assert`, or `cover` statements in DUT sources were not covered by the concurrent-SVA isolation check | DUT AST isolation now rejects every slang assertion node, including immediate and deferred forms, before output creation or Yosys execution | Assertion-bearing design sources must be sanitized or separated |
| P24-F08 | High | An unsupported original requested in BMC mode could return an aggregate `PROVEN` result whose mode was changed to prove | Verified decomposition aggregation is accepted only in explicit `--mode prove`; BMC rejects without creating output | Bounded member evidence cannot discharge an unbounded aggregate claim |
| P24-F09 | High | `--force` could remove a certificate or member proof located under the selected output after validating it | Certificate, relation result, subproperty, and member result paths join the protected-input set before any replacement | A dedicated output outside every proof-input tree remains mandatory |
| P24-F10 | Medium | Aggregate replay reopened the caller's original property and DUT paths even though the bundle already contained a hashed snapshot | Aggregation now derives expected input hashes from the integrity-checked manifest and validates the copied normalized certificate against them | External source changes after bundle creation do not alter the captured proof question; changing bundle copies still rejects |

## Local qualification evidence

| Gate | Result |
|---|---|
| Complete default/Icarus suite | 1722 passed, 3 conditional skips, 1 dynamically classified k-induction xfail |
| Verilator simulation and fast differential selection | 174 passed, 1 reviewed skip |
| Generated RTL synthesis and lint | 133/133 passed |
| Full Formal selection | 212 passed, 2 local missing-Super-Prove skips, 1 k-induction xfail |
| Differential | Fixed-seed Icarus 16/16 and Verilator 16/16; rotating-seed slow sweep 1/1 per backend |
| Coverage | 1666 passed; aggregate branch coverage 86.89%; all critical-module floors passed; `formal_flow.py` 83.62% |
| Python semantic mutation | 335/335 covered mutants killed; 56 uncovered candidates excluded from the score |
| RTL template mutation | 12/12 reviewed mutants killed |
| Python 3.14 | 1321 selected tests passed with no skips |
| Distribution | Wheel and sdist built; external-install compile smoke passed |
| Static/release checks | Ruff, strict mypy, lock check, shell syntax, diff check, source privacy, and archive privacy passed |

Local tool versions were Icarus 12.0, Verilator 5.028, slang 11.0.0,
Yosys 0.66, SBY 0.65, and Z3 4.15.0. `suprove` was not installed.

## Residual risks and release gates

1. The replay-bound decomposition path makes every accepted proof object
   inspectable and rerunnable, but it cannot automatically prove that a
   human-authored relation property faithfully captures an arbitrary unsupported
   SVA construct. That review obligation is explicit, not hidden.
2. The local machine cannot close real open-liveness good/bad qualification.
   Exact-SHA Linux Full Formal must run both cases with Super Prove.
3. The mutation score covers a declared finite operator vocabulary and excludes
   56 unexecuted candidates. It is strong fault-detection evidence, not a
   completeness proof.
4. No support-matrix row should be promoted to `Fully supported` until the
   committed SHA passes remote CI, nightly differential/mutation, and all Full
   Formal shards with its row-specific evidence intact.

## Final review verdict

No unresolved Critical, High, or Medium defect was found in the changed scope
after the qualification run. The candidate is commit-ready, with the remote
same-SHA and trusted-relation boundaries above remaining explicit.
