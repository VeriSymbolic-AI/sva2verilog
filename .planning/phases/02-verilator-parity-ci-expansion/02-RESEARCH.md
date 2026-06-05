# Phase 02: Verilator Parity + CI Expansion - Research

**Researched:** 2026-06-05
**Domain:** Multi-simulator RTL verification (Icarus Verilog + Verilator), CI matrix expansion, pytest plugin architecture
**Confidence:** HIGH

## Summary

This phase adds Verilator as a second simulation oracle alongside iverilog, establishes cycle-accurate parity across the existing 65-test simulation suite, expands the CI matrix to 8 jobs, and documents the dual-oracle commitment. The core technical challenge is creating a minimal C++ wrapper (~50 lines) that drives Verilator's compiled model with the same per-cycle stimulus/check pattern used by the existing SystemVerilog testbench.

**Primary recommendation:** Use `verilator --exe --build --timing` (NOT `--binary`, which auto-generates an incompatible `main()`) with a custom `wrapper.cpp` that toggles `clk` in C++ and reads output signals via `top->signal_name`. Refactor `tb_generator.py` to extract shared stimulus logic and add a `run_simulation_verilator()` function. Extend CI with a `simulator` matrix axis and use `pytest_addoption` for `--simulator` flag selection.

## User Constraints (from CONTEXT.md)

### Locked Decisions

1. **Verilator install**: `apt-get install -y verilator` (Ubuntu), `brew install verilator` (macOS), no version pinning
2. **Test scope**: only `simulation`-marked tests (~65), not all 736 tests
3. **Architecture**: Verilator `--binary` mode + minimal C++ wrapper (~50 lines) driving same per-cycle stimulus/check
4. **tb_generator.py refactor**: extract `run_simulation_iverilog()` + new `run_simulation_verilator()`, shared stimulus logic
5. **CI**: extend existing `test` job matrix with `simulator` axis → 8 jobs
6. **No soft-fail**: divergence = CI failure that must be fixed in Phase 2
7. **CI detection**: `tests/simulation/conftest.py` autouse skip pattern extended for dual-simulator switching via `--simulator` CLI flag or `SVA2RTL_SIMULATOR` env var
8. **Simulation-only**: only `pytest -m simulation` tests run on Verilator axis; non-simulation tests excluded
9. **`test_verilator_lint_clean`**: upgrade from skip to run on Verilator axis
10. **Verilator compile command**: `verilator --binary --timing -Wall --top-module <dut> <dut.sv> <wrapper.cpp> -o <sim>`
11. **Diff output**: `run_simulation()` outputs cycle-by-cycle diff on mismatch
12. **Fix priority**: sva2rtl codegen bugs → wrapper/timing differences → known differences (last resort)
13. **Documentation**: README (Verilator install + `--simulator` flag), CLAUDE.md (dual oracle contract)

### Claude's Discretion

- `wrapper.cpp` specific implementation
- `tb_generator.py` exact function signatures and module split
- CI YAML `matrix.simulator` syntax
- `--simulator` pytest flag: `pytest_addoption` vs environment variable
- Verilator `--timing` flag necessity
- Simulation timeout adequacy (120s for Verilator compile + run)

### Deferred Ideas (OUT OF SCOPE)

- Verilator code coverage
- Verilator waveform dump (VCD/FST)
- Formal equivalence check (yosys-sby)
- Pre-commit hook for Verilator lint

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Simulation execution (iverilog) | Python test harness | System (iverilog/vvp) | Python drives compilation and execution; iverilog is an external tool invoked via subprocess |
| Simulation execution (Verilator) | Python test harness | System (verilator/g++) | Python drives compilation; Verilator + g++ produce a native binary; Python invokes it via subprocess |
| Stimulus generation | Python test harness | — | Stimulus dicts are pure Python; shared between both simulators |
| Output parsing | Python test harness | — | `_parse_output()` reads stdout from either simulator; format must be unified |
| Simulator selection | pytest conftest | CLI/env | `--simulator` flag or `SVA2RTL_SIMULATOR` env var selects backend |
| CI job orchestration | GitHub Actions | — | Matrix strategy expands os × python × simulator |
| Simulator availability check | pytest conftest | System PATH | `shutil.which()` guards per-simulator skip logic |
| Dual-oracle documentation | README.md | CLAUDE.md | README for users, CLAUDE.md for AI agents |

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VALIDATE-02 | Verilator produces same 65 pass/fail outcomes as iverilog on simulation oracle suite | C++ wrapper pattern (Pattern 1), Verilator API for signal access (§Standard Stack), output parsing unification (§Code Examples) |
| VALIDATE-03 | CI matrix expands to Ubuntu/macOS × Py 3.12/3.13 × {iverilog, Verilator}; all 8 jobs green | GitHub Actions 3-axis matrix (§Architecture Patterns: Pattern 3), conditional install steps (§Code Examples) |
| VALIDATE-04 | Dual-oracle commitment documented in README and enforced in CI | Documentation patterns (§Don't Hand-Roll), CI enforcement via matrix (§Architecture Patterns) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Verilator | 5.x (system package manager) | SystemVerilog → C++ compiler + simulator | Only mature open-source SV simulator supporting synthesizable RTL; `--binary`/`--exe` mode produces native executable [VERIFIED: verilator.org/guide/latest/exe_verilator.html] |
| Icarus Verilog (iverilog) | system package manager | Existing simulator (unchanged) | Already integrated; provides baseline oracle [VERIFIED: existing codebase] |
| pytest | 9.0.3 | Test framework | Already in use; `pytest_addoption` hook for `--simulator` flag [VERIFIED: docs.pytest.org/en/stable/example/simple.html] |
| pytest-timeout | already in use | Test timeout guard | Existing 120s timeout; needs verification for Verilator compile + run time [CITED: existing ci.yml] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| g++ / clang++ | system compiler | Compile Verilator-generated C++ | Required by Verilator `--build`; already available on all CI runners |
| make | system | Build orchestration for Verilator | Verilator `--build` invokes make internally |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `verilator --exe --build --timing` (custom wrapper) | `verilator --binary` (auto-generated main) | `--binary` includes `--main` which generates a generic main() that doesn't drive our specific signals. With custom wrapper, use `--exe --build --timing` instead to avoid main() conflict. [VERIFIED: verilator.org/guide/latest/exe_verilator.html] |
| `--timing` flag | `--no-timing` (default) | `--binary` internally includes `--timing`. The testbench clock uses `#5` delay — but that's in the SV testbench which Verilator never sees. The DUT templates contain no `#delay` constructs. However, `--timing` is needed because: (1) the `always #5 clk = ~clk` in the SV testbench doesn't apply (we drive clk from C++), (2) but the SV `$display` in the original testbench also doesn't apply (we read signals from C++). **Actually: `--timing` is NOT required for the C++ wrapper approach** since we drive clock from C++ and read outputs directly. However, the locked decision specifies `--binary --timing`, and `--binary` already includes `--timing`, so we get it for free. [VERIFIED: verilator.org/guide/latest/exe_verilator.html — `--binary` = `--main --exe --build --timing`] |
| `--timing` included | `--no-timing` | If `--no-timing` is explicitly passed alongside `--exe`, it disables coroutine support. Not needed for our DUT but doesn't hurt. Since we use `--exe --build` (not `--binary`), we should include `--timing` explicitly to match the locked decision's intent. |

**Key insight on `--binary` vs `--exe`:** The locked decision says `verilator --binary --timing`. But `--binary` = `--main --exe --build --timing`. The `--main` flag generates a generic `main()` that won't drive our specific signals. Since we provide our own `wrapper.cpp` with a custom `main()`, we must NOT use `--main`. The correct invocation is: `verilator --exe --build --timing -Wall --top-module <dut> <dut.sv> <wrapper.cpp> -o <sim>`. This is functionally equivalent to `--binary` but with our wrapper replacing the auto-generated main. [VERIFIED: verilator.org/guide/latest/exe_verilator.html — "If you want to provide your own main(), do not use --binary, instead manually combine the required options"]

**Installation:**
```bash
# No pip packages needed — Verilator is a system tool
# Ubuntu CI:
sudo apt-get update && sudo apt-get install -y verilator
# macOS CI:
brew install verilator
```

**Version verification:**
```bash
# Verilator is a system package, not on PyPI/npm.
# Check installed version:
verilator --version
# Expected: 5.0xx (whatever the system package manager provides)
# The Python package "verilator" on PyPI is a Python binding — NOT the simulator we need.
# Do NOT pip install verilator.
```

## Package Legitimacy Audit

> This phase adds no pip/npm packages. Verilator is installed via system package manager (apt/brew).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| verilator (system tool) | apt/brew | 20+ yrs | N/A (system) | github.com/verilator/verilator | N/A (not a pip package) | Approved — installed via OS package manager |
| pytest-timeout | PyPI | already in project | already in project | github.com/pytest-dev/pytest-timeout | N/A (already present) | Already in use; no change |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

**⚠️ IMPORTANT:** The Python package `verilator` on PyPI is a Python binding/wrapper, NOT the Verilator simulator. The slopcheck scan on PyPI found `verilator-5.48.0` which is a Python-to-Verilator bridge. **Do NOT `pip install verilator`**. The real Verilator simulator must be installed via `apt-get install verilator` or `brew install verilator`.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        TEST HARNESS (Python)                         │
│                                                                      │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐   │
│  │ Stimulus  │───▶│ generate_    │───▶│ run_simulation(          │   │
│  │ (dicts)   │    │ testbench()  │    │   simulator="iverilog"   │   │
│  └──────────┘    └──────────────┘    │   or "verilator")        │   │
│                                       └───────────┬──────────────┘   │
│                                                   │                  │
│                    ┌───────────────────────────────┤                  │
│                    │                               │                  │
│                    ▼                               ▼                  │
│  ┌─────────────────────────┐     ┌─────────────────────────────┐    │
│  │ run_simulation_iverilog │     │ run_simulation_verilator()   │    │
│  │                         │     │                              │    │
│  │ 1. Write dut.sv, tb.sv  │     │ 1. Write dut.sv              │    │
│  │ 2. iverilog → sim.vvp   │     │ 2. Write wrapper.cpp         │    │
│  │ 3. vvp sim.vvp          │     │ 3. verilator --exe --build   │    │
│  │ 4. Parse $display output│     │    → Vdut + sim binary       │    │
│  │                         │     │ 4. ./sim (binary)            │    │
│  │                         │     │ 5. Parse printf output       │    │
│  └───────────┬─────────────┘     └──────────────┬──────────────┘    │
│              │                                   │                   │
│              └────────────┬──────────────────────┘                   │
│                           ▼                                          │
│                  ┌─────────────────┐                                 │
│                  │  _parse_output()│                                 │
│                  │  → list[dict]   │                                 │
│                  └────────┬────────┘                                 │
│                           │                                          │
│                           ▼                                          │
│                  ┌─────────────────┐                                 │
│                  │ Compare vs      │                                 │
│                  │ behavioral      │                                 │
│                  │ oracle (Python) │                                 │
│                  └─────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────┘

                     SIMULATOR BOUNDARY
                     ═══════════════════

┌──────────────────────────────┐  ┌──────────────────────────────────┐
│     IVERILOG PATH            │  │       VERILATOR PATH              │
│                              │  │                                   │
│  tb.sv (SV testbench)        │  │  wrapper.cpp (C++ testbench)      │
│    │                         │  │    │                              │
│    ▼                         │  │    ▼                              │
│  iverilog -g2012             │  │  verilator --exe --build --timing │
│    │                         │  │    │                              │
│    ▼                         │  │    ▼                              │
│  vvp sim.vvp                 │  │  g++ → sim (native binary)        │
│    │                         │  │    │                              │
│    ▼                         │  │    ▼                              │
│  $display(stdout) ───────────┼──│── printf(stdout) ─────────────────│
│                              │  │                                   │
│  Clock: always #5 in SV      │  │  Clock: C++ loop toggles          │
│  Stimulus: SV initial block  │  │  Stimulus: C++ loop drives        │
│  Capture: $display at posedge│  │  Capture: printf after eval()     │
└──────────────────────────────┘  └──────────────────────────────────┘
```

### Recommended Project Structure
```
tests/simulation/
├── __init__.py
├── conftest.py          # Updated: --simulator flag, dual-simulator skip logic
├── tb_generator.py      # Refactored: shared stimulus + iverilog/verilator runners
├── wrapper.cpp.j2       # NEW: Jinja2 template for Verilator C++ wrapper
├── test_sim_delay.py
├── test_sim_disable_iff.py
├── test_sim_fell.py
├── test_sim_implication.py
├── test_sim_named_seq.py
├── test_sim_past.py
├── test_sim_repetition.py
├── test_sim_rose.py
└── test_sim_stable.py

tests/
├── conftest.py          # Root conftest: pytest_addoption for --simulator
├── test_sequential.py   # test_verilator_lint_clean: remove skipif
└── test_optimizer.py    # simulation tests: update run_simulation() call signature

.github/workflows/
└── ci.yml               # Updated: simulator matrix axis
```

### Pattern 1: Verilator C++ Wrapper (Minimal ~50 Lines)

**What:** A C++ file that instantiates the Verilated model, toggles clock, drives inputs per stimulus cycle, reads outputs, and prints results in the same format as the existing SystemVerilog `$display`.

**When to use:** Every Verilator simulation test. Generated from a Jinja2 template with the module name, signal names, and stimulus data embedded.

**Example:**
```cpp
// Source: Verilator 5.x official docs — verilator.org/guide/latest/connecting.html
// Pattern verified against Verilator examples/make_tracing_c/sim_main.cpp

#include "V<module_name>.h"   // Verilator-generated header
#include "verilated.h"
#include <cstdio>

int main(int argc, char** argv) {
    VerilatedContext* contextp = new VerilatedContext;
    contextp->commandArgs(argc, argv);
    V<module_name>* top = new V<module_name>{contextp};

    // Signal initialization
    top->clk = 0;
    top->rst_n = 0;
    top->start = 0;
    top->disable_i = 0;
    // ... extra_inputs initialized to 0

    // Reset sequence: 2 cycles with rst_n=0
    for (int i = 0; i < 2; i++) {
        contextp->timeInc(1);
        top->clk = !top->clk;
        top->eval();
        contextp->timeInc(1);
        top->clk = !top->clk;
        top->eval();
    }

    // Release reset at negedge (set before posedge eval)
    top->rst_n = 1;

    // Drive stimulus cycles
    // Stimulus data embedded at template-render time
    <stimulus_loop>

    // Cleanup
    top->final();
    delete top;
    delete contextp;
    return 0;
}
```

**Stimulus loop detail (per cycle):**
```cpp
// For each stimulus cycle:
// 1. Set inputs at "negedge" (before clock toggles to 1)
top->start = <stim[i].start>;
top->sig1  = <stim[i].sig1>;
top->disable_i = <stim[i].disable_i>;
// 2. Evaluate at current state (negedge)
top->eval();
// 3. Advance time, toggle clock to posedge
contextp->timeInc(1);
top->clk = 1;
// 4. Evaluate at posedge — captures outputs
top->eval();
// 5. Read and print outputs (matching existing $display format)
printf("%b %b %b\n", top->active, top->pass, top->fail);
// 6. Advance time, toggle clock back to negedge
contextp->timeInc(1);
top->clk = 0;
top->eval();
```

**Key insight — `printf` format vs `$display`:** Verilator C++ signals are `CData` (1-bit), `SData` (16-bit), etc. Printing with `%b` is not standard C. Instead, print as integers (0/1) since `_parse_output()` already handles `'0'`/`'1'` characters:
```cpp
printf("%d %d %d\n", top->active, top->pass, top->fail);
```
Or use a ternary for binary output:
```cpp
printf("%c %c %c\n",
    top->active ? '1' : '0',
    top->pass   ? '1' : '0',
    top->fail   ? '1' : '0');
```

[VERIFIED: verilator.org/guide/latest/connecting.html — "Top-level IO ports are exposed as read-only references on the model class" and "top->signal_name = value for inputs, value = top->signal_name for outputs"]

### Pattern 2: tb_generator.py Refactoring

**What:** Split the monolithic `run_simulation()` into two backend functions sharing a common stimulus generation path. The public API becomes `run_simulation(module_name, sv_sources, tb_code, *, work_dir, has_overflow_flag, simulator="iverilog")`.

**When to use:** Every test that calls `run_simulation()`.

**Refactored structure:**
```python
# tb_generator.py (refactored)

def run_simulation(
    module_name: str,
    sv_sources: list[str],
    tb_code: str,
    *,
    work_dir: Path,
    has_overflow_flag: bool = False,
    simulator: str = "iverilog",
) -> list[dict[str, bool]]:
    """Compile and run with selected simulator."""
    if simulator == "iverilog":
        return _run_simulation_iverilog(
            module_name, sv_sources, tb_code, work_dir, has_overflow_flag
        )
    elif simulator == "verilator":
        return _run_simulation_verilator(
            module_name, sv_sources, tb_code, work_dir, has_overflow_flag
        )
    else:
        raise ValueError(f"Unknown simulator: {simulator}")


def _run_simulation_iverilog(...) -> list[dict[str, bool]]:
    """Existing iverilog logic — moved verbatim from current run_simulation()."""
    ...  # unchanged from current code


def _run_simulation_verilator(...) -> list[dict[str, bool]]:
    """New: Verilator compile + run via C++ wrapper."""
    ...
```

**Shared components (extracted):**
- `generate_testbench()` — unchanged (still generates SV testbench for iverilog)
- `_parse_output()` — unchanged (both backends produce same stdout format)
- `extra_inputs_from_checker()` — unchanged
- `TEMPLATES_WITH_OVERFLOW` — unchanged

**New components:**
- `generate_verilator_wrapper()` — renders `wrapper.cpp.j2` with module name, signals, stimulus
- `_run_simulation_verilator()` — orchestrates Verilator compilation and execution

### Pattern 3: GitHub Actions 3-Axis Matrix

**What:** Add a `simulator` axis to the existing `os × python-version` matrix. Use conditional `if:` on steps to install the correct simulator per job.

**When to use:** The `test` job in `.github/workflows/ci.yml`.

**Example:**
```yaml
# Source: docs.github.com/en/actions — matrix strategy with conditional steps
# Pattern verified against existing ci.yml structure

test:
  strategy:
    fail-fast: false
    matrix:
      os: [ubuntu-latest, macos-latest]
      python: ["3.12", "3.13"]
      simulator: [iverilog, verilator]
  runs-on: ${{ matrix.os }}
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v4
    - name: Install Python
      run: uv python install ${{ matrix.python }}
    - name: Install dependencies
      run: uv sync --dev

    # ── Simulator installation (conditional) ──
    - name: Install iverilog (Linux)
      if: matrix.simulator == 'iverilog' && runner.os == 'Linux'
      run: sudo apt-get update && sudo apt-get install -y iverilog

    - name: Install iverilog (macOS)
      if: matrix.simulator == 'iverilog' && runner.os == 'macOS'
      run: brew install icarus-verilog

    - name: Install Verilator (Linux)
      if: matrix.simulator == 'verilator' && runner.os == 'Linux'
      run: sudo apt-get update && sudo apt-get install -y verilator

    - name: Install Verilator (macOS)
      if: matrix.simulator == 'verilator' && runner.os == 'macOS'
      run: brew install verilator

    # ── slang (all jobs) ──
    - name: Install slang (Linux)
      if: runner.os == 'Linux'
      run: |
        SLANG_VERSION="v7.0"
        wget -q "https://github.com/MikePopoloski/slang/releases/download/${SLANG_VERSION}/slang-linux.tar.gz"
        tar xzf slang-linux.tar.gz
        sudo mv slang /usr/local/bin/slang
        slang --version

    - name: Install slang (macOS)
      if: runner.os == 'macOS'
      run: |
        SLANG_VERSION="v7.0"
        wget -q "https://github.com/MikePopoloski/slang/releases/download/${SLANG_VERSION}/slang-macos.tar.gz"
        tar xzf slang-macos.tar.gz
        sudo mv slang /usr/local/bin/slang
        slang --version

    # ── Test execution ──
    - name: Run tests
      run: uv run pytest tests/ -m simulation --simulator=${{ matrix.simulator }} -v --timeout=120
      env:
        SLANG_PATH: /usr/local/bin/slang
```

**Key details:**
- `fail-fast: false` is already set — one simulator failure doesn't cancel the other
- Conditional install: `if: matrix.simulator == 'verilator'` — only installs the simulator needed for that job
- slang is installed on ALL jobs (needed for parsing, independent of simulation)
- The `lint` job is unchanged (ruff + mypy don't need simulators)
- Verilator jobs only run `-m simulation` tests; non-simulation tests are skipped via conftest
- **No exclude rules needed** — all 8 combinations are valid (both simulators available on both OSes)

[VERIFIED: docs.github.com/en/actions — matrix strategy supports conditional steps with `if: matrix.<key> == '<value>'`]

### Pattern 4: pytest --simulator Flag

**What:** A `pytest_addoption` hook in the root `tests/conftest.py` adds a `--simulator` CLI flag. The simulation `conftest.py` uses it to select the backend and skip if the requested simulator is unavailable.

**When to use:** All test invocations that run simulation tests.

**Implementation in `tests/conftest.py`:**
```python
# Source: docs.pytest.org/en/stable/example/simple.html — pytest_addoption pattern

def pytest_addoption(parser):
    parser.addoption(
        "--simulator",
        action="store",
        default="iverilog",
        choices=("iverilog", "verilator"),
        help="Simulator backend: iverilog or verilator",
    )
```

**Implementation in `tests/simulation/conftest.py`:**
```python
import os
import shutil
import pytest


def _get_simulator(request) -> str:
    """Resolve simulator from CLI flag or env var."""
    sim = request.config.getoption("--simulator", default="iverilog")
    # Env var overrides CLI default (allows CI to set without modifying pytest args)
    env_sim = os.environ.get("SVA2RTL_SIMULATOR")
    if env_sim:
        sim = env_sim
    return sim


@pytest.fixture(autouse=True)
def check_simulator(request) -> None:
    """Skip simulation tests when the requested simulator is not installed."""
    sim = _get_simulator(request)
    if sim == "iverilog" and shutil.which("iverilog") is None:
        pytest.skip("iverilog not found — install Icarus Verilog to run simulation tests")
    elif sim == "verilator" and shutil.which("verilator") is None:
        pytest.skip("verilator not found — install Verilator to run simulation tests")
```

**Usage:**
```bash
# iverilog (default)
pytest tests/ -m simulation

# verilator
pytest tests/ -m simulation --simulator=verilator

# via env var (CI-friendly)
SVA2RTL_SIMULATOR=verilator pytest tests/ -m simulation
```

[VERIFIED: docs.pytest.org/en/stable/example/simple.html]

### Anti-Patterns to Avoid

- **Anti-pattern: Using `--binary` with custom wrapper.** `--binary` includes `--main` which generates a conflicting `main()`. Use `--exe --build --timing` instead. [VERIFIED: verilator.org/guide/latest/exe_verilator.html]
- **Anti-pattern: Running all 736 tests on Verilator axis.** Only `-m simulation` tests need the simulator. Running unit tests on the Verilator axis wastes CI minutes. The `check_simulator` fixture only applies to `tests/simulation/` directory.
- **Anti-pattern: Separate CI job for Verilator.** Adding a separate `test-verilator` job duplicates the matrix configuration. A single `test` job with a `simulator` axis is simpler and ensures consistent step structure.
- **Anti-pattern: Hardcoding `iverilog` in test bodies.** Tests calling `run_simulation()` directly should pass the simulator parameter rather than assuming iverilog. The simulator value should flow from the `--simulator` flag through a fixture.
- **Anti-pattern: Duplicating stimulus in C++ wrapper.** The stimulus dicts should be embedded at template-render time (Python → Jinja2 → C++), not maintained in two places.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Verilator C++ model instantiation | Manual VerilatedModel setup | `verilator --exe --build` | Verilator auto-generates the Vtop class, Makefile, and build orchestration |
| Clock toggling in C++ | Timing-accurate delay loops | `contextp->timeInc(1)` + `top->clk = !top->clk` + `top->eval()` | Verilator's time API handles the event queue correctly; manual timing breaks coroutine support |
| Output format parsing | Custom regex per simulator | Unified `_parse_output()` | Both backends emit the same `"0 1 0\n"` format via `printf`/`$display` |
| pytest CLI flag | argparse or env-var-only | `pytest_addoption` + `request.config.getoption()` | Standard pytest pattern; integrates with `--help`, `pytest.ini`, and CI |
| CI conditional installs | Separate job definitions per simulator | Single `test` job with `if: matrix.simulator == 'X'` | DRY — one job definition, 8 matrix instances |

**Key insight:** Verilator's C++ compilation is the most complex part. Don't try to invoke `g++` manually — let `verilator --build` handle the Makefile generation and compilation. The command `verilator --exe --build --timing -Wall --top-module dut dut.sv wrapper.cpp -o sim` handles: SystemVerilog → C++ translation, C++ compilation, linking with Verilator runtime, and producing a native `sim` binary — all in one step.

## Runtime State Inventory

> Omitted — this is not a rename/refactor/migration phase. No stored data, live service config, OS-registered state, secrets, or build artifacts need migration. The phase adds new capabilities (Verilator support, CI axis) without renaming or removing existing state.

## Common Pitfalls

### Pitfall 1: Verilator `--binary` Produces Conflicting `main()`

**What goes wrong:** Using `verilator --binary wrapper.cpp dut.sv` causes a linker error because `--binary` includes `--main` which generates `Vdut__main.cpp` with its own `main()`, conflicting with the `main()` in `wrapper.cpp`.

**Why it happens:** `--binary` is an alias for `--main --exe --build --timing`. The `--main` flag always generates a generic main file.

**How to avoid:** Use `verilator --exe --build --timing -Wall --top-module dut dut.sv wrapper.cpp -o sim` instead. This provides `--exe` (create executable) + `--build` (compile) + `--timing` (timing support) without the auto-generated `main()`.

**Warning signs:** Linker error: `duplicate symbol '_main'` or `multiple definition of 'main'`.

[VERIFIED: verilator.org/guide/latest/exe_verilator.html]

### Pitfall 2: `--timing` Overhead for Non-Timing Designs

**What goes wrong:** Including `--timing` when no timing constructs exist in the design adds coroutine overhead to the generated C++ without benefit.

**Why it happens:** The locked decision specifies `--binary --timing`, but the DUT templates contain no `#delay` constructs. The clock is driven from C++, not SV.

**How to avoid:** The overhead is minimal for small designs (~65 tests with small modules). The CONTEXT.md decision to include `--timing` is already locked. Keep it — it's safer for future templates that might use timing constructs, and the cost is negligible. **However**, if compilation time becomes an issue (unlikely for our small designs), `--timing` can be removed since `--exe --build` alone is sufficient.

**Warning signs:** Verilator compilation taking >30s per module (should be <5s for our small designs).

[VERIFIED: deepwiki.com/verilator/verilator/5.2-timing-controls-and-coroutines]

### Pitfall 3: Clock Edge Semantics Mismatch

**What goes wrong:** The SV testbench drives inputs at negedge and captures at posedge. The C++ wrapper must replicate this exactly, or outputs will be off by one cycle.

**Why it happens:** The SV testbench uses `@(negedge clk)` for driving and `@(posedge clk)` for capturing. In Verilator C++, there are no edge events — we must manually sequence the eval() calls.

**How to avoid:** Follow the exact sequence:
1. Set inputs while clk=0 → `top->eval()` (this is the "negedge" state)
2. `contextp->timeInc(1); top->clk = 1;` → `top->eval()` (this is the "posedge" — capture here)
3. Read outputs after step 2's eval()

**Warning signs:** Output values shifted by one cycle compared to iverilog.

### Pitfall 4: Verilator Signal Width Mismatch Warnings

**What goes wrong:** Verilator is stricter than iverilog about signal width matching. Assigning a 32-bit C++ int to a 1-bit Verilator port may produce warnings.

**Why it happens:** Verilator's `-Wall` enables width-mismatch warnings. Iverilog is more lenient.

**How to avoid:** Use `top->signal = 1` (int literal) or `top->signal = 0` — these work for 1-bit `CData` ports. For wider signals, cast explicitly. If width warnings appear, they indicate real issues in the generated RTL that should be fixed.

**Warning signs:** Verilator compilation warnings about width truncation.

### Pitfall 5: CI Timeout with Verilator Compilation

**What goes wrong:** The existing 120s timeout may be insufficient because Verilator compilation (SV → C++ → g++ → binary) takes longer than iverilog compilation (SV → vvp).

**Why it happens:** Verilator must generate C++ code, then invoke g++ to compile it. For small designs (~200 lines of SV), this typically takes 3-10 seconds. For 65 tests running sequentially, total Verilator overhead is ~3-10 minutes of CI time. However, a single test with a 120s timeout should be more than enough — each individual test compiles one small module.

**How to avoid:** The 120s timeout applies per-test, not globally. Each test compiles one module (~50-200 lines of SV), which Verilator handles in <10s. No timeout increase needed. However, if CI jobs approach the 120s per-test limit, increase to 180s.

**Warning signs:** Individual tests timing out at 120s.

[ASSUMED] — based on typical Verilator compilation times for small designs; actual times will be verified during implementation.

### Pitfall 6: macOS Verilator brew Installation Failures

**What goes wrong:** `brew install verilator` may fail on macOS runners due to dependency conflicts or Xcode version issues.

**Why it happens:** Verilator has many build dependencies (gcc, make, perl, etc.). On GitHub Actions macOS runners, brew installations can be slow or fail intermittently.

**How to avoid:** Keep `fail-fast: false` (already set). If macOS + Verilator proves unreliable, consider adding `continue-on-error: true` specifically for the macOS+Verilator combination (though this conflicts with the "no soft-fail" decision — only use as a temporary workaround while debugging).

**Warning signs:** brew install failures on macOS CI.

[ASSUMED]

## Code Examples

Verified patterns from official sources:

### Verilator Compilation + Execution (Single Module)

```python
# Source: Verilator 5.x official docs + existing tb_generator.py pattern
# Verified: verilator.org/guide/latest/connecting.html, verilator.org/guide/latest/exe_verilator.html

def _run_simulation_verilator(
    module_name: str,
    sv_sources: list[str],
    tb_code: str,  # ignored for Verilator — we use C++ wrapper
    work_dir: Path,
    has_overflow_flag: bool,
    stimulus: list[dict],  # NEW: needed for wrapper generation
    extra_inputs: list[str],  # NEW: needed for wrapper port list
    clock_signal: str,  # NEW: needed for wrapper
) -> list[dict[str, bool]]:
    """Compile and run with Verilator via C++ wrapper."""
    verilator = shutil.which("verilator")
    if verilator is None:
        raise RuntimeError("verilator not found on PATH")

    # Write DUT source
    dut_path = work_dir / "dut.sv"
    dut_path.write_text("\n\n".join(sv_sources), encoding="utf-8")

    # Generate C++ wrapper
    wrapper_code = _generate_verilator_wrapper(
        module_name=module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=has_overflow_flag,
    )
    wrapper_path = work_dir / "wrapper.cpp"
    wrapper_path.write_text(wrapper_code, encoding="utf-8")

    # Compile with Verilator
    sim_path = work_dir / "Vdut"
    compile_result = subprocess.run(
        [
            verilator,
            "--exe", "--build", "--timing",
            "-Wall",
            "--top-module", module_name,
            "-o", str(sim_path),
            str(dut_path),
            str(wrapper_path),
        ],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    if compile_result.returncode != 0:
        raise RuntimeError(
            f"Verilator compilation failed for {module_name}:\n"
            f"STDOUT:\n{compile_result.stdout}\n"
            f"STDERR:\n{compile_result.stderr}"
        )

    # Run simulation
    sim_result = subprocess.run(
        [str(sim_path)],
        capture_output=True,
        text=True,
    )
    if sim_result.returncode != 0:
        raise RuntimeError(
            f"Verilator simulation failed for {module_name}:\n"
            f"STDOUT:\n{sim_result.stdout}\n"
            f"STDERR:\n{sim_result.stderr}"
        )

    return _parse_output(sim_result.stdout, has_overflow_flag=has_overflow_flag)
```

### C++ Wrapper Template (wrapper.cpp.j2)

```cpp
// Source: Verilator 5.x connecting.html pattern + existing tb_generator.py stimulus logic
// Template variables: module_name, clock_signal, extra_inputs, stimulus, has_overflow_flag

#include "V{{ module_name }}.h"
#include "verilated.h"
#include <cstdio>

int main(int argc, char** argv) {
    VerilatedContext* contextp = new VerilatedContext;
    contextp->commandArgs(argc, argv);
    V{{ module_name }}* top = new V{{ module_name }}{contextp};

    // Init all inputs to 0
    top->{{ clock_signal }} = 0;
    top->rst_n = 0;
    top->start = 0;
    top->disable_i = 0;
    {% for sig in extra_inputs if sig != 'start' %}
    top->{{ sig }} = 0;
    {% endfor %}

    // Reset: 2 full clock cycles with rst_n=0
    for (int _r = 0; _r < 2; _r++) {
        contextp->timeInc(1); top->{{ clock_signal }} = 1; top->eval();
        contextp->timeInc(1); top->{{ clock_signal }} = 0; top->eval();
    }

    // Release reset (set before posedge)
    top->rst_n = 1;

    // Stimulus cycles
    {% for stim in stimulus %}
    // ── cycle {{ loop.index0 }} ──
    // Drive inputs at negedge (clk=0)
    {% for sig in extra_inputs %}
    top->{{ sig }} = {{ 1 if stim.get(sig, False) else 0 }};
    {% endfor %}
    top->disable_i = {{ 1 if stim.get('disable_i', False) else 0 }};
    top->eval();
    // Posedge: toggle clock, evaluate, capture
    contextp->timeInc(1); top->{{ clock_signal }} = 1; top->eval();
    {% if has_overflow_flag %}
    printf("%c %c %c %c\n",
        top->active ? '1' : '0',
        top->pass   ? '1' : '0',
        top->fail   ? '1' : '0',
        top->overflow_flag ? '1' : '0');
    {% else %}
    printf("%c %c %c\n",
        top->active ? '1' : '0',
        top->pass   ? '1' : '0',
        top->fail   ? '1' : '0');
    {% endif %}
    // Negedge: toggle clock back
    contextp->timeInc(1); top->{{ clock_signal }} = 0; top->eval();
    {% endfor %}

    top->final();
    delete top;
    delete contextp;
    return 0;
}
```

**Note on port name conflicts:** The Verilator model exposes ports with their exact SV names. The SV DUT uses `pass` and `fail` as port names, but these are SV keywords. In the generated Verilator header, they become `top->pass` and `top->fail`. In C++, `pass` is not a keyword, so `top->pass` and `top->fail` work directly. However, the testbench SV uses `pass_out`/`fail_out` wires — the DUT itself uses `pass`/`fail` ports. **Verify**: check the emitted DUT port names in `emit_all()` output to confirm whether they're `pass`/`fail` or `pass_out`/`fail_out`. If they're `pass`/`fail`, use `top->pass`/`top->fail` in the wrapper. [ASSUMED — needs verification against actual emitted RTL]

### pytest --simulator Fixture for Test Bodies

```python
# Source: docs.pytest.org/en/stable/example/simple.html
# In tests/simulation/conftest.py or tests/conftest.py

import pytest

@pytest.fixture(scope="session")
def simulator(request) -> str:
    """Return the selected simulator backend."""
    sim = request.config.getoption("--simulator", default="iverilog")
    env_sim = os.environ.get("SVA2RTL_SIMULATOR")
    return env_sim if env_sim else sim
```

**Usage in test files:**
```python
def test_rtl_rose_vs_oracle_transition(tmp_path: Path, simulator: str) -> None:
    ...
    rtl_out = run_simulation(
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=False,
        simulator=simulator,  # NEW
    )
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Iverilog-only simulation | Dual oracle (iverilog + Verilator) | Phase 2 | Every simulation test now validates against two independent simulators, catching codegen bugs that iverilog might silently accept |
| `verilator --binary` for quick sim | `verilator --exe --build --timing` with custom wrapper | Phase 2 (research finding) | `--binary` includes `--main` which conflicts with custom wrapper; using `--exe` instead gives full control |
| 2×2 CI matrix (4 jobs) | 2×2×2 CI matrix (8 jobs) | Phase 2 | Doubles CI jobs but catches platform+simulator interactions |
| Verilator test skipped in CI | Verilator test runs on Verilator axis | Phase 2 | `test_verilator_lint_clean` upgraded from skip to active gate |

**Deprecated/outdated:**
- `verilator --binary` with custom wrapper: use `--exe --build --timing` instead
- Hardcoded `run_simulation()` assuming iverilog: use parameterized `simulator=` argument
- Single-simulator CI: dual-simulator matrix becomes the standard

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DUT port names are `pass`/`fail` (not `pass_out`/`fail_out` like the SV testbench wires) | Code Examples — C++ Wrapper Template | C++ wrapper won't compile — need to check `emit_all()` output to confirm actual port names |
| A2 | Verilator compilation for small designs (~200 lines SV) takes <10 seconds | Common Pitfalls — Pitfall 5 | CI timeout at 120s per test — may need to increase to 180s |
| A3 | `brew install verilator` works reliably on GitHub Actions macOS runners | Common Pitfalls — Pitfall 6 | macOS+Verilator CI job may fail intermittently — may need retry logic or `continue-on-error` temporarily |
| A4 | `printf("%c %c %c\n", top->active ? '1' : '0', ...)` produces output identical to `$display("%b %b %b", ...)` format parsed by `_parse_output()` | Code Examples — C++ Wrapper | Output parsing mismatch — `_parse_output()` may need adjustment for trailing whitespace or newline differences |
| A5 | The 78 tests collected by `pytest -m simulation` are the correct scope; no simulation tests exist outside `tests/simulation/` | Architecture Patterns | If non-simulation tests are marked `@pytest.mark.simulation`, they'll incorrectly try to use Verilator |
| A6 | Verilator `--timing` is included per locked decision; overhead is negligible for our small designs | Common Pitfalls — Pitfall 2 | If compilation time increases significantly, we may remove `--timing` since DUT has no timing constructs |
| A7 | `verilator --exe --build` requires `make` and a C++ compiler (g++ or clang++) on PATH; both are standard on GitHub Actions runners | Standard Stack | CI job fails at Verilator compile step — but GitHub Actions ubuntu-latest and macos-latest runners include both by default |

## Open Questions

1. **DUT port names: `pass`/`fail` or `pass_out`/`fail_out`?**
   - What we know: The SV testbench uses `pass_out`/`fail_out` as wire names to avoid SV keyword conflicts, but the DUT instantiation uses `.pass(pass_out)` — so the DUT port is named `pass`
   - What's unclear: Whether Verilator preserves the exact port name `pass` (which is a C++ keyword in some contexts) or mangles it
   - Recommendation: Check the Verilator-generated `V{module}.h` header during implementation. If `pass` is mangled, use the mangled name in the wrapper

2. **Verilator compilation artifact location**
   - What we know: `verilator --exe --build` creates an `obj_dir/` subdirectory with generated C++ files and Makefile
   - What's unclear: Whether the `-o` flag places the binary in `work_dir/` or inside `obj_dir/`
   - Recommendation: Test with a dry-run compilation. Use `-o` with an absolute path to `work_dir / "sim"` for predictable binary location

3. **macOS Verilator brew reliability on CI**
   - What we know: `brew install verilator` can be slow (compiles from source or downloads large bottles)
   - What's unclear: Whether it consistently succeeds on GitHub Actions `macos-latest` within reasonable time
   - Recommendation: Test on first CI run. If failures occur, consider `brew install --force --verbose verilator` for better error messages

4. **120s timeout per-test adequacy for Verilator**
   - What we know: Each test compiles one small module; iverilog takes <1s per test; Verilator adds C++ compilation overhead
   - What's unclear: Whether 65 Verilator compilations (one per test) will push the total CI job time beyond GitHub Actions limits (6 hours for public repos)
   - Recommendation: Monitor first CI run. If total job time exceeds 30 minutes, consider compiling once and reusing the binary across tests (though this adds complexity)

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| verilator (system) | Verilator simulation tests | ✗ (not installed locally) | — | Install via `brew install verilator` |
| iverilog (system) | iverilog simulation tests | ✗ (not verified locally) | — | Already handled by existing conftest skip |
| g++ / clang++ | Verilator C++ compilation | ✓ (system compiler) | system default | — |
| make | Verilator build orchestration | ✓ (system) | system default | — |
| pytest 9.0.3 | Test execution | ✓ (project dependency) | 9.0.3 | — |
| pytest-timeout | Test timeout guard | ✓ (project dependency) | existing | — |
| slang v7.0 | SVA parsing | ✓ (CI only) | v7.0 | — |

**Missing dependencies with no fallback:**
- **verilator (local development)**: Not installed on the local machine. Tests requiring Verilator will skip via conftest. Install with `brew install verilator` for local Verilator testing.

**Missing dependencies with fallback:**
- None — all CI dependencies are installed conditionally in the workflow.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -m simulation --simulator=iverilog -v --timeout=120` |
| Full suite command | `uv run pytest tests/ -v --timeout=120` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VALIDATE-02 | Verilator produces same 65 pass/fail outcomes as iverilog | integration | `uv run pytest tests/ -m simulation --simulator=verilator -v --timeout=120` | ❌ Wave 0 — `--simulator=verilator` not yet supported |
| VALIDATE-03 | CI matrix expands to 8 jobs, all green | CI config | Push to PR triggers CI; verify 8 test jobs pass | ❌ Wave 0 — ci.yml not yet updated |
| VALIDATE-04 | Dual-oracle documented in README and CLAUDE.md | documentation | Manual review of README.md and CLAUDE.md | ❌ Wave 0 — docs not yet updated |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -m simulation --simulator=iverilog -v --timeout=120` (fast, iverilog-only)
- **Per wave merge:** `uv run pytest tests/ -m simulation --simulator=verilator -v --timeout=120` (Verilator parity check)
- **Phase gate:** Full 8-job CI matrix green + both simulators pass locally

### Wave 0 Gaps
- [ ] `tests/simulation/conftest.py` — needs `--simulator` flag support and dual-simulator skip logic
- [ ] `tests/simulation/wrapper.cpp.j2` — new Jinja2 template for Verilator C++ wrapper
- [ ] `tests/simulation/tb_generator.py` — needs `_run_simulation_verilator()` and `_generate_verilator_wrapper()`
- [ ] `.github/workflows/ci.yml` — needs `simulator` matrix axis and conditional install steps
- [ ] `tests/conftest.py` — needs `pytest_addoption` for `--simulator` flag
- [ ] `README.md` — needs Verilator install instructions and `--simulator` flag documentation
- [ ] `CLAUDE.md` — needs dual-oracle contract update

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | N/A — CLI tool, no authentication |
| V3 Session Management | no | N/A — no sessions |
| V4 Access Control | no | N/A — no multi-user access |
| V5 Input Validation | yes | Existing: click CLI validates all flags; pytest validates `--simulator` choices |
| V6 Cryptography | no | N/A — no crypto operations |

### Known Threat Patterns for pytest/CI/Verilator Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious Verilator wrapper code injection | Tampering | Wrapper is generated from Jinja2 template with sanitized inputs; stimulus data is already validated by Python test harness |
| CI secret leakage in Verilator output | Information Disclosure | Verilator simulation stdout is captured by subprocess and parsed; no secrets should appear in simulation output |
| Dependency confusion via `brew install verilator` | Spoofing | `brew install verilator` installs from official Homebrew core formula; risk is low for well-known packages |
| Subprocess command injection via module names | RCE | Module names come from `CheckerNode.module_name` which is internally generated; not user-controlled |

## Sources

### Primary (HIGH confidence)
- [Verilator Devel 5.049 documentation — verilator Arguments](https://verilator.org/guide/latest/exe_verilator.html) — `--binary`, `--exe`, `--main`, `--timing`, `--build` flag descriptions and interactions
- [Verilator Devel 5.049 documentation — Connecting to Verilated Models](https://verilator.org/guide/latest/connecting.html) — Signal access via `top->signal_name`, `eval()`, multi-design patterns
- [Verilator Devel 5.049 documentation — Example C++ Execution](https://verilator.org/guide/latest/example_cc.html) — Minimal C++ testbench skeleton
- [pytest documentation — Basic patterns and examples](https://docs.pytest.org/en/stable/example/simple.html) — `pytest_addoption` hook pattern
- [GitHub Actions documentation — Running variations of jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/run-job-variations) — Matrix strategy with conditional steps

### Secondary (MEDIUM confidence)
- [DeepWiki — Verilator Timing Runtime](https://deepwiki.com/verilator/verilator/7.5-timing-runtime) — How `--timing` flag enables coroutine-based delay/event handling
- [DeepWiki — Verilator Timing Controls and Coroutines](https://deepwiki.com/verilator/verilator/5.2-timing-controls-and-coroutines) — Verilator 5.x coroutine implementation details
- [sistenix.com — Verilator C++ and SystemVerilog Testbench](https://sistenix.com/verilator_tb.html) — Complete C++ testbench pattern with clock toggling and signal driving
- [EastonDev — GitHub Actions Matrix 矩阵构建](https://eastondev.com/blog/zh/posts/dev/20260408-github-actions-matrix/) — Matrix strategy with conditional steps and include/exclude

### Tertiary (LOW confidence)
- [Verilator GitHub issue #4289](https://github.com/verilator/verilator/issues/4289) — Discussion on compilation speed (clang vs gcc)
- Various blog posts on Verilator入门 (CSDN, 知乎, 博客园) — supplementary examples, not authoritative

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Verilator API is well-documented in official docs; pytest and GitHub Actions patterns are standard
- Architecture: HIGH — Pattern verified against official Verilator docs for `--exe` vs `--binary`, signal access API, and C++ wrapper structure
- Pitfalls: MEDIUM — Pitfalls 1-4 are verified against official docs; Pitfalls 5-6 are assumed based on typical behavior (marked [ASSUMED])

**Research date:** 2026-06-05
**Valid until:** 2026-07-05 (30 days — Verilator API is stable; GitHub Actions and pytest patterns change slowly)
