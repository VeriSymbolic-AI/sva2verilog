"""CLI entry point for sva2rtl — wires the full compiler pipeline via click.

Exit code mapping (requirement CLI-05):
    0 — Success: output written successfully
    1 — SvaCompileError / InternalError / unexpected exception
    2 — UnsupportedConstruct (SVA operator not yet implemented, with source loc)
    3 — SlangNotFound (binary absent from PATH or --slang-path)

Pipeline order (requirement CLI-06):
    invoke_slang -> import_assertion -> compose -> emit -> write_output
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, write_output
from sva2rtl.errors import SlangNotFound, SvaError, UnsupportedConstruct
from sva2rtl.frontend import invoke_slang


@click.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file path (default: stdout)",
)
@click.option(
    "--slang-path",
    default="slang",
    envvar="SLANG_PATH",
    help="Path to slang binary (default: slang on PATH)",
    show_envvar=True,
)
def main(input_file: str, output: str | None, slang_path: str) -> None:
    """Compile an SVA property file to a synthesizable SystemVerilog monitor.

    INPUT_FILE is a SystemVerilog file containing one or more concurrent
    assertion statements (``assert property (...)``).
    """
    try:
        ast = invoke_slang(Path(input_file), slang_path)
        node, clock, original_text, label = import_assertion(ast)
        checker_node = compose(node, clock, label, original_text)
        sv_text = emit(checker_node)
        write_output(sv_text, Path(output) if output else None)
        sys.exit(0)

    except SlangNotFound as exc:
        click.echo(str(exc), err=True)
        sys.exit(3)

    except UnsupportedConstruct as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    except SvaError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        click.echo(f"internal error: {exc}", err=True)
        sys.exit(1)
