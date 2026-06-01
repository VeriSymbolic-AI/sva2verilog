---
status: issues_found
phase: 06-cli-polish-verilog-2001-integration-testing
depth: standard
files_reviewed: 28
findings:
  critical: 0
  high: 5
  medium: 10
  low: 9
  total: 24
created: "2026-06-02T00:09:00Z"
---

# Phase 06 Code Review

**Scope:** Phase 06 additions — CLI flags (`--dump-ast`, `--dump-ir`,
`--property`, `--verilog`, `--version`), multi-property pipeline,
Verilog-2001 output mode (`verilog_mode` Jinja2 guards in 11 templates),
integration tests, and CI workflow.

**Diff base:** `d8f5c9e..HEAD` (~+2984 / −170 across 46 files).

**Files reviewed:**
- `.github/workflows/ci.yml`
- `LICENSE`, `README.md`, `SUPPORTED_CONSTRUCTS.md`, `pyproject.toml`
- `src/sva2rtl/{ast_importer,cli,debug,emitter,errors}.py`
- `templates/{bool_expr,concat_delay,disable_iff_top,fell,nonoverlap,
  overlap_bitvec,past,rep_consecutive,rose,seq_concat_top,stable}.sv.j2`
- `tests/{conftest.py,test_cli.py,test_cli_phase6.py,test_disable_iff.py,
  test_integration_full.py,test_optimizer.py,test_verilog_mode.py}`

**Severity key:** HIGH = likely bug / correctness defect (>80% confidence).
MEDIUM = code smell / maintainability risk. LOW = style.

> **Note on H-01..H-04 from `03-REVIEW.md`:** the Phase 03 high-severity
> defects (`_DECLARATIONS` global not reset, `rep_consecutive` silent miss,
> `attempt_fired_q` cleared by `disable_i`, `_collect_signals` discarding
> sig_name) are still present in this diff. They are out of Phase 06 scope
> and not re-listed below, but Phase 06's broadening of the verilog_mode
> templates means H-03 (`attempt_fired_q` reset on `disable_i`) is now
> reproduced verbatim in the Verilog-2001 branch of every leaf template
> as well. Tracking should escalate.

---

## HIGH — Likely Bugs

### H-06.1 · `--dump-tree` after `--property` filter prints **all** assertions, not just the matched one (multi-property branch)

**File:** `src/sva2rtl/cli.py` — multi-assertion branch, lines 178–224.

In the multi-property branch the code unconditionally iterates every
`normalized_assertions` entry, calls `compose()` on it, and emits a
`format_dump_tree(...)` for each, even when the user supplied
`--property foo`. The `--property` filter on lines 120–135 *does* trim
`assertions` down to a single match, but only single-property assertions
go through the `len(assertions) == 1` branch which has its own `dump_tree`
handling. If `--property` matches the single result, we go to the
single-assertion path (good); however, if the user passes `--dump-tree`
with `--no-optimize`, the `unoptimized_checker` is captured **after**
`optimize()` has already run on the same name (lines 150–165) — meaning
the “before” count shown by `format_dump_tree` is **identical** to the
“after” count, defeating the purpose of the optimization summary.

Concretely:
```python
checker_node = compose(node, clock, label, original_text)
unoptimized_checker = checker_node           # ← snapshot

if not no_optimize:
    checker_node = optimize(checker_node)    # ← rebinds checker_node only
```
This works correctly when `optimize()` returns a *new* tree (it does —
`optimize()` is purely functional). But the dump-tree handler then does:
```python
unoptimized_checker=(unoptimized_checker if not no_optimize else None),
```
So when `--no-optimize` is set, it deliberately passes `None`, and
`format_dump_tree` falls back to the single-line stats output. That part
is fine. The real issue is that the multi-property branch (lines 196–214)
**never** captures `unoptimized_checker` and always passes
`unoptimized_checker=None` regardless of `--no-optimize`, so the
optimization summary is never shown for multi-property dumps even when
optimization ran. This is silent feature loss for the most common
use case (a file with several assertions).

**Fix:** capture `unoptimized = compose(...)` before optimize in the
multi-property loop, and pass it through to `format_dump_tree` mirroring
the single-property branch.

---

### H-06.2 · `--property` filter compares against the **label**, but unlabeled assertions cannot be selected and produce a misleading `available: <none>` error

**File:** `src/sva2rtl/cli.py` — lines 121–135.

```python
matched = [
    (node, clock, text, label)
    for node, clock, text, label in assertions
    if label == property_name
]
if not matched:
    available_labels = [
        label for _, _, _, label in assertions if label is not None
    ]
    raise PropertyNotFound(...)
```

The CLI documents `--property` as “Compile only the assertion with this
label”, but in practice the AST importer assigns `label=None` to **every
unlabeled** `assert property (...)` statement (see
`_find_assertion_in_members` in `ast_importer.py:382` — only `Block`
nodes carry a label). For a file with multiple `assert property (...)`
statements (no leading labels), `available` is `[]`, and the user sees
`Available: [<none>]` even though several assertions exist. There is no
actionable workaround in the message — the user is left to guess that
they need to add labels.

In addition: a user passing `--property foo` against a file with **only
unlabeled** assertions silently filters everything out, exits 2, and
produces an error message that does not mention this possibility.

**Fix options:**
1. Auto-generate fallback labels (`prop_0`, `prop_1`, …) and surface
   them in `available` when `label is None`. Then the error message can
   say `Available: [prop_0, prop_1] (auto-generated; original
   assertions are unlabeled)`.
2. Document explicitly in the CLI help and `README.md` that `--property`
   requires a labeled assertion, and produce a clearer error
   (`SVA-E005: '<name>' not found; only labeled assertions are
   selectable. <N> unlabeled assertions found.`).

`README.md` line 53–55 implies labels work via the example
`req_ack_prop`, but never warns the user that unlabeled assertions are
unselectable.

---

### H-06.3 · `cli.py` interprets `--output` as a directory **iff** `checker_node.children` is truthy — surprising and undocumented

**File:** `src/sva2rtl/cli.py` — single-property branch lines 171–177;
multi-property branch lines 222–224; CLI help text line 45.

```python
if checker_node.children:
    modules = emit_all(checker_node, verilog_mode=verilog)
    out_dir = Path(output) if output else Path(".")
    write_output_dir(modules, out_dir)
else:
    sv_text = emit(checker_node, verilog_mode=verilog)
    write_output(sv_text, Path(output) if output else None)
```

The CLI help string says `Output file path (default: stdout)`. But in
practice:
- For a `bool_expr`-only assertion: `--output foo.sv` writes one file.
- For an `implication`/`disable_iff`/`seq_concat` assertion: `--output
  foo.sv` is interpreted as a *directory* `foo.sv/` and emits multiple
  `.sv` files inside it. The user almost certainly expected a single file.

`README.md` line 49 reinforces the file-path assumption with
`-o monitor.sv`. The integration test `test_property_filter_single`
(`test_integration_full.py:214`) succeeds only because its mocked
assertion uses `BoolExpr` (no children) — the test would fail with a
real implication property writing into a path treated as a file.

This is a UX bug rather than a hard correctness bug, but it will lead
to bug reports.

**Fix options:**
1. If `output` is non-`None` *and* the path has a suffix (e.g.,
   `.sv`/`.v`), warn (or error) that hierarchical checkers must use a
   directory; document this in CLI help.
2. Always emit to a directory when `emit_all()` is used; require a
   trailing `/` from the user.
3. Bundle multi-module output into a single file (concatenating
   modules) when `output` looks like a file path.

Whichever is chosen, the discrepancy between help text and behavior
must be removed. This also intersects with H-06.4 (multi-property +
`--output` always treated as directory).

---

### H-06.4 · `--verilog` flag is **not threaded** to `format_dump_tree`, `format_dump_ir`, or the bind emitter

**Files:** `src/sva2rtl/cli.py` — lines 91, 115, 144–169, 187–215;
`src/sva2rtl/debug.py`; `src/sva2rtl/emitter.py:emit_bind`.

Symptoms:
- `--dump-ast --verilog` is silently accepted but `--verilog` has no
  effect on AST output (acceptable — the AST is JSON).
- `--dump-ir --verilog` is silently accepted but `--verilog` has no
  effect because `format_dump_ir` does not consume `verilog_mode`
  (acceptable — IR is mode-independent).
- `--dump-tree --verilog` is silently accepted but neither
  `compute_hash_map` nor `format_dump_tree` consume `verilog_mode`. The
  dumped composition tree is identical between modes (acceptable —
  composition is mode-independent).
- `emit_bind` (`emitter.py:206`) accepts `verilog_mode` but the CLI
  never invokes the bind emitter, so the bind `templates/bind.sv.j2`
  has no Verilog-2001 path tested by Phase 06.

These are all *acceptable today* given the scope of Phase 06, but
none of them are documented. A user reading the CLI help would
reasonably expect `--verilog` to combine meaningfully with the dump
flags (e.g., to produce a Verilog-2001-shaped IR comment or bind),
and may file a bug. Recommend adding a one-line note in the CLI help
or `README.md`: `--verilog only affects emitted RTL output; it is
ignored with --dump-ast/--dump-ir/--dump-tree.`

The genuine bug here: `bind.sv.j2` is not in the diff but `emit_bind`
silently accepts a `verilog_mode` kwarg it never uses (see
`emitter.py:246`). Either remove the parameter or thread it through
the template (with a `verilog_mode` guard) to match the rest of the
codebase. As-is the kwarg looks intentional but is dead code.

---

### H-06.5 · `verilog_mode` Jinja2 guards duplicate ~30 lines of always-block body across 11 templates → one-place edit becomes 22-place edit

**Files:** `templates/{bool_expr,concat_delay,disable_iff_top,fell,
nonoverlap,overlap_bitvec,past,rep_consecutive,rose,stable}.sv.j2`.

Every template that contains an `always_ff` block uses this pattern:

```jinja
{% if verilog_mode %}
    reg [N-1:0] state_q;
    always @({{ clock_edge }} {{ clock_signal }}) begin
        if (!rst_n || disable_i) begin
            state_q <= 0;
            ...
        end else begin
            state_q <= ...;
        end
    end
{% else %}
    logic [N-1:0] state_q;
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        if (!rst_n || disable_i) begin
            state_q <= '0;
            ...
        end else begin
            state_q <= ...;
        end
    end
{% endif %}
```

The body of the `always` block is **textually duplicated** between the
two branches. Any logic change to the always block (e.g., the H-03 fix
from Phase 03 review separating `attempt_fired_q` from the disable
reset) now requires an edit in 22 places (11 templates × 2 branches),
each of which can drift independently.

`overlap_bitvec.sv.j2` and `nonoverlap.sv.j2` already show drift risk:
the body is ~50 lines long and most of it is identical between branches
except for the four token differences (`logic`/`reg`, `always_ff`/`always`,
`<= '0`/`<= 0`, sometimes `'0` vs `0`).

**Fix:** Refactor templates with Jinja2 macros or filters that abstract
just the four lexical differences. Two viable approaches:

```jinja
{# macro / set-based approach #}
{% set logic_kw = "reg" if verilog_mode else "logic" %}
{% set always_kw = "always" if verilog_mode else "always_ff" %}
{% set zero = "0" if verilog_mode else "'0" %}

{{ logic_kw }} [N-1:0] state_q;
{{ always_kw }} @({{ clock_edge }} {{ clock_signal }}) begin
    if (!rst_n || disable_i) begin
        state_q <= {{ zero }};
    end else begin
        state_q <= ...;
    end
end
```

This shrinks every template by ~40% and makes future logic changes
local. It also reduces the chance of subtle SystemVerilog/Verilog-2001
divergence (e.g., one mode missing a sticky-bit assignment).

I would not block Phase 06 release on this, but it should be the very
next refactor before any further changes land in the templates. Mark as
HIGH because the code-duplication has a concrete near-term failure mode
(silent template drift) that the H-03 fix from Phase 03 review will
need to navigate immediately.

---

## MEDIUM — Code Smell / Maintainability

### M-06.1 · `cli.py` exception handlers are order-sensitive and the `SvaError` catch silently swallows new error subclasses

**File:** `src/sva2rtl/cli.py` — lines 228–246.

```python
except SlangNotFound as exc:        # exit 3
    ...
except PropertyNotFound as exc:     # exit 2
    ...
except UnsupportedConstruct as exc: # exit 2
    ...
except SvaError as exc:             # exit 1 (catch-all for SvaError subclasses)
    ...
except Exception as exc:            # exit 1 (BLE001: bare except)
    ...
```

Adding a new `SvaError` subclass (e.g., a future `MultiClockError` for
SVA-E003 with its own exit code) without updating this stack will cause
it to be silently mapped to exit code 1, which contradicts the error
docs in `SUPPORTED_CONSTRUCTS.md` lines 138–144 that imply distinct
error codes per error class. Recommend either:

1. A small dispatch table mapping exception class → exit code.
2. Adding `exit_code: int` as a class attribute on every `SvaError`
   subclass, and using a single `except SvaError as exc: sys.exit(
   exc.exit_code)` block.

The current ad-hoc approach has already produced the
`SvaCompileError(message="SVA-E002: …")` collision (see L-06.2).

---

### M-06.2 · `SvaCompileError` is **also** used for SVA-E002 and SVA-E003 messages → exit code becomes inconsistent with `SUPPORTED_CONSTRUCTS.md`

**Files:** `src/sva2rtl/ast_importer.py` lines 537, 651, 659, 778, 788
(all raise `SvaCompileError(message="SVA-E00{2,3}: ...")`);
`src/sva2rtl/errors.py` lines 50–55 (SvaCompileError → exit 1);
`SUPPORTED_CONSTRUCTS.md` line 141 (SVA-E002 / SVA-E003 categorized
as “Error”, no exit code mapping shown but readers will assume it
matches `UnsupportedConstruct` → exit 2).

The SVA-E002 / SVA-E003 *messages* are surfaced via `SvaCompileError`
so they exit 1, but `UnsupportedConstruct` (also documented as
SVA-E002 in `errors.py:71`) exits 2. There are now two SVA-E002
producers with different exit codes:

- `_build_seq_repetition` raises `SvaCompileError("SVA-E002: ...")` →
  exit 1.
- `_check_unsupported` raises `UnsupportedConstruct(...)` (string
  contains SVA-E002) → exit 2.

A wrapper script that does `sva2rtl x.sv; if [[ $? -eq 2 ]]; then echo
unsupported; fi` will see one of the two SVA-E002 cases and miss the
other.

**Fix:** Refactor SVA-E002/E003 to use dedicated exception classes
(or a single `SvaSemanticError` with a numeric `code` field), and
update the error-code → exit-code mapping table in `errors.py`'s
docstring to be the single source of truth.

---

### M-06.3 · `--dump-ir` for multi-property dumps every property without a separator label, making them indistinguishable

**File:** `src/sva2rtl/cli.py` — lines 187–192.

```python
parts: list[str] = []
for norm_node, _clock, _text, _label, _raw in normalized_assertions:
    parts.append(format_dump_ir(norm_node))
click.echo("\n\n".join(parts))
```

Each property gets the same `=== Normalized IR ===` header with no
mention of which assertion it belongs to. A user dumping a 5-property
file gets 5 identical headers and 5 IR trees in unmarked sequence.
Compare to the single-property branch which would have the same
header and no label.

**Fix:** Pass the label/text into `format_dump_ir` so the header reads:
```
=== Normalized IR — property 'foo' (file.sv:12:5) ===
```
Same applies to multi-property `--dump-tree` (lines 201–214).

---

### M-06.4 · CLI documents `--default-clock` (in error message text) but the flag does not exist

**File:** `src/sva2rtl/ast_importer.py:806`.

```python
raise SvaCompileError(
    message=(
        f"Property at {source_loc} has no clock annotation. "
        "Use @(posedge clk) or --default-clock flag."
    )
)
```

`--default-clock` is referenced in the error help but is not declared
in `cli.py`. A user following the suggestion would hit `Error: No such
option: --default-clock`. The flag was apparently planned but never
implemented.

**Fix:** Either implement `--default-clock` (a single string option
that becomes the fallback `ClockSpec`) or remove the suggestion from
the error message until it is wired up. Currently this is misleading
documentation.

---

### M-06.5 · `SUPPORTED_CONSTRUCTS.md` describes SVA-E005 as a *warning* about state-space size, but the code uses SVA-E005 for `PropertyNotFound`

**Files:** `SUPPORTED_CONSTRUCTS.md` line 144;
`src/sva2rtl/errors.py:103` (`PropertyNotFound.__str__` →
`error SVA-E005: property 'foo' not found.`).

The error-code table says:
```
| SVA-E005 | Warning | Property may generate large state space (>256 states) | ... |
```
But in code SVA-E005 is the property-not-found error, severity =
Error, exit = 2. The `>256 states` warning does not exist in code at
all. Two collisions: error number is reused and the warning is
unimplemented documentation.

**Fix:** Either reassign one of them to SVA-W001 (warnings) /
SVA-E006 (next free number), or remove the unimplemented row from the
table. Either way the public error reference must match what the
binary emits.

---

### M-06.6 · Missing CLI snapshot / golden-output coverage for `--verilog`

**File:** `tests/test_verilog_mode.py`, `tests/test_integration_full.py`.

The Phase 06 tests verify *negative* properties of Verilog-2001
output (no `logic`, no `always_ff`, no `'0`). They do **not** lock
down the *positive* shape of the generated Verilog-2001, so a future
template edit could quietly regress the output (e.g., emit
`reg [N:0]` instead of `reg [N-1:0]`) and the tests would still pass.
The single integration test
(`test_out05_verilog_compiles_iverilog`) only checks `bool_simple`
through `iverilog -g2001 -o /dev/null`, which is a syntactic gate
and ignores semantics.

**Fix:** Add at least 3–4 golden `.v` files (one per template family:
`bool_expr`, `concat_delay`, `rose`/`fell`, `overlap_bitvec`) and
compare via `assert_golden` (already implemented in `conftest.py:82`).
The golden harness handles trailing-whitespace robustness, so this is
low-friction.

---

### M-06.7 · CI pins slang to v7.0 but the `README.md` and `CLAUDE.md` advertise v11.0

**Files:** `.github/workflows/ci.yml:48,59`; `README.md:30`;
`CLAUDE.md` lines 29, 46.

CI deliberately pins slang to v7.0 because the JSON AST fixtures were
generated against that version. The user-facing docs say v11.0+. A
contributor who installs slang v11.0 per the README and runs `pytest`
locally may see fixture mismatches not present in CI (or vice versa).

**Fix options:**
1. Pin both CI and the README to v7.0 with a roadmap item: “update
   fixtures + bump to v11.0 in Phase 07”.
2. Regenerate fixtures against v11.0 now and update CI.
3. Have a regeneration script committed so devs can `make regen-fixtures`
   when their slang version differs.

The current state will surface as a mysterious test failure for new
contributors.

---

### M-06.8 · `tests/conftest.py` registers `simulation` marker manually but `pyproject.toml` already does so → silent disagreement risk

**Files:** `tests/conftest.py:23–28`; `pyproject.toml:60`.

Both files register the `simulation` marker. Only `pyproject.toml`
registers `integration`. A future refactor that consolidates markers
in one place will trip over this duplication. Drop the
`pytest_configure` hook in `conftest.py` and rely on
`pyproject.toml`.

---

### M-06.9 · `cli.py` imports `compute_hash_map` and `format_dump_tree` *inside* the `if dump_tree:` branch

**File:** `src/sva2rtl/cli.py:154–168, 201–213`.

```python
if dump_tree:
    from sva2rtl.composer import compute_hash_map
    from sva2rtl.debug import format_dump_tree
    ...
```

Function-local imports are usually a sign of an unresolved circular
import, but in this case `composer` and `debug` are already imported
at the top of `cli.py` (transitive). The deferred imports save a
few microseconds at startup but make the dependency graph harder to
read and break IDE go-to-definition. Promote them to module level.

---

### M-06.10 · `pyproject.toml` `[project.urls]` uses `allenenli` while `README.md` uses `allenli`

**Files:** `pyproject.toml:22–24` (`https://github.com/allenenli/sva2rtl`);
`README.md:112` (`git clone https://github.com/allenli/sva2rtl.git`).

Two different GitHub usernames in the same repo. One of them is dead.

**Fix:** pick the canonical URL and update the other.

---

## LOW — Style

### L-06.1 · `cli.py` swallows `__name__` of unexpected exceptions

**File:** `src/sva2rtl/cli.py:244–246`.

```python
except Exception as exc:  # noqa: BLE001
    click.echo(f"internal error: {exc}", err=True)
    sys.exit(1)
```

The exception class is dropped. A `KeyError` and a `ValueError` are
indistinguishable in the user-visible message. Recommend
`f"internal error: {type(exc).__name__}: {exc}"` so a bug report
contains actionable info. The `InternalError` class in
`errors.py:77–85` already has the right pattern; reuse it.

---

### L-06.2 · `errors.py:71` puts the error code into the message string instead of into a numeric field

**File:** `src/sva2rtl/errors.py:68–73`.

```python
def __str__(self) -> str:
    loc_prefix = f"{self.source_loc}: " if self.source_loc else ""
    return (
        f"{loc_prefix}error SVA-E002: unsupported construct "
        f"'{self.construct_name}': {self.message}"
    )
```

If we want machine-readable error categorization (so external tools
can grep on `SVA-E\d+`), the code should be a class attribute, not a
hard-coded string substring inside `__str__`. As-is, the
SVA-E002/E003/E004/E005 codes are scattered: some live in
`error.__str__` (E002, E005), others in `SvaCompileError(message="SVA-
E00x: ...")` strings (E001, E003, E004). See M-06.2.

---

### L-06.3 · `templates/seq_concat_top.sv.j2` lacks a `wire` declaration helper for the `disable_i` chain

**File:** `templates/seq_concat_top.sv.j2`.

Each child instantiation passes `disable_i` directly. There is no
`always` block in this template, so verilog_mode/SV mode parity is
mostly trivial — yet it still doubles a long port list inside an `{%
if %}{% else %}{% endif %}` block. The 18-line port list is duplicated
exactly except for `input logic`/`input`. This is the same H-06.5
duplication issue at smaller scale. Same fix applies via macros.

---

### L-06.4 · `concat_delay.sv.j2` zero-delay case skips `count_q`/`running_q` declarations only inside `{% else %}` — Verilog-2001 branch declares them anyway

**File:** `templates/concat_delay.sv.j2:29–50`.

When `delay_min == "0"` and `delay_max == "0"` the SystemVerilog branch
provides only the combinational pass-through, but the structure of the
template is `{% if delay_min == "0" and delay_max == "0" %}<combo>{%
else %}<counter>{% endif %}` — and **inside the `<combo>` block**
there is a separate `{% if verilog_mode %}` for the `attempt_fired_q`
register. This nested-if logic is correct but very hard to follow and
has already led to `delay_zero` fixture coverage in
`test_verilog_mode.py:_ALL_FIXTURES`. Recommend extracting the
common port list and the `attempt_fired_q` always block into a Jinja2
include so each template only has to render the operator-specific
body. (Same root cause as H-06.5.)

---

### L-06.5 · `bool_expr.sv.j2` registered outputs gate `attempt_fired_q` on `disable_i` (Phase 03 H-03 reproduced in verilog_mode branch)

**File:** `templates/bool_expr.sv.j2:50–60`.

Both verilog_mode branches now reset `attempt_fired_q` on `disable_i`,
duplicating the Phase 03 H-03 defect across 11 templates × 2 branches
= 22 sites. Fixing H-03 will be 22 line edits unless we first do the
H-06.5 refactor. Calling this out as a sequencing concern, not a new
defect.

---

### L-06.6 · `SUPPORTED_CONSTRUCTS.md` describes `attempt_fired` as a “pulse” but the templates make it sticky

**File:** `SUPPORTED_CONSTRUCTS.md` line 99 vs `README.md:104`
(`output logic attempt_fired, // Pulse when a new attempt begins`).

Both files imply `attempt_fired` is a pulse. Every template implements
it as a sticky bit (`attempt_fired_q <= attempt_fired_q | start`),
which is consistent with the `ir.py` doc comment but contradicts the
public-facing README/SUPPORTED_CONSTRUCTS.

**Fix:** Update the public docs to say `output logic attempt_fired,
// Sticky: latched on first start; cleared only by rst_n.`

---

### L-06.7 · Repeated `disable_i ? 1'b0 : ...` boilerplate

**File:** every leaf template (e.g., `bool_expr.sv.j2:62–67`,
`rose.sv.j2:71–75`, `fell.sv.j2:71–75`, `stable.sv.j2:71–75`,
`past.sv.j2:114–118`, `rep_consecutive.sv.j2:113–117`).

```sv
assign active = disable_i ? 1'b0 : active_q;
assign pass   = disable_i ? 1'b0 : pass_q;
assign fail   = disable_i ? 1'b0 : fail_q;
```

This pattern is repeated 7 times per template across 11 templates. A
small Jinja2 macro `{% macro gate_output(name, src) %}assign {{ name
}} = disable_i ? 1'b0 : {{ src }};{% endmacro %}` would cut
~50 lines. Same root cause as H-06.5.

---

### L-06.8 · `cli.py` `version` flag exits before any other processing — but it is declared *after* `--no-optimize` on the command line

**File:** `src/sva2rtl/cli.py:91`.

`@click.version_option(package_name="sva2rtl", prog_name="sva2rtl")`
is fine — click handles `--version` before invoking `main()`. But the
flag is registered without a help string, so `--help` shows
`--version  Show the version and exit.` (default click string), which
is fine but inconsistent in tone with the rest of the help (which
uses sentence-case descriptions). Consider
`help="Print version and exit."` to match `README.md:89`.

---

### L-06.9 · `tests/test_cli_phase6.py:_LOC` shadows the global SourceLoc fixture in `conftest.py`

**File:** `tests/test_cli_phase6.py:21`.

The module-level `_LOC` and the conftest fixture
`sample_source_loc` both produce a `SourceLoc("test.sv", N, M)`. Only
the test_cli_phase6 module uses `_LOC`, but the duplication invites
divergence. Replace with the conftest fixture.

---

## Positive Observations

- **Test architecture is solid.** Every code path in the new CLI
  branches is covered by unit tests in `test_cli_phase6.py` plus
  black-box integration tests in `test_integration_full.py`. The
  `assert_golden` helper in `conftest.py:82` is well-designed
  (whitespace-robust diffing).

- **Verilog-2001 negative tests are thorough.** Parametrized over 16
  fixtures × 4 keyword properties = 64 assertions; an iverilog
  `-g2001` syntactic compile gate is the right minimum.

- **Optimizer parity tests** in `test_optimizer.py` (lines 786–818)
  enforce three meaningful invariants (no node growth, no module
  growth, idempotency). These are exactly the right structural
  contracts for an optimizer.

- **CI matrix is reasonable.** Linux+macOS × Python 3.12+3.13 × ruff
  + mypy strict + pytest = 4 lanes. The slang install steps are
  separated for each OS. The `--timeout=120` on pytest is a good
  guard against deadlocked simulation tests.

- **Error class hierarchy** is clean (`SvaError` base + 5 subclasses,
  each with a meaningful exit code). The `__str__` method
  customizations are appropriate.

---

## Summary Table

| ID    | Severity | File(s)                                           | Description                                                                                            |
|-------|----------|---------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| H-06.1| HIGH     | `cli.py:178–224`                                  | Multi-property branch never captures `unoptimized_checker` → `--dump-tree` summary missing             |
| H-06.2| HIGH     | `cli.py:121–135`                                  | `--property` cannot select unlabeled assertions; error msg lists `<none>` and is misleading            |
| H-06.3| HIGH     | `cli.py:171–177,222–224`; `README.md:49`          | `--output` is a file or a directory depending on tree shape; help says “file path”                     |
| H-06.4| HIGH     | `cli.py`, `emitter.py:206`                        | `--verilog` silently ignored by dump flags + dead `verilog_mode` kwarg in `emit_bind`                  |
| H-06.5| HIGH     | All 11 verilog_mode templates                     | Massive Jinja2 if/else duplication of always-block bodies → fix-once becomes fix-22                    |
| M-06.1| MEDIUM   | `cli.py:228–246`                                  | Exception → exit-code mapping is order-sensitive; new `SvaError` subclasses silently exit 1            |
| M-06.2| MEDIUM   | `ast_importer.py`, `errors.py`                    | SVA-E002 raised with two different exit codes (1 and 2) depending on call site                         |
| M-06.3| MEDIUM   | `cli.py:187–214`                                  | `--dump-ir`/`--dump-tree` for multi-property emits identical headers, no label                         |
| M-06.4| MEDIUM   | `ast_importer.py:806`                             | Error message advises `--default-clock` flag that does not exist                                       |
| M-06.5| MEDIUM   | `SUPPORTED_CONSTRUCTS.md:144`, `errors.py:103`    | SVA-E005 documented as state-space warning but used as PropertyNotFound error                          |
| M-06.6| MEDIUM   | `tests/test_verilog_mode.py`                      | Verilog-2001 tests are negative-only; no positive golden RTL coverage                                  |
| M-06.7| MEDIUM   | `ci.yml`, `README.md`                             | CI pins slang v7.0; docs advertise v11.0+ → contributor mismatch                                       |
| M-06.8| MEDIUM   | `conftest.py:23`, `pyproject.toml:60`             | `simulation` marker registered in two places                                                           |
| M-06.9| MEDIUM   | `cli.py:154–168,201–213`                          | Function-local imports of `compute_hash_map`/`format_dump_tree` despite no circular dep                |
| M-06.10| MEDIUM  | `pyproject.toml:22–24`, `README.md:112`           | Inconsistent GitHub username (`allenenli` vs `allenli`)                                                |
| L-06.1| LOW      | `cli.py:244–246`                                  | Internal-error message drops exception class name                                                      |
| L-06.2| LOW      | `errors.py:71`                                    | Error code is a substring inside `__str__`, not a class attribute                                      |
| L-06.3| LOW      | `templates/seq_concat_top.sv.j2`                  | 18-line port-list duplication across `verilog_mode` branches                                           |
| L-06.4| LOW      | `templates/concat_delay.sv.j2`                    | Nested `{% if delay_min == "0" %}` × `{% if verilog_mode %}` is hard to follow                         |
| L-06.5| LOW      | All 11 leaf templates                             | Phase 03 H-03 (`attempt_fired_q` cleared by `disable_i`) now duplicated across both mode branches      |
| L-06.6| LOW      | `SUPPORTED_CONSTRUCTS.md:99`, `README.md:104`     | Public docs call `attempt_fired` a pulse; templates implement it as sticky                             |
| L-06.7| LOW      | All 11 leaf templates                             | `disable_i ? 1'b0 : <q>` triplet repeated ~7× per template — refactorable to a Jinja2 macro            |
| L-06.8| LOW      | `cli.py:91`                                       | `--version` help string falls back to default click text; inconsistent tone vs other flags             |
| L-06.9| LOW      | `tests/test_cli_phase6.py:21`                     | Module-level `_LOC` shadows shared `sample_source_loc` fixture from conftest                           |

---

## Fix Priority

1. **H-06.5** first — the duplication shape is now baked into 11
   templates × 2 branches and will only get worse. This refactor
   should land before any further template work, including the H-03
   fix carried over from Phase 03.

2. **H-06.3 + H-06.4** together — both are CLI/UX bugs that produce
   surprising user-visible output. One contains a dead `verilog_mode`
   kwarg in `emit_bind` that is best removed in the same PR.

3. **H-06.2** — affects the most-likely use case (a file with multiple
   `assert property (...)` statements without leading labels) and
   currently produces an `Available: <none>` message that does not
   help the user.

4. **H-06.1** — silent feature loss for `--dump-tree` on multi-property
   files; small fix once located.

5. **M-06.4 + M-06.5** — both are documentation/code drift in the
   user-visible error catalog. Correct as a single docs-and-code PR.

6. **M-06.2 + M-06.1** — refactor exception → exit-code mapping into
   a class attribute. Together they remove the order-sensitivity of
   the `cli.py` except-stack and the SVA-E002 collision.

7. **M-06.6** — add 3–4 Verilog-2001 golden files; cheap with the
   existing `assert_golden` helper.

The remaining MEDIUM/LOW items can land opportunistically.
