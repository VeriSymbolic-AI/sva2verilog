# sva2rtl v1.5.2 Release Notes

**Release date:** 2026-07-06
**Type:** Quality release — bug fix + formal verification expansion + CI hardening

v1.5.2 is a quality release that fixes a real RTL generation bug (`first_match` posedge parameter), expands formal equivalence proofs from 55 to 62 BMC miters (all supported operators now have non-circular proofs), fixes all mypy --strict errors (49 → 0), and extends CI to run the full formal verification suite.

## Summary

| Area | Change |
|------|--------|
| Version | Bumped to `1.5.2` |
| `first_match` bug fix | `posedge` keyword used as bare parameter value — yosys/iverilog syntax error |
| Formal BMC proofs | 55 → 62 (+7: disable_iff, [*N], $past, first_match, [->N], [=N]) |
| mypy --strict | 49 errors → 0 errors |
| disable_iff oracle fix | `simulate_checker_hierarchy` effective_disable gate + subtree reset |
| CI formal job | Extended to run all SVA↔RTL equiv + NFA BMC tests + sby installation |
| README | Operator table updated with Tier 2 + Tier 3 + Multi-clock + NFA |
| Tests | 1081 passed, 4 skipped, 1 xfailed, 0 failed |
| Ruff | 0 errors repo-wide |

## Bug fix: `first_match` posedge parameter (P0)

**Symptom:** The `first_match_top.sv.j2` template passed `clock_edge` (value `posedge`) as a bare parameter to the child module instance: `#(.clock_edge(posedge))`. Since `posedge` is a SystemVerilog keyword, both yosys and iverilog reported syntax errors — the generated RTL for `first_match` could not be compiled or simulated.

**Root cause:** The template's parameter exclusion list did not include `clock_edge` and `clock_signal`, so these template-internal parameters were emitted as RTL parameter overrides.

**Fix:** Added `clock_edge` and `clock_signal` to the exclusion list in `first_match_top.sv.j2`. Golden file regenerated. yosys prep verified.

## Formal verification expansion: 7 new BMC miters

All 6 previously simulation-only operators now have non-circular SymbiYosys BMC equivalence proofs with independently authored IEEE-1800 reference monitors:

| Operator | Reference structure | BMC depth | Proof |
|----------|-------------------|-----------|-------|
| `disable iff` | Independent prev_a + prev_b registers | 15 | pass + fail |
| `[*N]` consecutive rep | Independent counter + combinational pass | 20 | pass |
| `$past(sig, N)` | Independent N-stage shift register | 15 | pass |
| `first_match` | Independent a_q + match_w + pass_q | 15 | pass |
| `[->N]` goto rep | Independent count_q + passed_q | 25 | pass |
| `[=N]` nonconsec rep | Independent count_q + combinational pass | 30 | pass |

Total formal BMC proofs: **62** (was 55). All supported operators now have non-circular formal equivalence backing.

## mypy --strict: 49 errors → 0

Fixed type annotation issues across 3 files:

- `ast_importer.py` (~35 errors): Unified `ir_node: SVANode` declaration before match/case; renamed `stmts` variables to avoid redefinition; `name` variable wrapped with `str()`; per-case `rep_ir` variables renamed.
- `behavioral_oracle.py` (~5 errors): `type: ignore` comments corrected from `[arg-type]` to `[call-overload]`.
- `composer.py` (~9 errors): `overlapping` param annotated with `# type: ignore[dict-item]`; `node.consequent.body/.clock` annotated with `# type: ignore[attr-defined]`; `trans` variable renamed to `rep_trans`; `node.false_branch` guarded with `assert is not None`.

CI `lint` job now passes cleanly.

## disable_iff oracle fix

`simulate_checker_hierarchy._tick_disable_iff` previously only checked `cond_expr` signals, ignoring the external `disable_i` input. Composite body nodes (overlap_bitvec, seq_concat_top) did not propagate the `"disable"` key to leaf oracles, so leaf state was never reset and accumulated fail events leaked through.

**Fix:** `effective_disable = disable_i | cond_result` (RTL semantics). Negated conditions (`!rst_n`) correctly evaluated. On disable, all leaf oracles in the body subtree are reset via new `_reset_subtree()` method. `test_disable_iff_oracle_disabled` xfail flipped to real pass.

## CI hardening

- `formal` job: Added SymbiYosys (sby) installation step
- `formal` job: Extended test scope to include `test_formal_sva_equiv.py`, `test_v151_nfa_bmc.py`, `test_v151_p2_bmc.py`
- `test` job: Added slang installation for macOS

## Known limitations (carried forward)

- 1 xfail: `test_named_seq_oracle_fail_event` — structural limitation: `bool_expr` leaves do not independently produce fail events; fail semantics come from the implication parent. Honest witness.
- BMC depth: 15-30 cycles (bounded model checking). k-induction (complete proof) planned for future release.
- `##0` fusion: registered-leaf pipeline cannot sample two operands same cycle; retains +1. Workaround: `a && b`.
- NFA engine still rejects: ranged delays in operands, SeqOr/SeqGotoRep/SeqNonconsecRep inside intersections, multi-cycle throughout conditions. Low-frequency; compile-time rejection with actionable message.
- Multi-clock formal equivalence: permanently excluded (industry-wide limitation, DVCon 2024).

## Test status

1081 passed, 4 skipped (verilator not installed locally), 1 xfailed, 0 failed. Ruff 0 errors. mypy --strict 0 errors. All 62 BMC formal proofs pass.

## Commit list

- mypy --strict fixes (ast_importer, behavioral_oracle, composer)
- disable_iff oracle fix (effective_disable + _reset_subtree)
- first_match posedge parameter bug fix (template exclusion list)
- 7 new BMC miter proofs (disable_iff, rep_consecutive, $past, first_match, goto_rep, nonconsec_rep)
- CI formal job extension (+sby +NFA BMC tests)
- README operator table update (Tier 2 + Tier 3 + Multi-clock + NFA)
- SUPPORTED_CONSTRUCTS.md version label update (v1.3.1 → v1.5.1)
- .gsd/ document reconciliation (STATE.md, CODEBASE.md, MILESTONES.md, ROADMAP checkboxes)
