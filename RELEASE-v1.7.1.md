# Release v1.7.1 — Semantic Correctness and Release Gate Hardening

Released: 2026-07-31

> Post-release qualification update (2026-08-01): executable/workflow baseline
> `b055105` passed CI run
> [`30683023280`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30683023280),
> differential nightly run
> [`30683026683`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30683026683),
> and all six shards of Full Formal run
> [`30683026438`](https://github.com/VeriSymbolic-AI/sva2verilog/actions/runs/30683026438).
> This closes the post-release same-commit execution gap and remotely verifies
> F-01. It does not rewrite the `v1.7.1` tag or automatically promote construct
> rows: the support matrix keeps 0 rows at `Fully supported` pending row-specific
> evidence-chain closure.

Fresh local post-release qualification on 2026-08-01 passed the full Icarus
suite (1473 passed / 1 skipped / 1 xfailed), generated RTL (133 passed), Full
Formal (125 passed / 1 documented strict-liveness xfail), Python 3.14 broad
non-simulation tests (1247 passed / 1 xfailed), branch coverage (86.31%), both
simulator differential fast/slow sweeps, Python mutation (260/301, 86.4%), RTL
template mutation (11/11), and Python 3.12/3.14 out-of-tree distribution smoke.
These local counts are complemented by the same-commit remote records above;
neither local nor remote workflow success removes the stated formal and CDC
boundaries.

This is a correctness release. It supersedes v1.7.0, which contained
full-contract semantic defects in twelve monitor templates that were found by a
subsequent independent-reference audit. Users of v1.7.0 should upgrade.

## Why This Release Exists

v1.7.0 closed the language surface but its evidence chain had not yet been
audited against a reference model that was written independently of the compiler.
Building that reference (`tests/differential_reference.py`, which imports neither
compiler IR nor composition/emission code) exposed real semantic divergence in
the full-contract behaviour of several property templates. Those divergences are
fixed here.

## Semantic Corrections

Full-contract semantics were corrected across the following templates:
`prop_and`, `prop_or`, `prop_not`, `prop_if_else`, `prop_intersect`,
`prop_throughout`, `prop_within`, `nonoverlap`, `overlap_bitvec`, `mc_seq_top`,
and `sync_2dff`.

The composition layer was simplified as part of the fix rather than extended,
removing net logic from `composer.py`.

## Verification Infrastructure

An independent source-semantic reference model was added for differential
testing. It consumes the typed specification that rendered the SVA source, so an
importer or composer mistake cannot become the expected differential result.

Release identity is now enforced by test rather than by convention.
`tests/test_release_identity.py` asserts agreement between `__version__`,
`pyproject.toml`, `uv.lock`, `LICENSE`, and `SUPPORTED_CONSTRUCTS.md`.
`tests/test_ci_workflows.py` additionally guards the README against describing
capabilities the project does not implement.

Verilator is now pinned to v5.028 with checksum verification via
`tools/ci/install_verilator.sh`. Verilator v5.050, which reached CI runner
images in July 2026, introduced lint and simulation behaviour changes unrelated
to this project's code.

Packaging was corrected so that Jinja2 templates are included in both wheel and
sdist distributions.

## Support Status

No construct row is promoted to `Fully supported` in this release. The six rows
that were promoted in the v1.7.0 documentation have been returned to
`Bounded evidence`, because that promotion relied on a remote CI run for a
different commit rather than on current-commit evidence. Promotion requires a
same-commit green remote run across all gates.

See [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md) for per-construct evidence and
[INDUSTRIAL_VALIDATION_GAPS.md](INDUSTRIAL_VALIDATION_GAPS.md) for open gaps.

## Documentation

The README now documents the formal verification methodology, including the
non-circularity principle, the distinction between bounded (BMC) and unbounded
(k-induction) claims, miter construction, and stated limitations. Academic
references, standards, and tool attributions were added.

A request for commercial formal tool sponsorship was added. Cross-tool
validation against JasperGold or an equivalent would let the project confirm or
locate divergence between its reading of IEEE 1800 and a reading developed
independently against industrial designs.

## Verification Baseline

Local, this commit:

| Gate | Result |
|------|--------|
| Fast suite | 1296 passed, 1 xfailed, 0 failed |
| ruff | 0 errors |
| mypy --strict | 0 errors |

Post-release remote qualification is recorded for baseline `b055105` in CI run
`30683023280`, differential nightly run `30683026683`, and Full Formal run
`30683026438`. These runs validate the post-release baseline, not the immutable
`v1.7.1` tag itself.
