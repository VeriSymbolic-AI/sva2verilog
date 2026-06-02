# Phase 1 Research: Foundation — IR + Slang Frontend + Boolean Assert → SV Monitor

**Phase:** 1 of 6
**Requirements covered:** PARSE-01, PARSE-02, PARSE-04, PARSE-05, OUT-01, OUT-02, OUT-03, OUT-07, OUT-08, CLI-05, CLI-06, TEST-01
**Researched:** 2026-05-25
**Confidence:** HIGH (all findings verified empirically with slang v11.0 + iverilog)

---

## Executive Summary

Phase 1 delivers the thinnest possible end-to-end slice: a single boolean SVA assertion (`@(posedge clk) a && b`) goes in; a synthesizable, iverilog-clean SystemVerilog monitor module comes out. Every architectural decision made here — IR shape, module interface, token-passing contract, error exit codes — propagates through all six phases. Getting these right in Phase 1 is far cheaper than retrofitting them later.

The key findings: slang's `--ast-json` JSON schema is well-structured and consistent; the frozen-dataclass IR design maps cleanly onto it; the boolean monitor template is simple (1 FF pipeline, combinational `bool_result`, registered outputs); and the `attempt_fired` output is non-negotiable from day one. All findings below are verified empirically.

---

## Research Question 1: Slang `--ast-json` JSON Schema for Boolean SVA Assertions

### How to Invoke

```bash
slang --ast-json output.json --ast-json-source-info input.sv
```

**Critical finding:** `--ast-json -` (stdout) prepends non-JSON build status messages ("Top level design units: ...\nBuild succeeded: ...") to the JSON stream, breaking `json.loads()`. **Always write to a named file** and read the file afterward.

`--ast-json-source-info` adds source location fields to every node:
- `source_file_start` / `source_file_end` — absolute path strings
- `source_line_start` / `source_line_end` — 1-based integers
- `source_column_start` / `source_column_end` — 1-based integers

### Top-Level JSON Structure

```json
{
  "design": {
    "members": [
      {
        "kind": "Instance",
        "name": "test_bool",
        "body": {
          "kind": "InstanceBody",
          "members": [
            { ... }   // port declarations, statements
          ]
        }
      }
    ]
  }
}
```

### Inline Unlabeled Boolean Assertion

Input:
```systemverilog
module test_bool(input logic clk, rst_n, a, b);
  assert property (@(posedge clk) a && b)
    else $error("a && b violated");
endmodule
```

JSON path: `design.members[0].body.members[-1]`

```json
{
  "kind": "ConcurrentAssertion",
  "assertionKind": "assert",
  "body": {
    "kind": "PropertySpec",
    "clocking": {
      "kind": "TimingControl",
      "event": {
        "kind": "SignalEvent",
        "edge": "posedge",
        "expr": {
          "kind": "NamedValue",
          "symbol": "6338700060480 clk"
        }
      }
    },
    "expr": {
      "kind": "BinaryPropertyExpr",
      "op": "And",
      "left": {
        "kind": "SequenceExpr",
        "expr": {
          "kind": "NamedValue",
          "symbol": "6338700060480 a"
        }
      },
      "right": {
        "kind": "SequenceExpr",
        "expr": {
          "kind": "NamedValue",
          "symbol": "6338700060480 b"
        }
      }
    }
  }
}
```

**Important:** Boolean operators at property level appear as `BinaryPropertyExpr` with `op: "And"/"Or"`. Single signals are wrapped in `SequenceExpr`.

### Labeled Named Assertion with Named Property

Input:
```systemverilog
module test_named(input logic clk, rst_n, a, b, c);
  property p_bool_check;
    @(posedge clk) a && b;
  endproperty
  my_assert: assert property (p_bool_check);
endmodule
```

Labeled assertion: `ConcurrentAssertion` is wrapped in a `Block` statement; block has `"block": "ADDRESS my_assert"` field. The label is extracted from `block.split(" ", 1)[-1]`.

Named property reference: `expr.kind == "PropertyReference"` with `"symbol": "ADDRESS p_bool_check"`. The property body is under `design.members[0].body.members[N]` where `kind == "Property"`.

### `SequenceExpr` Wrapper Pattern

For simple signal references at property level, slang wraps them in a `SequenceExpr`:
```json
{
  "kind": "SequenceExpr",
  "expr": { "kind": "NamedValue", "symbol": "ADDRESS signalname" }
}
```

The boolean property forms you'll encounter in Phase 1:
```json
{ "kind": "BinaryPropertyExpr", "op": "And", "left": ..., "right": ... }
{ "kind": "BinaryPropertyExpr", "op": "Or",  "left": ..., "right": ... }
{ "kind": "UnaryPropertyExpr",  "op": "Not", "expr": ... }
{ "kind": "SequenceExpr",       "expr": { "kind": "NamedValue", ... } }
```

### Boolean Expression Node Kinds (within `expr` fields)

These appear inside `SequenceExpr.expr` or directly as `NamedValue`, etc.:

| `kind` | Description | Fields |
|--------|-------------|--------|
| `NamedValue` | Signal or variable reference | `symbol: "ADDRESS name"` |
| `BinaryOp` | Bitwise/logical operators | `op, left, right` |
| `UnaryOp` | Bitwise/logical not, reduction | `op, operand` |
| `IntegerLiteral` | Numeric constant | `value` |
| `Conversion` | Type cast | `operand` |

**Op strings for `BinaryOp`:** `"BinaryAnd"`, `"BinaryOr"`, `"BinaryXor"`, `"LogicalAnd"`, `"LogicalOr"`, `"Equality"`, `"Inequality"`, `"LessThan"`, `"LessThanEqual"`, `"GreaterThan"`, `"GreaterThanEqual"`

**Op strings for `UnaryOp`:** `"LogicalNot"`, `"BitwiseNot"`, `"UnaryPlus"`, `"UnaryMinus"`

### Symbol Field Extraction

All `symbol` fields have format `"ADDRESS name"` (e.g., `"6338700060480 clk"`). Extract the name with:
```python
name = node["symbol"].split(" ", 1)[-1]
```

### Unsupported Constructs in Phase 1 (Detect and Reject)

| JSON pattern | Meaning | Error |
|---|---|---|
| `propertySpec.expr.kind == "SequenceConcat"` | `##N` operator | SVA-E002 |
| `propertySpec.expr.kind == "Binary"` + `op: "OverlappedImplication"` | `\|->` | SVA-E002 |
| `propertySpec.expr.kind == "Binary"` + `op: "NonOverlappedImplication"` | `\|=>` | SVA-E002 |
| `propertySpec.expr.kind == "SequenceRepetition"` | `[*N]` | SVA-E002 |

The `SequenceConcat` structure for `a ##1 b`:
```json
{
  "kind": "SequenceConcat",
  "elements": [
    { "sequence": { ... }, "min": "1", "max": "1" }
  ]
}
```

Implication (`a |-> b`) uses:
```json
{
  "kind": "Binary",
  "op": "OverlappedImplication",
  "left": { ... },
  "right": { ... }
}
```

---

## Research Question 2: Frozen Dataclass IR Design

### Design Principles

1. **Frozen** (`frozen=True`) — enables `__hash__` for structural CSE deduplication
2. **SourceLoc first-class** — every node carries source location; pitfall P5.1 cannot be retrofitted
3. **Leaf node for Phase 1** — `BoolExpr` is the only property node needed; tree structure is trivial
4. **`attempt_fired` first-class on `CheckerNode`** — not optional, not added later

### `ir.py` — Core IR Definitions

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SourceLoc:
    """Source location from slang AST, threaded through entire pipeline (prevents P5.1)."""
    file: str
    line: int
    col: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.col}"


# ── SVA IR Node hierarchy ──────────────────────────────────────────────────

@dataclass(frozen=True)
class SVANode:
    """Base class for all SVA IR nodes."""
    source_loc: SourceLoc


@dataclass(frozen=True)
class BoolExpr(SVANode):
    """
    Leaf node: a purely boolean SVA property (no temporal operators).
    `text` is the verbatim reconstructed SV expression for embedding in RTL.

    Example: BoolExpr(text="(a && b)", source_loc=SourceLoc("foo.sv", 3, 5))
    """
    text: str   # reconstructed SV boolean expression, ready for RTL embedding


@dataclass(frozen=True)
class PropImplication(SVANode):
    """
    Overlapping implication: antecedent |-> consequent.
    Phase 2+ only; raises UnsupportedConstruct in Phase 1.
    """
    antecedent: SVANode
    consequent: SVANode
    overlapping: bool = True   # False = |=>


@dataclass(frozen=True)
class SeqConcat(SVANode):
    """
    Sequence concatenation: s1 ##N s2.
    Phase 2+ only; raises UnsupportedConstruct in Phase 1.
    """
    elements: tuple[SVANode, ...]
    delays: tuple[tuple[int, int], ...]   # (min, max) delay between elements


# ── CheckerNode: IR-to-RTL bridge ─────────────────────────────────────────

@dataclass(frozen=True)
class CheckerNode:
    """
    Represents one instantiated template in the RTL hierarchy.
    Carries enough information for the emitter to generate the module + instantiation.

    Port contract (standard interface — every checker module exposes all of these):
        clk          : input  clock
        rst_n        : input  active-low synchronous reset
        start        : input  pulse to begin monitoring (top-level: tied 1'b1)
        active       : output sequence is currently being evaluated
        pass         : output check passed this cycle
        fail         : output check failed this cycle
        attempt_fired: output sticky — goes high when at least one attempt has started

    `observed_signals`: list of (port_name, dut_signal_name) pairs for bind generation
    """
    template_name: str        # e.g. "bool_expr"
    module_name: str          # e.g. "sva_my_check" (derived from property label)
    params: dict[str, str]    # Jinja2 template parameter dict
    observed_signals: tuple[tuple[str, str], ...]   # (port_name, signal_name)
    source_loc: SourceLoc
    children: tuple[CheckerNode, ...] = ()


# ── Clocking ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ClockSpec:
    """Extracted clock event from @(posedge clk) or @(negedge clk)."""
    edge: str          # "posedge" or "negedge"
    signal: str        # clock signal name, e.g. "clk"
    source_loc: SourceLoc
```

### Design Rationale

- **`BoolExpr.text` is verbatim SV** — the composer reconstructs the expression string by recursive descent over the JSON AST; the emitter embeds it directly in the Jinja2 template. This avoids encoding a full expression AST for Phase 1 and keeps the template simple.
- **`CheckerNode.params: dict[str, str]`** — all template parameters are strings (SV expressions); the template renders them verbatim. No type coercion needed.
- **`observed_signals: tuple[tuple[str, str], ...]`** — immutable tuples for hashability. The `bind` generator uses this in Phase 3.
- **`ClockSpec` separate from `SVANode`** — the clock is extracted once and threaded into every template; it is not part of the property tree.

---

## Research Question 3: Jinja2 Template for Boolean Assertion Monitor

### Template: `templates/bool_expr.sv.j2`

```jinja2
// Generated by sva2rtl {{ sva2rtl_version }}
// Source: {{ source_loc }}
// Original property: {{ clock_edge }} {{ clock_signal }}) {{ bool_expr }}
module {{ module_name }} (
    input  logic {{ clock_signal }},
    input  logic rst_n,
    input  logic start,
{% for port_name, _ in observed_signals %}
    input  logic {{ port_name }},
{% endfor %}
    output logic active,
    output logic pass,
    output logic fail,
    output logic attempt_fired
);
    // ── Combinational evaluation ───────────────────────────────────────
    logic bool_result;
    assign bool_result = ({{ bool_expr }});

    // ── Registered outputs (OUT-02: no combinational glitches) ─────────
    logic active_q, pass_q, fail_q, attempt_fired_q;
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        if (!rst_n) begin
            active_q        <= 1'b0;
            pass_q          <= 1'b0;
            fail_q          <= 1'b0;
            attempt_fired_q <= 1'b0;
        end else begin
            active_q        <= start;
            pass_q          <= start &  bool_result;
            fail_q          <= start & ~bool_result;
            attempt_fired_q <= attempt_fired_q | start;  // sticky
        end
    end

    assign active        = active_q;
    assign pass          = pass_q;
    assign fail          = fail_q;
    assign attempt_fired = attempt_fired_q;

endmodule
```

### Template Variables

| Variable | Type | Example |
|---|---|---|
| `sva2rtl_version` | `str` | `"0.1.0"` |
| `source_loc` | `str` | `"foo.sv:3:5"` |
| `module_name` | `str` | `"sva_my_check"` |
| `clock_signal` | `str` | `"clk"` |
| `clock_edge` | `str` | `"posedge"` |
| `bool_expr` | `str` | `"(a && b)"` |
| `observed_signals` | `list[tuple[str,str]]` | `[("a","dut.a"),("b","dut.b")]` |

### Design Notes

1. **`bool_result` is combinational** — the expression is evaluated in the same cycle as `start`. No timing issue for boolean-only properties.
2. **All outputs registered** — satisfies OUT-02 (no glitches on pass/fail).
3. **Synchronous reset to 0** — satisfies OUT-03 (every FF has synchronous reset to idle).
4. **`attempt_fired_q` is sticky** — once high, never goes low (except on reset). This is intentional: it indicates the monitor ever checked something meaningful.
5. **`start` is the token input** — at top level the composer ties `start = 1'b1`; for sub-sequences in Phase 2+ `start` comes from the parent module's `pass` output.
6. **`pass = start & bool_result`** — only asserts pass when both triggered AND condition holds.
7. **`fail = start & ~bool_result`** — only asserts fail when triggered AND condition fails. A monitor with `start=0` never fires fail.

### Verified: This template compiles and simulates correctly under iverilog -g2012.

Simulation results (verified):
- reset cycle: all outputs 0 ✓
- a=1, b=1 → `pass=1, fail=0, attempt_fired=1` ✓
- a=1, b=0 → `pass=0, fail=1, attempt_fired=1` ✓
- a=0, b=0 → `pass=0, fail=1, attempt_fired=1` ✓

---

## Research Question 4: Standard RTL Monitor Interface

### Port Contract

Every generated checker module exposes this interface (non-negotiable — established in Phase 1, used unchanged through Phase 6):

```systemverilog
module sva_<property_label> (
    // ── Standard token-passing interface ──
    input  logic clk,          // clock (edge from @(posedge/negedge clk))
    input  logic rst_n,        // active-low synchronous reset
    input  logic start,        // begin evaluation this cycle
    // ── Observed DUT signals ──
    input  logic <sig1>,       // one port per signal used in property
    input  logic <sig2>,
    // ... (multi-bit signals: input logic [W-1:0] <sigN>)
    // ── Monitor outputs ──
    output logic active,       // evaluation in progress
    output logic pass,         // check passed this cycle (registered)
    output logic fail,         // check failed this cycle (registered)
    output logic attempt_fired // sticky: at least one attempt ever started
);
```

### Port Semantics

| Port | Direction | Semantics |
|---|---|---|
| `clk` | input | Clock; edge from `@(posedge clk)` annotation |
| `rst_n` | input | Active-low; synchronous reset (all FFs → 0 on `!rst_n`) |
| `start` | input | Token input: pulse HIGH to begin evaluating this cycle |
| `active` | output | HIGH while an evaluation is in progress (registered) |
| `pass` | output | HIGH for exactly 1 cycle when check succeeds (registered) |
| `fail` | output | HIGH for exactly 1 cycle when check fails (registered) |
| `attempt_fired` | output | Sticky: set HIGH on first `start` pulse; never cleared except reset |

### Why `attempt_fired` Is Non-Negotiable (P1.1 prevention)

A monitor where `start` is never pulsed will have `pass=0, fail=0` forever — which looks like "no failures" but actually means "nothing was checked." Without `attempt_fired`, vacuous satisfaction is indistinguishable from correct behavior.

The meaningful pass condition is: `(fail == 0) AND (attempt_fired == 1)`.

This port must be present from Phase 1. It cannot be added in Phase 3 without changing the module interface (breaking all existing tests and bind wrappers).

### Module Naming Convention (OUT-07)

```
sva_<property_label>
```

- Label from SVA: `my_check: assert property (...)` → `sva_my_check`
- No label: `sva_prop_<hash>` (deterministic 8-char hash of property text)
- Property name: `property p_req_ack; ... endproperty` → `sva_p_req_ack`

Python derivation:
```python
import re
import hashlib

def module_name_from_label(label: str | None, property_text: str) -> str:
    if label:
        # sanitize: replace non-alphanumeric with underscore
        safe = re.sub(r'[^a-zA-Z0-9_]', '_', label)
        return f"sva_{safe}"
    h = hashlib.sha256(property_text.encode()).hexdigest()[:8]
    return f"sva_prop_{h}"
```

### Original SVA Text Comment (OUT-08)

The module header comment must include the original property text. Extract before AST import (read the source file, extract lines corresponding to the assertion's source location from `--ast-json-source-info`).

---

## Research Question 5: Token-Passing Architecture for the Boolean Case

### What Token-Passing Means for Boolean

For the boolean leaf case, the "token" is simply `start`. The token-passing contract is:

```
parent.pass  →  child.start     (consequent starts when antecedent passes)
child.pass   →  grandchild.start
```

For a top-level assertion, there is no parent — so the top-level monitor's `start` is tied HIGH by the `bind` wrapper or testbench. The top-level always evaluates.

For Phase 1, this means:
1. Composer sees a `BoolExpr` node
2. Creates a `CheckerNode` for the `bool_expr` template
3. Sets `start` connection to `1'b1` in the top-level wrapper

### Top-Level Wrapper (Structural Verilog)

```systemverilog
// bind wrapper or top-level instantiation
sva_my_check u_sva_my_check (
    .clk           (clk),
    .rst_n         (rst_n),
    .start         (1'b1),      // top-level: always active
    .a             (a),
    .b             (b),
    .active        (),          // can leave unconnected
    .pass          (),
    .fail          (assertion_fail),   // connect to error tracking
    .attempt_fired (attempt_fired_mon)
);
```

### Why `start=1'b1` for Top-Level Boolean

A boolean property `@(posedge clk) a && b` evaluates every clock cycle. There is no antecedent that needs to "fire" to trigger it. The property either holds or violates on every cycle.

This is the degenerate case of token-passing: the token source is a permanent HIGH, producing a token every cycle. The monitor tracks the running total of `pass` and `fail` pulses.

### Token-Passing Wiring Table for Phase 1

| Level | `start` source | Notes |
|---|---|---|
| Top-level `bool_expr` | `1'b1` | Always evaluating |
| Sub-expression (Phase 2+) | parent's `pass` output | Token flows on match |
| `|->` antecedent (Phase 2+) | `1'b1` | Antecedent always listening |
| `|->` consequent (Phase 2+) | antecedent's `pass` output | Starts when antecedent matches |

---

## Research Question 6: Phase 1 Pitfalls and Prevention

### P1.1 — Vacuous Satisfaction (CRITICAL)

**Risk:** Monitor reports `pass` having never checked anything (zero `start` pulses).

**Phase 1 prevention:**
- `attempt_fired` is a required output port on every checker template
- Unit tests MUST assert `attempt_fired == 1` after any test that expects `pass == 1`
- `attempt_fired_q` implementation: sticky register, only cleared by `!rst_n`

**Test pattern:**
```python
def test_vacuous_detection():
    # After reset, without any start pulses:
    # attempt_fired must be 0; pass must be 0
    # This is NOT a "pass" — it's vacuous
    assert attempt_fired == 0
    assert pass_out == 0
```

### P5.1 — Source Location Not Threaded (CRITICAL)

**Risk:** After IR build, source information is lost; errors point to generated RTL line numbers.

**Phase 1 prevention:**
- `SourceLoc(file, line, col)` is a field on EVERY IR dataclass (not optional)
- `ASTImporter` must extract `source_line_start`, `source_column_start`, `source_file_start` from every JSON node it visits
- `CheckerNode` also carries `source_loc` — threads through to emitter
- All `SvaError` and `UnsupportedConstruct` exceptions include a `SourceLoc`

**SourceLoc extraction from slang JSON:**
```python
def extract_source_loc(node: dict) -> SourceLoc:
    return SourceLoc(
        file=node.get("source_file_start", "<unknown>"),
        line=node.get("source_line_start", 0),
        col=node.get("source_column_start", 0),
    )
```

(Requires `--ast-json-source-info` flag when invoking slang.)

### P8.1 — Unknown Slang Node Kinds (HIGH)

**Risk:** Slang outputs a `kind` string the importer doesn't know; it silently skips the node or crashes with a KeyError, producing wrong output.

**Phase 1 prevention:**
- `ASTImporter` must raise `UnsupportedConstruct` for any unrecognized `kind`, never silently skip
- Implement a `_dispatch(node)` method with exhaustive `match node["kind"]:` and a `case _: raise UnsupportedConstruct(...)` default
- Write a `--dump-ast` mode that prints the raw JSON (debugging aid for operators not yet implemented)

### P8.4 — Wrong Clock (HIGH)

**Risk:** Multiple clocks in file; importer picks wrong one; monitor latches on wrong edge.

**Phase 1 prevention:**
- Extract clock from `PropertySpec.clocking` field (not from module ports)
- Require explicit `@(posedge ...)` in the property; reject assertions without clocking event
- Error: `"Property has no clock annotation; use @(posedge clk) or --default-clock flag"`

### P2.4 — Missing Reset (HIGH)

**Risk:** FFs have no reset; simulator starts in X; first cycle behavior is undefined.

**Phase 1 prevention:**
- Template rule: every `always_ff` block MUST have a `if (!rst_n) begin ... end` reset clause
- Reset values: always `0` (idle state)
- Unit test: drive `rst_n=0` for first 2 cycles, verify all outputs are 0

### P8.2 — Incorrect `expr_to_sv` Reconstruction (MEDIUM for Phase 1)

**Risk:** Boolean expression text is reconstructed incorrectly; monitor checks wrong condition.

**Phase 1 prevention:**
- Validate `expr_to_sv()` output against the original source text
- Test every operator combination: `&&`, `||`, `!`, `^`, comparisons
- Add parentheses around every binary expression to preserve precedence

**Correct `expr_to_sv` implementation:**
```python
_BINARY_OPS = {
    "BinaryAnd":        "&",
    "BinaryOr":         "|",
    "BinaryXor":        "^",
    "LogicalAnd":       "&&",
    "LogicalOr":        "||",
    "Equality":         "==",
    "Inequality":       "!=",
    "LessThan":         "<",
    "LessThanEqual":    "<=",
    "GreaterThan":      ">",
    "GreaterThanEqual": ">=",
}
_UNARY_OPS = {
    "LogicalNot":  "!",
    "BitwiseNot":  "~",
    "UnaryMinus":  "-",
    "UnaryPlus":   "+",
}

def expr_to_sv(node: dict) -> str:
    match node["kind"]:
        case "NamedValue":
            return node["symbol"].split(" ", 1)[-1]
        case "BinaryOp":
            op = _BINARY_OPS[node["op"]]
            left = expr_to_sv(node["left"])
            right = expr_to_sv(node["right"])
            return f"({left} {op} {right})"
        case "UnaryOp":
            op = _UNARY_OPS[node["op"]]
            operand = expr_to_sv(node["operand"])
            return f"({op}{operand})"
        case "IntegerLiteral":
            return node["value"]
        case "SequenceExpr":
            return expr_to_sv(node["expr"])
        case "BinaryPropertyExpr":
            # Boolean ops at property level
            op_map = {"And": "&&", "Or": "||"}
            op = op_map[node["op"]]
            left = expr_to_sv(node["left"])
            right = expr_to_sv(node["right"])
            return f"({left} {op} {right})"
        case "UnaryPropertyExpr" if node["op"] == "Not":
            return f"(!{expr_to_sv(node['expr'])})"
        case _:
            raise UnsupportedConstruct(
                f"Unsupported expression kind: {node['kind']}",
                source_loc=extract_source_loc(node),
            )
```

---

## Research Question 7: Error Handling Strategy

### Exit Codes (CLI-05)

| Code | Meaning | Trigger |
|---|---|---|
| 0 | Success | Output file written cleanly |
| 1 | Compile error | Invalid SV syntax; slang parse error; internal IR error |
| 2 | Unsupported construct | SVA operator not yet implemented (e.g., `##N` in Phase 1) |
| 3 | Slang not found | `slang` binary absent from PATH and `--slang-path` not set |

### Detecting Slang Absence (CLI-06)

```python
import subprocess
from pathlib import Path

def invoke_slang(sv_file: Path, out_json: Path, slang_path: str = "slang") -> None:
    try:
        result = subprocess.run(
            [slang_path, "--ast-json", str(out_json),
             "--ast-json-source-info", str(sv_file)],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        raise SlangNotFound(
            f"slang not found at '{slang_path}'.\n"
            f"Install: https://github.com/MikePopoloski/slang/releases\n"
            f"Or pass: --slang-path /path/to/slang"
        )
    if result.returncode != 0:
        raise SvaCompileError(
            f"slang failed:\n{result.stderr}",
            source_loc=None,
        )
```

`SlangNotFound` → exit code 3. `SvaCompileError` → exit code 1.

### Error Class Hierarchy (`errors.py`)

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class SvaError(Exception):
    """Base class for all sva2rtl errors."""
    message: str
    source_loc: Optional["SourceLoc"] = None  # forward ref

    def __str__(self) -> str:
        if self.source_loc:
            return f"{self.source_loc}: error: {self.message}"
        return f"error: {self.message}"


@dataclass
class SlangNotFound(SvaError):
    """slang binary not found (exit code 3)."""
    pass


@dataclass
class SvaCompileError(SvaError):
    """SV parse error from slang (exit code 1)."""
    pass


@dataclass
class UnsupportedConstruct(SvaError):
    """SVA construct not yet implemented (exit code 2)."""
    construct_name: str = ""

    def __str__(self) -> str:
        loc = f"{self.source_loc}: " if self.source_loc else ""
        suggestion = f" (supported in Phase 2+)" if self.construct_name else ""
        return f"{loc}error SVA-E002: unsupported construct '{self.construct_name}'{suggestion}: {self.message}"


@dataclass
class InternalError(SvaError):
    """Internal compiler bug (exit code 1)."""
    pass
```

### CLI Error Handler Pattern

```python
import click
import sys

@click.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", default=None)
@click.option("--slang-path", default="slang", envvar="SLANG_PATH")
def main(input_file: str, output: str | None, slang_path: str) -> None:
    try:
        run_pipeline(input_file, output, slang_path)
    except SlangNotFound as e:
        click.echo(str(e), err=True)
        sys.exit(3)
    except UnsupportedConstruct as e:
        click.echo(str(e), err=True)
        sys.exit(2)
    except SvaError as e:
        click.echo(str(e), err=True)
        sys.exit(1)
```

### Unsupported Construct Detection (CLI-06)

```python
UNSUPPORTED_KINDS_PHASE1 = {
    "SequenceConcat":            "##N sequence concatenation (Phase 2)",
    "SequenceRepetition":        "[*N] consecutive repetition (Phase 2)",
    "Binary|OverlappedImplication":   "|-> overlapping implication (Phase 2)",
    "Binary|NonOverlappedImplication": "|=> non-overlapping implication (Phase 2)",
    "SystemCall|$rose":          "$rose() (Phase 3)",
    "SystemCall|$fell":          "$fell() (Phase 3)",
    "SystemCall|$stable":        "$stable() (Phase 3)",
    "SystemCall|$past":          "$past() (Phase 3)",
}

def check_unsupported(node: dict, source_loc: SourceLoc) -> None:
    kind = node.get("kind", "")
    op = node.get("op", "")
    key = f"{kind}|{op}" if op else kind
    if key in UNSUPPORTED_KINDS_PHASE1:
        raise UnsupportedConstruct(
            message=f"Use a future version of sva2rtl for this feature",
            construct_name=UNSUPPORTED_KINDS_PHASE1[key],
            source_loc=source_loc,
        )
```

---

## Research Question 8: Python Package Setup with uv

### Project Initialization

```bash
# Create project with src/ layout (recommended for installable packages)
uv init --lib --name sva2rtl
cd sva2rtl

# Set Python version
echo "3.12" > .python-version

# Add runtime dependencies
uv add click "jinja2>=3.1.6"

# Add dev dependencies
uv add --dev pytest hypothesis mypy ruff
```

### `pyproject.toml` (Complete)

```toml
[project]
name = "sva2rtl"
version = "0.1.0"
description = "SVA to synthesizable RTL monitor compiler"
requires-python = ">=3.12"
dependencies = [
    "click>=8.0",
    "jinja2>=3.1.6",
]

[project.scripts]
sva2rtl = "sva2rtl.cli:main"

[build-system]
requires = ["uv_build>=0.1"]
build-backend = "uv_build"

[dependency-groups]
dev = [
    "hypothesis>=6.100",
    "mypy>=1.10",
    "pytest>=9.0",
    "ruff>=0.4",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "N", "ANN"]
ignore = ["ANN101", "ANN102"]

[tool.mypy]
strict = true
python_version = "3.12"
```

**Critical:** `[dependency-groups]` NOT `[project.optional-dependencies]`. uv uses `[dependency-groups]` for dev/test deps; `uv add --dev pkg` writes there.

### Source Layout

```
sva2rtl/
├── pyproject.toml
├── .python-version               # "3.12"
├── src/
│   └── sva2rtl/
│       ├── __init__.py           # version = "0.1.0"
│       ├── py.typed              # PEP 561 marker (empty file)
│       ├── ir.py                 # SVA IR dataclasses (BoolExpr, SourceLoc, etc.)
│       ├── errors.py             # SvaError, SlangNotFound, UnsupportedConstruct
│       ├── frontend.py           # invoke_slang() subprocess wrapper
│       ├── ast_importer.py       # JSON AST → SVA IR
│       ├── checker_node.py       # CheckerNode (or keep in ir.py)
│       ├── composer.py           # SVA IR → CheckerNode tree
│       ├── emitter.py            # CheckerNode tree → SV text via Jinja2
│       └── cli.py                # click entry point
├── templates/
│   └── bool_expr.sv.j2           # Jinja2 boolean assertion template
└── tests/
    ├── __init__.py
    ├── test_ir.py
    ├── test_ast_importer.py
    ├── test_expr_to_sv.py
    ├── test_emitter.py
    ├── fixtures/
    │   ├── bool_simple.json      # slang JSON fixture
    │   ├── bool_labeled.json
    │   └── bool_complex.json
    └── golden/
        ├── bool_simple.sv        # expected emitter output
        └── bool_labeled.sv
```

### Template Loading Pattern

```python
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

def make_jinja_env(template_dir: Path | None = None) -> Environment:
    if template_dir is None:
        # Default: templates/ relative to package root
        template_dir = Path(__file__).parent.parent.parent / "templates"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        trim_blocks=True,
        lstrip_blocks=True,
    )

# Custom filter for SV bus width notation
def sv_width(n: int) -> str:
    return f"[{n-1}:0]" if n > 1 else ""

env = make_jinja_env()
env.filters["sv_width"] = sv_width
```

### Running Tests

```bash
uv run pytest tests/ -v
uv run mypy src/sva2rtl --strict
uv run ruff check src/ tests/
```

### `uv run sva2rtl` Entry Point

After `uv sync`, `uv run sva2rtl input.sv` invokes `src/sva2rtl/cli.py:main` correctly. The `[project.scripts]` entry in `pyproject.toml` maps the `sva2rtl` command to `sva2rtl.cli:main`.

---

## Concrete Implementation Build Order for Phase 1

Based on the research, the correct build order for Phase 1 sub-tasks:

### Step 1.1 — `ir.py` + `errors.py`
Pure data definitions; no dependencies. Write and unit test first.

```python
# Minimal smoke test
loc = SourceLoc("test.sv", 1, 5)
expr = BoolExpr(text="(a && b)", source_loc=loc)
assert expr.source_loc.line == 1
assert hash(expr) == hash(BoolExpr(text="(a && b)", source_loc=loc))  # frozen hashable
```

### Step 1.2 — `frontend.py` (slang invocation)
- `invoke_slang(sv_file, out_json, slang_path) -> dict`
- Handles `FileNotFoundError` → `SlangNotFound`
- Reads output JSON file (not stdout)
- Unit test: mock subprocess; fixture JSON files in `tests/fixtures/`

### Step 1.3 — `ast_importer.py`
- `import_property(ast: dict) -> tuple[SVANode, ClockSpec]`
- Dispatches on `kind` strings documented in Research Q1
- Extracts `SourceLoc` from every node
- Reconstructs `bool_expr` text via `expr_to_sv()`
- Raises `UnsupportedConstruct` for Phase 2+ node kinds

### Step 1.4 — `composer.py` + `emitter.py` + `templates/bool_expr.sv.j2`
- `compose(node: SVANode) -> CheckerNode`
- `emit(checker: CheckerNode) -> str` (Jinja2 render)
- Integration test: `invoke_slang → import_property → compose → emit → write_file`

### Step 1.5 — `cli.py`
- Click entry point with `--output`, `--slang-path`, `--dump-ast`
- Exception handler mapping errors to exit codes
- End-to-end test: `subprocess.run(["sva2rtl", "bool.sv"])` and check exit code + output file

---

## Key Findings Summary

| Question | Finding |
|---|---|
| Slang JSON schema | `ConcurrentAssertion → PropertySpec → clocking + expr`; `BinaryPropertyExpr` for boolean ops; symbol format `"ADDRESS name"` |
| IR design | Frozen dataclasses; `BoolExpr(text, source_loc)`; `SourceLoc` on every node; `CheckerNode` with `attempt_fired` first-class |
| Jinja2 template | 1-FF pipeline; combinational `bool_result`; all outputs registered; `attempt_fired_q` sticky; verified under iverilog -g2012 |
| Monitor interface | `(clk, rst_n, start, active, pass, fail, attempt_fired)` + observed signals; non-negotiable from Phase 1 |
| Token-passing for boolean | `start=1'b1` at top level; `pass = start & bool_result`; `fail = start & ~bool_result` |
| Phase 1 pitfalls | P1.1 (vacuous): `attempt_fired` required; P5.1 (source loc): `SourceLoc` on all IR nodes; P8.1 (unknown kinds): exhaustive match + default raise; P2.4 (reset): synchronous reset in every FF block |
| Error handling | `FileNotFoundError` → `SlangNotFound` (exit 3); unknown `kind` → `UnsupportedConstruct` (exit 2); parse error → `SvaCompileError` (exit 1) |
| Package setup | `uv init --lib`; `src/` layout; `[dependency-groups]` for dev deps; `[project.scripts]` for CLI |

---

## Risks Specific to Phase 1

| Risk | Likelihood | Mitigation |
|---|---|---|
| slang JSON schema differs between minor versions | LOW | Pin `slang-v11.0`; document tested version in `CLAUDE.md` |
| `expr_to_sv` produces incorrect SV for edge cases | MEDIUM | Round-trip test: parse SV → extract text → compare with original |
| Jinja2 template whitespace issues in generated SV | LOW | `trim_blocks=True, lstrip_blocks=True`; iverilog compile test |
| `attempt_fired` semantics wrong (resets on each start) | LOW | Use sticky OR, not per-cycle assignment |
| Multi-bit signals break the template | MEDIUM | Phase 1 can restrict to `logic` (1-bit); log TODO for multi-bit |

---

*Research completed: 2026-05-25*
*Status: COMPLETE — ready for planning (02-PLAN.md)*
