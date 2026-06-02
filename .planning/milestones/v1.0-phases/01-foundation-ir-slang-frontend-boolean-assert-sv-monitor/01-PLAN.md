---
phase: 1
plan: "01"
title: "Project skeleton + SVA IR"
wave: 1
depends_on: []
requirements: [PARSE-05, OUT-01, OUT-07]
files_modified:
  - pyproject.toml
  - .python-version
  - src/sva2rtl/__init__.py
  - src/sva2rtl/py.typed
  - src/sva2rtl/ir.py
  - src/sva2rtl/errors.py
  - tests/__init__.py
  - tests/test_ir.py
autonomous: true
estimated_minutes: 30
---

# Plan 01: Project Skeleton + SVA IR

<objective>
Bootstrap the Python package with uv, establish the frozen-dataclass IR hierarchy (SourceLoc, BoolExpr, SeqConcat, PropImplication, ClockSpec, CheckerNode), define the error class hierarchy (SvaError, SlangNotFound, UnsupportedConstruct, SvaCompileError), and prove the IR is correct with unit tests. This is the foundation every other plan depends on.
</objective>

<threat_model>
- **Dependency supply chain:** Only adding well-known packages (click, jinja2, pytest, ruff, mypy, hypothesis) from PyPI. Pin versions in pyproject.toml.
- **File I/O:** This plan only creates project files; no external subprocess or network access.
- **No secrets:** No credentials or API keys involved.
</threat_model>

<tasks>

## Task 1: Initialize project with uv

<read_first>
- CLAUDE.md (project conventions and tech stack)
- .planning/phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-RESEARCH.md (pyproject.toml spec from Research Q8)
</read_first>

<action>
Run `uv init --lib --name sva2rtl` in the project root. Create `.python-version` containing `3.12`. Create `pyproject.toml` with:
- `[project]` section: name="sva2rtl", version="0.1.0", requires-python=">=3.12", dependencies=["click>=8.0", "jinja2>=3.1.6"]
- `[project.scripts]` section: sva2rtl = "sva2rtl.cli:main"
- `[build-system]` section: requires=["hatchling"], build-backend="hatchling.build" (hatchling chosen over uv_build for broader ecosystem compatibility and stable wheel generation)
- `[tool.hatch.build.targets.wheel]` section: packages=["src/sva2rtl"]
- `[dependency-groups]` section: dev=["hypothesis>=6.100", "mypy>=1.10", "pytest>=9.0", "ruff>=0.4"]
- `[tool.ruff]` section: line-length=100, target-version="py312"
- `[tool.ruff.lint]` section: select=["E", "F", "I", "UP", "N", "ANN"], ignore=["ANN101", "ANN102"]
- `[tool.mypy]` section: strict=true, python_version="3.12"
- `[tool.pytest.ini_options]` section: testpaths=["tests"]

Create `src/sva2rtl/__init__.py` with `__version__ = "0.1.0"`. Create empty `src/sva2rtl/py.typed` (PEP 561 marker). Create empty `tests/__init__.py`.
</action>

<acceptance_criteria>
- `pyproject.toml` exists at project root with `name = "sva2rtl"` and `version = "0.1.0"`
- `[project.scripts]` contains `sva2rtl = "sva2rtl.cli:main"`
- `.python-version` contains exactly `3.12`
- `src/sva2rtl/__init__.py` contains `__version__ = "0.1.0"`
- `src/sva2rtl/py.typed` exists (empty file)
- `uv sync` completes without errors
- `uv run python -c "import sva2rtl; print(sva2rtl.__version__)"` prints `0.1.0`
</acceptance_criteria>

## Task 2: Implement ir.py — SVA IR frozen dataclasses

<read_first>
- .planning/phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-RESEARCH.md (Research Q2: IR design)
- .planning/research/ARCHITECTURE.md (Section 2.2: SVA IR)
</read_first>

<action>
Create `src/sva2rtl/ir.py` with the following frozen dataclasses:

1. `SourceLoc(frozen=True)` — fields: `file: str`, `line: int`, `col: int`; `__str__` returns `"{file}:{line}:{col}"`
2. `SVANode(frozen=True)` — base class with field `source_loc: SourceLoc`
3. `BoolExpr(SVANode, frozen=True)` — field: `text: str` (reconstructed SV expression)
4. `SeqConcat(SVANode, frozen=True)` — fields: `elements: tuple[SVANode, ...]`, `delays: tuple[tuple[int, int], ...]`
5. `PropImplication(SVANode, frozen=True)` — fields: `antecedent: SVANode`, `consequent: SVANode`, `overlapping: bool = True`
6. `ClockSpec(frozen=True)` — fields: `edge: str`, `signal: str`, `source_loc: SourceLoc`
7. `CheckerNode(frozen=True)` — fields: `template_name: str`, `module_name: str`, `params: dict[str, str]`, `observed_signals: tuple[tuple[str, str], ...]`, `source_loc: SourceLoc`, `children: tuple[CheckerNode, ...] = ()`; add explicit `__hash__` override using `hash((self.template_name, self.module_name, frozenset(self.params.items()), self.observed_signals, self.source_loc, self.children))` and `__eq__` based on same tuple; add explicit `__hash__` override using `hash((self.template_name, self.module_name, frozenset(self.params.items()), self.observed_signals, self.source_loc, self.children))` and `__eq__` based on same tuple

Include `from __future__ import annotations` at top. Use `typing` imports as needed. All type annotations must pass mypy --strict.
</action>

<acceptance_criteria>
- `src/sva2rtl/ir.py` defines exactly these classes: `SourceLoc`, `SVANode`, `BoolExpr`, `SeqConcat`, `PropImplication`, `ClockSpec`, `CheckerNode`
- All classes use `@dataclass(frozen=True)`
- `SourceLoc("test.sv", 3, 5).__str__()` returns `"test.sv:3:5"`
- `BoolExpr` is hashable: `hash(BoolExpr(text="a", source_loc=SourceLoc("f", 1, 1)))` does not raise
- `CheckerNode` is hashable via explicit `__hash__` override (params is dict[str, str] for Jinja2 compatibility; hash uses frozenset(self.params.items()))
- `BoolExpr` inherits from `SVANode`
- `uv run mypy src/sva2rtl/ir.py --strict` reports zero errors
</acceptance_criteria>

## Task 3: Implement errors.py — Error class hierarchy

<read_first>
- .planning/phases/01-foundation-ir-slang-frontend-boolean-assert-sv-monitor/01-RESEARCH.md (Research Q7: Error handling)
- src/sva2rtl/ir.py (for SourceLoc import)
</read_first>

<action>
Create `src/sva2rtl/errors.py` with:

1. `SvaError(Exception)` — fields: `message: str`, `source_loc: Optional[SourceLoc] = None`; `__str__` returns `"{source_loc}: error: {message}"` if source_loc else `"error: {message}"`
2. `SlangNotFound(SvaError)` — no additional fields; exit code 3
3. `SvaCompileError(SvaError)` — no additional fields; exit code 1
4. `UnsupportedConstruct(SvaError)` — fields: `construct_name: str = ""`; `__str__` returns `"{source_loc}: error SVA-E002: unsupported construct '{construct_name}': {message}"`
5. `InternalError(SvaError)` — no additional fields; exit code 1

Use `@dataclass` (NOT frozen — exceptions need mutability). Import `SourceLoc` from `sva2rtl.ir`.
</action>

<acceptance_criteria>
- `src/sva2rtl/errors.py` defines: `SvaError`, `SlangNotFound`, `SvaCompileError`, `UnsupportedConstruct`, `InternalError`
- All inherit from `Exception` (via `SvaError`)
- `str(UnsupportedConstruct(message="msg", construct_name="##N", source_loc=SourceLoc("f.sv", 3, 5)))` contains `"f.sv:3:5"` and `"SVA-E002"` and `"##N"`
- `str(SlangNotFound(message="not found"))` contains `"not found"`
- `isinstance(SlangNotFound(message="x"), SvaError)` is True
- `uv run mypy src/sva2rtl/errors.py --strict` reports zero errors
</acceptance_criteria>

## Task 4: Unit tests for ir.py and errors.py

<read_first>
- src/sva2rtl/ir.py (the module under test)
- src/sva2rtl/errors.py (the module under test)
</read_first>

<action>
Create `tests/test_ir.py` with pytest tests:
- `test_source_loc_str()`: asserts `str(SourceLoc("foo.sv", 10, 3))` == `"foo.sv:10:3"`
- `test_bool_expr_frozen()`: asserts `BoolExpr` cannot be mutated (raises `FrozenInstanceError`)
- `test_bool_expr_hashable()`: asserts two identical `BoolExpr` instances have same hash
- `test_checker_node_creation()`: creates a `CheckerNode` with template_name="bool_expr", verifies all fields accessible
- `test_clock_spec_fields()`: creates `ClockSpec(edge="posedge", signal="clk", source_loc=...)`, asserts fields
- `test_sva_node_inheritance()`: asserts `isinstance(BoolExpr(...), SVANode)` is True

Create `tests/test_errors.py` with:
- `test_sva_error_with_loc()`: asserts str output includes source location
- `test_sva_error_without_loc()`: asserts str output starts with "error:"
- `test_unsupported_construct_format()`: asserts "SVA-E002" in str output
- `test_slang_not_found_is_sva_error()`: asserts isinstance check
- `test_exceptions_are_catchable()`: asserts `try/except SvaError` catches `SlangNotFound`
</action>

<acceptance_criteria>
- `tests/test_ir.py` exists with at least 6 test functions
- `tests/test_errors.py` exists with at least 5 test functions
- `uv run pytest tests/test_ir.py tests/test_errors.py -v` shows all tests passing
- `uv run ruff check tests/` reports zero violations
</acceptance_criteria>

</tasks>

<verification>
```bash
# All verification steps must pass:
uv sync
uv run python -c "import sva2rtl; print(sva2rtl.__version__)"  # -> 0.1.0
uv run python -c "from sva2rtl.ir import BoolExpr, SourceLoc; e = BoolExpr(text='a', source_loc=SourceLoc('f',1,1)); print(hash(e))"
uv run pytest tests/test_ir.py tests/test_errors.py -v  # all pass
uv run mypy src/sva2rtl --strict  # zero errors
uv run ruff check src/ tests/  # zero violations
```
</verification>

<must_haves>
## truths
- All IR dataclasses are frozen (immutable) and hashable
- SourceLoc is a required field on every SVANode subclass (prevents P5.1 pitfall)
- CheckerNode includes attempt_fired in its interface contract (prevents P1.1 pitfall)
- Error hierarchy maps cleanly to exit codes: SlangNotFound->3, UnsupportedConstruct->2, SvaCompileError->1
- Package is installable via uv and importable as `sva2rtl`

## goal_backward
- Provides the IR types that Plans 02 and 03 consume
- Establishes the error types that Plan 04 (CLI) maps to exit codes
- Package skeleton enables all subsequent plans to add modules
</must_haves>
