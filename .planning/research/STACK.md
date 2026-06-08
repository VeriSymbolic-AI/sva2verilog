# Stack Research: SVA-to-RTL Compiler

**Project:** SVA-to-RTL Compiler (Python-based)
**Pipeline:** SVA input -> slang JSON AST -> Python IR -> NFA/DFA -> synthesizable SystemVerilog/Verilog
**Research Date:** 2026-05-25

---

## Summary Table

| Layer | Choice | Version | Confidence |
|---|---|---|---|
| Runtime | Python | 3.12+ | High |
| Package manager | uv | latest | High |
| SVA frontend | slang CLI --ast-json (primary) / pyslang (alternative) | v11.0 / 9.1.0 | High |
| IR modeling | dataclasses (frozen=True) | stdlib | High |
| NFA/DFA engine | automata-lib | 9.0.0 | High |
| Graph algorithms | networkx | 3.6.1 | High |
| RTL code generation | Jinja2 | 3.1.6 | High |
| CLI framework | click | 8.x | High |
| Test framework | pytest | 9.0.3 | High |
| Property testing | hypothesis | 6.150.2 | High |
| Linter + formatter | ruff | 0.15.x | High |
| Type checker | mypy | latest | High |

---

## 1. Runtime: Python 3.12+

**Rationale:**
- 3.12+ gives structural pattern matching (`match`/`case`) — ideal for AST visitor dispatch on `kind` fields
- Performance improvements over 3.10/3.11
- `pyslang` and all key libraries support 3.12+

**What NOT to use:**
- PyPy (pyslang uses C extensions via pybind11)
- Python < 3.12 (miss match/case ergonomics)

---

## 2. SVA Frontend: slang CLI --ast-json

**Rationale:**
- slang v11.0 (May 2026) — most complete open-source SV parser, MIT license
- `--ast-json` provides full elaborated AST as JSON — stable interface
- Isolates compiler from slang version changes (JSON schema more stable than Python binding API)
- pyslang 9.1.0 available as alternative for in-process access

**What NOT to use:**
- ANTLR4 + SV grammar (no spec-compliant grammar exists)
- tree-sitter-systemverilog (parse-tree only, no semantic info)
- Custom parser (months of work, slang already does it perfectly)

---

## 3. IR Modeling: Frozen Dataclasses

**Rationale:**
- `@dataclass(frozen=True)` enables structural hashing for CSE
- No external dependency needed
- Pattern matching with `match node:` is natural
- Immutable — safe to share across passes without copy

**Why not Pydantic:**
- Pydantic adds validation overhead unnecessary for internal IR (slang already validates)
- Frozen dataclasses are simpler and faster for compiler-internal tree structures
- Pydantic useful for the JSON import boundary only (ast_importer)

---

## 4. NFA/DFA Construction: automata-lib 9.0.0

**Rationale:**
- Purpose-built Python library for DFA/NFA with clean API
- Provides `NFA.to_dfa()` (subset construction) and `DFA.minify()` (Hopcroft minimization)
- Both are critical for Phase B/C of the pipeline
- Optional graphviz rendering for debugging

**What NOT to use:**
- Building NFA/DFA from scratch initially (use automata-lib, replace later if perf needed)
- NLTK's FSA utilities (NLP-focused, wrong abstraction)

---

## 5. Graph Algorithms: networkx 3.6.1

**Rationale:**
- Needed for: cycle detection, SCC analysis, topological sort of RTL modules
- Complements automata-lib for structural graph analysis on state graphs
- Mature, well-documented, excellent Graphviz export

**What NOT to use:**
- igraph-python (overkill for <1000 state DFAs)

---

## 6. RTL Code Generation: Jinja2 3.1.6

**Rationale:**
- Template inheritance (base monitor skeleton + specialized templates)
- Whitespace control (critical for readable RTL output)
- Custom filters (`| sv_width` to emit `[N-1:0]`)
- Separation of RTL structure from Python logic
- Maintainable and reviewable by RTL engineers

**What NOT to use:**
- Mako (arbitrary Python in templates is a footgun for RTL correctness)
- f-strings (unmanageable for multi-hundred-line RTL modules)
- No mature Python Verilog-AST-to-text library exists

---

## 7. CLI Framework: click 8.x

**Rationale:**
- Proven, composable subcommand architecture
- Clean option/argument declaration
- Good error messages out of the box
- Lighter than typer for a compiler CLI

---

## 8. Testing: pytest 9.x + hypothesis 6.x

**pytest:** Industry standard. `@pytest.mark.parametrize` for exhaustive SVA operator testing.

**hypothesis:** Property-based testing generates edge-case SVA structures that manual tests miss. Shrinking finds minimal reproducing fragments — invaluable for compiler debugging.

**Test structure:**
```
tests/
  unit/           # per-module isolation
  integration/    # full pipeline with golden files
    golden/       # input.sv + expected.sv pairs
  simulation/     # Icarus/Verilator behavioral validation
```

---

## 9. Code Quality: ruff + mypy

**ruff:** Replaces Black + Flake8 + isort in one tool, 100x faster.

**mypy (strict):** Compiler IR benefits enormously from strict typing — catches missing match cases at analysis time.

---

## 10. What NOT to Use

| Tool | Reason |
|---|---|
| ANTLR4 + SV grammar | No maintained spec-compliant grammar exists |
| tree-sitter-sv | Parse-tree only, no semantic info |
| Poetry | Slower than uv; use uv for new projects |
| Black + Flake8 separately | Superseded by ruff |
| Mako templates | Arbitrary Python in templates → RTL bugs |
| PyPy | Incompatible with pyslang pybind11 |
| Custom NFA/DFA from scratch | automata-lib handles edge cases correctly |

---

*Sources: pyslang on PyPI, automata-lib on GitHub (caleb531/automata), slang releases (MikePopoloski/slang), ruff releases (astral-sh/ruff)*
