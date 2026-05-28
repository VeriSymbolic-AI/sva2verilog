"""CLI entry point for sva2rtl — wires the full compiler pipeline via click.

Exit code mapping (requirement CLI-05):
    0 — Success: output written successfully
    1 — SvaCompileError / InternalError / unexpected exception
    2 — UnsupportedConstruct (SVA operator not yet implemented, with source loc)
    3 — SlangNotFound (binary absent from PATH or --slang-path)

Pipeline order (requirement CLI-06):
    invoke_slang -> import_assertion -> normalize -> compose -> optimize -> emit -> write_output
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all, write_output, write_output_dir
from sva2rtl.errors import SlangNotFound, SvaError, UnsupportedConstruct
from sva2rtl.frontend import invoke_slang
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize


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
@click.option(
    "--dump-tree",
    is_flag=True,
    default=False,
    help="Print CheckerNode composition tree and exit (no RTL emitted)",
)
@click.option(
    "--no-optimize",
    is_flag=True,
    default=False,
    help="Skip optimization passes (emit unoptimized output)",
)
def main(
    input_file: str,
    output: str | None,
    slang_path: str,
    dump_tree: bool,
    no_optimize: bool,
) -> None:
    """Compile an SVA property file to a synthesizable SystemVerilog monitor.

    INPUT_FILE is a SystemVerilog file containing one or more concurrent
    assertion statements (``assert property (...)``).
    """
    try:
        ast = invoke_slang(Path(input_file), slang_path)
        node, clock, original_text, label = import_assertion(ast)
        raw_node = node
        node = normalize(node)
        checker_node = compose(node, clock, label, original_text)
        unoptimized_checker = checker_node

        if not no_optimize:
            checker_node = optimize(checker_node)

        if dump_tree:
            from sva2rtl.composer import compute_hash_map
            from sva2rtl.debug import format_dump_tree

            hash_map = compute_hash_map(checker_node)
            click.echo(
                format_dump_tree(
                    raw_node,
                    checker_node,
                    hash_map,
                    unoptimized_checker=(
                        unoptimized_checker if not no_optimize else None
                    ),
                )
            )
            sys.exit(0)

        if checker_node.children:
            # Hierarchical output: write one .sv file per module to a directory
            modules = emit_all(checker_node)
            out_dir = Path(output) if output else Path(".")
            write_output_dir(modules, out_dir)
        else:
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
