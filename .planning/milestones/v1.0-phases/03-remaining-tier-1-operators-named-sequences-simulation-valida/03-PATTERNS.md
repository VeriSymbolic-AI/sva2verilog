# Phase 3 Pattern Mapping

**Generated:** 2026-05-27
**Phase:** 3 - Remaining Tier 1 Operators + Named Sequences + Simulation Validation

---

## Table of Contents

1. [File Inventory](#1-file-inventory)
2. [Pattern Mapping by File](#2-pattern-mapping)
3. [Cross-Cutting Patterns](#3-cross-cutting)
4. [Data Flow Summary](#4-data-flow)

---

## 1. File Inventory {#1-file-inventory}

### Files to MODIFY

| File | Role | Plan |
|------|------|------|
| `src/sva2rtl/ir.py` | IR node definitions | 3.1, 3.2, 3.3 |
| `src/sva2rtl/ast_importer.py` | JSON AST → IR translation | 3.1, 3.2, 3.3 |
| `src/sva2rtl/composer.py` | IR → CheckerNode builder | 3.1, 3.2, 3.3 |
| `src/sva2rtl/emitter.py` | CheckerNode → SV text | 3.3 |
| `src/sva2rtl/behavioral_oracle.py` | Cycle-by-cycle behavioral model | 3.1, 3.2, 3.4 |
| `templates/bool_expr.sv.j2` | Leaf boolean expression template | 3.3 (disable port) |
| `templates/concat_delay.sv.j2` | Counter-based delay template | 3.3 (disable port) |
| `templates/overlap_bitvec.sv.j2` | Overlapping implication template | 3.3 (disable port) |
| `templates/nonoverlap.sv.j2` | Non-overlapping implication template | 3.3 (disable port) |
| `templates/seq_concat_top.sv.j2` | Sequence concatenation wrapper | 3.3 (disable port) |

### Files to CREATE

| File | Role | Plan |
|------|------|------|
| `templates/rep_consecutive.sv.j2` | Counter-based repetition `[*N]/[*M:N]` | 3.1 |
| `templates/rose.sv.j2` | `$rose` edge detect | 3.2 |
| `templates/fell.sv.j2` | `$fell` edge detect | 3.2 |
| `templates/stable.sv.j2` | `$stable` XNOR comparator | 3.2 |
| `templates/past.sv.j2` | `$past` N-stage shift register | 3.2 |
| `templates/disable_iff_top.sv.j2` | Top wrapper with disable gating | 3.3 |
| `templates/bind.sv.j2` | Bind statement file | 3.3 |
| `tests/test_repetition.py` | Unit/integration for `[*N]/[*M:N]` | 3.1 |
| `tests/test_signal_functions.py` | Unit/integration for rose/fell/stable/past | 3.2 |
| `tests/test_disable_iff.py` | Unit/integration for disable iff | 3.3 |
| `tests/test_bind.py` | Unit/integration for bind generation | 3.3 |
| `tests/test_simulation_oracle.py` | Dual-oracle simulation harness | 3.4 |
| `tests/fixtures/rep_fixed.json` | Fixture: `a[*3]` | 3.1 |
| `tests/fixtures/rep_range.json` | Fixture: `a[*2:5]` | 3.1 |
| `tests/fixtures/rose.json` | Fixture: `$rose(sig)` | 3.2 |
| `tests/fixtures/fell.json` | Fixture: `$fell(sig)` | 3.2 |
| `tests/fixtures/stable.json` | Fixture: `$stable(sig)` | 3.2 |
| `tests/fixtures/past.json` | Fixture: `$past(sig, 3)` | 3.2 |
| `tests/fixtures/disable_iff.json` | Fixture: `disable iff (rst) ...` | 3.3 |
| `tests/fixtures/named_seq.json` | Fixture: named sequence ref | 3.3 |

---

## 2. Pattern Mapping by File {#2-pattern-mapping}

---

### 2.1 `src/sva2rtl/ir.py` — Add IR Nodes + CSE field

**Role:** Core IR definitions (frozen dataclasses)
**Closest analog:** Existing `SeqConcat`, `PropImplication`, `BoolExpr` nodes in same file

#### Existing Pattern: SVANode subclass

```python
# FROM: src/sva2rtl/ir.py lines 63-76
@dataclass(frozen=True)
class SeqConcat(SVANode):
    """Sequence concatenation: ``s1 ##N s2`` (Phase 2+).

    ``delays[i]`` is the ``(min, max)`` cycle delay between ``elements[i]`` and
    ``elements[i+1]``.  For a fixed delay ``##N`` both values are ``N``.
    """

    elements: tuple[SVANode, ...]
    delays: tuple[tuple[int, int], ...]  # (min, max) delay between elements
```

#### New Nodes to Add (follow same frozen dataclass pattern):

```python
@dataclass(frozen=True)
class SeqRepetition(SVANode):
    """Consecutive repetition [*N] or [*M:N]."""
    expr: SVANode          # the expression to repeat
    rep_min: int           # minimum repetitions
    rep_max: int           # maximum repetitions

@dataclass(frozen=True)
class SignalFunc(SVANode):
    """Signal function: $rose, $fell, $stable, $past."""
    func_name: str         # "rose" | "fell" | "stable" | "past"
    signal: str            # signal name
    depth: int = 1         # pipeline depth (for $past; ignored for others)

@dataclass(frozen=True)
class DisableIff(SVANode):
    """disable iff (condition) property_expr."""
    condition: str         # disable condition expression text
    body: SVANode          # the property being disabled
```

#### CheckerNode `cse_origin` field addition:

```python
# FROM: src/sva2rtl/ir.py lines 110-148 (CheckerNode)
# ADD: one new optional field for CSE tagging (Phase 5 optimizer)
@dataclass(frozen=True)
class CheckerNode:
    # ... existing fields ...
    template_name: str
    module_name: str
    params: dict[str, str]
    observed_signals: tuple[tuple[str, str], ...]
    source_loc: SourceLoc
    children: tuple[CheckerNode, ...] = ()
    cse_origin: str | None = None  # NEW: None=unique, non-None=named source decl

    # __hash__ and __eq__ must also include cse_origin
```

**Key constraint:** `frozen=True` on all nodes, `source_loc: SourceLoc` mandatory, hashable for CSE.

---

### 2.2 `src/sva2rtl/ast_importer.py` — Dispatch for New Constructs

**Role:** JSON AST walk → IR node production
**Closest analog:** `_build_seq_concat()`, `_build_prop_implication()`, `_dispatch_expr_to_ir()`

#### Pattern A: UNSUPPORTED_KINDS removal

```python
# FROM: src/sva2rtl/ast_importer.py lines 49-51
UNSUPPORTED_KINDS_PHASE1: dict[str, str] = {
    "SequenceRepetition": "[*N] consecutive repetition (Phase 2)",
}
# CHANGE TO: Remove "SequenceRepetition" entry (now supported)
UNSUPPORTED_KINDS_PHASE1: dict[str, str] = {}
```

#### Pattern B: Top-level dispatch in `_import_concurrent_assertion`

```python
# FROM: src/sva2rtl/ast_importer.py lines 288-305
match expr_node.get("kind"):
    case "SequenceConcat":
        seq_ir = _build_seq_concat(expr_node, source_loc)
        ir_node: SVANode = seq_ir
        text = _reconstruct_seq_text(seq_ir)
    case "BinaryPropertyExpr" if expr_node.get("op") in (
        "OverlappedImplication",
        "NonOverlappedImplication",
    ):
        prop_ir = _build_prop_implication(expr_node, source_loc)
        ir_node = prop_ir
        text = _reconstruct_impl_text(prop_ir)
    case _:
        _check_unsupported(expr_node, extract_source_loc(expr_node))
        text = expr_to_sv(expr_node)
        ir_node = BoolExpr(text=text, source_loc=source_loc)
```

**New dispatch cases to add (same match/case style):**

```python
    case "SimpleAssertionExpr" if expr_node.get("repetition"):
        # Consecutive repetition [*N]/[*M:N]
        rep_ir = _build_seq_repetition(expr_node, source_loc)
        ir_node = rep_ir
        text = _reconstruct_rep_text(rep_ir)
    case "DisableIff":
        # disable iff (condition) body
        dis_ir = _build_disable_iff(expr_node, source_loc)
        ir_node = dis_ir
        text = _reconstruct_disable_text(dis_ir)
```

#### Pattern C: expr_to_sv dispatch for CallExpression (system functions)

```python
# FROM: src/sva2rtl/ast_importer.py lines 127-200 (expr_to_sv match/case)
# ADD new case in the match block:
    case "CallExpression":
        sub_name = node.get("subroutineName", "")
        if sub_name in ("$rose", "$fell", "$stable", "$past"):
            return _build_signal_func_text(node, source_loc)
        raise UnsupportedConstruct(...)
```

#### Pattern D: Builder function structure (analogous to `_build_seq_concat`)

```python
# FROM: src/sva2rtl/ast_importer.py lines 323-365 (_build_seq_concat)
def _build_seq_concat(node: dict[str, Any], source_loc: SourceLoc) -> SeqConcat:
    """Build a SeqConcat IR node from a slang SequenceConcat JSON node."""
    elements_raw: list[dict[str, Any]] = node.get("elements", [])
    elements: list[SVANode] = []
    delays: list[tuple[int, int]] = []
    for i, elem in enumerate(elements_raw):
        # ... extract fields, validate, append ...
    return SeqConcat(elements=tuple(elements), delays=tuple(delays), source_loc=source_loc)

# NEW (same structure):
def _build_seq_repetition(node: dict[str, Any], source_loc: SourceLoc) -> SeqRepetition:
    """Build a SeqRepetition IR node from a SimpleAssertionExpr with repetition."""
    rep = node["repetition"]
    rep_min = int(rep.get("min", 0))
    rep_max_raw = rep.get("max", "0")
    if rep_max_raw == "$":
        raise SvaCompileError(message="SVA-E002: unbounded repetition [*0:$] ...")
    rep_max = int(rep_max_raw)
    inner_expr = _dispatch_expr_to_ir(node.get("expr", {}))
    return SeqRepetition(expr=inner_expr, rep_min=rep_min, rep_max=rep_max, source_loc=source_loc)
```

#### Pattern E: Named sequence expansion (new helper)

```python
# Follow recursive pattern like _build_seq_concat traversal
def _expand_named_sequence(
    node: dict[str, Any],
    declarations: dict[str, dict[str, Any]],
    visited: set[str],
    source_loc: SourceLoc,
) -> SVANode:
    """Recursively expand named sequence reference to primitive operators.
    Raises SvaCompileError on circular reference (cycle detection via visited set).
    """
    name = node.get("sequenceName", "")
    if name in visited:
        raise SvaCompileError(message=f"SVA-E0xx: circular sequence reference: {name}")
    visited.add(name)
    body = declarations[name]
    expanded = _dispatch_expr_to_ir(body)  # recursive
    visited.discard(name)
    return expanded
```

---

### 2.3 `src/sva2rtl/composer.py` — Handle New IR Nodes

**Role:** IR → CheckerNode tree builder
**Closest analog:** `_compose_seq_concat()`, `_make_delay_node()`

#### Pattern A: Top-level compose() dispatch

```python
# FROM: src/sva2rtl/composer.py lines 381-396
def compose(node: SVANode, clock: ClockSpec, label: str | None, original_text: str) -> CheckerNode:
    match node:
        case BoolExpr():
            return _compose_bool_expr(node, clock, label, original_text)
        case SeqConcat():
            return _compose_seq_concat(node, clock, label, original_text)
        case PropImplication():
            return _compose_implication(node, clock, label, original_text)
        case _:
            raise UnsupportedConstruct(...)

# ADD new cases:
        case SeqRepetition():
            return _compose_repetition(node, clock, label, original_text)
        case SignalFunc():
            return _compose_signal_func(node, clock, label, original_text)
        case DisableIff():
            return _compose_disable_iff(node, clock, label, original_text)
```

#### Pattern B: Leaf CheckerNode construction (analog: `_make_delay_node`)

```python
# FROM: src/sva2rtl/composer.py lines 481-515 (_make_delay_node)
def _make_delay_node(delay_min: int, delay_max: int, clock: ClockSpec, source_loc: SourceLoc) -> CheckerNode:
    cnt_width = max(1, math.ceil(math.log2(delay_max + 1))) if delay_max > 0 else 1
    mod_name = f"sva_delay_{delay_min}_{delay_max}"
    params: dict[str, str] = {
        "module_name": mod_name,
        "delay_min": str(delay_min),
        "delay_max": str(delay_max),
        "cnt_width": str(cnt_width),
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(source_loc),
        "sva2rtl_version": __version__,
        "original_text": orig,
    }
    return CheckerNode(
        template_name="concat_delay",
        module_name=mod_name,
        params=params,
        observed_signals=(),
        source_loc=source_loc,
        children=(),
    )

# NEW repetition node (reuses same counter width formula):
def _compose_repetition(
    node: SeqRepetition, clock: ClockSpec, label: str | None, original_text: str
) -> CheckerNode:
    cnt_width = max(1, math.ceil(math.log2(node.rep_max + 1))) if node.rep_max > 0 else 1
    module_name = module_name_from_label(label, original_text)
    # Extract signals from inner expression (BoolExpr leaf)
    observed = extract_signals(node.expr.text) if isinstance(node.expr, BoolExpr) else ()
    params: dict[str, str] = {
        "module_name": module_name,
        "rep_min": str(node.rep_min),
        "rep_max": str(node.rep_max),
        "cnt_width": str(cnt_width),
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name="rep_consecutive",
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
    )
```

#### Pattern C: Signal function composer (leaf, single observed signal)

```python
# Analog: _compose_bool_expr (leaf with observed signals)
# FROM: src/sva2rtl/composer.py lines 402-429
def _compose_bool_expr(node: BoolExpr, clock: ClockSpec, label: str | None, original_text: str) -> CheckerNode:
    module_name = module_name_from_label(label, original_text)
    observed = extract_signals(node.text)
    params: dict[str, str] = {
        "module_name": module_name,
        "bool_expr": node.text,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        ...
    }
    return CheckerNode(template_name="bool_expr", ...)

# NEW: signal function (one signal port, template selected by func_name)
def _compose_signal_func(
    node: SignalFunc, clock: ClockSpec, label: str | None, original_text: str
) -> CheckerNode:
    module_name = module_name_from_label(label, original_text)
    observed = ((node.signal, node.signal),)  # single observed signal
    params: dict[str, str] = {
        "module_name": module_name,
        "signal_name": node.signal,
        "depth": str(node.depth),          # for $past
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        "source_loc": str(node.source_loc),
        "sva2rtl_version": __version__,
        "original_text": original_text,
    }
    return CheckerNode(
        template_name=node.func_name,  # "rose", "fell", "stable", "past"
        module_name=module_name,
        params=params,
        observed_signals=observed,
        source_loc=node.source_loc,
        children=(),
    )
```

#### Pattern D: Wrapper composer (analog: `_compose_implication` — wraps children)

```python
# FROM: src/sva2rtl/composer.py lines 536-569 (_compose_implication)
def _compose_implication(node: PropImplication, ...) -> CheckerNode:
    module_name = module_name_from_label(label, original_text)
    template = "overlap_bitvec" if node.overlapping else "nonoverlap"
    ant_checker = compose(node.antecedent, clock, None, original_text)
    con_checker = compose(node.consequent, clock, None, original_text)
    ...
    return CheckerNode(
        template_name=template,
        children=(ant_checker, con_checker),
        ...
    )

# NEW disable_iff wrapper (wraps body child):
def _compose_disable_iff(
    node: DisableIff, clock: ClockSpec, label: str | None, original_text: str
) -> CheckerNode:
    module_name = module_name_from_label(label, original_text)
    body_checker = compose(node.body, clock, None, original_text)
    observed = extract_signals(node.condition) + body_checker.observed_signals
    params: dict[str, str] = {
        "module_name": module_name,
        "disable_expr": node.condition,
        "clock_signal": clock.signal,
        "clock_edge": clock.edge,
        ...
    }
    return CheckerNode(
        template_name="disable_iff_top",
        module_name=module_name,
        params=params,
        observed_signals=_dedupe_signals(observed),
        source_loc=node.source_loc,
        children=(body_checker,),
    )
```

---

### 2.4 `src/sva2rtl/emitter.py` — Add `emit_bind()` Function

**Role:** Jinja2 rendering entry point
**Closest analog:** `emit()` function (single template render with context)

#### Existing Pattern: `emit()`

```python
# FROM: src/sva2rtl/emitter.py lines 75-103
def emit(checker: CheckerNode, template_dir: Path | None = None) -> str:
    env = _make_env(template_dir)
    template_file = checker.template_name + ".sv.j2"
    tmpl = env.get_template(template_file)
    ctx: dict[str, object] = dict(checker.params)
    ctx["observed_signals"] = checker.observed_signals
    ctx["children"] = checker.children
    return str(tmpl.render(**ctx))
```

#### New: `emit_bind()` (same structure, different template + extra params)

```python
def emit_bind(
    checker: CheckerNode,
    dut_module: str,
    template_dir: Path | None = None,
) -> str:
    """Render a bind statement file for the given checker."""
    env = _make_env(template_dir)
    tmpl = env.get_template("bind.sv.j2")
    ctx: dict[str, object] = dict(checker.params)
    ctx["observed_signals"] = checker.observed_signals
    ctx["dut_module"] = dut_module
    ctx["module_name"] = checker.module_name
    return str(tmpl.render(**ctx))
```

---

### 2.5 `src/sva2rtl/behavioral_oracle.py` — New Operator Kinds

**Role:** Pure-Python cycle-by-cycle reference model
**Closest analog:** `_tick_delay()` method (counter-based state machine)

#### Pattern A: `_valid_kinds` extension

```python
# FROM: src/sva2rtl/behavioral_oracle.py lines 41-47
_valid_kinds = {
    "delay_fixed",
    "delay_range",
    "implication_overlap",
    "implication_nonoverlap",
}
# ADD:
    "rep_consecutive",    # [*N]/[*M:N]
    "rose",              # $rose(sig)
    "fell",              # $fell(sig)
    "stable",            # $stable(sig)
    "past",              # $past(sig, N)
```

#### Pattern B: tick() dispatch extension

```python
# FROM: src/sva2rtl/behavioral_oracle.py lines 76-96
def tick(self, signals: dict[str, bool]) -> dict[str, bool]:
    if self._kind in ("delay_fixed", "delay_range"):
        return self._tick_delay(signals)
    elif self._kind == "implication_overlap":
        return self._tick_overlap(signals)
    else:
        return self._tick_nonoverlap(signals)
# ADD:
    elif self._kind == "rep_consecutive":
        return self._tick_rep_consecutive(signals)
    elif self._kind == "rose":
        return self._tick_rose(signals)
    elif self._kind == "fell":
        return self._tick_fell(signals)
    elif self._kind == "stable":
        return self._tick_stable(signals)
    elif self._kind == "past":
        return self._tick_past(signals)
```

#### Pattern C: Counter state machine (analog: `_tick_delay`)

```python
# FROM: src/sva2rtl/behavioral_oracle.py lines 100-159 (_tick_delay)
def _tick_delay(self, signals: dict[str, bool]) -> dict[str, bool]:
    start: bool = bool(signals.get("start", False))
    delay_min: int = int(self._params.get("delay_min", 0))
    delay_max: int = int(self._params.get("delay_max", 0))
    # ... counter increment logic ...
    # ... window comparison: (count >= min) && (count <= max) ...
    return {"active": active, "pass": pass_val, "fail": False, "overflow": False}

# NEW repetition (very similar but also checks sig each cycle):
def _tick_rep_consecutive(self, signals: dict[str, bool]) -> dict[str, bool]:
    start: bool = bool(signals.get("start", False))
    sig: bool = bool(signals.get("sig", False))
    rep_min: int = int(self._params.get("rep_min", 1))
    rep_max: int = int(self._params.get("rep_max", 1))
    # Counter only increments while sig is true; resets when sig false
    # pass = running && count in [rep_min, rep_max]
    # fail = running && !sig && count < rep_min
    ...
```

#### Pattern D: Single-FF state for edge detection (new, simpler than delay)

```python
def _tick_rose(self, signals: dict[str, bool]) -> dict[str, bool]:
    sig: bool = bool(signals.get("sig", False))
    prev = self._sig_prev  # state: previous cycle value
    self._sig_prev = sig
    rose_detect = sig and not prev
    return {"active": rose_detect, "pass": rose_detect, "fail": not rose_detect, "overflow": False}
```

---

### 2.6 `templates/rep_consecutive.sv.j2` — Counter-Based Repetition

**Role:** RTL template for `[*N]/[*M:N]`
**Closest analog:** `templates/concat_delay.sv.j2` (counter + window comparator)

#### Existing Pattern (counter + window)

```jinja2
{# FROM: templates/concat_delay.sv.j2 lines 31-61 #}
    logic [CNT_WIDTH-1:0] count_q;
    logic                 running_q;
    logic                 attempt_fired_q;

    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        if (!rst_n) begin
            count_q         <= '0;
            running_q       <= 1'b0;
            attempt_fired_q <= 1'b0;
        end else begin
            attempt_fired_q <= attempt_fired_q | start;
            if (start) begin
                count_q   <= '0;
                running_q <= 1'b1;
            end else if (running_q) begin
                if (count_q == {{ cnt_width }}'d{{ delay_max }}) begin
                    running_q <= 1'b0;
                end else begin
                    count_q <= count_q + 1'b1;
                end
            end
        end
    end

    assign active        = running_q;
    assign pass          = running_q && (count_q >= {{ cnt_width }}'d{{ delay_min }}) && (count_q <= {{ cnt_width }}'d{{ delay_max }});
    assign fail          = 1'b0;
    assign attempt_fired = attempt_fired_q;
```

#### New Template (key differences from `concat_delay`):
- **Adds `sig` input port** (the signal being repeated)
- **Counter increments only while `sig` is true** (not unconditionally)
- **Fail condition exists:** `running_q && !sig && (count_q < rep_min)`
- **Output gating with `disable_i`** (new standard interface)

```jinja2
// Generated by sva2rtl {{ sva2rtl_version }}
// Source: {{ source_loc }}
// Original property: @({{ clock_edge }} {{ clock_signal }}) {{ original_text }}
module {{ module_name }} #(
    parameter CNT_WIDTH = {{ cnt_width }}
) (
    input  logic {{ clock_signal }},
    input  logic rst_n,
    input  logic start,
{% for port_name, _ in observed_signals %}
    input  logic {{ port_name }},
{% endfor %}
    input  logic disable_i,
    output logic active,
    output logic pass,
    output logic fail,
    output logic attempt_fired,
    output logic disabled_o
);
    // ... counter increments only when sig is true ...
    // ... fail = running_q && !sig && (count_q < rep_min) ...
    // ... disable gating on outputs ...
endmodule
```

---

### 2.7 `templates/rose.sv.j2` — Edge Detect (1 FF)

**Role:** RTL template for `$rose(sig)`
**Closest analog:** `templates/bool_expr.sv.j2` (leaf template, single always_ff, registered outputs)

#### Existing Pattern (registered outputs in `bool_expr.sv.j2`)

```jinja2
{# FROM: templates/bool_expr.sv.j2 lines 22-40 #}
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
            attempt_fired_q <= attempt_fired_q | start;
        end
    end

    assign active        = active_q;
    assign pass          = pass_q;
    assign fail          = fail_q;
    assign attempt_fired = attempt_fired_q;
```

#### New Template (adds `sig_prev_q` FF + edge detection logic):

```jinja2
module {{ module_name }} (
    input  logic {{ clock_signal }},
    input  logic rst_n,
    input  logic start,
    input  logic {{ signal_name }},
    input  logic disable_i,
    output logic active,
    output logic pass,
    output logic fail,
    output logic attempt_fired,
    output logic disabled_o
);
    logic sig_prev_q;
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        if (!rst_n | disable_i) sig_prev_q <= 1'b0;
        else                    sig_prev_q <= {{ signal_name }};
    end

    logic rose_detect;
    assign rose_detect = {{ signal_name }} & ~sig_prev_q;

    // Registered outputs (same pattern as bool_expr)
    logic pass_internal, fail_internal, active_internal;
    assign pass_internal   = start & rose_detect;
    assign fail_internal   = start & ~rose_detect;
    assign active_internal = start;

    // Disable gating
    assign pass       = disable_i ? 1'b0 : pass_internal;
    assign fail       = disable_i ? 1'b0 : fail_internal;
    assign active     = disable_i ? 1'b0 : active_internal;
    assign disabled_o = disable_i;
    ...
endmodule
```

---

### 2.8 `templates/fell.sv.j2` — Edge Detect (Falling)

**Role:** RTL template for `$fell(sig)`
**Closest analog:** `templates/rose.sv.j2` (identical structure, different detect logic)

#### Key difference from `rose.sv.j2`:

```verilog
// rose: assign detect = sig & ~sig_prev_q;
// fell: assign detect = ~sig & sig_prev_q;
assign fell_detect = ~{{ signal_name }} & sig_prev_q;
```

---

### 2.9 `templates/stable.sv.j2` — XNOR Comparator

**Role:** RTL template for `$stable(sig)`
**Closest analog:** `templates/rose.sv.j2` (identical structure, XNOR detect logic)

#### Key difference from `rose.sv.j2`:

```verilog
// stable: XNOR comparison
assign stable_detect = ({{ signal_name }} == sig_prev_q);
```

---

### 2.10 `templates/past.sv.j2` — N-Stage Shift Register

**Role:** RTL template for `$past(sig, N)`
**Closest analog:** `templates/concat_delay.sv.j2` (counter state, parameterized width)

#### New Template (shift register instead of counter):

```jinja2
module {{ module_name }} #(
    parameter DEPTH = {{ depth }}
) (
    input  logic {{ clock_signal }},
    input  logic rst_n,
    input  logic {{ signal_name }},
    input  logic disable_i,
    output logic past_value,
    output logic disabled_o
);
    logic [DEPTH-1:0] shift_q;
    always_ff @({{ clock_edge }} {{ clock_signal }}) begin
        if (!rst_n | disable_i) shift_q <= '0;
        else                    shift_q <= {shift_q[DEPTH-2:0], {{ signal_name }}};
    end
    assign past_value  = shift_q[DEPTH-1];
    assign disabled_o  = disable_i;
endmodule
```

**Note:** `$past` produces a VALUE (not pass/fail) — different interface from other signal functions. It feeds into a parent module's boolean expression rather than producing pass/fail directly.

---

### 2.11 `templates/disable_iff_top.sv.j2` — Disable Gating Wrapper

**Role:** Top-level wrapper that generates the `disable_i` signal from an expression
**Closest analog:** `templates/seq_concat_top.sv.j2` (wrapper instantiating children)

#### Existing wrapper pattern:

```jinja2
{# FROM: templates/seq_concat_top.sv.j2 lines 26-52 (child instantiation) #}
{% for child in children %}
    {{ child.module_name }} u_{{ child.module_name }} (
        .{{ clock_signal }}({{ clock_signal }}),
        .rst_n    (rst_n),
        .start    ({% if loop.first %}start{% else %}w_pass_{{ loop.index0 - 1 }}{% endif %}),
{% for port_name, _ in child.observed_signals %}
        .{{ port_name }}({{ port_name }}),
{% endfor %}
        .active        (w_active_{{ loop.index0 }}),
        .pass          (w_pass_{{ loop.index0 }}),
        .fail          (w_fail_{{ loop.index0 }}),
        .attempt_fired (w_afired_{{ loop.index0 }})
    );
{% endfor %}
```

#### New Template:

```jinja2
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
    output logic attempt_fired,
    output logic disabled_o
);
    // disable condition evaluation
    logic disable_cond;
    assign disable_cond = ({{ disable_expr }});

    // Child body instantiation with disable_i connected
    {{ children[0].module_name }} u_body (
        .{{ clock_signal }}({{ clock_signal }}),
        .rst_n     (rst_n),
        .start     (start & ~disable_cond),  // suppress start while disabled
        .disable_i (disable_cond),
{% for port_name, _ in children[0].observed_signals %}
        .{{ port_name }}({{ port_name }}),
{% endfor %}
        .active        (active),
        .pass          (pass),
        .fail          (fail),
        .attempt_fired (attempt_fired),
        .disabled_o    (disabled_o)
    );
endmodule
```

---

### 2.12 `templates/bind.sv.j2` — Bind Statement

**Role:** SystemVerilog `bind` statement generation (new pattern, no existing analog)
**Closest analog:** Module instantiation port list pattern from `overlap_bitvec.sv.j2`

#### Port connection pattern from existing template:

```jinja2
{# FROM: templates/overlap_bitvec.sv.j2 lines 34-45 #}
    {{ children[0].module_name }} u_{{ children[0].module_name }} (
        .{{ clock_signal }}({{ clock_signal }}),
        .rst_n    (rst_n),
        .start    (start),
{% for port_name, _ in children[0].observed_signals %}
        .{{ port_name }}({{ port_name }}),
{% endfor %}
        .active        (ant_active_w),
        .pass          (ant_pass_w),
        ...
    );
```

#### New bind template:

```jinja2
// Generated by sva2rtl {{ sva2rtl_version }}
// Bind file for property: {{ module_name }}
// Source: {{ source_loc }}
bind {{ dut_module }} {{ module_name }} u_{{ module_name }} (
    .{{ clock_signal }}({{ clock_signal }}),
    .rst_n     (rst_n),
    .start     (1'b1),
    .disable_i (1'b0),
{% for port_name, sig_name in observed_signals %}
    .{{ port_name }}({{ sig_name }}),
{% endfor %}
    .active        (),
    .pass          (),
    .fail          (),
    .attempt_fired (),
    .disabled_o    ()
);
```

---

### 2.13 Template Interface Update (ALL 5 existing templates)

**Role:** Add `disable_i`/`disabled_o` ports to all existing templates
**Pattern:** Uniform delta applied to each template

#### Delta to apply to ALL existing templates:

**Port list addition (after `start`, before outputs):**
```jinja2
    input  logic disable_i,
```

**Output list addition (after `attempt_fired`):**
```jinja2
    output logic disabled_o
```

**Effective reset change (in `always_ff` reset clause):**
```jinja2
        if (!rst_n | disable_i) begin
```

**Output gating (before `endmodule`):**
```jinja2
    // Disable gating
    assign pass          = disable_i ? 1'b0 : pass_internal;
    assign fail          = disable_i ? 1'b0 : fail_internal;
    assign active        = disable_i ? 1'b0 : active_internal;
    assign disabled_o    = disable_i;
```

**Child instantiation wiring update (in wrapper templates):**
```jinja2
        .disable_i (disable_i),
        ...
        .disabled_o (),
```

---

### 2.14 `tests/test_repetition.py` — Repetition Tests

**Role:** Unit + integration tests for `[*N]/[*M:N]`
**Closest analog:** `tests/test_sequential.py` (golden file harness), `tests/test_behavioral_oracle.py`

#### Existing test patterns:

```python
# FROM: tests/test_sequential.py lines 33-44
def _compile_fixture(fixture_json_path: Path) -> dict[str, str]:
    ast = json.loads(fixture_json_path.read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    return emit_all(checker)

# FROM: tests/test_behavioral_oracle.py lines 33-40
def test_oracle_delay_fixed_3() -> None:
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 3, "delay_max": 3})
    outputs = _run(sim, [
        {"start": True},
        {"start": False},
        ...
    ])
    assert outputs[3]["pass"], "tick 3: should pass"
```

---

### 2.15 `tests/test_simulation_oracle.py` — Dual-Layer Validation

**Role:** End-to-end simulation harness (Python oracle + Icarus co-sim)
**Closest analog:** No direct analog; new test pattern

#### Key patterns to follow:

```python
# Marker for optional skip (from conftest.py pattern)
@pytest.mark.simulation
class TestSimulationOracle:
    @pytest.fixture(autouse=True)
    def check_iverilog(self):
        if not shutil.which("iverilog"):
            pytest.skip("iverilog not installed")

    def test_rose_cosim(self, tmp_path):
        # 1. Generate monitor via pipeline
        # 2. Generate testbench with stimulus
        # 3. Compile with iverilog
        # 4. Run with vvp
        # 5. Parse sim_output.txt
        # 6. Compare cycle-by-cycle with Python oracle
```

---

## 3. Cross-Cutting Patterns {#3-cross-cutting}

### 3.1 Standard Interface Contract

Every generated module MUST expose this port set (Phase 3 update):

```
clk, rst_n, start,           // control
<observed_signals>,           // DUT signals
disable_i,                    // NEW: disable input
active, pass, fail,           // outputs
attempt_fired,                // debug
[overflow_flag],              // implication-only
disabled_o                    // NEW: disable indicator
```

### 3.2 Registered Output Pattern

All outputs are registered (`always_ff`) with synchronous reset to avoid glitches:

```verilog
always_ff @(posedge clk) begin
    if (!rst_n | disable_i) begin
        pass_q <= 1'b0;
        ...
    end else begin
        pass_q <= <logic>;
    end
end
assign pass = disable_i ? 1'b0 : pass_q;
```

### 3.3 Counter Width Formula

Reused across `concat_delay` and `rep_consecutive`:

```python
cnt_width = max(1, math.ceil(math.log2(max_value + 1))) if max_value > 0 else 1
```

### 3.4 Module Naming Convention

```python
# Parameterized leaf modules:
f"sva_delay_{min}_{max}"      # existing
f"sva_rep_{min}_{max}"        # new (repetition)
f"sva_rose_{signal}"          # new (signal function)

# Top-level from label:
module_name_from_label(label, text)  # existing utility
```

### 3.5 Error Handling Pattern

```python
# Rejecting unsupported constructs with source location:
raise SvaCompileError(
    message=f"SVA-E002: unbounded repetition [*0:$] not synthesizable at {source_loc}"
)
# Or via UnsupportedConstruct for graceful "use future version" message:
raise UnsupportedConstruct(
    message="Use a future version of sva2rtl for this feature",
    construct_name="[*0:$] unbounded repetition",
    source_loc=source_loc,
)
```

### 3.6 Golden File Testing Pattern

```python
# Compile fixture → emit_all → compare each module against golden file
def test_golden_rep_fixed() -> None:
    modules = _compile_fixture(_FIXTURES / "rep_fixed.json")
    assert "sva_rep_check" in modules
    _assert_golden_match(modules["sva_rep_check"], _GOLDEN / "sva_rep_check.sv")
```

---

## 4. Data Flow Summary {#4-data-flow}

```
                    slang --ast-json
                          │
                          ▼
               ┌──────────────────────┐
               │  ast_importer.py     │  JSON → IR nodes
               │  (add repetition,    │  (SeqRepetition, SignalFunc, DisableIff)
               │   signal funcs,      │
               │   disable iff,       │
               │   named seq expand)  │
               └──────────┬───────────┘
                          │ SVANode tree
                          ▼
               ┌──────────────────────┐
               │  composer.py         │  IR → CheckerNode tree
               │  (add _compose_*     │  (template selection, params, hierarchy)
               │   for new operators) │
               └──────────┬───────────┘
                          │ CheckerNode tree
                          ▼
               ┌──────────────────────┐
               │  emitter.py          │  CheckerNode → SV text
               │  (emit_all +         │  (Jinja2 templates)
               │   emit_bind NEW)     │
               └──────────┬───────────┘
                          │ dict[module_name, sv_text]
                          ▼
                   Output .sv files
                   + bind .sv file (NEW)

        ═══════════════════════════════════════════
        VALIDATION (parallel path):

               ┌──────────────────────┐
               │ behavioral_oracle.py │  Python reference model
               │ (add rose/fell/      │  (cycle-by-cycle, no RTL)
               │  stable/past/rep)    │
               └──────────┬───────────┘
                          │ expected outputs
                          ▼
               ┌──────────────────────┐
               │ test_simulation_     │  Compare:
               │ oracle.py            │  Python oracle vs Icarus sim
               │ (dual-layer check)   │
               └──────────────────────┘
```

### 4.1 Implementation Dependency Order

```
Step 1: Update ALL templates with disable_i/disabled_o
         └── Regenerate ALL golden files
             └── All Phase 2 tests pass with new interface

Step 2: (parallel after Step 1)
    ├── Plan 3.1: ir.py(SeqRepetition) → ast_importer → composer → rep_consecutive.sv.j2
    └── Plan 3.2: ir.py(SignalFunc) → ast_importer → composer → rose/fell/stable/past.sv.j2

Step 3: (after Step 1)
    Plan 3.3 remaining: ir.py(DisableIff) → ast_importer → composer → disable_iff_top.sv.j2
                        named sequence expansion (ast_importer + cse_origin)
                        emit_bind() + bind.sv.j2

Step 4: (after 3.1 + 3.2 + 3.3)
    Plan 3.4: behavioral_oracle extensions + simulation harness
```

---

*Pattern mapping completed: 2026-05-27*
*Source files analyzed: ir.py, ast_importer.py, composer.py, emitter.py, behavioral_oracle.py, 5 templates, conftest.py, test_sequential.py, test_behavioral_oracle.py*
