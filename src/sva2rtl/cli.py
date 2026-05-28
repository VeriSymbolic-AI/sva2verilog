"""CLI entry point for sva2rtl — wires the full compiler pipeline via click.

Exit code mapping (requirement CLI-05):
    0 — Success: output written successfully
    1 — SvaCompileError / InternalError / unexpected exception
    2 — UnsupportedConstruct / PropertyNotFound (SVA operator not yet implemented, with source loc)
    3 — SlangNotFound (binary absent from PATH or --slang-path)

Pipeline order (requirement CLI-06):
    invoke_slang -> [--dump-ast] -> import_all_assertions -> [--property filter]
    -> normalize -> [--dump-ir] -> compose -> optimize -> [--dump-tree] -> emit -> write_output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from sva2rtl.ast_importer import import_all_assertions
from sva2rtl.composer import compose
from sva2rtl.debug import format_dump_ir
from sva2rtl.emitter import emit, emit_all, write_output, write_output_dir
from sva2rtl.errors import (
    PropertyNotFound,
    SlangNotFound,
    SvaError,
    UnsupportedConstruct,
)
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import ClockSpec, SVANode
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
    "--dump-ast",
    is_flag=True,
    default=False,
    help="Print the raw slang JSON AST and exit (no RTL emitted)",
)
@click.option(
    "--dump-ir",
    is_flag=True,
    default=False,
    help="Print the normalized IR tree and exit (no RTL emitted)",
)
@click.option(
    "--dump-tree",
    is_flag=True,
    default=False,
    help="Print CheckerNode composition tree and exit (no RTL emitted)",
)
@click.option(
    "--property",
    "property_name",
    type=str,
    default=None,
    help="Compile only the assertion with this label (default: all)",
)
@click.option(
    "--verilog",
    is_flag=True,
    default=False,
    help="Emit Verilog-2001 compatible output instead of SystemVerilog",
)
@click.option(
    "--no-optimize",
    is_flag=True,
    default=False,
    help="Skip optimization passes (emit unoptimized output)",
)
@click.version_option(package_name="sva2rtl", prog_name="sva2rtl")
def main(
    input_file: str,
    output: str | None,
    slang_path: str,
    dump_ast: bool,
    dump_ir: bool,
    dump_tree: bool,
    property_name: str | None,
    verilog: bool,
    no_optimize: bool,
) -> None:
    """Compile an SVA property file to a synthesizable SystemVerilog monitor.

    INPUT_FILE is a SystemVerilog file containing one or more concurrent
    assertion statements (``assert property (...)``).
    """
    try:
        ast = invoke_slang(Path(input_file), slang_path)

        # --dump-ast: print raw JSON AST and exit
        if dump_ast:
            click.echo(json.dumps(ast, indent=2))
            sys.exit(0)

        # Import all assertions
        assertions = import_all_assertions(ast)

        # --property filter: select matching assertion
        if property_name is not None:
            matched: list[tuple[SVANode, ClockSpec, str, str | None]] = [
                (node, clock, text, label)
                for node, clock, text, label in assertions
                if label == property_name
            ]
            if not matched:
                available_labels = [
                    label for _, _, _, label in assertions if label is not None
                ]
                raise PropertyNotFound(
                    message=f"property '{property_name}' not found",
                    property_name=property_name,
                    available=available_labels,
                )
            assertions = matched

        # Process single or multiple assertions
        if len(assertions) == 1:
            node, clock, original_text, label = assertions[0]
            raw_node = node
            node = normalize(node)

            # --dump-ir: print normalized IR and exit
            if dump_ir:
                click.echo(format_dump_ir(node))
                sys.exit(0)

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
                modules = emit_all(checker_node, verilog_mode=verilog)
                out_dir = Path(output) if output else Path(".")
                write_output_dir(modules, out_dir)
            else:
                sv_text = emit(checker_node, verilog_mode=verilog)
                write_output(sv_text, Path(output) if output else None)
        else:
            # Multi-property: normalize all, optionally dump-ir for first
            normalized_assertions = []
            for node, clock, text, label in assertions:
                raw_node = node
                node = normalize(node)
                normalized_assertions.append((node, clock, text, label, raw_node))

            # --dump-ir: print normalized IR for all assertions
            if dump_ir:
                parts: list[str] = []
                for norm_node, _clock, _text, _label, _raw in normalized_assertions:
                    parts.append(format_dump_ir(norm_node))
                click.echo("\n\n".join(parts))
                sys.exit(0)

            # Compose, optimize, and emit each assertion
            all_modules: dict[str, str] = {}
            for norm_node, clock, text, label, raw_node in normalized_assertions:
                checker_node = compose(norm_node, clock, label, text)
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
                            unoptimized_checker=None,
                        )
                    )
                    continue

                modules = emit_all(checker_node, verilog_mode=verilog)
                all_modules.update(modules)

            if dump_tree:
                sys.exit(0)

            if all_modules:
                out_dir = Path(output) if output else Path(".")
                write_output_dir(all_modules, out_dir)

        sys.exit(0)

    except SlangNotFound as exc:
        click.echo(str(exc), err=True)
        sys.exit(3)

    except PropertyNotFound as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    except UnsupportedConstruct as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    except SvaError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)

    except Exception as exc:  # noqa: BLE001
        click.echo(f"internal error: {exc}", err=True)
        sys.exit(1)
