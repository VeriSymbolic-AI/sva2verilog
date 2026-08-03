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
    build_formal_bundle,
    run_formal_bundle,
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
    "--output",
    "output_dir",
    required=True,
    type=click.Path(path_type=Path),
    help="Evidence bundle directory",
)
@click.option("--slang-path", default="slang", envvar="SLANG_PATH", show_envvar=True)
@click.option("--sby-path", default="sby", envvar="SBY_PATH", show_envvar=True)
@click.option("--force", is_flag=True, help="Replace an existing evidence directory")
@click.option(
    "--compile-only",
    is_flag=True,
    help="Generate the replayable bundle without invoking SymbiYosys",
)
@click.version_option(package_name="sva2rtl", prog_name="sva2rtl-formal")
def main(
    dut_sources: tuple[Path, ...],
    property_file: Path,
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
    output_dir: Path,
    slang_path: str,
    sby_path: str,
    force: bool,
    compile_only: bool,
) -> None:
    """Verify a separate SVA property against a real DUT with open tools.

    The original property source is retained as evidence but is never passed to
    Yosys.  Exit codes: 0 PROVEN/compiled, 10 FAILED, 11 UNKNOWN,
    12 UNSUPPORTED, 13 TIMEOUT, 1 ERROR, 2 usage/unsupported source, 3 slang missing.
    """
    try:
        config = FormalRunConfig(
            dut_sources=dut_sources,
            property_file=property_file,
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
            output_dir=output_dir,
            slang_path=slang_path,
            sby_path=sby_path,
            force=force,
        )
        evidence = build_formal_bundle(config)
        result_path = evidence.bundle_dir / "result.json"
        if compile_only:
            click.echo(f"UNKNOWN: formal bundle compiled but not executed: {result_path}")
            return

        result = run_formal_bundle(evidence)
        click.echo(f"{result.status.value}: {result.message}")
        click.echo(f"Evidence: {result_path}")
        raise click.exceptions.Exit(_EXIT_CODES[result.status])
    except SlangNotFound as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(3) from exc
    except (PropertyNotFound, UnsupportedConstruct) as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(2) from exc
    except SvaError as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(1) from exc
    except (FileExistsError, ValueError) as exc:
        raise click.UsageError(str(exc)) from exc
