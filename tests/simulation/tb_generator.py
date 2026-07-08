"""Testbench generator and simulation runner for sva2rtl simulation tests.

This module provides utilities to:
1. Generate a SystemVerilog testbench for a sva2rtl-compiled checker module.
2. Compile and run the testbench with Icarus Verilog (iverilog + vvp) or
   Verilator (native binary).
3. Parse the simulation output into per-cycle output dicts.

The generated testbench drives inputs at negedge (to satisfy setup time) and
captures outputs at posedge using ``$fdisplay`` (iverilog) or ``printf``
(Verilator C++ wrapper).  This matches the cycle-exact semantics of the
behavioral oracle in ``sva2rtl.behavioral_oracle``.

Typical flow::

    checker  = compose(node, clock, label, text)
    modules  = emit_all(checker)
    inputs   = extra_inputs_from_checker(checker)

    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=checker.params["clock_signal"],
        extra_inputs=inputs,
        stimulus=stim_list,
        has_overflow_flag=(checker.template_name in ("overlap_bitvec", "nonoverlap")),
    )

    results = run_simulation(
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=...,
        simulator="iverilog",   # or "verilator"
        stimulus=stim_list,      # required for Verilator
        extra_inputs=inputs,     # required for Verilator
    )
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from sva2rtl.ir import CheckerNode

# ── Templates with overflow_flag output port ──────────────────────────────────

TEMPLATES_WITH_OVERFLOW = frozenset({"overlap_bitvec", "nonoverlap"})


# ── Public helpers ────────────────────────────────────────────────────────────


def extra_inputs_from_checker(checker: CheckerNode) -> list[str]:
    """Return the list of extra (non-clock, non-rst_n, non-disable_i) input names.

    Matches the port order used in all sva2rtl templates:
    ``start`` is always first, followed by observed_signals in declaration order.
    For templates that do not have a ``start`` port (none currently), only
    observed signals are returned.

    Parameters
    ----------
    checker:
        The top-level ``CheckerNode`` as returned by ``compose()``.

    Returns
    -------
    list[str]
        Signal names in port order: ``["start", sig1, sig2, ...]``.
    """
    return ["start"] + [p for p, _ in checker.observed_signals]


def generate_testbench(
    module_name: str,
    clock_signal: str,
    extra_inputs: list[str],
    stimulus: list[dict[str, Any]],
    *,
    has_overflow_flag: bool = False,
) -> str:
    """Generate a self-contained SystemVerilog testbench string.

    The testbench:
    - Drives inputs at negedge (half-cycle before the sampling posedge).
    - Captures outputs at posedge using ``$fdisplay``.
    - Runs 2 posedge reset cycles, then drives ``len(stimulus)`` active cycles.
    - Uses wire ``pass_out`` / ``fail_out`` to avoid the SV keyword ``pass``.

    Parameters
    ----------
    module_name:
        The DUT module name (must match the emitted SV).
    clock_signal:
        Name of the clock input port on the DUT.
    extra_inputs:
        All non-clock, non-rst_n, non-disable_i inputs in port order.
        Typically ``extra_inputs_from_checker(checker)``.
    stimulus:
        Per-cycle input dicts.  Keys are a subset of ``extra_inputs`` plus
        optional ``"disable_i"``.  Missing keys default to 0.
    has_overflow_flag:
        When ``True``, the DUT exposes an ``overflow_flag`` output and the
        testbench captures it as a fourth column.

    Returns
    -------
    str
        Complete SV testbench source text.
    """
    lines: list[str] = []

    def _w(s: str = "") -> None:
        lines.append(s)

    _w("`timescale 1ns/1ps")
    _w("module tb;")
    _w()

    # Clock
    _w(f"    reg {clock_signal};")
    _w(f"    initial {clock_signal} = 0;")
    _w(f"    always #5 {clock_signal} = ~{clock_signal};")
    _w()

    # Control inputs
    _w("    reg rst_n;")
    _w("    reg disable_i;")

    # Extra inputs
    for sig in extra_inputs:
        _w(f"    reg {sig};")
    _w()

    # Output wires — rename pass/fail to avoid SV keyword clash
    _w("    wire active;")
    _w("    wire pass_out;")
    _w("    wire fail_out;")
    _w("    wire attempt_fired;")
    _w("    wire disabled_o;")
    if has_overflow_flag:
        _w("    wire overflow_flag;")
    _w()

    # DUT instantiation
    _w(f"    {module_name} dut (")
    _w(f"        .{clock_signal}({clock_signal}),")
    _w("        .rst_n    (rst_n),")
    for sig in extra_inputs:
        _w(f"        .{sig}({sig}),")
    _w("        .disable_i     (disable_i),")
    _w("        .active        (active),")
    _w("        .pass          (pass_out),")
    _w("        .fail          (fail_out),")
    _w("        .attempt_fired (attempt_fired),")
    if has_overflow_flag:
        _w("        .overflow_flag (overflow_flag),")
    _w("        .disabled_o    (disabled_o)")
    _w("    );")
    _w()

    # Initial block
    _w("    initial begin")
    # Reset sequence: assert rst_n=0 for 2 posedge cycles
    _w("        rst_n    = 0;")
    _w("        disable_i = 0;")
    for sig in extra_inputs:
        _w(f"        {sig} = 0;")
    _w(f"        repeat(2) @(posedge {clock_signal});")
    _w()
    # Release reset at negedge (so it is seen by the NEXT posedge)
    _w(f"        @(negedge {clock_signal}); rst_n = 1;")
    _w()

    # Drive stimulus and capture outputs
    for i, stim in enumerate(stimulus):
        # Drive inputs at negedge
        _w(f"        // ── cycle {i} ──────────────────────────────────────────────")
        for sig in extra_inputs:
            val = 1 if stim.get(sig, False) else 0
            _w(f"        {sig} = {val};")
        dis_val = 1 if stim.get("disable_i", False) else 0
        _w(f"        disable_i = {dis_val};")
        # Capture at posedge
        _w(f"        @(posedge {clock_signal});")
        if has_overflow_flag:
            _w(
                "        $display(\"%b %b %b %b\","
                " active, pass_out, fail_out, overflow_flag);"
            )
        else:
            _w(
                "        $display(\"%b %b %b\","
                " active, pass_out, fail_out);"
            )
        if i < len(stimulus) - 1:
            # Move to negedge for next stimulus (skip for last cycle)
            _w(f"        @(negedge {clock_signal});")
    _w()
    _w("        $finish;")
    _w("    end")
    _w()
    _w("endmodule")

    return "\n".join(lines)


def run_simulation(
    module_name: str,
    sv_sources: list[str],
    tb_code: str,
    *,
    work_dir: Path,
    has_overflow_flag: bool = False,
    simulator: str = "iverilog",
    stimulus: list[dict[str, Any]] | None = None,
    extra_inputs: list[str] | None = None,
    clock_signal: str = "clk",
) -> list[dict[str, bool]]:
    """Compile and run a sva2rtl testbench with the selected simulator.

    Parameters
    ----------
    module_name:
        DUT module name (used only for diagnostic messages).
    sv_sources:
        List of SV source strings from ``emit_all(checker).values()``.
        Must include the top-level module and all its children.
    tb_code:
        Testbench SV source string from ``generate_testbench()``.
        Used by the iverilog backend; ignored by the Verilator backend.
    work_dir:
        Temporary directory for compilation artefacts.
    has_overflow_flag:
        Passed to ``_parse_output`` to determine column count.
    simulator:
        Backend selector: ``"iverilog"`` (default) or ``"verilator"``.
    stimulus:
        Per-cycle input dicts (required when ``simulator="verilator"``).
    extra_inputs:
        Non-clock/non-rst_n/non-disable_i port names in order
        (required when ``simulator="verilator"``).
    clock_signal:
        Name of the clock port on the DUT (default ``"clk"``).

    Returns
    -------
    list[dict[str, bool]]
        One dict per stimulus cycle.  Keys: ``"active"``, ``"pass"``,
        ``"fail"`` (and ``"overflow"`` when ``has_overflow_flag`` is True).

    Raises
    ------
    RuntimeError
        When the requested simulator is not found, compilation fails, or
        simulation fails.
    ValueError
        When ``simulator`` is unknown or required parameters are missing.
    """
    env_simulator = os.environ.get("SVA2RTL_SIMULATOR")
    if simulator == "iverilog" and env_simulator in {"iverilog", "verilator"}:
        simulator = env_simulator

    if simulator == "iverilog":
        return _run_simulation_iverilog(
            module_name, sv_sources, tb_code, work_dir=work_dir,
            has_overflow_flag=has_overflow_flag,
        )
    elif simulator == "verilator":
        if stimulus is None:
            raise ValueError(
                "stimulus is required when simulator='verilator'"
            )
        if extra_inputs is None:
            raise ValueError(
                "extra_inputs is required when simulator='verilator'"
            )
        return _run_simulation_verilator(
            module_name, sv_sources, tb_code, work_dir=work_dir,
            has_overflow_flag=has_overflow_flag,
            stimulus=stimulus, extra_inputs=extra_inputs,
            clock_signal=clock_signal,
        )
    else:
        raise ValueError(f"Unknown simulator: {simulator}")


def _run_simulation_iverilog(
    module_name: str,
    sv_sources: list[str],
    tb_code: str,
    *,
    work_dir: Path,
    has_overflow_flag: bool = False,
) -> list[dict[str, bool]]:
    """Compile and run a sva2rtl testbench with Icarus Verilog."""
    iverilog = shutil.which("iverilog")
    if iverilog is None:
        raise RuntimeError(
            "iverilog not found on PATH — install Icarus Verilog to run simulation tests"
        )

    # Write all DUT source files
    dut_path = work_dir / "dut.sv"
    dut_path.write_text("\n\n".join(sv_sources), encoding="utf-8")

    # Write testbench
    tb_path = work_dir / "tb.sv"
    tb_path.write_text(tb_code, encoding="utf-8")

    # Compile
    vvp_path = work_dir / "sim.vvp"
    compile_result = subprocess.run(
        [iverilog, "-g2012", "-o", str(vvp_path), str(tb_path), str(dut_path)],
        capture_output=True,
        text=True,
    )
    if compile_result.returncode != 0:
        raise RuntimeError(
            f"iverilog compilation failed for {module_name}:\n"
            f"STDOUT:\n{compile_result.stdout}\n"
            f"STDERR:\n{compile_result.stderr}"
        )

    # Run simulation
    vvp = shutil.which("vvp")
    if vvp is None:
        vvp = str(Path(iverilog).parent / "vvp")

    sim_result = subprocess.run(
        [vvp, str(vvp_path)],
        capture_output=True,
        text=True,
    )
    if sim_result.returncode != 0:
        raise RuntimeError(
            f"vvp simulation failed for {module_name}:\n"
            f"STDOUT:\n{sim_result.stdout}\n"
            f"STDERR:\n{sim_result.stderr}"
        )

    return _parse_output(sim_result.stdout, has_overflow_flag=has_overflow_flag)


def _generate_verilator_wrapper(
    module_name: str,
    clock_signal: str,
    extra_inputs: list[str],
    stimulus: list[dict[str, Any]],
    has_overflow_flag: bool,
) -> str:
    """Render the Verilator C++ wrapper for a given module and stimulus.

    Uses the Jinja2 template at ``wrapper.cpp.j2`` in the same directory.
    """
    template_dir = Path(__file__).parent
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("wrapper.cpp.j2")
    return template.render(
        module_name=module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=has_overflow_flag,
    )


def _run_simulation_verilator(
    module_name: str,
    sv_sources: list[str],
    tb_code: str,  # ignored — Verilator uses C++ wrapper, not SV testbench
    *,
    work_dir: Path,
    has_overflow_flag: bool,
    stimulus: list[dict[str, Any]],
    extra_inputs: list[str],
    clock_signal: str,
) -> list[dict[str, bool]]:
    """Compile and run a sva2rtl checker with Verilator via C++ wrapper.

    Per RESEARCH.md, uses ``verilator --exe --build --timing`` (NOT
    ``--binary``, which includes ``--main`` and conflicts with our wrapper's
    ``main()``).
    """
    verilator = shutil.which("verilator")
    if verilator is None:
        raise RuntimeError(
            "verilator not found on PATH — install Verilator to run simulation tests"
        )

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
            "--cc", "--exe", "--build", "--timing",
            "-Wno-fatal",
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


# ── Private helpers ───────────────────────────────────────────────────────────


def _parse_output(
    output: str,
    *,
    has_overflow_flag: bool = False,
) -> list[dict[str, bool]]:
    """Parse ``$fdisplay`` output from the testbench into per-cycle output dicts.

    Each line contains space-separated bit characters (``'0'`` or ``'1'``).
    Column order matches what ``generate_testbench`` emits:
    - 3 columns: ``active pass fail``
    - 4 columns: ``active pass fail overflow``

    Empty lines and lines that don't parse as bit vectors are ignored.

    Parameters
    ----------
    output:
        Raw stdout string from ``vvp``.
    has_overflow_flag:
        When ``True``, expect 4 columns and include ``"overflow"`` in output.

    Returns
    -------
    list[dict[str, bool]]
        Per-cycle output dicts.
    """
    results: list[dict[str, bool]] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        # Require at least 3 columns of single-bit values
        if len(parts) < 3 or not all(c in ("0", "1") for p in parts for c in p):
            continue
        # Each part is a single character '0' or '1'
        if not all(len(p) == 1 for p in parts):
            continue
        row: dict[str, bool] = {
            "active": parts[0] == "1",
            "pass":   parts[1] == "1",
            "fail":   parts[2] == "1",
        }
        if has_overflow_flag and len(parts) >= 4:
            row["overflow"] = parts[3] == "1"
        elif has_overflow_flag:
            row["overflow"] = False
        results.append(row)
    return results
