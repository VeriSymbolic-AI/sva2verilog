# SVA-to-RTL Compiler — Internal Architecture

**Research type:** Project Architecture
**Date:** 2026-05-25
**Scope:** Greenfield compiler — component boundaries, data flow, build order

---

## 1. High-Level Pipeline

```
SVA source (.sv / .sva)
        |
        v
+-------------------+
|   1. Frontend     |  subprocess: slang --ast-json -> JSON string
+--------+----------+
         | raw JSON
         v
+-------------------+
|  2. AST Import    |  JSON -> SVA IR (Python dataclasses)
+--------+----------+
         | SVA IR (Property / Sequence tree)
         v
+-------------------+
|  3. Normalizer    |  rewrite rules -> canonical form  (Patent 7810056)
+--------+----------+
         | Normalized IR
         v
+-------------------+
|  4. Composer      |  IR -> CheckerNode tree  (Patent 10726182)
+--------+----------+
         | CheckerNode tree
         v
+-------------------+
|  5. Optimizer     |  CSE, counter merging, dead-state elim
+--------+----------+
         | Optimized CheckerNode tree
         v
+-------------------+
|   6. Emitter      |  Jinja2 templates -> RTL text
+--------+----------+
         | SystemVerilog / Verilog-2001 string(s)
         v
      Output file(s) / stdout
```

---

## 2. Module Descriptions

### 2.1 Frontend (`frontend.py`)

**Responsibility:** Invoke `slang` as an external subprocess and capture its JSON AST.

**Inputs:** file path, optional `--slang-path` override
**Outputs:** `dict` (parsed JSON)
**Dependencies:** `subprocess`, `json` (stdlib only)

```python
class SlangFrontend:
    def __init__(self, slang_binary: str = "slang"): ...
    def parse(self, source_file: Path) -> dict:
        """Run slang --ast-json, return parsed JSON dict. Raises on slang error."""
```

Key concerns:
- Capture stderr for diagnostics; surface slang errors as `ParseError` with message.
- Validate that top-level JSON contains expected `"kind": "CompilationUnit"` root.
- Accept pre-parsed JSON dict (for testing without slang binary).

---

### 2.2 SVA IR (`ir.py`)

**Responsibility:** Typed, immutable representation of SVA constructs used by all downstream passes.

**Design rules:**
- Python `@dataclass(frozen=True)` throughout — safe to hash, use in sets/dicts for CSE.
- No RTL concepts at this layer; purely semantic.
- Visitor protocol for tree traversal: `def visit(self, visitor: IRVisitor)`.

**Core node types:**

```python
# -- Leaf --
@dataclass(frozen=True)
class BoolExpr:
    """Atomic boolean expression (verbatim slang expression text)."""
    text: str
    source_loc: SourceLoc | None

# -- Sequence operators --
@dataclass(frozen=True)
class SeqConcat:
    """a ##N b  or  a ##[M:N] b"""
    left: "SeqNode"
    right: "SeqNode"
    delay_min: int               # ##N -> min=max=N; ##[M:N] -> min=M, max=N
    delay_max: int               # -1 means $

@dataclass(frozen=True)
class SeqOr:          left: "SeqNode"; right: "SeqNode"
@dataclass(frozen=True)
class SeqAnd:         left: "SeqNode"; right: "SeqNode"
@dataclass(frozen=True)
class SeqIntersect:   left: "SeqNode"; right: "SeqNode"
@dataclass(frozen=True)
class SeqFirstMatch:  seq: "SeqNode"
@dataclass(frozen=True)
class SeqThroughout:  cond: BoolExpr;  seq: "SeqNode"
@dataclass(frozen=True)
class SeqWithin:      outer: "SeqNode"; inner: "SeqNode"

@dataclass(frozen=True)
class SeqRep:
    """a[*N], a[->N], a[=N]"""
    seq: "SeqNode"
    kind: Literal["consecutive", "goto", "nonconsecutive"]
    rep_min: int
    rep_max: int                 # -1 means $

SeqNode = BoolExpr | SeqConcat | SeqOr | SeqAnd | SeqIntersect | \
           SeqFirstMatch | SeqThroughout | SeqWithin | SeqRep

# -- Property operators --
@dataclass(frozen=True)
class PropImplication:
    antecedent: SeqNode
    consequent: "PropNode"
    overlapping: bool            # True = |->   False = |=>

@dataclass(frozen=True)
class PropAlways:     prop: "PropNode"; clk_event: str | None
@dataclass(frozen=True)
class PropNot:        prop: "PropNode"
@dataclass(frozen=True)
class PropAnd:        left: "PropNode"; right: "PropNode"
@dataclass(frozen=True)
class PropOr:         left: "PropNode"; right: "PropNode"
@dataclass(frozen=True)
class PropSeq:        seq: SeqNode     # bare sequence used as property

PropNode = PropImplication | PropAlways | PropNot | PropAnd | PropOr | PropSeq

# -- Top-level --
@dataclass(frozen=True)
class SVAProperty:
    name: str
    prop: PropNode
    clk: str                     # clock signal name
    rst_n: str                   # reset signal name
    source_loc: SourceLoc | None
```

---

### 2.3 AST Importer (`ast_importer.py`)

**Responsibility:** Walk slang JSON AST, construct SVA IR nodes.

**Inputs:** `dict` (slang JSON)
**Outputs:** `list[SVAProperty]`
**Dependencies:** `ir.py` only

Key concerns:
- Dispatch on `node["kind"]` string from slang's AST.
- Map slang's delay-range representation to `(delay_min, delay_max)`.
- Collect clock/reset from `clocking_event` / `property_spec` nodes.
- Raise `ImportError` with source location for unsupported node kinds.
- Slang JSON schema knowledge is **isolated here** — all other modules speak IR.

---

### 2.4 Normalizer (`normalizer.py`)

**Responsibility:** Transform SVA IR into canonical form suitable for template-based synthesis.
Based on rewrite normalization from **Patent 7810056**.

**Canonical forms produced:**

| Pass | Transformation | Rationale |
|------|---------------|-----------|
| Desugar non-overlap | `a \|=> b` -> `a ##1 true \|-> b` | Unify to one implication kind |
| Flatten same-op chains | `(a ##1 b) ##1 c` -> right-assoc normal form | Template simplification |
| Desugar `##0` | `a ##0 b` -> `SeqAnd(a, b)` at same cycle | Template simplification |
| Expand fixed repetition | `a[*N]` where N <= threshold -> unrolled concat | Avoid specialized template for small N |
| Preserve range repetition | `a[*M:N]` -> keep as `SeqRep` with counter hint | Counter encoding, not state expansion |
| Normalize boolean constants | `1 ##1 a` -> propagate identity | Template simplification |

Implementation: `NodeTransformer` base class — bottom-up rewrite, returns new frozen nodes.

---

### 2.5 Operator Template Library (`templates/`)

**Standard checker interface** (all modules):
```systemverilog
module sva_<op>_<uid> #(parameters) (
    input  logic clk,
    input  logic rst_n,
    input  logic start,    // token arrives: begin monitoring
    output logic active,   // token in flight
    output logic pass,     // token reached sequence end
    output logic fail      // monitored violation detected
);
```

**Template directory layout:**

```
templates/
├── _base.sv.j2                  # shared macros (clk/rst boilerplate)
├── sequence/
│   ├── bool_expr.sv.j2          # leaf: combinational boolean check
│   ├── concat_fixed.sv.j2       # ##N  (shift-register delay)
│   ├── concat_range.sv.j2       # ##[M:N] with counter
│   ├── seq_or.sv.j2             # sequence disjunction (fork tokens)
│   ├── seq_and.sv.j2            # sequence conjunction (join tokens)
│   ├── seq_intersect.sv.j2
│   ├── throughout.sv.j2
│   ├── within.sv.j2
│   ├── first_match.sv.j2
│   ├── rep_consecutive.sv.j2    # [*N] / [*M:N] with counter
│   ├── rep_goto.sv.j2           # [->N]
│   └── rep_nonconsec.sv.j2      # [=N]
├── implication/
│   ├── overlap_bitvec.sv.j2     # |-> Phase A/B bit-vector method
│   ├── overlap_nfa.sv.j2        # |-> Phase C NFA/DFA
│   └── nonoverlap.sv.j2         # |=> wrapper
├── property/
│   ├── prop_always.sv.j2
│   ├── prop_not.sv.j2
│   ├── prop_and.sv.j2
│   └── prop_or.sv.j2
└── checker/
    └── checker_top.sv.j2        # top-level wrapper with bind point
```

---

### 2.6 Composer (`composer.py`)

**Responsibility:** Walk normalized IR, select templates, build `CheckerNode` tree, wire token-passing signals.

**Token-passing wiring protocol:**

```
Parent node                    Child node
--------------------           --------------------
start  ----------------------> start
                               active ------------> parent monitors
                               pass   ------------> parent's next start
                               fail   ------------> aggregate to top fail
```

**Implication composition:**
- `PropImplication` -> two child subtrees (antecedent, consequent)
- Antecedent's `pass` drives consequent's `start`
- `overlapping=True`: share cycle (bit-vector template)
- `overlapping=False`: consequent starts one cycle later

---

### 2.7 Optimizer (`optimizer.py`)

**Passes (in application order):**

| Pass | What it does |
|------|-------------|
| `ConstantFoldPass` | `##0 && true` -> identity simplifications |
| `ConcatMergePass` | Adjacent `##N ##M` -> `##(N+M)`; range arithmetic |
| `CounterMergePass` | Range counters with same bounds -> share hardware |
| `CSEPass` | Identical `structural_hash()` subtrees -> shared instance |
| `DeadNodePass` | Prune nodes whose pass/fail are unreachable from root |

---

### 2.8 Emitter (`emitter.py`)

**Emission strategy:**
1. DFS-collect all unique `CheckerNode` instances by UID (CSE already deduplicated).
2. Emit children before parents -> correct forward-declaration order.
3. Each node renders its template with `node.params` + child port names as Jinja2 vars.
4. SV vs Verilog-2001: templates use conditional guards for `logic`/`wire`, `always_ff`/`always @(posedge clk)`.

---

### 2.9 CLI (`cli.py`)

```
sva2rtl [OPTIONS] <input.sv>

  --property NAME         Extract specific property (default: all)
  --verilog               Emit Verilog-2001 (default: SystemVerilog)
  --output FILE           Output path (default: stdout)
  --multi-file            One file per checker module
  --optimize              Enable all optimization passes (default: on)
  --slang-path PATH       Override slang binary location
  --dump-ast              Print slang JSON AST and exit
  --dump-ir               Print normalized IR and exit
  --dump-tree             Print CheckerNode tree and exit
  -v, --verbose           Verbose logging
```

---

## 3. Suggested Build Order

```
Stage 1 — Foundation (no deps)
  ir.py, errors.py, checker_node.py

Stage 2 — Ingestion
  frontend.py, ast_importer.py
  -> Tests with JSON fixtures (no slang binary needed)

Stage 3 — Normalization
  normalizer.py
  -> Pure IR->IR tests

Stage 4 — Templates + Emitter skeleton
  Minimal templates (bool_expr, concat_fixed)
  emitter.py
  -> Validate template design against hand-crafted CheckerNodes
  ** Do this BEFORE composition — validates interface cheaply **

Stage 5 — Composition
  composer.py
  -> Full pipeline golden tests (concat only initially)

Stage 6 — Full operator coverage
  Remaining templates (range, repetition, implication, property wrappers)
  -> Golden files added per operator

Stage 7 — Optimization
  optimizer.py
  -> Before/after tree tests + golden parity checks

Stage 8 — CLI + polish
  cli.py + integration test suite

Stage 9 — Simulation validation
  tests/simulation/ (requires Icarus/Verilator)
```

---

## 4. Package Structure

```
sva2rtl/
├── __init__.py
├── ir.py                  # SVA IR dataclasses
├── errors.py              # ParseError, UnsupportedConstruct, ...
├── frontend.py            # slang subprocess wrapper
├── ast_importer.py        # JSON -> IR
├── normalizer.py          # IR rewrite passes
├── checker_node.py        # CheckerNode + ImplicationStrategy
├── composer.py            # IR -> CheckerNode tree
├── optimizer.py           # CheckerNode optimization passes
├── emitter.py             # CheckerNode -> RTL text
├── cli.py                 # click entry point
└── templates/             # Jinja2 .sv.j2 files

tests/
├── unit/
├── integration/
│   └── golden/
└── simulation/

pyproject.toml
```

---

## 5. Component Boundary Summary

| Component | Consumes | Produces | Must NOT touch |
|-----------|----------|----------|----------------|
| Frontend | file path + slang binary | `dict` JSON | IR, templates |
| ASTImporter | `dict` JSON | `list[SVAProperty]` | slang internals post-import |
| Normalizer | `SVAProperty` (raw IR) | `SVAProperty` (normalized IR) | CheckerNode, templates |
| Composer | `SVAProperty` (normalized IR) | `CheckerNode` tree | RTL text, Jinja2 |
| Optimizer | `CheckerNode` tree | `CheckerNode` tree | IR, templates |
| Emitter | `CheckerNode` tree | `str` / `dict[str,str]` | IR passes, composition logic |
| CLI | all modules | exit code + output | business logic directly |

---

*Sources: TIMA Lab token-passing composition (Patent US10726182B2); SVA rewrite normalization (Patent US7810056B2); slang SystemVerilog compiler JSON AST output format.*
