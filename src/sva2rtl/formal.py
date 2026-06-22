"""Formal equivalence verification via yosys equivalence checking.

Proves that the optimizer pipeline preserves semantic equivalence between
unoptimized and optimized RTL.  Uses yosys ``equiv_make`` + ``equiv_induct``
to perform temporal induction proofs on the generated hardware.

Design rationale:
- yosys is invoked as a subprocess (same pattern as slang CLI subprocess)
  — no in-process binding, stable schema boundary, tool version isolation.
- ``equiv_induct`` with fallback to ``equiv_simple`` for bounded proofs.
- Timeout at 300 seconds prevents hung proofs from blocking CI.
- Module names in gold/gate SV are suffixed (_gold/_gate) before yosys reads
  them, avoiding name collisions in the single yosys process.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from sva2rtl.ir import CheckerNode

_LOG = logging.getLogger(__name__)

_VersionOutput = tuple[str, str]


def _suffix_module_names(sv_text: str, suffix: str, all_module_names: set[str] | None = None) -> str:
    """Rename all module definitions and instantiations by appending *suffix*.

    Processes module declarations, instantiations, and endmodule comments
    so yosys can read both gold and gate designs in a single process.
    When *all_module_names* is provided, only those names are renamed;
    otherwise module names are auto-detected from *sv_text* itself.
    Names are sorted longest-first to avoid partial substitution.
    """
    if all_module_names is None:
        all_module_names = set(re.findall(r"^\s*module\s+(\w+)", sv_text, re.MULTILINE))
    module_names = sorted(all_module_names, key=len, reverse=True)
    result = sv_text
    for name in module_names:
        new_name = f"{name}{suffix}"
        # Module definition
        result = re.sub(
            rf"(module\s+){re.escape(name)}(\s*[#(])",
            rf"\1{new_name}\2",
            result,
        )
        # Module instantiation: <mod_name> <inst_name> (
        result = re.sub(
            rf"\b{re.escape(name)}\s+(\w+\s*\()",
            rf"{new_name} \1",
            result,
        )
        # endmodule trailing comment
        result = re.sub(
            rf"(endmodule\s*//\s*){re.escape(name)}\b",
            rf"\1{new_name}",
            result,
        )
    return result


def yosys_version() -> _VersionOutput:
    """Return (yosys_version, sby_version) strings.

    Returns empty strings if either tool is not found on PATH.
    """
    try:
        yosys_out = subprocess.run(
            ["yosys", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        yosys_out = ""
    try:
        sby_out = subprocess.run(
            ["sby", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        sby_out = ""
    return yosys_out, sby_out


def _extract_top_module_names(sv_text: str) -> list[str]:
    """Extract module names from SystemVerilog source text.

    Returns a list of module names in declaration order.
    Matches patterns like ``module checker_foo (...);``.
    """
    return re.findall(r"^\s*module\s+(\w+)\s*[#(]", sv_text, re.MULTILINE)


def _yosys_is_available() -> bool:
    """Check whether yosys is installed and on PATH."""
    try:
        subprocess.run(
            ["yosys", "--version"],
            capture_output=True,
            timeout=10,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


def run_equiv_check(
    unoptimized_sv: str,
    optimized_sv: str,
    *,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Run yosys equivalence checking between unoptimized and optimized RTL.

    Suffixes module names with ``_gold`` / ``_gate`` to avoid collisions
    when both designs are read into the same yosys process.  Then runs
    ``equiv_make`` + ``equiv_induct`` for temporal induction proof.

    Parameters
    ----------
    unoptimized_sv:
        SystemVerilog source text for the unoptimized (gold) design.
    optimized_sv:
        SystemVerilog source text for the optimized (gate) design.
    timeout:
        Maximum time (seconds) for the yosys subprocess.  Default 300.

    Returns
    -------
    tuple[bool, str]
        ``(passed, output_text)`` where *passed* is ``True`` iff yosys
        reports all equivalence classes as proven.
    """
    if not _yosys_is_available():
        return False, "ERROR: yosys not found on PATH"

    top_modules = _extract_top_module_names(unoptimized_sv)
    if not top_modules:
        return False, "ERROR: could not find any module in unoptimized RTL"

    top = top_modules[0]
    gold_top = f"{top}_gold"
    gate_top = f"{top}_gate"
    _LOG.info("formal: top module = %s", top)

    gold_sv = _suffix_module_names(unoptimized_sv, "_gold")
    gate_sv = _suffix_module_names(optimized_sv, "_gate")

    with tempfile.TemporaryDirectory(prefix="sva2rtl_formal_") as tmpdir:
        gold_path = Path(tmpdir) / "gold.sv"
        gate_path = Path(tmpdir) / "gate.sv"
        gold_path.write_text(gold_sv)
        gate_path.write_text(gate_sv)

        tcl_script = f"""\
read_verilog -sv {gold_path}
read_verilog -sv {gate_path}
proc
flatten
equiv_make {gold_top} {gate_top} equiv
equiv_induct -ignore-unknown-cells equiv
equiv_simple -seq 10 equiv
equiv_status -assert equiv
"""

        tcl_path = Path(tmpdir) / "equiv.ys"
        tcl_path.write_text(tcl_script)

        try:
            result = subprocess.run(
                ["yosys", "-s", str(tcl_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + "\n" + result.stderr
            passed = result.returncode == 0
            return passed, output
        except subprocess.TimeoutExpired:
            return False, "ERROR: yosys equivalence check timed out"


def run_equiv_check_multi(
    unoptimized_modules: dict[str, str],
    optimized_modules: dict[str, str],
    *,
    top_module: str | None = None,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Run yosys equivalence checking on multi-module designs.

    Each module SV text is suffixed with ``_gold`` / ``_gate`` so that both
    designs can coexist in the same yosys process without name collisions.

    Parameters
    ----------
    unoptimized_modules:
        Dict of ``{module_name: sv_text}`` for the gold design.
    optimized_modules:
        Dict of ``{module_name: sv_text}`` for the gate design.
    top_module:
        Name of the top-level module.  If ``None``, the last module
        found in the unoptimized SV text is used (which matches
        ``emit_all``'s depth-first insertion order).
    timeout:
        Maximum time (seconds) for the yosys subprocess.

    Returns
    -------
    tuple[bool, str]
        ``(passed, output_text)``.
    """
    if not _yosys_is_available():
        return False, "ERROR: yosys not found on PATH"

    if not unoptimized_modules:
        return False, "ERROR: no modules to verify — empty module dict"

    if top_module is None:
        all_sv = "\n".join(unoptimized_modules.values())
        tops = _extract_top_module_names(all_sv)
        if not tops:
            return False, "ERROR: could not find any module in unoptimized RTL"
        top_module = tops[-1]

    top_gold = f"{top_module}_gold"
    top_gate = f"{top_module}_gate"

    # Collect ALL module names so instantiations are renamed too
    all_module_names: set[str] = set()
    for sv_text in unoptimized_modules.values():
        all_module_names.update(_extract_top_module_names(sv_text))
    for sv_text in optimized_modules.values():
        all_module_names.update(_extract_top_module_names(sv_text))

    # Suffix module names in every SV text file
    gold_suffixed = {
        mn: _suffix_module_names(sv, "_gold", all_module_names)
        for mn, sv in unoptimized_modules.items()
    }
    gate_suffixed = {
        mn: _suffix_module_names(sv, "_gate", all_module_names)
        for mn, sv in optimized_modules.items()
    }

    with tempfile.TemporaryDirectory(prefix="sva2rtl_formal_") as tmpdir:
        gold_dir = Path(tmpdir) / "gold"
        gate_dir = Path(tmpdir) / "gate"
        gold_dir.mkdir()
        gate_dir.mkdir()

        for mn, sv_text in gold_suffixed.items():
            (gold_dir / f"{mn}.sv").write_text(sv_text)
        for mn, sv_text in gate_suffixed.items():
            (gate_dir / f"{mn}.sv").write_text(sv_text)

        gold_files = " ".join(str(gold_dir / f"{mn}.sv") for mn in gold_suffixed)
        gate_files = " ".join(str(gate_dir / f"{mn}.sv") for mn in gate_suffixed)

        tcl_script = f"""\
read_verilog -sv {gold_files}
read_verilog -sv {gate_files}
proc
flatten
equiv_make {top_gold} {top_gate} equiv
equiv_induct -ignore-unknown-cells equiv
equiv_simple -seq 10 equiv
equiv_status -assert equiv
"""

        tcl_path = Path(tmpdir) / "equiv.ys"
        tcl_path.write_text(tcl_script)

        try:
            result = subprocess.run(
                ["yosys", "-s", str(tcl_path)],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout + "\n" + result.stderr
            passed = result.returncode == 0
            return passed, output
        except subprocess.TimeoutExpired:
            return False, "ERROR: yosys equivalence check timed out"


def check_optimizer_pass(
    unoptimized_root: CheckerNode,
    optimized_root: CheckerNode,
    *,
    timeout: int = 300,
) -> tuple[bool, str]:
    """Verify that *optimized_root* is semantically equivalent to *unoptimized_root*.

    This is the main entry point for formal verification of the optimizer.
    It emits both trees to SystemVerilog text and runs yosys equivalence checking.

    Parameters
    ----------
    unoptimized_root:
        The CheckerNode tree before optimization (from ``compose()``).
    optimized_root:
        The CheckerNode tree after optimization (from ``optimize()``).
    timeout:
        Maximum time for yosys subprocess.

    Returns
    -------
    tuple[bool, str]
        ``(passed, output_text)``.
    """
    from sva2rtl.emitter import emit, emit_all

    # Single module: use emit(); multi-module: use emit_all()
    if unoptimized_root.children:
        unopt_modules = emit_all(unoptimized_root)
        opt_modules = emit_all(optimized_root)
        return run_equiv_check_multi(
            unopt_modules, opt_modules,
            top_module=unoptimized_root.module_name,
            timeout=timeout,
        )
    else:
        unopt_sv = emit(unoptimized_root)
        opt_sv = emit(optimized_root)
        return run_equiv_check(unopt_sv, opt_sv, timeout=timeout)
