<!-- GSD:project-start source:PROJECT.md -->
## Project

**sva2rtl**

An open-source SVA (SystemVerilog Assertion) to synthesizable RTL compiler. It takes SVA properties/sequences as input and generates hardware monitor modules in SystemVerilog (with Verilog-2001 compatibility flag) that can be simulated with Verilator/Icarus or synthesized to FPGA. No mature open-source tool exists in this space globally — this fills a critical gap in the EDA toolchain.

**Core Value:** Turn any supported SVA property into an area-efficient,
evidence-backed synthesizable hardware monitor while rejecting unsupported or
insufficiently verified forms.

### Constraints

- **Parsing**: Must use slang library (not re-implement parser) — slang is MIT, IEEE 1800-2017+ complete
- **Language**: Python for v1 (rapid iteration), potential C++ rewrite for v2 performance
- **Output**: SystemVerilog default, Verilog-2001 via --verilog flag
- **Validation**: All generated monitors must pass equivalence checking against behavioral simulation (Icarus/Verilator). Dual-oracle contract enforced: every simulation test passes under both iverilog and Verilator in CI.
- **License**: Apache License 2.0 (SPDX: `Apache-2.0`)
- **Architecture**: Token-passing composition model (TIMA Lab) with operator-aware templates (counter encoding for ranges)
- **Interface standard**: Every generated checker exposes (clk, rst_n, start, pass, fail, active) ports

### Dual-Oracle Validation Contract

- A test passing under iverilog but failing under Verilator is a defect that MUST be fixed — never waived or marked as xfail.
- The `--simulator` pytest flag controls which backend is used: `--simulator=iverilog` (default) or `--simulator=verilator`.
- Simulation tests live in `tests/simulation/` and are marked `@pytest.mark.simulation`.
- The Verilator backend uses a C++ wrapper (`tests/simulation/wrapper.cpp.j2`) compiled with `verilator --exe --build --timing` (NOT `--binary`).
- CI enforces parity: iverilog axis runs full test suite, Verilator axis runs `-m simulation`. 8 total jobs: `{ubuntu,macos} × {3.12,3.13} × {iverilog,verilator}`.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

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
## 1. Runtime: Python 3.12+
- 3.12+ gives structural pattern matching (`match`/`case`) — ideal for AST visitor dispatch on `kind` fields
- Performance improvements over 3.10/3.11
- `pyslang` and all key libraries support 3.12+
- PyPy (pyslang uses C extensions via pybind11)
- Python < 3.12 (miss match/case ergonomics)
## 2. SVA Frontend: slang CLI --ast-json
- slang v11.0 (May 2026) — most complete open-source SV parser, MIT license
- `--ast-json` provides full elaborated AST as JSON — stable interface
- Isolates compiler from slang version changes (JSON schema more stable than Python binding API)
- pyslang 9.1.0 available as alternative for in-process access
- ANTLR4 + SV grammar (no spec-compliant grammar exists)
- tree-sitter-systemverilog (parse-tree only, no semantic info)
- Custom parser (months of work, slang already does it perfectly)
## 3. IR Modeling: Frozen Dataclasses
- `@dataclass(frozen=True)` enables structural hashing for CSE
- No external dependency needed
- Pattern matching with `match node:` is natural
- Immutable — safe to share across passes without copy
- Pydantic adds validation overhead unnecessary for internal IR (slang already validates)
- Frozen dataclasses are simpler and faster for compiler-internal tree structures
- Pydantic useful for the JSON import boundary only (ast_importer)
## 4. NFA/DFA Construction: automata-lib 9.0.0
- Purpose-built Python library for DFA/NFA with clean API
- Provides `NFA.to_dfa()` (subset construction) and `DFA.minify()` (Hopcroft minimization)
- Both are critical for Phase B/C of the pipeline
- Optional graphviz rendering for debugging
- Building NFA/DFA from scratch initially (use automata-lib, replace later if perf needed)
- NLTK's FSA utilities (NLP-focused, wrong abstraction)
## 5. Graph Algorithms: networkx 3.6.1
- Needed for: cycle detection, SCC analysis, topological sort of RTL modules
- Complements automata-lib for structural graph analysis on state graphs
- Mature, well-documented, excellent Graphviz export
- igraph-python (overkill for <1000 state DFAs)
## 6. RTL Code Generation: Jinja2 3.1.6
- Template inheritance (base monitor skeleton + specialized templates)
- Whitespace control (critical for readable RTL output)
- Custom filters (`| sv_width` to emit `[N-1:0]`)
- Separation of RTL structure from Python logic
- Maintainable and reviewable by RTL engineers
- Mako (arbitrary Python in templates is a footgun for RTL correctness)
- f-strings (unmanageable for multi-hundred-line RTL modules)
- No mature Python Verilog-AST-to-text library exists
## 7. CLI Framework: click 8.x
- Proven, composable subcommand architecture
- Clean option/argument declaration
- Good error messages out of the box
- Lighter than typer for a compiler CLI
## 8. Testing: pytest 9.x + hypothesis 6.x
## 9. Code Quality: ruff + mypy
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
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

### Template Design: `wire` vs `logic` for Intermediate Signals

**CRITICAL**: In iverilog, `logic x = expr;` is a **variable initial assignment** (executed once at time 0), NOT a continuous assignment. This causes x-propagation in multi-module simulations.

Rules for Jinja2 templates:
- **Registered signals** (`_q`): use `{{ signal_type(verilog_mode) }}` → `logic`
- **Inter-module connection wires** (driven by child module outputs): use explicit `wire`
- **Combinational logic wires** (`_body_*`, `_cond_*`): use explicit `wire = expr` or `wire x; assign x = expr;`

Never use `{{ wire_type(verilog_mode) }} _body_active = expr;` — it produces `logic _body_active = expr;` which is init-only in iverilog.

### Port Instantiation

Always use **explicit port connections** for child module instantiations in composed templates.  Do NOT use `.*` implicit connections — they connect child output ports (active/pass/fail) to parent output ports of the same name, creating multi-driver conflicts.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
