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
import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sva2rtl.emitter import emit_all, observed_signal_widths
from sva2rtl.ir import CheckerNode

_LOG = logging.getLogger(__name__)

FormalStartMode = Literal["continuous", "single_shot", "arbitrary_start"]
FormalDisableMode = Literal["held_low", "arbitrary_disable"]
FormalResetMode = Literal["first_cycle", "reset_recovery"]
FormalOutputName = Literal[
    "pass",
    "fail",
    "active",
    "attempt_fired",
    "disabled_o",
    "overflow_flag",
]
FormalCoverName = Literal["pass", "fail", "disable", "overflow", "overlap"]
FormalOverlapPolicy = Literal["unconstrained", "bounded", "excluded"]


@dataclass(frozen=True)
class FormalOutputContract:
    """Structured monitor-output comparison contract for formal miters."""

    outputs: tuple[FormalOutputName, ...] = ("fail",)
    excluded: tuple[FormalOutputName, ...] = ()

    def __post_init__(self) -> None:
        valid = set(_MONITOR_OUTPUT_VARS)
        invalid_outputs = sorted(set(self.outputs) - valid)
        invalid_excluded = sorted(set(self.excluded) - valid)
        if invalid_outputs or invalid_excluded:
            msg = (
                "invalid formal output contract: "
                f"outputs={invalid_outputs}, excluded={invalid_excluded}"
            )
            raise ValueError(msg)
        if not self.outputs:
            raise ValueError("formal output contract must compare at least one output")

    @classmethod
    def single(cls, output: Literal["pass", "fail"]) -> FormalOutputContract:
        """Return the legacy one-output miter contract."""
        return cls(outputs=(output,))

    @classmethod
    def full_monitor(
        cls,
        *,
        include_overflow: bool = True,
    ) -> FormalOutputContract:
        """Return the standard monitor contract bundle used by Phase 10."""
        outputs: tuple[FormalOutputName, ...] = (
            "pass",
            "fail",
            "active",
            "attempt_fired",
            "disabled_o",
        )
        if include_overflow:
            outputs = (*outputs, "overflow_flag")
        return cls(outputs=outputs)


@dataclass(frozen=True)
class FormalHarnessConfig:
    """Explicit contract for formal harness start/disable/reset behavior."""

    start_mode: FormalStartMode = "continuous"
    disable_mode: FormalDisableMode = "held_low"
    reset_mode: FormalResetMode = "first_cycle"
    output_contract: FormalOutputContract = field(
        default_factory=FormalOutputContract
    )
    covers: tuple[FormalCoverName, ...] = ()
    assumption_notes: tuple[str, ...] = ()
    overlap: FormalOverlapPolicy = "unconstrained"
    minimum_start_gap: int | None = None
    assume_start_low_during_reset: bool = True
    assume_disable_low_during_reset: bool = True
    reference_disable_port: bool = False

    def __post_init__(self) -> None:
        """Reject ambiguous contracts before a solver can report a false PASS."""
        valid_start = {"continuous", "single_shot", "arbitrary_start"}
        valid_disable = {"held_low", "arbitrary_disable"}
        valid_reset = {"first_cycle", "reset_recovery"}
        valid_overlap = {"unconstrained", "bounded", "excluded"}
        valid_covers = {"pass", "fail", "disable", "overflow", "overlap"}

        if self.start_mode not in valid_start:
            raise ValueError(f"invalid start_mode: {self.start_mode!r}")
        if self.disable_mode not in valid_disable:
            raise ValueError(f"invalid disable_mode: {self.disable_mode!r}")
        if self.reset_mode not in valid_reset:
            raise ValueError(f"invalid reset_mode: {self.reset_mode!r}")
        if self.overlap not in valid_overlap:
            raise ValueError(f"invalid overlap policy: {self.overlap!r}")
        invalid_covers = sorted(set(self.covers) - valid_covers)
        if invalid_covers:
            raise ValueError(f"invalid formal cover probes: {invalid_covers}")
        if any("\n" in note or "\r" in note for note in self.assumption_notes):
            raise ValueError("formal assumption notes must be single-line text")

        if self.overlap != "unconstrained" and self.start_mode != "arbitrary_start":
            raise ValueError(
                "bounded/excluded overlap policies require start_mode='arbitrary_start'"
            )
        if self.overlap == "bounded":
            if (
                isinstance(self.minimum_start_gap, bool)
                or not isinstance(self.minimum_start_gap, int)
                or self.minimum_start_gap < 1
            ):
                raise ValueError(
                    "overlap='bounded' requires minimum_start_gap >= 1"
                )
        elif self.minimum_start_gap is not None:
            raise ValueError(
                "minimum_start_gap is valid only when overlap='bounded'"
            )

    @classmethod
    def equivalence_default(cls) -> FormalHarnessConfig:
        """Compatibility default for expression equivalence checks."""
        return cls(
            start_mode="continuous",
            disable_mode="held_low",
            reset_mode="first_cycle",
            output_contract=FormalOutputContract.single("fail"),
        )

    @classmethod
    def miter_default(
        cls,
        *,
        compare: Literal["pass", "fail"] = "pass",
    ) -> FormalHarnessConfig:
        """Compatibility default for reference-monitor miters."""
        return cls(
            start_mode="single_shot",
            disable_mode="held_low",
            reset_mode="first_cycle",
            output_contract=FormalOutputContract.single(compare),
        )


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


def _extra_input_ports(config: FormalHarnessConfig) -> tuple[str, ...]:
    ports: list[str] = []
    if config.start_mode == "arbitrary_start":
        ports.append("formal_start")
    if config.disable_mode == "arbitrary_disable":
        ports.append("formal_disable")
    if config.reset_mode == "reset_recovery":
        ports.append("formal_reset")
    return tuple(ports)


def _render_extra_input_decls(config: FormalHarnessConfig) -> str:
    ports = _extra_input_ports(config)
    if not ports:
        return ""
    return "\n".join(f"    input logic {port}," for port in ports) + "\n"


def _render_timing_controls(
    config: FormalHarnessConfig,
    *,
    clock: str,
) -> str:
    if config.reset_mode == "reset_recovery":
        reset_expr = "(_t == 0) || formal_reset"
        reset_note = (
            "    // Formal assumption: reset_mode=reset_recovery permits reset "
            "after activity.\n"
        )
    else:
        reset_expr = "(_t == 0)"
        reset_note = (
            "    // Formal assumption: reset_mode=first_cycle uses the legacy "
            "one-cycle reset pulse.\n"
        )

    if config.start_mode == "continuous":
        start_note = (
            "    // Formal assumption: start_mode=continuous ties start high "
            "every non-reset cycle.\n"
        )
    elif config.start_mode == "single_shot":
        start_note = (
            "    wire start_pulse = (_t == 1);\n"
            "    // Formal assumption: start_mode=single_shot pulses start "
            "exactly once after reset.\n"
        )
    else:
        start_note = (
            "    // Formal assumption: start_mode=arbitrary_start leaves start "
            "as a free input.\n"
            f"    // Executed overlap policy: {config.overlap}.\n"
        )

    if config.disable_mode == "arbitrary_disable":
        disable_note = (
            "    // Formal assumption: disable_mode=arbitrary_disable leaves "
            "disable_i variable.\n"
            "    // Disable assumptions document reset, active/pass/fail, "
            "disabled_o, and sticky attempt_fired behavior.\n"
        )
    else:
        disable_note = (
            "    // Formal assumption: disable_mode=held_low ties disable_i "
            "low for compatibility.\n"
        )

    assumption_notes = "".join(
        f"    // Non-semantic contract note: {note}\n"
        for note in config.assumption_notes
    )

    assumption_lines: list[str] = []
    if (
        config.start_mode == "arbitrary_start"
        and config.assume_start_low_during_reset
    ):
        assumption_lines.append("            assume (!formal_start);")
    if (
        config.disable_mode == "arbitrary_disable"
        and config.assume_disable_low_during_reset
    ):
        assumption_lines.append("            assume (!formal_disable);")

    reset_assume = ""
    if assumption_lines:
        reset_assume = (
            "    always @(posedge {clock}) begin\n"
            "        if (!rst_n) begin\n"
            "{assumptions}\n"
            "        end\n"
            "    end\n"
        ).format(
            clock=clock,
            assumptions="\n".join(assumption_lines),
        )

    start_gap_constraint = ""
    if config.overlap == "bounded":
        assert config.minimum_start_gap is not None
        start_gap_constraint = f"""\
    // Executable rate bound: after a start, forbid another start for the
    // configured number of complete sampling cycles.
    localparam integer FORMAL_MIN_START_GAP = {config.minimum_start_gap};
    integer formal_start_gap_q = 0;
    always @(posedge {clock}) begin
        if (!rst_n) begin
            formal_start_gap_q <= 0;
        end else begin
            assume (!formal_start || formal_start_gap_q == 0);
            if (formal_start)
                formal_start_gap_q <= FORMAL_MIN_START_GAP;
            else if (formal_start_gap_q > 0)
                formal_start_gap_q <= formal_start_gap_q - 1;
        end
    end
"""

    return f"""\
    integer _t = 0;
    always @(posedge {clock}) _t <= _t + 1;
    wire _in_reset = {reset_expr};
    assign rst_n = ~_in_reset;
{reset_note}{start_note}{disable_note}{assumption_notes}{reset_assume}{start_gap_constraint}"""


def _render_post_monitor_constraints(
    config: FormalHarnessConfig,
    *,
    clock: str,
) -> str:
    """Render assumptions that depend on monitor state after instantiation."""
    if config.overlap != "excluded":
        return ""
    return f"""\
    // Executable overlap exclusion: a new attempt cannot start while the
    // generated monitor reports an earlier attempt active.
    always @(posedge {clock}) begin
        if (rst_n)
            assume (!formal_start || !m_active);
    end
"""


def _start_expr(config: FormalHarnessConfig) -> str:
    if config.start_mode == "continuous":
        return "1'b1"
    if config.start_mode == "single_shot":
        return "start_pulse"
    return "formal_start"


def _disable_expr(config: FormalHarnessConfig) -> str:
    if config.disable_mode == "held_low":
        return "1'b0"
    return "formal_disable"


_MONITOR_OUTPUT_VARS: dict[FormalOutputName, str] = {
    "pass": "m_pass",
    "fail": "m_fail",
    "active": "m_active",
    "attempt_fired": "m_afired",
    "disabled_o": "m_disabled",
    "overflow_flag": "m_ovf",
}

_REFERENCE_OUTPUT_VARS: dict[FormalOutputName, str] = {
    "pass": "r_pass",
    "fail": "r_fail",
    "active": "r_active",
    "attempt_fired": "r_afired",
    "disabled_o": "r_disabled",
    "overflow_flag": "r_ovf",
}


def _contract_outputs(
    config: FormalHarnessConfig,
    *,
    has_overflow_flag: bool,
) -> tuple[tuple[FormalOutputName, ...], tuple[FormalOutputName, ...]]:
    included: list[FormalOutputName] = []
    explicitly_excluded = set(config.output_contract.excluded)
    excluded: list[FormalOutputName] = list(config.output_contract.excluded)
    for output in config.output_contract.outputs:
        if output in explicitly_excluded:
            continue
        if output == "overflow_flag" and not has_overflow_flag:
            if output not in excluded:
                excluded.append(output)
            continue
        if output not in included:
            included.append(output)
    if not included:
        raise ValueError(
            "formal output contract has no comparable outputs after exclusions"
        )
    return tuple(included), tuple(excluded)


def _render_excluded_contract_comment(excluded: tuple[FormalOutputName, ...]) -> str:
    if not excluded:
        return ""
    joined = ", ".join(excluded)
    return f"    // Excluded contract signals: {joined}\n"


def _render_contract_assertions(outputs: tuple[FormalOutputName, ...]) -> str:
    lines = []
    for output in outputs:
        lines.append(
            f"            equiv_{output}: assert "
            f"({_MONITOR_OUTPUT_VARS[output]} == {_REFERENCE_OUTPUT_VARS[output]});"
        )
    return "\n".join(lines)


def _render_ref_signal_decls(outputs: tuple[FormalOutputName, ...]) -> str:
    lines = [f"    logic {_REFERENCE_OUTPUT_VARS[output]};" for output in outputs]
    return "\n".join(lines)


def _render_ref_output_conns(outputs: tuple[FormalOutputName, ...]) -> str:
    return "".join(
        f",\n        .{output}({_REFERENCE_OUTPUT_VARS[output]})"
        for output in outputs
    )


def _render_cover_probes(
    config: FormalHarnessConfig,
    *,
    has_overflow_flag: bool,
) -> str:
    if not config.covers:
        return ""

    expressions: dict[FormalCoverName, str] = {
        "pass": "m_pass",
        "fail": "m_fail",
        "disable": "m_disabled",
        "overflow": "m_ovf" if has_overflow_flag else "1'b0",
        "overlap": f"{_start_expr(config)} && m_active",
    }
    lines = ["", "            // Cover probes check setup reachability, not equivalence."]
    for cover in config.covers:
        if cover == "overflow" and not has_overflow_flag:
            lines.append("            // cover_probe_overflow excluded: overflow_flag absent")
            continue
        lines.append(f"            cover_probe_{cover}: cover ({expressions[cover]});")
    return "\n".join(lines)


def _required_covers(
    config: FormalHarnessConfig,
    *,
    has_overflow_flag: bool,
) -> tuple[FormalCoverName, ...]:
    """Return cover probes that actually exist in the rendered harness."""
    return tuple(
        cover
        for cover in config.covers
        if cover != "overflow" or has_overflow_flag
    )


def _sby_reported_pass(output: str) -> bool:
    """Recognize PASS as a standalone status token, not an arbitrary substring."""
    for line in output.splitlines():
        tokens = line.replace("(", " ").replace(")", " ").replace(",", " ").split()
        if "PASS" in tokens:
            return True
    return False


def _run_sby_with_timeout(
    cmd: list[str],
    *,
    cwd: str,
    timeout: int,
) -> tuple[int, str, bool]:
    """Run SymbiYosys and kill its whole process group on timeout."""
    proc: subprocess.Popen[str] = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        returncode = proc.returncode if proc.returncode is not None else -1
        return returncode, (stdout or "") + "\n" + (stderr or ""), False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        stdout, stderr = proc.communicate()
        return -1, (stdout or "") + "\n" + (stderr or ""), True


def _sby_project_text(
    *,
    mode: str,
    depth: int,
    script_reads: str,
    files_block: str,
) -> str:
    return f"""\
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


def _run_sby_plan(
    work: Path,
    *,
    stem: str,
    primary_mode: str,
    depth: int,
    timeout: int,
    script_reads: str,
    files_block: str,
    required_covers: tuple[FormalCoverName, ...],
) -> tuple[bool, str]:
    """Run proof/BMC first, then require a separate reachability cover task."""
    primary_path = work / f"{stem}.sby"
    primary_path.write_text(
        _sby_project_text(
            mode=primary_mode,
            depth=depth,
            script_reads=script_reads,
            files_block=files_block,
        ),
        encoding="utf-8",
    )
    returncode, output, timed_out = _run_sby_with_timeout(
        ["sby", "-f", primary_path.name],
        cwd=str(work),
        timeout=timeout,
    )
    if timed_out:
        return False, f"ERROR: sby {stem} check timed out after {timeout}s\n{output}"
    if returncode != 0 or not _sby_reported_pass(output):
        return False, output
    if not required_covers:
        return True, output

    cover_path = work / f"{stem}_cover.sby"
    cover_path.write_text(
        _sby_project_text(
            mode="cover",
            depth=depth,
            script_reads=script_reads,
            files_block=files_block,
        ),
        encoding="utf-8",
    )
    cover_rc, cover_output, cover_timed_out = _run_sby_with_timeout(
        ["sby", "-f", cover_path.name],
        cwd=str(work),
        timeout=timeout,
    )
    covers = ", ".join(required_covers)
    combined = f"{output}\n\n=== required cover task ({covers}) ===\n{cover_output}"
    if cover_timed_out:
        return False, (
            f"UNKNOWN: required cover reachability timed out after {timeout}s\n{combined}"
        )
    if cover_rc != 0 or not _sby_reported_pass(cover_output):
        return False, f"UNKNOWN: required cover reachability failed ({covers})\n{combined}"
    return True, combined


def build_harness(
    monitor_top: str,
    observed_signals: tuple[tuple[str, str], ...],
    reference_expr: str,
    *,
    clock: str = "clk",
    has_overflow_flag: bool = True,
    signal_widths: dict[str, int] | None = None,
    config: FormalHarnessConfig | None = None,
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
    harness_config = config or FormalHarnessConfig.equivalence_default()
    widths = signal_widths or {}
    input_decls = "\n".join(
        f"    input logic "
        f"{'[' + str(widths.get(port, 1) - 1) + ':0] ' if widths.get(port, 1) > 1 else ''}"
        f"{port},"
        for port, _ in observed_signals
    )
    extra_input_decls = _render_extra_input_decls(harness_config)
    port_conns = " ".join(f".{port}({port})," for port, _ in observed_signals)
    # Leaf templates (bool_expr, sampled-value funcs) have no overflow_flag port;
    # composed templates (implication, seq_concat) do. Connect it only if present.
    ovf_decl = "    logic m_ovf;\n" if has_overflow_flag else ""
    ovf_conn = ".overflow_flag(m_ovf), " if has_overflow_flag else ""
    timing_controls = _render_timing_controls(harness_config, clock=clock)
    start_expr = _start_expr(harness_config)
    disable_expr = _disable_expr(harness_config)
    cover_probes = _render_cover_probes(
        harness_config,
        has_overflow_flag=has_overflow_flag,
    )
    _, excluded = _contract_outputs(
        harness_config,
        has_overflow_flag=has_overflow_flag,
    )
    excluded_comment = _render_excluded_contract_comment(excluded)
    post_monitor_constraints = _render_post_monitor_constraints(
        harness_config,
        clock=clock,
    )

    if "fail" not in harness_config.output_contract.outputs:
        raise ValueError("expression equivalence harness requires output 'fail'")
    if "fail" in harness_config.output_contract.excluded:
        raise ValueError("expression equivalence harness cannot exclude output 'fail'")

    return f"""\
// Auto-generated SVA-to-Verilog equivalence harness (formal_equiv).
module harness (
    input logic {clock},
{input_decls}
{extra_input_decls}\
    input logic _unused_pad
);
    // rst_n is driven internally by a deterministic reset pulse (see below) so
    // BMC starts from a well-defined reset state rather than an arbitrary one.
    logic rst_n;
{timing_controls}
    logic m_active, m_pass, m_fail, m_afired, m_disabled;
{ovf_decl}    {monitor_top} dut (
        .{clock}({clock}), .rst_n(rst_n),
        .start({start_expr}),
        {port_conns}
        .disable_i({disable_expr}),
        .active(m_active), .pass(m_pass), .fail(m_fail),
        .attempt_fired(m_afired), {ovf_conn}.disabled_o(m_disabled)
    );
{excluded_comment}
{post_monitor_constraints}

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
{cover_probes}
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
    signal_widths: dict[str, int] | None = None,
    config: FormalHarnessConfig | None = None,
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
    if compare not in ("pass", "fail"):
        msg = f"compare must be 'pass' or 'fail', got {compare!r}"
        raise ValueError(msg)

    harness_config = config or FormalHarnessConfig.miter_default(
        compare=compare,  # type: ignore[arg-type]
    )
    outputs, excluded = _contract_outputs(
        harness_config,
        has_overflow_flag=has_overflow_flag,
    )
    widths = signal_widths or {}
    input_decls = "\n".join(
        f"    input logic "
        f"{'[' + str(widths.get(port, 1) - 1) + ':0] ' if widths.get(port, 1) > 1 else ''}"
        f"{port},"
        for port, _ in observed_signals
    )
    extra_input_decls = _render_extra_input_decls(harness_config)
    port_conns = " ".join(f".{port}({port})," for port, _ in observed_signals)
    ovf_decl = "    logic m_ovf;\n" if has_overflow_flag else ""
    ovf_conn = ".overflow_flag(m_ovf), " if has_overflow_flag else ""
    timing_controls = _render_timing_controls(harness_config, clock=clock)
    start_expr = _start_expr(harness_config)
    disable_expr = _disable_expr(harness_config)
    ref_signal_decls = _render_ref_signal_decls(outputs)
    ref_conn_items = [
        f".{clock}({clock})",
        ".rst_n(rst_n)",
        f".start({start_expr})",
        *(f".{port}({port})" for port, _ in observed_signals),
    ]
    if harness_config.reference_disable_port:
        ref_conn_items.append(f".disable_i({disable_expr})")
    ref_conn_items.extend(
        f".{output}({_REFERENCE_OUTPUT_VARS[output]})" for output in outputs
    )
    ref_conn_block = ",\n        ".join(ref_conn_items)
    contract_assertions = _render_contract_assertions(outputs)
    cover_probes = _render_cover_probes(
        harness_config,
        has_overflow_flag=has_overflow_flag,
    )
    excluded_comment = _render_excluded_contract_comment(excluded)
    post_monitor_constraints = _render_post_monitor_constraints(
        harness_config,
        clock=clock,
    )

    return f"""\
{reference_module}

// Auto-generated SVA-to-Verilog miter harness (formal_equiv, reference monitor).
module harness (
    input logic {clock},
{input_decls}
{extra_input_decls}\
    input logic _unused_pad
);
    logic rst_n;
{timing_controls}

    logic m_active, m_pass, m_fail, m_afired, m_disabled;
{ovf_decl}    {monitor_top} dut (
        .{clock}({clock}), .rst_n(rst_n),
        .start({start_expr}),
        {port_conns}
        .disable_i({disable_expr}),
        .active(m_active), .pass(m_pass), .fail(m_fail),
        .attempt_fired(m_afired), {ovf_conn}.disabled_o(m_disabled)
    );
{excluded_comment}
{post_monitor_constraints}

{ref_signal_decls}
    {reference_top} ref_dut (
        {ref_conn_block}
    );

    always @(posedge {clock}) begin
        if (rst_n) begin
{contract_assertions}
{cover_probes}
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
    config: FormalHarnessConfig | None = None,
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
    harness_config = config or FormalHarnessConfig.miter_default(
        compare=compare,  # type: ignore[arg-type]
    )

    harness = build_miter_harness(
        monitor_top,
        monitor_root.observed_signals,
        reference_module,
        reference_top,
        clock=clock,
        has_overflow_flag=has_ovf,
        compare=compare,
        signal_widths=observed_signal_widths(monitor_root),
        config=harness_config,
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
        return _run_sby_plan(
            work,
            stem="miter",
            primary_mode=mode,
            depth=depth,
            timeout=timeout,
            script_reads=script_reads,
            files_block=files_block,
            required_covers=_required_covers(
                harness_config,
                has_overflow_flag=has_ovf,
            ),
        )


def run_sva_equiv_check(
    monitor_root: CheckerNode,
    reference_expr: str,
    *,
    helper_regs: str = "",
    clock: str = "clk",
    depth: int = 20,
    timeout: int = 300,
    mode: str = "bmc",
    config: FormalHarnessConfig | None = None,
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
    harness_config = config or FormalHarnessConfig.equivalence_default()

    harness = build_harness(
        monitor_top,
        monitor_root.observed_signals,
        reference_expr,
        clock=clock,
        has_overflow_flag=has_ovf,
        signal_widths=observed_signal_widths(monitor_root),
        config=harness_config,
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

        return _run_sby_plan(
            work,
            stem="equiv",
            primary_mode=mode,
            depth=depth,
            timeout=timeout,
            script_reads=script_reads,
            files_block=files_block,
            required_covers=_required_covers(
                harness_config,
                has_overflow_flag=has_ovf,
            ),
        )


def run_sva_equiv_prove(
    monitor_root: CheckerNode,
    reference_expr: str,
    *,
    helper_regs: str = "",
    clock: str = "clk",
    depth: int = 20,
    timeout: int = 600,
    config: FormalHarnessConfig | None = None,
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
        config=config,
    )
