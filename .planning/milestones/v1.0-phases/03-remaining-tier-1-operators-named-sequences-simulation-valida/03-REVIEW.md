# Phase 03 Code Review

**Scope:** Phase 03 additions — `[*N]/[*M:N]`, `$rose/$fell/$stable/$past`,
`disable iff`, named-sequence expansion, bind generation, behavioral oracle.

**Files reviewed:**
- `src/sva2rtl/ir.py`
- `src/sva2rtl/ast_importer.py`
- `src/sva2rtl/composer.py`
- `src/sva2rtl/emitter.py`
- `src/sva2rtl/behavioral_oracle.py`
- `templates/*.sv.j2` (all 12 templates)

**Severity key:** HIGH = likely bug / correctness defect (>80% confidence).
MEDIUM = code smell / maintainability risk. LOW = style.

---

## HIGH — Likely Bugs

---

### H-01 · `_DECLARATIONS` global not reset between `import_assertion()` calls

**File:** `src/sva2rtl/ast_importer.py` — lines 73, 110–115

```python
# module-level global, never explicitly reset to {}
_DECLARATIONS: dict[str, dict[str, Any]] = {}

def import_assertion(ast):
    global _DECLARATIONS
    for member in members:
        if member.get("kind") == "Instance":
            body = member.get("body", {})
            if body.get("kind") == "InstanceBody":
                _DECLARATIONS = _collect_declarations(body.get("members", []))
    # (second pass proceeds to find the assertion)
```

**Problem:** `_DECLARATIONS` is only overwritten when the AST contains an
`Instance` → `InstanceBody` node. If `import_assertion()` is called on an AST
that has no such nodes (e.g., a flat SVA-only file, or a mock dict in a unit
test), the global retains whatever value was left by the **previous** call in
the same process. In a pytest run, Test A (with named sequences `req_seq`) sets
`_DECLARATIONS = {"req_seq": ...}`. Test B (a plain BoolExpr test) never
triggers the reassignment, so `_DECLARATIONS` still contains `req_seq`. If the
plain-BoolExpr AST happens to contain a `SequenceInstance` referencing
`req_seq`, it would expand silently using the stale declaration from Test A
instead of raising `SVA-E003`.

The comment "Single-threaded compiler; module-level state is safe" is
incorrect: single-threaded means no *race* conditions, but it says nothing
about accumulated state across function calls.

**Fix:** Reset at the top of `import_assertion()` before the collection loop:
```python
global _DECLARATIONS
_DECLARATIONS = {}          # ← add this line
for member in members:
    ...
```

---

### H-02 · `rep_consecutive`: silent miss when `start=1` but `sig_eval=0` and `running_q=0`

**File:** `templates/rep_consecutive.sv.j2` — always_ff block (lines 36–48)
and output logic (lines 56–60); mirrored in `behavioral_oracle.py`
`_tick_rep_consecutive()` (lines 214–231).

**Problem:** When a new evaluation starts (`start=1`) and the expression is
false on the triggering cycle (`sig_eval=0`), and no prior evaluation is
running (`running_q=0`), none of the three `if/else if` branches in the RTL
applies:

```sv
if (start && sig_eval) begin   // false — sig_eval=0
    ...
end else if (running_q && sig_eval) begin  // false — running_q=0
    ...
end else if (running_q && !sig_eval) begin // false — running_q=0
    ...
end
// ← fall-through: nothing updates state
```

`attempt_fired_q` IS set (via `attempt_fired_q | start`), but neither pass nor
fail ever fires. For SVA semantics, `a[*N]` evaluated at a cycle where `a` is
false must immediately produce a **fail** — the sequence cannot match. The
monitor instead silently absorbs the evaluation token with no observable output.

The behavioral oracle reproduces the same gap:
```python
elif start and not sig:
    self._attempt_fired = True   # ← sets attempt_fired
    # no fail fired, no state transition
```

Since oracle and RTL agree, oracle-vs-RTL comparison tests will not catch this.
A cross-validation against a Verilog simulator will expose it.

**Fix (RTL):** Add an explicit branch:
```sv
end else if (start && !sig_eval) begin
    // sequence fails immediately — emit fail on this cycle
    // (can be done combinationally in the output section instead)
end
```
Or change the output combinationally:
```sv
assign fail_internal = (start && !sig_eval && !running_q)   // immediate fail
                     | (running_q && !sig_eval && (count_q < cnt_width'd{rep_min}));
```
**Fix (oracle):** Mirror the immediate-fail case in `_tick_rep_consecutive`.

---

### H-03 · `attempt_fired_q` cleared by `disable_i` — violates documented port contract

**Files:** `templates/bool_expr.sv.j2` (line 31), `templates/rose.sv.j2`
(line 22), `templates/fell.sv.j2` (line 22), `templates/stable.sv.j2`
(line 22), `templates/past.sv.j2` (line 27 / 43), `templates/rep_consecutive.sv.j2`
(line 31).

Every leaf template resets `attempt_fired_q` when `disable_i` is asserted:

```sv
if (!rst_n || disable_i) begin   // ← disable_i clears attempt_fired_q
    ...
    attempt_fired_q <= 1'b0;
end
```

The `CheckerNode` port contract (documented in `ir.py` lines 190–195) states:

> `attempt_fired` — sticky: set on first `start` pulse, **never cleared
> except by reset**.  Prevents vacuous-satisfaction (pitfall P1.1).

`disable_i` is not a reset — it is a conditional suppression of evaluation.
Clearing `attempt_fired` on a disable event means:

1. Assertion fires at cycle T → `attempt_fired = 1`.
2. `disable iff` condition becomes true at T+5 → body receives `effective_disable = 1`.
3. `attempt_fired_q` resets to 0.
4. External monitor / testbench reads `attempt_fired = 0` → incorrectly
   concludes the property was **never** checked → vacuous-satisfaction false
   negative, exactly the pitfall the field exists to prevent.

The `disable_iff_top.sv.j2` wrapper passes `effective_disable = disable_i |
cond_result` into the body, so the condition firing is sufficient to trigger
this reset.

The behavioral oracle also clears `_attempt_fired` in `reset()`, which is
called on every `disable` tick, reproducing the same incorrect behavior.

**Fix:** Separate the `attempt_fired_q` register from the `disable_i` reset
path. It should only be cleared by `!rst_n`:

```sv
always_ff @(posedge clk) begin
    if (!rst_n) begin
        attempt_fired_q <= 1'b0;
    end else begin
        attempt_fired_q <= attempt_fired_q | start;  // sticky; not cleared by disable_i
    end
end
```
Apply to all six leaf templates. Mirror in the oracle by not calling
`reset()` (or by not resetting `_attempt_fired`) in the `disable` branch.

---

### H-04 · `_collect_signals()` silently discards signal renaming

**File:** `src/sva2rtl/composer.py` — `_collect_signals()`, lines 676–685.

```python
def _collect_signals(children):
    seen: dict[str, None] = {}
    for child in children:
        for port_name, sig_name in child.observed_signals:
            if port_name not in seen:
                seen[port_name] = None              # ← sig_name thrown away
    return tuple((name, name) for name in seen)     # ← always (name, name)
```

The function receives `(port_name, sig_name)` pairs from child checkers but
discards `sig_name`. The returned tuple always has `port_name == sig_name`.

This is data-loss that is invisible today because all Phase 1–3 composers emit
`port_name == sig_name` (1:1 via `extract_signals`). However, `_collect_signals`
is the aggregation point for hierarchical nodes (`seq_concat_top`,
`overlap_bitvec`, `nonoverlap`, `disable_iff_top`). The moment any future
composer introduces port renaming (e.g., for name-collision resolution), the
parent's `observed_signals` will silently map every signal to itself rather than
to the DUT signal name, breaking bind-statement generation without any
diagnostic.

**Fix:**
```python
def _collect_signals(children):
    seen: dict[str, str] = {}
    for child in children:
        for port_name, sig_name in child.observed_signals:
            if port_name not in seen:
                seen[port_name] = sig_name          # preserve sig_name
    return tuple(seen.items())
```

---

## MEDIUM — Code Smell / Maintainability

---

### M-01 · `rep_consecutive` counter never resets after a max-count match

**File:** `templates/rep_consecutive.sv.j2` — always_ff (lines 37–48) and
`behavioral_oracle.py` `_tick_rep_consecutive()` (lines 222–228).

When `count_q == rep_max` and `sig_eval=1`, the counter-increment guard
`count_q < rep_max` is false, so nothing updates. `running_q` stays 1,
`count_q` stays at `rep_max`, and `pass_internal` keeps firing every subsequent
cycle as long as `sig_eval` remains true. The sequence never returns to idle
after matching.

For a token-passing chain (`a[*3] ##1 b`), this means the `rep_consecutive`
module emits a continuous stream of pass tokens, causing the downstream delay
module to receive multiple starts and potentially fire multiple times per
intended sequence. Both RTL and oracle share this behavior, so tests do not
catch it, but a Verilog simulator will expose incorrect waveforms.

Suggested fix: clear `running_q` when the match completes (`count_q == rep_max
&& sig_eval`):
```sv
end else if (running_q && sig_eval) begin
    if (count_q < cnt_width'd{rep_max})
        count_q <= count_q + 1'b1;
    else begin
        running_q <= 1'b0;   // ← clear after match
        count_q   <= '0;
    end
end
```

---

### M-02 · `_import_concurrent_assertion` pattern-match on `SimpleAssertionExpr` is brittle

**File:** `src/sva2rtl/ast_importer.py` — lines 382–383.

```python
case "SimpleAssertionExpr" if expr_node.get("repetition", {}).get("kind") == "Consecutive":
```

A `SimpleAssertionExpr` node without a `repetition` sub-dict (or with a
different `kind`) silently falls through to the default `BoolExpr` branch.
Slang may emit other `repetition.kind` values (e.g., `"Goto"`, `"Nonconsecutive"`)
that would be silently treated as boolean expressions, corrupting the output
without any diagnostic. The `_dispatch_expr_to_ir` function has the same
pattern at line 431.

**Fix:** Add an explicit guard in the default branch for unhandled
`SimpleAssertionExpr` repetition kinds:
```python
case "SimpleAssertionExpr":
    rep_kind = expr_node.get("repetition", {}).get("kind", "")
    if rep_kind and rep_kind != "Consecutive":
        raise UnsupportedConstruct(
            message=f"Repetition kind '{rep_kind}' is not yet supported",
            construct_name=f"repetition_{rep_kind.lower()}",
            source_loc=source_loc,
        )
    # else treat as BoolExpr fallthrough
```

---

### M-03 · `_compose_implication` passes `original_text` (full property) to child sub-labels

**File:** `src/sva2rtl/composer.py` — `_compose_implication()` lines 649–650.

```python
ant_checker = compose(node.antecedent, clock, f"{base}_ant", original_text)
con_checker = compose(node.consequent, clock, f"{base}_con", original_text)
```

Both child `compose()` calls receive the **full** `original_text` of the parent
property (e.g., `"a |-> b ##1 c"`). If the label is `None` and two properties
share the same `original_text` but have structurally different antecedents,
the child module names still collide. More importantly, the `header comment`
in every child module will say the full implication text, not the sub-expression
text. `_compose_disable_iff()` has the same pattern (line 723).

This is a cosmetic accuracy issue today, but becomes a naming-collision risk
once a caller passes `None` for both label and provides the same `original_text`
for structurally distinct children.

---

### M-04 · `_make_delay_node` has stray formatting

**File:** `src/sva2rtl/composer.py` — line 579.

```python
def _make_delay_node(    delay_min: int,
```

The opening `(` and first parameter are on the same line with extra leading
spaces, inconsistent with every other function in the file. Causes a minor
`ruff` format warning.

---

### M-05 · `overlap_bitvec.sv.j2` comment contradicts code for BV bit ordering

**File:** `templates/overlap_bitvec.sv.j2` — line 68 (similar in `nonoverlap.sv.j2`).

```sv
// bit[0] = thread started this cycle; shift right = all threads age.
bv_q <= {ant_pass_w, bv_q[BV_WIDTH-1:1]};
```

The comment claims `bit[0]` is the newest thread, but the concatenation
`{ant_pass_w, bv_q[BV_WIDTH-1:1]}` places the new thread at bit `[BV_WIDTH-1]`
(MSB). The oldest thread is at bit `[0]` (LSB). The comment is backwards.
`con_start_w = bv_q[BV_WIDTH-1]` correctly reads the newest thread (for
overlapping semantics), but the comment makes the logic hard to audit.

**Fix (doc only):**
```sv
// bit[BV_WIDTH-1] = thread started this cycle (MSB = newest);
// bits shift right each cycle — bit[0] = oldest thread maturing now.
```

---

## LOW — Style

---

### L-01 · `_UNSUPPORTED_BINARY_OPS` is defined but always empty

**File:** `src/sva2rtl/ast_importer.py` — line 67.

```python
_UNSUPPORTED_BINARY_OPS: dict[str, str] = {}
```

The dict is never populated and the check at line 192–197 is dead code. Either
remove both the dict and the check, or document why it is kept as a future
extension point with a `# noqa: F841` / comment.

---

### L-02 · `UNSUPPORTED_KINDS_PHASE1` is also always empty

**File:** `src/sva2rtl/ast_importer.py` — line 64.

```python
UNSUPPORTED_KINDS_PHASE1: dict[str, str] = {}
```

`_check_unsupported()` iterates this dict but it is always empty, making the
function a no-op. Document the intent or remove both. The public export name
(`UNSUPPORTED_KINDS_PHASE1` vs `_UNSUPPORTED_BINARY_OPS` which is private)
suggests this was meant for external use — if so, add a comment.

---

### L-03 · `_reconstruct_impl_text` falls through to `"<ant>"` / `"<con>"` for many node types

**File:** `src/sva2rtl/ast_importer.py` — lines 637–648.

```python
if isinstance(node.antecedent, BoolExpr):
    ant_text = node.antecedent.text
elif isinstance(node.antecedent, SeqConcat):
    ant_text = _reconstruct_seq_text(node.antecedent)
else:
    ant_text = "<ant>"     # ← catches SignalFunc, SeqRepetition, PropImplication, DisableIff
```

Phase 3 adds `SignalFunc`, `SeqRepetition`, and `DisableIff` as valid
antecedent/consequent types, but this function does not handle them. The
fallback `"<ant>"` would appear verbatim in the generated module comment. Use
the already-defined `_reconstruct_node_text()` helper (lines 652–668) instead:

```python
ant_text = _reconstruct_node_text(node.antecedent)
con_text = _reconstruct_node_text(node.consequent)
```

---

## Summary Table

| ID   | Severity | File(s)                                  | Description                                              |
|------|----------|------------------------------------------|----------------------------------------------------------|
| H-01 | HIGH     | `ast_importer.py:73,110`                 | `_DECLARATIONS` global not reset between calls → test pollution / stale expansion |
| H-02 | HIGH     | `rep_consecutive.sv.j2`, `behavioral_oracle.py` | `start=1, sig=0, running=0` → no pass, no fail, silent drop |
| H-03 | HIGH     | All 6 leaf templates, `behavioral_oracle.py` | `attempt_fired_q` cleared by `disable_i` — violates port contract |
| H-04 | HIGH     | `composer.py:676`                        | `_collect_signals()` discards `sig_name`; always emits `(name, name)` |
| M-01 | MEDIUM   | `rep_consecutive.sv.j2`, `behavioral_oracle.py` | Counter never resets after match → continuous spurious pass tokens |
| M-02 | MEDIUM   | `ast_importer.py:382,431`               | Unhandled `SimpleAssertionExpr` repetition kinds fall through silently |
| M-03 | MEDIUM   | `composer.py:649,723`                   | Child nodes receive parent's `original_text` → wrong header comments |
| M-04 | MEDIUM   | `composer.py:579`                        | Stray formatting in `_make_delay_node` signature         |
| M-05 | MEDIUM   | `overlap_bitvec.sv.j2`, `nonoverlap.sv.j2` | BV bit-ordering comment is backwards (says bit[0]=newest, code puts new at MSB) |
| L-01 | LOW      | `ast_importer.py:67`                    | `_UNSUPPORTED_BINARY_OPS` always empty, dead code block  |
| L-02 | LOW      | `ast_importer.py:64`                    | `UNSUPPORTED_KINDS_PHASE1` always empty, `_check_unsupported` is no-op |
| L-03 | LOW      | `ast_importer.py:637`                   | `_reconstruct_impl_text` uses `"<ant>"`/`"<con>"` fallback for Phase 3 node types |

---

## Fix Priority

1. **H-01** first — one-line fix, prevents silent test pollution immediately.
2. **H-03** — applies to 6 templates + oracle; critical for correct `attempt_fired` semantics under `disable iff`.
3. **H-02** + **M-01** — fix together; both are in `rep_consecutive.sv.j2` and `behavioral_oracle.py`, and the correct fix for H-02 (immediate fail on `start && !sig`) also informs the counter-reset logic for M-01.
4. **H-04** — one-line fix in `_collect_signals()`.
