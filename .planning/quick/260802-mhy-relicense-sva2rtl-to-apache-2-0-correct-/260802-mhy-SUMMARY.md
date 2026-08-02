---
quick_id: 260802-mhy
status: complete
date: 2026-08-02
execution_commit: c957bdf3d3ed9cf145f23057d9e2a94d555c30e3
---

# Quick Task 260802-mhy Summary

## Outcome

The current distribution is licensed under Apache License 2.0. The root license
is the exact official text, package metadata uses the `Apache-2.0` SPDX
expression, and release tests verify the wheel and sdist identity. The README
now presents the compiler as an open-source implementation of a supported,
bounded SVA subset instead of implying full IEEE 1800 or industrial proof.

`FORMAL_VERIFICATION.md` adds an implementation-oriented formal workflow:
independent reference miters, explicit assumptions, BMC, k-induction, required
cover reachability, dual-simulator comparison, synthesis/lint, differential
testing, mutation testing, and exact-commit remote qualification. It explains
how bounded advanced operators are lowered to counters, token networks, and
bounded NFAs, and gives safe alternatives for constructs that cannot currently
be lowered without changing semantics.

## Evidence

- Local Icarus: 1580 passed, 1 skipped, 1 classified bounded-liveness xfail.
- Local Verilator simulation: 174 passed, 1 reviewed skip.
- Generated RTL: 133 passed under Yosys synthesis and strict Verilator lint.
- Full Formal: 126 passed, 1 classified bounded-liveness induction boundary.
- Differential: both simulators passed fixed-seed fast and date-seeded slow
  sweeps; each slow sweep executed 64 generated examples.
- Mutation: 317/317 covered valid Python mutants and 12/12 RTL-template mutants
  killed; 32 uncovered candidates remain outside the denominator.
- Coverage: 88.12% branch coverage with aggregate and critical-module floors.
- Packaging, strict mypy, ruff, changed-file formatting, lockfile, whitespace,
  relative-link, and privacy checks passed.
- Remote commit `c957bdf3d3ed9cf145f23057d9e2a94d555c30e3`:
  CI run `30741073680` passed 13/13, differential-nightly run `30741082278`
  passed 3/3, and Full Formal run `30741083516` passed 6/6.

## Boundaries Retained

No construct was promoted to Fully supported. Formal conclusions remain scoped
to the named harness, assumptions, outputs, depth or induction model, tools,
and exact source SHA. Multi-clock CDC, industrial corpus breadth, unsupported
full-SVA forms, finite NFA/thread budgets, and row-specific evidence gaps remain
explicit. The technical relicense also assumes that project rightsholders have
authority to relicense all included contributions; repository tests cannot
establish that legal fact.

## Privacy

The implementation commit uses repository-local anonymous author and committer
metadata. Changed and staged content was checked for home paths, personal email,
credentials, tokens, and private-key material before push.
