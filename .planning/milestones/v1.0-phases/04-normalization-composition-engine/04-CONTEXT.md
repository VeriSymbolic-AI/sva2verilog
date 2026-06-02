# Phase 4: Normalization + Composition Engine - Context

**Gathered:** 2026-05-27
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase installs a proper normalization→composition pipeline that canonicalizes SVA IR before template composition. It adds `normalizer.py` as a standalone IR→IR preprocessing pass, evolves the existing `composer.py` to consume normalized IR with stable structural hashing for Phase 5 CSE, and delivers `--dump-tree` as the developer debugging window into the CheckerNode composition tree. All Phase 1–3 golden files must regenerate byte-for-byte — normalization is transparent for existing simple cases, additive only for complex multi-operator compositions.

</domain>

<decisions>
## Implementation Decisions

### Normalization Architecture
- **D-01:** Normalizer is a standalone `normalizer.py` module — a pure IR→IR transform that runs as a separate pre-pass before `compose()`. Not integrated into composer dispatch. Clean separation enables isolated testing.
- **D-02:** Traversal strategy is bottom-up single pass (O(n) on tree size). Each node is visited after its children are normalized. No fixed-point iteration — cascading rewrites are handled naturally by bottom-up order (e.g., `|=>` desugars to `##1 |->`, then parent SeqConcat sees the `##1` child during its own visit).
- **D-03:** Normalization rules (from ROADMAP): `|=>` → `##1 |->` desugaring; flatten `SeqConcat` chains; `##[N:N]` → `##N` canonicalization; normalize boolean constants. `[*1]` normalizes to identity (removes trivial repetition node). `[*2]` and `[*3]` are NOT expanded — they stay as SeqRepetition nodes handled by the existing counter template (2-bit counter overhead is negligible).
- **D-04:** Normalizer input: raw IR from `ast_importer`. Normalizer output: canonical IR. Composer never sees unnormalized forms in normal operation.

### Composer Refactoring
- **D-05:** Evolutionary refactoring — keep existing `composer.py` mostly intact. The current dispatch already builds CheckerNode trees with token-passing wiring. Phase 4 adds normalization in front and `--dump-tree` visibility. Minimal disruption, golden parity is easy.
- **D-06:** API wiring: `compose()` takes pre-normalized IR. Call site becomes `compose(normalize(ir_root), clock, label, text)`. Minimal API surface change.
- **D-07:** Structural hash added NOW in Phase 4 (not deferred to Phase 5). Implementation: recursive content hash — `hash(type(node), tuple(sorted(params.items())), tuple(child_hashes))`. Leverages frozen dataclass properties. Phase 5 CSE uses this to find merge candidates.

### `--dump-tree` Output
- **D-08:** Format is indented text tree printed to stdout. Shows: node type, module name, key params, token wiring (pass→start connections), and structural hash per node. Human-readable, grep-able, no external tools needed.
- **D-09:** Shows before/after normalization effect — pre-normalized IR printed first, then the post-normalized composed CheckerNode tree below. Makes normalization effects visible to users debugging complex properties.
- **D-10:** `--dump-tree` prints and exits 0 without emitting any RTL (same behavior as `--dump-ast`).

### Golden File Parity
- **D-11:** Strict byte-for-byte parity. If normalization changes even whitespace in golden output, tests fail. Normalization MUST be transparent for all existing Phase 1–3 inputs.
- **D-12:** Enforcement via pytest golden regeneration test — a fixture that regenerates all golden files and diffs against committed versions. Any diff = hard test failure. Part of the normal test suite.
- **D-13:** Phase 3 simulation oracle (65 Icarus tests) re-run against regenerated monitors as belt-and-suspenders proof of behavioral equivalence through the new composition path.

### Claude's Discretion
- Internal structure of `normalizer.py` (class-based visitor vs function-based dispatch — match the pattern used in `composer.py`)
- How `--dump-tree` formats the "before normalization" section (could be a simple IR repr or a minimal tree)
- Whether to add a `--no-normalize` debug flag for skipping normalization (useful during Phase 4 development)
- Complex composition test cases for Plan 4.3 (choose patterns that exercise multiple normalization rules in combination)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Algorithms
- `.planning/ROADMAP.md` Phase 4 section — Plan breakdown (4.1-4.3), success criteria, requirements (PIPE-01, PIPE-02)
- `.planning/REQUIREMENTS.md` — PIPE-01 (normalization rewrites), PIPE-02 (composition engine + CheckerNode tree)
- `.planning/PROJECT.md` §Key Decisions — Token-passing architecture, frozen dataclasses, counter encoding

### Prior Phase Context (patterns to follow)
- `.planning/phases/03-remaining-tier-1-operators-named-sequences-simulation-valida/03-CONTEXT.md` — Phase 3 decisions (D-01 CSE tagging, D-09/D-10 disable interface, D-12 standard port interface)
- `.planning/phases/02-core-sequential-operators-n-m-n/02-CONTEXT.md` — Phase 2 decisions (counter encoding, module topology, token-passing wiring)

### Existing Implementation (modify/extend these files)
- `src/sva2rtl/composer.py` — 763-line existing composition dispatch (match/case on IR types → CheckerNode). Evolutionary refactoring target.
- `src/sva2rtl/ir.py` — Frozen dataclass IR nodes (SVANode base, SeqConcat, SeqRepetition, SignalFunc, PropImplication, DisableIff, BoolExpr)
- `src/sva2rtl/ast_importer.py` — Produces raw IR from slang JSON AST
- `src/sva2rtl/cli.py` — CLI entry point (add --dump-tree flag here)
- `tests/golden/*.sv` — 20+ golden files that must regenerate byte-for-byte

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `composer.py` `compose()` function: already implements full CheckerNode tree construction with template selection and token-passing wiring — this IS the composition engine, just needs normalization in front
- `ir.py` frozen dataclasses: already hashable via `__hash__` — structural hash can build on top
- `tests/test_pipeline_e2e.py`: existing end-to-end test patterns (JSON → IR → compose → emit → golden compare)
- `behavioral_oracle.py`: existing simulation oracle for all Tier 1 operators

### Established Patterns
- `match`/`case` dispatch on IR node `type()` (used in `composer.py`, `ast_importer.py`, `emitter.py`)
- Frozen dataclass construction with typed fields (all IR nodes follow this)
- Golden file testing: fixture generates output, pytest compares against committed `.sv` file
- Click CLI with `--dump-ast` existing pattern (print and exit 0)

### Integration Points
- `cli.py` pipeline: currently `frontend → import → compose → emit`. Becomes `frontend → import → normalize → compose → emit`
- `compose()` call sites in tests: update to pass through `normalize()` first
- `--dump-tree` hooks into the same Click group as `--dump-ast`

</code_context>

<specifics>
## Specific Ideas

- `--dump-tree` output format should match the indented preview:
  ```
  CheckerNode: sva_prop_my_check (disable_iff_top) [hash:a3f2c1]
    condition: rst_n
    body:
      CheckerNode: sva_prop_my_check_impl (overlap_bitvec) [hash:b7e4d2]
        bv_width: 4
        ...
        wiring: ant.pass -> impl.start
  ```
- Normalization should be idempotent: `normalize(normalize(x)) == normalize(x)`
- Structural hash should be deterministic across runs (no Python hash randomization dependency)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 4-Normalization + Composition Engine*
*Context gathered: 2026-05-27*
