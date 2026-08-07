"""Dedicated CLI for open formal verification of a user DUT."""

from __future__ import annotations

from pathlib import Path

import click

from sva2rtl.errors import (
    PropertyNotFound,
    SlangNotFound,
    SvaError,
    UnsupportedConstruct,
)
from sva2rtl.formal_flow import (
    AttemptMode,
    FormalMode,
    FormalRunConfig,
    FormalStatus,
    LogicSemantics,
    build_formal_bundle,
    run_formal_bundle,
    write_unsupported_evidence,
)

_EXIT_CODES = {
    FormalStatus.PROVEN: 0,
    FormalStatus.FAILED: 10,
    FormalStatus.UNKNOWN: 11,
    FormalStatus.UNSUPPORTED: 12,
    FormalStatus.TIMEOUT: 13,
    FormalStatus.ERROR: 1,
}


@click.command()
@click.option(
    "--dut",
    "dut_sources",
    multiple=True,
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Assertion-free DUT SystemVerilog source (repeatable, required)",
)
@click.option(
    "--property-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Separate SVA property source parsed only by slang/sva2rtl",
)
@click.option(
    "--property-source",
    "property_sources",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Additional property/package source kept outside Yosys (repeatable)",
)
@click.option(
    "-F",
    "--filelist",
    "filelists",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Structured slang project filelist (repeatable)",
)
@click.option(
    "-I",
    "--include",
    "include_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="SystemVerilog include directory (repeatable)",
)
@click.option("-D", "--define", "defines", multiple=True, metavar="NAME[=VALUE]")
@click.option(
    "-G",
    "--parameter",
    "parameter_overrides",
    multiple=True,
    metavar="NAME=VALUE",
    help="Atomic top parameter override bound into replay (repeatable)",
)
@click.option(
    "-v",
    "--library-file",
    "library_files",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "-y",
    "--library-dir",
    "library_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("-Y", "--library-extension", "library_extensions", multiple=True)
@click.option("-L", "--library-order", "library_order", multiple=True)
@click.option("--single-unit", is_flag=True, help="Compile project as one unit")
@click.option("--property", "property_name", help="Assertion label, 1-based index, or @line")
@click.option("--top", required=True, help="DUT top module receiving the generated bind")
@click.option("--clock", default="clk", show_default=True, help="Property clock signal")
@click.option("--reset", default="rst_n", show_default=True, help="Active-low reset signal")
@click.option(
    "--mode",
    type=click.Choice([mode.value for mode in FormalMode], case_sensitive=False),
    default=FormalMode.PROVE.value,
    show_default=True,
    help="prove is unbounded; bmc is bounded bug finding and returns UNKNOWN on PASS",
)
@click.option(
    "--attempt-mode",
    type=click.Choice([mode.value for mode in AttemptMode], case_sensitive=False),
    default=AttemptMode.AUTO.value,
    show_default=True,
    help="Represent bounded attempts with an automatic, monitor, or symbolic-witness backend",
)
@click.option("--depth", type=click.IntRange(min=1), default=20, show_default=True)
@click.option("--timeout", "timeout_seconds", type=click.IntRange(min=1), default=120)
@click.option("--engine", default="smtbmc", show_default=True, help="SBY engine token")
@click.option("--solver", default="yices", show_default=True, help="Engine solver token")
@click.option(
    "--logic-semantics",
    type=click.Choice(
        [semantics.value for semantics in LogicSemantics], case_sensitive=False
    ),
    default=LogicSemantics.TWO_STATE.value,
    show_default=True,
    help="Explicit formal value-domain abstraction; X/Z-dependent SVA rejects",
)
@click.option(
    "--output",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Evidence bundle directory",
)
@click.option("--slang-path", default="slang", envvar="SLANG_PATH", show_envvar=True)
@click.option("--sby-path", default="sby", envvar="SBY_PATH", show_envvar=True)
@click.option(
    "--suprove-path",
    default="suprove",
    envvar="SUPROVE_PATH",
    show_envvar=True,
    help="Super Prove executable used by SBY mode live",
)
@click.option(
    "--fairness",
    "fairness_signals",
    multiple=True,
    metavar="SIGNAL",
    help="Explicit GF(signal) user/model fairness assumption (repeatable)",
)
@click.option(
    "--decomposition-certificate",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help=(
        "Schema-v2 replay-bound certificate for an equivalent/stronger "
        "property decomposition"
    ),
)
@click.option(
    "--force",
    is_flag=True,
    help="Replace only a previous marked sva2rtl formal evidence directory",
)
@click.option(
    "--compile-only",
    is_flag=True,
    help="Generate an UNKNOWN replayable bundle without invoking SymbiYosys (exit 11)",
)
@click.version_option(package_name="sva2rtl", prog_name="sva2rtl-formal")
def main(
    dut_sources: tuple[Path, ...],
    property_file: Path,
    property_sources: tuple[Path, ...],
    filelists: tuple[Path, ...],
    include_dirs: tuple[Path, ...],
    defines: tuple[str, ...],
    parameter_overrides: tuple[str, ...],
    library_files: tuple[Path, ...],
    library_dirs: tuple[Path, ...],
    library_extensions: tuple[str, ...],
    library_order: tuple[str, ...],
    single_unit: bool,
    property_name: str | None,
    top: str,
    clock: str,
    reset: str,
    mode: str,
    attempt_mode: str,
    depth: int,
    timeout_seconds: int,
    engine: str,
    solver: str,
    logic_semantics: str,
    output_dir: Path,
    slang_path: str,
    sby_path: str,
    suprove_path: str,
    fairness_signals: tuple[str, ...],
    decomposition_certificate: Path | None,
    force: bool,
    compile_only: bool,
) -> None:
    """Verify a separate SVA property against a real DUT with open tools.

    The original property source is retained as evidence but is never passed to
    Yosys.  Exit codes: 0 PROVEN, 10 FAILED, 11 UNKNOWN (including compile-only),
    12 UNSUPPORTED, 13 TIMEOUT, 1 ERROR, 2 usage/property selection, 3 slang missing.
    """
    config: FormalRunConfig | None = None
    try:
        config = FormalRunConfig(
            dut_sources=dut_sources,
            property_file=property_file,
            property_sources=property_sources,
            filelists=filelists,
            include_dirs=include_dirs,
            defines=defines,
            parameter_overrides=parameter_overrides,
            library_files=library_files,
            library_dirs=library_dirs,
            library_extensions=library_extensions,
            library_order=library_order,
            single_unit=single_unit,
            property_name=property_name,
            top=top,
            clock=clock,
            reset=reset,
            mode=FormalMode(mode.lower()),
            attempt_mode=AttemptMode(attempt_mode.lower()),
            depth=depth,
            timeout_seconds=timeout_seconds,
            engine=engine,
            solver=solver,
            logic_semantics=LogicSemantics(logic_semantics.lower()),
            output_dir=output_dir,
            slang_path=slang_path,
            sby_path=sby_path,
            suprove_path=suprove_path,
            fairness_signals=fairness_signals,
            decomposition_certificate=decomposition_certificate,
            force=force,
        )
        evidence = build_formal_bundle(config)
        result_path = evidence.bundle_dir / "result.json"
        if compile_only:
            click.echo(f"UNKNOWN: formal bundle compiled but not executed: {result_path}")
            raise click.exceptions.Exit(_EXIT_CODES[FormalStatus.UNKNOWN])

        result = run_formal_bundle(evidence)
        click.echo(f"{result.status.value}: {result.message}")
        click.echo(f"Evidence: {result_path}")
        raise click.exceptions.Exit(_EXIT_CODES[result.status])
    except SlangNotFound as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(3) from exc
    except UnsupportedConstruct as exc:
        click.echo(str(exc), err=True)
        if config is not None:
            try:
                result_path = write_unsupported_evidence(config, exc)
            except (FileExistsError, ValueError) as evidence_exc:
                raise click.UsageError(str(evidence_exc)) from evidence_exc
            click.echo(f"Evidence: {result_path}", err=True)
        raise click.exceptions.Exit(_EXIT_CODES[FormalStatus.UNSUPPORTED]) from exc
    except PropertyNotFound as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(2) from exc
    except SvaError as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(1) from exc
    except (FileExistsError, ValueError) as exc:
        raise click.UsageError(str(exc)) from exc
