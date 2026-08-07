"""Capability report for the open formal toolchain."""

from __future__ import annotations

import json

import click

from sva2rtl.formal_toolchain import probe_formal_toolchain


@click.command()
@click.option("--slang-path", default="slang", envvar="SLANG_PATH", show_envvar=True)
@click.option("--sby-path", default="sby", envvar="SBY_PATH", show_envvar=True)
@click.option("--suprove-path", default="suprove", envvar="SUPROVE_PATH", show_envvar=True)
@click.option(
    "--solver-path",
    default="yices-smt2",
    envvar="SVA2RTL_SOLVER_PATH",
    show_envvar=True,
)
@click.option("--require-live", is_flag=True, help="Exit nonzero unless open liveness is ready")
@click.option("--json-output", is_flag=True, help="Emit the capability report as JSON")
def main(
    slang_path: str,
    sby_path: str,
    suprove_path: str,
    solver_path: str,
    require_live: bool,
    json_output: bool,
) -> None:
    """Report safety and liveness readiness without exposing absolute tool paths."""
    toolchain = probe_formal_toolchain(
        slang_path=slang_path,
        sby_path=sby_path,
        suprove_path=suprove_path,
        solver_path=solver_path,
    )
    safety_ready = all(
        toolchain[role]["available"] for role in ("slang", "sby", "yosys", "yosys-smtbmc", "solver")
    )
    live_ready = safety_ready and bool(toolchain["suprove"]["available"])
    report = {
        "schema_version": 1,
        "safety_ready": safety_ready,
        "liveness_ready": live_ready,
        "tools": toolchain,
        "guidance": (
            "open safety and liveness are ready"
            if live_ready
            else (
                "open safety is ready; use the pinned Linux OSS CAD Suite runner "
                "for Super Prove-backed liveness"
                if safety_ready
                else "install slang, Yosys/SymbiYosys, and optionally Super Prove"
            )
        ),
    }
    if json_output:
        click.echo(json.dumps(report, indent=2, sort_keys=True))
    else:
        click.echo(f"Safety: {'READY' if safety_ready else 'UNAVAILABLE'}")
        click.echo(f"Liveness: {'READY' if live_ready else 'UNAVAILABLE'}")
        for role, identity in sorted(toolchain.items()):
            state = "available" if identity["available"] else "missing"
            click.echo(f"{role}: {state}; {identity['version']}")
        click.echo(str(report["guidance"]))
    if require_live and not live_ready:
        raise click.exceptions.Exit(11)
    if not safety_ready:
        raise click.exceptions.Exit(1)
