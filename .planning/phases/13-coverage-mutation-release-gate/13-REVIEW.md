---
status: resolved
review_date: 2026-08-10
findings: 15
scope: NFA timing semantics, bounded implication PPA, public monitor contract, external-tool gates
remote_issues: [1, 2]
---

# Deep semantic and PPA review

## Verdict

The two reported GitHub issues are reproduced and fixed on the current local
tree.  The review also found thirteen adjacent correctness, evidence, resource,
and interface risks.  All fifteen findings below have a code fix and a focused
regression.  The resulting local tree passes both simulators, complete local
formal suites, strict lint/type checks, generated-RTL lint/synthesis, a targeted
template-mutation gate, and the rotating differential sweep.

This is local same-tree evidence only.  It is not a commercial-EDA equivalence
result, a remote CI result, or permission to close the two issues before the
fix commit is pushed and independently replayed.

## Findings and disposition

| ID | Priority | Finding | Resolution / evidence |
|---|---:|---|---|
| F-01 | P0 | `##[1:3]` omitted the +1 transition and duplicated the last transition | Rewrote ranged-delay lowering; independent +1/+2/+3/+4 boundary vectors and real-source slang E2E added. |
| F-02 | P1 | Common delay-window implication used a K-by-T generic NFA (issue #2) | Added `implication_delay_window`; Yosys 0.66 maps the issue shape to 25 cells, with a <=40 regression gate (old generic path was 100+). |
| F-03 | P0 | NFA `or` used fake unconditional fork edges that consumed a cycle | Same-cycle union start expansion plus short-branch simulation and independent BMC miter. |
| F-04 | P0 | Multi-cycle `within` aligned starts and accepted at inner completion | Replaced by waiting/running/done containment NFA; late inner starts and outer-end completion covered by simulation and independent BMC. |
| F-05 | P1 | Multi-cycle `and` forgot an early branch completion | Added later-endpoint product with done-state families; simulation and BMC miter added. |
| F-06 | P0 | Nested NFA implication routing called a primitive-only lowerer and crashed | Router now uses recursive lifting; nested `within` consequent compiles and simulates. |
| F-07 | P1 | Python NFA guard evaluator silently misread `!`, `&&`, `||`, equality, literals, and trailing tokens | Grammar expanded and full token consumption enforced; mutation-boundary tests added. |
| F-08 | P1 | Terminal nonaccept states delayed property failure one cycle | Reverse co-reachability pruning removes dead transitions; outer-end failure timing covered. |
| F-09 | P1 | Multi-slot allocator was combinationally self-referential and required `UNOPTFLAT` suppression | Replaced with prefix-free priority expression; waiver removed; full strict generated lint passes. |
| F-10 | P1 | `disable iff` dropped `overflow_flag` for NFA-family children | Central checker-capability query and recursive propagation added; generic NFA, implication NFA, compact window, and no-overflow leaf cases covered. |
| F-11 | P1 | `--output out/` became a file when optimization produced a leaf checker | Explicit trailing-slash directory mode added with CLI and source-E2E regression. |
| F-12 | P1 | NFA composition lost `(generated port, DUT signal)` aliases for reserved names such as `start` / `disable_i` | Mappings now survive all NFA products and wrappers; reserved-name emission tests added. |
| F-13 | P1 | Huge delay bounds could materialize a massive transition list before the K<=32 rejection | Added pre-construction state estimate and compact-window age-bit budget; million-delay regression fails fast. |
| F-14 | P1 | New multi-cycle `or/and` NFA path stopped reporting top-level failed attempts | Public emitted nodes use property dead-end semantics; nested sequence lifting remains sequence semantics; full simulator regression caught and verifies the fix. |
| F-15 | P2 | Legacy `prop_or` failure latches became unreachable for multi-cycle use and could mix consecutive starts | Multi-cycle OR is NFA-backed; aligned single-cycle wrapper now uses direct `left_fail & right_fail`; obsolete mutation sites removed. |

## Independent evidence added

- Real `.sv` fixture for `req |-> ##[1:3] ack` through slang, importer,
  normalizer, composer, emitter, and directory output.
- Independent Icarus and Verilator vectors for exact window bounds,
  nontrivial lower bound `##[2:3]`, deadline failure, continuous overlapping
  starts, same-cycle ACK plus new launch, non-overlap timing, nested `or`,
  later-endpoint `and`, and containment `within`.
- Independent shift/history-reference formal miters for `and`, `or`, `within`,
  and the compact delay-window full public contract.  The delay-window proof
  covers lower bounds 1 and 2, arbitrary overlapping starts, pass, fail,
  active, attempt evidence, disable output, and overflow.
- Generated RTL catalog entry, strict Verilator lint, Yosys synthesis smoke,
  and an explicit area ceiling for the issue-2 shape.
- Three reviewed RTL mutants for lower-bound masking, satisfied-attempt
  retirement, and max-cycle ACK/fail precedence; all are killed.

## Local verification snapshot

| Gate | Result |
|---|---|
| Ruff + strict mypy | PASS |
| Non-simulation/non-lint suite | 1593 passed, 2 skipped, 1 xfailed |
| Icarus simulation | 187 passed |
| Verilator simulation | 185 passed, 1 conditional skip in the full run; 33/33 final affected tests passed after the last template/test additions |
| Generated lint + synthesis | 139 passed |
| NFA and compact-window formal miters | 16 passed after the lower-bound extension |
| Coverage run | 1778 passed, 86.28% branch-aware total (threshold 82%) |
| Slow rotating differential, seed 20260810 | PASS on Icarus and Verilator |
| Targeted RTL template mutation | 13/13 killed |

## Residual boundaries (not defects closed by this change)

1. The randomized differential grammar still emphasizes simpler source
   families; it does not establish broad random coverage of recursive temporal
   implication.  Deterministic independent vectors and formal miters are the
   present evidence for the newly fixed advanced paths.
2. NFA state/thread products and the compact age vector are intentionally
   capped at 32 bits.  Packed-vector NFA operands remain fail-closed and require
   a scalar helper signal or a separately proven decomposition.
3. No JasperGold or other commercial reference execution has occurred.  Local
   open-source proofs materially improve confidence but do not replace the
   planned independent commercial pilot.
4. Remote CI/nightly results for the eventual fix commit do not exist until the
   focused changes are committed and pushed.  Do not use the local working-tree
   results as remote same-SHA evidence.
