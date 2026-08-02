# sva2rtl Deep Review — 2026-08-01

## Scope and evidence boundary

This review covers compiler semantics, generated RTL, CDC, formal evidence,
differential and mutation testing, CLI behavior, CI disappearance gates,
distribution, licensing, privacy, and maintainability.

Current repository baseline when reviewed:

- HEAD: `bbb81d21a8f1333c5c9aa3f210c9962cb1c78f8e`
- Same-commit CI: run `30687603682`, passed
- Same-commit differential nightly: run `30688022213`, passed
- Latest Full Formal executable baseline: parent commit
  `1841ed40a149ef6971225fe00255e9587d5995ae`, run `30686820029`, passed
- Current support status: zero construct rows promoted to `Fully supported`

Green regression results are evidence for the exercised subset. They do not
prove correctness for input shapes or evidence conditions absent from the test
catalog.

## Findings

| ID | Severity | Finding | Failure mode | Required closure |
|---|---|---|---|---|
| F-01 | High | Signal widths are not carried into observed ports | Accepted vector expressions emit scalar ports and can silently miscompile | Preserve slang type/width in IR, emit typed ports, reject unknown widths, and add dual-backend vector tests |
| F-02 | High | Generated module identity is not scope-safe | Assertions with the same label in different source modules overwrite each other | Include source scope and semantic identity, detect conflicting collisions, never overwrite silently |
| F-03 | High | Observed signals can collide with standard checker ports | Properties referencing `start`, `disable_i`, or output names generate duplicate ports | Central reserved-port aliasing with explicit DUT-signal mapping |
| F-04 | High | Formal cover probes are not cover-mode gates | An assertion task can return PASS while every critical cover is unreachable | Run and parse separate cover-mode tasks; unreachable critical covers produce UNKNOWN/failure |
| F-05 | High | Multi-clock Verilog-2001 output contains SystemVerilog syntax | `--verilog` can emit `always_ff` and `logic`, failing `iverilog -g2001` | Route all templates through compatibility macros and compile every template family in V2001 mode |
| F-06 | High | Multi-clock event delivery is not reliable | Level synchronization can miss narrow tokens or coalesce events | Keep fail-closed/experimental until a handshake or toggle protocol has explicit rate and overflow semantics |
| F-07 | High | CLI output mode is ambiguous and can overwrite files | Hierarchical output defaults to the current directory; a file-looking path becomes a directory | Separate file/directory modes, fail on incompatible paths, and add no-clobber/atomic behavior |
| F-08 | Medium | Critical test helpers swap `original_text` and `label` | Formal and generated-RTL gates do not exercise exact production artifact identity | Replace positional misuse, type-check tests/tools, and add exact source-to-output tests |
| F-09 | Medium | CI disappearance and skip budgets are loose | Large test-surface loss can remain green | Set per-suite floors near the reviewed baseline and allow only named skips/xfails |
| F-10 | Medium | Differential and mutation scopes omit key boundaries | Current gates do not challenge vectors, naming collisions, CLI output, or formal reachability | Add focused regressions and broaden mutation targets before raising trust claims |
| F-11 | Medium | Frontend lacks real-project compilation context | Filelists, include paths, defines, libraries, tops, and parameter overrides are unavailable | Add structured slang compilation options without shell interpolation |
| F-12 | High | Installation, publication, and license statements conflict | README install commands do not map to a published package; README license summary differs from LICENSE | Align documentation to actual distribution and license terms; publish only with authorized credentials |
| F-13 | Medium | Generated RTL embeds source paths | Artifacts can disclose directory structure and become non-reproducible | Normalize source locations relative to an explicit root and avoid absolute paths by default |
| F-14 | Low | Semantic hot paths have high cyclomatic complexity | Changes in importer/composer/CLI/oracle have broad regression blast radius | Refactor only under dedicated semantic tests and mutation protection |

## 2026-08-02 follow-up findings and closure

The original table remains the historical 2026-08-01 review. A fresh audit of
the later `de3f697` baseline found five additional evidence-governance issues;
local candidate `92a3b5a925325401dd6ead27a85f55ec6d0cd7bb` addresses them:

| ID | Severity | Finding | Closure in local candidate | Remaining boundary |
|---|---|---|---|---|
| F-15 | High | `TestKinductionBoundedEventually` had a blanket non-strict xfail, so a real counterexample or tool error could be reported as expected failure | Removed the marker; classify only basecase-pass plus induction non-convergence/timeout; added five log-classification regressions and exact JUnit reason gates | One bounded-liveness induction target still does not converge and remains explicit xfail; other formal results are bounded by their harnesses |
| F-16 | Medium | Workflow action SHAs were pinned but the uv CLI version could still float | All ten `setup-uv` uses explicitly request uv 0.12.1; workflow regression enforces action SHA and CLI version | Dependency lock and toolchain updates still require deliberate periodic review |
| F-17 | Medium | Row-level support evidence reused floating “current commit pending” text after exact remote runs existed | Matrix rows now name executable `de3f697` and CI run `30709818712`; local candidate evidence is separately marked non-remote | Candidate `92a3b5a` still needs same-SHA CI/nightly/Full Formal after explicit push authorization |
| F-18 | Medium | Twenty-one covered Python mutants survived, including importer dispatch and NFA routing boundaries; several survivors were equivalent duplicate conditions | Added operator/label/routing/disable regressions and simplified unreachable duplicate predicates; all 317 covered valid mutants and 12 reviewed RTL mutants are killed | Thirty-two uncovered Python candidates and the finite mutation vocabulary remain outside the score |
| F-19 | Medium | Real-project tests generated temporary toy projects and used RTL-vs-oracle agreement as the sole dynamic verdict | Added two versioned project corpora and a hand-authored cycle-exact source expectation checked before oracle agreement | No large industrial corpus, nested filelist/conflicting-library corpus, or repeated-instance corpus yet |

Fresh local gates for `92a3b5a`: Icarus 1579 passed / 1 skipped / 1 dynamic
xfail; Verilator 174 passed / 1 reviewed skip; generated RTL 133/133; branch
coverage 88.12%; Full Formal 126 passed / 1 identical bounded-liveness xfail;
dual-backend fixed/date-seeded differential passes; Python mutation 317/317;
RTL-template mutation 12/12; ruff and strict mypy pass. These are local results,
not remote or production evidence.

## Reproduced failures

The following were reproduced against the reviewed baseline:

1. A four-bit `data == 4'd3` assertion emitted scalar `input logic data`.
2. Two source modules with different assertions both labeled `p` produced one
   `sva_p.sv`; the later assertion silently replaced the earlier one.
3. A property whose observed signal was named `start` emitted two `start` input
   ports.
4. An SBY BMC task containing `assert(1)` and unreachable `cover(0)` returned
   PASS, confirming that cover probe presence is not reachability evidence.
5. Multi-clock output emitted with `--verilog` failed `iverilog -g2001`.
6. A hierarchical property invoked without `--output` wrote multiple files to
   the current directory; `-o monitor.sv` created a directory named
   `monitor.sv`.
7. Strict type checking of the three critical Formal/generated-RTL helper files
   reported the swapped tuple arguments.

## Fix order and acceptance gates

1. **Fail closed on semantic identity and typing.** Close F-01, F-02, and F-03.
2. **Make output behavior deterministic.** Close F-05, F-07, and F-13.
3. **Remove false-assurance paths.** Close F-04, F-08, F-09, and the focused
   portion of F-10.
4. **Keep CDC claims bounded.** Close the unsafe public path for F-06 before
   implementing a larger transfer protocol.
5. **Align user-facing truth.** Close the documentation portion of F-12 and
   record external publication as authorization-dependent.

Every fixed finding requires a regression that fails on the reviewed baseline,
passes after the change, and exercises the closest external boundary available:
slang source import, Icarus, Verilator, Yosys, or SymbiYosys. A critical formal
assertion PASS plus a failed required cover is not accepted as closure.

## Explicit non-claims

- A green optimizer equivalence check does not prove SVA-to-RTL translation.
- BMC proves only its stated depth and assumptions.
- A two-flop synchronizer does not guarantee pulse/event delivery.
- Local and parent-commit evidence is not silently attributed to a different
  executable commit.
- Building a wheel in CI does not mean the package is published.
