---
quick_id: 260802-mhy
mode: quick-full-inline
status: complete
date: 2026-08-02
---

# Quick Task 260802-mhy Plan

## Goal

Relicense the current sva2rtl distribution from BSL-1.1 to Apache-2.0, make
the public README accurate and easy to follow, document a reproducible formal
verification workflow and the boundary between supported bounded SVA and
unsupported advanced forms, then anonymously commit, push, and qualify the
exact remote commit.

## Must haves

### Truths

- The root license text is the unmodified official Apache License 2.0 text.
- Package metadata, public project instructions, tests, and README all identify
  the current license as `Apache-2.0`; no current BSL production-use restriction
  remains.
- README support claims defer to `SUPPORT_MATRIX.md`, state that zero construct
  rows are currently Fully supported, and do not imply that every SVA operator
  can be synthesized or formally proven.
- Formal guidance distinguishes simulation, BMC, induction/prove, cover
  reachability, synthesis/lint, mutation testing, local evidence, and
  exact-commit remote evidence.
- Unsupported or unsafe advanced forms have explicit bounded rewrites,
  hand-authored-monitor, simulation-only, or commercial-tool alternatives.
- Git author/committer metadata and committed content contain no personal email,
  home directory, token, credential, or other private information.

### Artifacts

- `LICENSE`
- `README.md`
- `FORMAL_VERIFICATION.md`
- `pyproject.toml`
- `AGENTS.md`
- `tests/test_release_identity.py`
- `tests/test_ci_workflows.py`

### Key links

- README links to the detailed formal guide and the authoritative support matrix.
- The formal guide derives executable commands from the checked-in CI, nightly,
  and Full Formal workflows.
- Project metadata uses an SPDX license expression accepted by the build backend.

## Tasks

### 1. Relicense and lock repository truth

**Files:** `LICENSE`, `pyproject.toml`, `AGENTS.md`, license-related tests.

**Action:** Replace BSL-1.1 with the official Apache-2.0 license text, update
package and project metadata, and change release-identity tests from a
version-bearing BSL assertion to cross-file Apache-2.0 consistency checks.

**Verify:** Search current public files for stale BSL/source-available terms;
build wheel and sdist; inspect their license metadata and contents.

**Done:** Fresh distributions carry Apache-2.0 and tests prevent license drift.

### 2. Correct README and add formal/advanced-SVA guide

**Files:** `README.md`, `FORMAL_VERIFICATION.md`, README contract tests.

**Action:** Lead with the bounded compiler scope; make support tiers explicitly
non-certification labels; add a practical compile-and-verify path; explain why
open-source SVA frontends alone do not synthesize every temporal construct;
document the implemented lowering, formal miter, assumptions, BMC/prove/cover
interpretation, current limitations, and fail-closed alternatives.

**Verify:** Link/path/command audit, README contract tests, Markdown diff check,
and comparison against `SUPPORT_MATRIX.md`, `SUPPORTED_CONSTRUCTS.md`, and the
checked-in workflow commands.

**Done:** A new contributor can identify what is supported, reproduce the
formal gates, interpret results without overclaiming, and choose a safe fallback.

### 3. Qualify, commit anonymously, and push

**Files:** all changed files plus GSD task artifacts/state.

**Action:** Run targeted tests, full dual-simulator tests, generated RTL gates,
Full Formal, differential sweeps, mutation tests, quality gates, packaging, and
privacy scan. Commit with repository-local anonymous identity, push `main`, then
trigger and wait for CI, differential-nightly, and Full Formal on the exact SHA.

**Verify:** Zero local failures; clean worktree; remote run head SHA equals the
pushed SHA and every required job concludes success.

**Done:** Apache-2.0 documentation is on `origin/main` with both local and remote
same-commit evidence, or any external blocker is reported without upgrading the
evidence claim.
