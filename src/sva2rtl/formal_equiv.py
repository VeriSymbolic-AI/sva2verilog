"""SVA-to-Verilog formal equivalence verification (FORMAL-EQUIV / v1.3.2).

This module proves that a *generated monitor* faithfully implements the original
SVA property's IEEE 1800 semantics — i.e. that the COMPILATION is correct.

This is fundamentally different from ``formal.py``, which only proves that the
optimizer preserves equivalence between two of the compiler's own RTL outputs
(unoptimized vs optimized). ``formal.py`` answers "does optimization preserve
semantics?"; this module answers "does the translation match the SVA spec?".

Methodology
-----------
For a property P, we build a SymbiYosys harness that:
  1. instantiates the generated monitor M with ``start`` pulsed every cycle
     (continuous monitoring), driven by the same input signals;
  2. constructs a REFERENCE violation indicator from first principles — a small,
     hand-verified RTL expression encoding the IEEE 1800 semantics of P, derived
     independently of the monitor's implementation;
  3. asserts ``M.fail == ref_violation`` (and where relevant ``M.pass``) as a
     concurrent SVA property under an explicit clock and reset.

A SymbiYosys bounded model check (BMC) then searches for any input trace where
the monitor disagrees with the reference. No counterexample within the depth
bound is strong evidence the monitor correctly implements the SVA semantics.

Because the reference is authored independently of the monitor implementation,
this breaks the verification-independence circularity that affects the behavioral
oracle for composed operators (RISK-01) — the reference is a genuinely separate
source of truth.

Scope and honesty
-----------------
yosys/SymbiYosys natively support a synthesizable subset of concurrent SVA
(booleans, ##N delays, |->/|=>, [*N] repetition, sampled-value functions,
property-level and/or/not/if-else). The operators ``intersect`` / ``within`` /
``throughout`` / ``[->N]`` / ``[=N]`` / ``first_match`` are documented by YosysHQ
as "not FPV-friendly" (AppNote-109) and may not converge — those are handled at
the test layer with bounded depth and honest boundary recording, not forced.

yosys is invoked via the ``sby`` subprocess, mirroring the existing slang/yosys
subprocess-boundary design. When ``sby`` is unavailable, callers should skip.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from sva2rtl.emitter import emit_all
from sva2rtl.ir import CheckerNode

_LOG = logging.getLogger(__name__)


def sby_is_available() -> bool:
    """Return True iff the ``sby`` (SymbiYosys) front-end is on PATH."""
    try:
        subprocess.run(
            ["sby", "--version"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def build_harness(
    monitor_top: str,
    observed_signals: tuple[tuple[str, str], ...],
    reference_expr: str,
    *,
    clock: str = "clk",
    has_overflow_flag: bool = True,
) -> str:
    """Build a SymbiYosys harness asserting ``M.fail == reference_expr``.

    Parameters
    ----------
    monitor_top:
        Top module name of the generated monitor.
    observed_signals:
        ``(port_name, signal_name)`` pairs the monitor observes; each becomes a
        free input of the harness.
    reference_expr:
        A SystemVerilog boolean expression (in terms of the harness signals and
        any locally-declared helper registers) encoding when the original SVA is
        violated this cycle. Authored independently of the monitor.
    clock:
        Clock signal name.

    Returns
    -------
    str
        SystemVerilog harness module text.
    """
    input_decls = "\n".join(
        f"    input logic {port}," for port, _ in observed_signals
    )
    port_conns = " ".join(f".{port}({port})," for port, _ in observed_signals)
    # Leaf templates (bool_expr, sampled-value funcs) have no overflow_flag port;
    # composed templates (implication, seq_concat) do. Connect it only if present.
    ovf_decl = "    logic m_ovf;\n" if has_overflow_flag else ""
    ovf_conn = ".overflow_flag(m_ovf), " if has_overflow_flag else ""

    return f"""\
// Auto-generated SVA-to-Verilog equivalence harness (formal_equiv).
module harness (
    input logic {clock},
{input_decls}
    input logic _unused_pad
);
    // rst_n is driven internally by a deterministic reset pulse (see below) so
    // BMC starts from a well-defined reset state rather than an arbitrary one.
    logic rst_n;
    logic m_active, m_pass, m_fail, m_afired, m_disabled;
{ovf_decl}    {monitor_top} dut (
        .{clock}({clock}), .rst_n(rst_n),
        .start(1'b1),
        {port_conns}
        .disable_i(1'b0),
        .active(m_active), .pass(m_pass), .fail(m_fail),
        .attempt_fired(m_afired), {ovf_conn}.disabled_o(m_disabled)
    );

    // Reset discipline for BMC: hold reset asserted on the first cycle, then
    // release. Without this, BMC would start from an arbitrary state where the
    // monitor's registers and the reference helpers are not aligned. A simple
    // timestep counter drives a deterministic reset pulse and only checks the
    // equivalence once both the monitor and the reference have seen reset.
    integer _t = 0;
    always @(posedge {clock}) _t <= _t + 1;
    wire _in_reset = (_t == 0);
    assign rst_n = ~_in_reset;

    // Reference violation indicator — encodes the original SVA semantics,
    // authored independently of the monitor implementation.
    wire ref_violation = {reference_expr};

    // Correctness claim: the monitor's fail matches the reference exactly.
    // Immediate assertion inside a clocked block is the form yosys parses most
    // reliably for FPV (avoids inline concurrent-assertion clock syntax).
    // Only check after reset has been released and propagated.
    always @(posedge {clock}) begin
        if (rst_n) begin
            equiv_fail: assert (m_fail == ref_violation);
        end
    end
endmodule
"""


def build_helper_regs(helper_decls: str) -> str:
    """Return optional helper register declarations to inject into the harness.

    Some references need pipelined copies of inputs (e.g. ``a_q``). Callers pass
    a SystemVerilog snippet declaring/clocking those regs; it is inserted before
    the assertion. Kept separate so simple cases need no helpers.
    """
    return helper_decls


def build_miter_harness(
    monitor_top: str,
    observed_signals: tuple[tuple[str, str], ...],
    reference_module: str,
    reference_top: str,
    *,
    clock: str = "clk",
    has_overflow_flag: bool = True,
    compare: str = "pass",
) -> str:
    """Build a miter harness comparing the monitor against a REFERENCE MONITOR.

    Unlike ``build_harness`` (which compares ``fail`` to a boolean expression),
    this instantiates BOTH the generated monitor and an independently-written
    reference monitor module, driving them with identical inputs and a single
    ``start`` pulse, then asserts their ``compare`` outputs (``pass`` or
    ``fail``) agree on every cycle. The reference monitor is authored with a
    structurally different (naive shift-register) implementation, providing
    genuine implementation independence for sequence operators.

    Parameters
    ----------
    monitor_top:
        Generated monitor top module name.
    observed_signals:
        ``(port, signal)`` pairs both monitors observe (free inputs).
    reference_module:
        Full SystemVerilog text of the independent reference monitor module.
    reference_top:
        Module name of the reference monitor.
    clock:
        Clock signal.
    has_overflow_flag:
        Whether the generated monitor exposes an overflow_flag port.
    compare:
        Which output to compare: ``"pass"`` or ``"fail"``.
    """
    input_decls = "\n".join(
        f"    input logic {port}," for port, _ in observed_signals
    )
    port_conns = " ".join(f".{port}({port})," for port, _ in observed_signals)
    ovf_decl = "    logic m_ovf;\n" if has_overflow_flag else ""
    ovf_conn = ".overflow_flag(m_ovf), " if has_overflow_flag else ""

    return f"""\
{reference_module}

// Auto-generated SVA-to-Verilog miter harness (formal_equiv, reference monitor).
module harness (
    input logic {clock},
{input_decls}
    input logic _unused_pad
);
    logic rst_n;
    // Single-attempt start: pulse start exactly once (cycle 1, after reset).
    integer _t = 0;
    always @(posedge {clock}) _t <= _t + 1;
    wire _in_reset = (_t == 0);
    assign rst_n = ~_in_reset;
    wire start_pulse = (_t == 1);

    logic m_active, m_pass, m_fail, m_afired, m_disabled;
{ovf_decl}    {monitor_top} dut (
        .{clock}({clock}), .rst_n(rst_n),
        .start(start_pulse),
        {port_conns}
        .disable_i(1'b0),
        .active(m_active), .pass(m_pass), .fail(m_fail),
        .attempt_fired(m_afired), {ovf_conn}.disabled_o(m_disabled)
    );

    logic r_{compare};
    {reference_top} ref_dut (
        .{clock}({clock}), .rst_n(rst_n),
        .start(start_pulse),
        {port_conns}
        .{compare}(r_{compare})
    );

    always @(posedge {clock}) begin
        if (rst_n) begin
            equiv_cmp: assert (m_{compare} == r_{compare});
        end
    end
endmodule
"""


def run_sva_miter_check(
    monitor_root: CheckerNode,
    reference_module: str,
    reference_top: str,
    *,
    clock: str = "clk",
    compare: str = "pass",
    depth: int = 20,
    timeout: int = 300,
    mode: str = "bmc",
) -> tuple[bool, str]:
    """Verify a monitor against an independent reference monitor via miter.

    See ``build_miter_harness``. Returns ``(passed, output)``.

    Parameters
    ----------
    mode:
        SymbiYosys mode: ``"bmc"`` (bounded, default) or ``"prove"``
        (complete proof via k-induction).
    """
    if not sby_is_available():
        return False, "ERROR: sby (SymbiYosys) not found on PATH"

    modules = emit_all(monitor_root)
    monitor_top = monitor_root.module_name
    top_sv = modules.get(monitor_top, "")
    has_ovf = "overflow_flag" in top_sv

    harness = build_miter_harness(
        monitor_top,
        monitor_root.observed_signals,
        reference_module,
        reference_top,
        clock=clock,
        has_overflow_flag=has_ovf,
        compare=compare,
    )

    with tempfile.TemporaryDirectory(prefix="sva2rtl_miter_") as tmpdir:
        work = Path(tmpdir)
        read_lines = []
        file_lines = []
        for name, sv in modules.items():
            (work / f"{name}.sv").write_text(sv)
            read_lines.append(f"read -sv {name}.sv")
            file_lines.append(f"{name}.sv")
        (work / "harness.sv").write_text(harness)
        read_lines.append("read -sv harness.sv")
        file_lines.append("harness.sv")

        script_reads = "\n".join(read_lines)
        files_block = "\n".join(file_lines)
        sby_text = f"""\
[options]
mode {mode}
depth {depth}

[engines]
smtbmc z3

[script]
{script_reads}
prep -top harness

[files]
{files_block}
"""
        (work / "miter.sby").write_text(sby_text)

        try:
            result = subprocess.run(
                ["sby", "-f", "miter.sby"],
                cwd=str(work),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + "\n" + result.stderr
            passed = result.returncode == 0 and "PASS" in output
            return passed, output
        except subprocess.TimeoutExpired:
            return False, f"ERROR: sby miter check timed out after {timeout}s"


def run_sva_equiv_check(
    monitor_root: CheckerNode,
    reference_expr: str,
    *,
    helper_regs: str = "",
    clock: str = "clk",
    depth: int = 20,
    timeout: int = 300,
    mode: str = "bmc",
) -> tuple[bool, str]:
    """Verify a generated monitor against an independent SVA reference.

    Parameters
    ----------
    monitor_root:
        The composed (optionally optimized) CheckerNode tree for the property.
    reference_expr:
        SystemVerilog boolean expression for when the SVA is violated this cycle.
    helper_regs:
        Optional SV snippet declaring/clocking helper registers used by
        ``reference_expr`` (e.g. one-cycle delayed input copies).
    clock:
        Clock signal name.
    depth:
        BMC search depth (cycles). Also used as k-induction depth when
        ``mode="prove"``.
    timeout:
        Subprocess timeout in seconds.
    mode:
        SymbiYosys verification mode: ``"bmc"`` (bounded model checking,
        default) or ``"prove"`` (complete proof via BMC + k-induction).
        ``"prove"`` provides mathematical completeness but may not converge
        for complex monitors.

    Returns
    -------
    tuple[bool, str]
        ``(passed, output_text)`` — *passed* is True iff no counterexample was
        found within *depth* (i.e. monitor matches the SVA reference). For
        ``mode="prove"``, *passed* is True iff the property is proven for all
        reachable states (complete proof, not just bounded).
    """
    if not sby_is_available():
        return False, "ERROR: sby (SymbiYosys) not found on PATH"

    modules = emit_all(monitor_root)
    monitor_top = monitor_root.module_name

    # Detect whether the top module exposes an overflow_flag port. Leaf templates
    # (bool_expr, $rose/$fell/etc.) do not; composed templates do. We check the
    # emitted top-module text directly to stay robust to template changes.
    top_sv = modules.get(monitor_top, "")
    has_ovf = "overflow_flag" in top_sv

    harness = build_harness(
        monitor_top,
        monitor_root.observed_signals,
        reference_expr,
        clock=clock,
        has_overflow_flag=has_ovf,
    )
    if helper_regs:
        # Insert helper regs just after the dut instantiation closing line.
        harness = harness.replace(
            "    // Reference violation indicator",
            helper_regs + "\n    // Reference violation indicator",
            1,
        )

    with tempfile.TemporaryDirectory(prefix="sva2rtl_equiv_") as tmpdir:
        work = Path(tmpdir)
        file_lines = []
        read_lines = []
        for name, sv in modules.items():
            (work / f"{name}.sv").write_text(sv)
            file_lines.append(f"{name}.sv")
            read_lines.append(f"read -sv {name}.sv")
        (work / "harness.sv").write_text(harness)
        file_lines.append("harness.sv")
        read_lines.append("read -sv harness.sv")

        script_reads = "\n".join(read_lines)
        files_block = "\n".join(file_lines)

        # k-induction: SymbiYosys "prove" mode runs BMC (base case) + k-induction
        # (inductive step). A PASS here is a COMPLETE proof (all reachable states).
        # The engine is always smtbmc with z3 — sby internally handles prove mode by
        # splitting into basecase and induction tasks.
        sby_text = f"""\
[options]
mode {mode}
depth {depth}

[engines]
smtbmc z3

[script]
{script_reads}
prep -top harness

[files]
{files_block}
"""
        (work / "equiv.sby").write_text(sby_text)

        try:
            result = subprocess.run(
                ["sby", "-f", "equiv.sby"],
                cwd=str(work),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + "\n" + result.stderr
            # sby returns 0 on PASS, non-zero on FAIL/ERROR.
            passed = result.returncode == 0 and "PASS" in output
            return passed, output
        except subprocess.TimeoutExpired:
            return False, f"ERROR: sby equivalence check timed out after {timeout}s"


def run_sva_equiv_prove(
    monitor_root: CheckerNode,
    reference_expr: str,
    *,
    helper_regs: str = "",
    clock: str = "clk",
    depth: int = 20,
    timeout: int = 600,
) -> tuple[bool, str]:
    """Verify a monitor via k-induction (complete proof, not just bounded).

    This is a convenience wrapper around ``run_sva_equiv_check`` with
    ``mode="prove"``. A PASS result means the monitor is proven equivalent to
    the SVA reference for ALL reachable states — a mathematical proof, not just
    a bounded check.

    k-induction works by:
    1. Base case: prove the property holds for the first k cycles (BMC).
    2. Inductive step: assume the property holds for k consecutive cycles and
       prove it holds for the (k+1)th cycle.

    If both steps succeed, the property is proven for all time.

    Not all monitors will converge with k-induction. Complex sequential logic
    may require high k values or may not converge at all. In such cases, fall
    back to ``run_sva_equiv_check`` (BMC) for bounded evidence.

    Parameters
    ----------
    monitor_root:
        The composed CheckerNode tree for the property.
    reference_expr:
        SystemVerilog boolean expression for when the SVA is violated.
    helper_regs:
        Optional helper register declarations.
    clock:
        Clock signal name.
    depth:
        k-induction depth (also BMC base-case depth).
    timeout:
        Subprocess timeout in seconds (default 600, induction can be slow).

    Returns
    -------
    tuple[bool, str]
        ``(passed, output_text)`` — *passed* is True iff the property is
        PROVEN for all reachable states.
    """
    return run_sva_equiv_check(
        monitor_root,
        reference_expr,
        helper_regs=helper_regs,
        clock=clock,
        depth=depth,
        timeout=timeout,
        mode="prove",
    )
