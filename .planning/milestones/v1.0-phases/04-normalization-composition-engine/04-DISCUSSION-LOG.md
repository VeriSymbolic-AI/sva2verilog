# Phase 4: Normalization + Composition Engine - Discussion Log

**Date:** 2026-05-27
**Duration:** ~10 minutes
**Areas discussed:** 4/4 selected

---

## Area 1: Normalization boundary

### Q1: How should normalization be architecturally organized relative to the existing composer?
- **Options:** Separate pre-pass (Recommended) | Integrated into composer | Multi-pass visitor framework
- **Selected:** Separate pre-pass
- **Notes:** Clean separation from composer, testable in isolation

### Q2: Should [*1] be normalized away to identity? And what about small fixed repetitions?
- **Options:** [*1] → identity (Recommended) | [*1] stays as repetition | [*1]→identity + [*2,3]→concat
- **Selected:** [*1] → identity

### Q3: For [*2] and [*3] specifically — expand to SeqConcat chains, or keep as SeqRepetition?
- **Options:** Only [*1] normalized (Recommended) | [*1,2,3] all expanded to concat | You decide
- **Selected:** Only [*1] normalized
- **Notes:** Counter overhead for N=2,3 is negligible; keep them as SeqRepetition

### Q4: Normalization traversal strategy — how do we handle cascading rewrites?
- **Options:** Bottom-up single pass (Recommended) | Fixed-point until stable | Two-pass bounded
- **Selected:** Bottom-up single pass
- **Notes:** O(n) traversal; cascading handled naturally by bottom-up order

---

## Area 2: Composer refactoring scope

### Q1: How much should the existing composer.py change?
- **Options:** Evolutionary (Recommended) | Clean-room rewrite | Dual-path (legacy + new)
- **Selected:** Evolutionary
- **Notes:** Existing composer already builds CheckerNode trees with token-passing. Phase 4 adds normalization in front + dump-tree visibility.

### Q2: How should normalization and composition be wired together at the API level?
- **Options:** compose() takes pre-normalized IR (Recommended) | New compile_property() wrapper | Pipeline abstraction
- **Selected:** compose() takes pre-normalized IR
- **Notes:** Call site becomes `compose(normalize(ir_root), ...)`

### Q3: Should CheckerNode gain stable structural hashes in Phase 4?
- **Options:** Add structural hash now (Recommended) | Defer to Phase 5 | Separate hash utility
- **Selected:** Add structural hash now
- **Notes:** Phase 5 CSE needs them; add while refactoring

### Q4: Implementation approach for structural hashing?
- **Options:** Recursive content hash (Recommended) | Merkle SHA-256 | Python __hash__ directly
- **Selected:** Recursive content hash
- **Notes:** hash(type(node), tuple(sorted(params.items())), tuple(child_hashes))

---

## Area 3: --dump-tree output design

### Q1: What format should --dump-tree output?
- **Options:** Indented text tree (Recommended) | DOT graph format | JSON output
- **Selected:** Indented text tree
- **Notes:** Human-readable, grep-able, no external tools needed

### Q2: Should --dump-tree include the structural hash for each node?
- **Options:** Yes, show hash per node (Recommended) | No, keep output minimal | --dump-tree --verbose adds hash
- **Selected:** Yes, show hash per node

### Q3: Should --dump-tree show the effect of normalization?
- **Options:** Show before/after (Recommended) | Post-normalized only | Separate --dump-ir and --dump-tree
- **Selected:** Show before/after
- **Notes:** Pre-normalized IR at top, post-normalized composed tree below

---

## Area 4: Golden file parity enforcement

### Q1: How strict is 'byte-for-byte' golden parity?
- **Options:** Strict byte-for-byte (Recommended) | Semantic equivalence | Byte-for-byte with one-time update allowance
- **Selected:** Strict byte-for-byte
- **Notes:** Highest confidence. Normalization must be truly transparent.

### Q2: Enforcement mechanism for golden parity?
- **Options:** Pytest golden regeneration test (Recommended) | Checksum script (CI gate) | Both
- **Selected:** Pytest golden regeneration test
- **Notes:** Part of normal test suite. Any diff = hard failure.

### Q3: Should Phase 4 also re-run Phase 3 simulation oracle?
- **Options:** Yes, re-run simulation oracle (Recommended) | No, golden parity is enough | Conditional — only on golden failure
- **Selected:** Yes, re-run simulation oracle
- **Notes:** Belt-and-suspenders behavioral equivalence proof

---

## Claude's Discretion Items
- Internal normalizer structure (class vs function dispatch)
- --dump-tree "before normalization" section format
- Whether to add --no-normalize debug flag
- Complex composition test cases for Plan 4.3

## Deferred Ideas
- None
