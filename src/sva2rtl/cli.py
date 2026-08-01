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
from sva2rtl.emitter import (
    emit,
    emit_all,
    merge_module_outputs,
    write_output,
    write_output_dir,
)
from sva2rtl.errors import (
    PropertyNotFound,
    SlangNotFound,
    SvaError,
    UnsupportedConstruct,
)
from sva2rtl.formal import check_optimizer_pass
from sva2rtl.frontend import invoke_slang
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_KNOWN_SV_EXTENSIONS = frozenset({".sv", ".v", ".svh"})

def _resolve_output_mode(
    output: str | None,
    *,
    multi_prop: bool,
) -> str | None:
    """Resolve --output path as file or directory mode.

    Returns the resolved output path or None.
    Incompatible combinations raise click.UsageError.
    """
    if output is None:
        if multi_prop:
            raise click.UsageError(
                "hierarchical or multi-assertion output requires --output DIRECTORY"
            )
        return None
    if output.endswith("/"):
        return output
    p = Path(output)
    if p.suffix in _KNOWN_SV_EXTENSIONS:
        if multi_prop:
            raise click.UsageError(
                f"--output looks like a file path ('{output}') but input has "
                "multiple assertions. Use a directory instead."
            )
        return output
    return output


@click.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output file for one leaf, or directory for hierarchical/multi output",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Replace differing generated files that already exist",
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
    "--experimental-multiclock",
    is_flag=True,
    default=False,
    help="Allow prototype multi-clock CDC output that may lose/coalesce events",
)
@click.option(
    "--no-optimize",
    is_flag=True,
    default=False,
    help="Skip optimization passes (emit unoptimized output)",
)
@click.option(
    "--verify",
    "verify_flag",
    is_flag=True,
    default=False,
    help="Run yosys formal equivalence check between unoptimized and optimized RTL",
)
@click.version_option(package_name="sva2rtl", prog_name="sva2rtl")
def main(
    input_file: str,
    output: str | None,
    force: bool,
    slang_path: str,
    dump_ast: bool,
    dump_ir: bool,
    dump_tree: bool,
    property_name: str | None,
    verilog: bool,
    experimental_multiclock: bool,
    no_optimize: bool,
    verify_flag: bool,
) -> None:
    """Compile an SVA property file to a synthesizable SystemVerilog monitor.

    INPUT_FILE is a SystemVerilog file containing one or more concurrent
    assertion statements (``assert property (...)``).
    """
    try:
        # HARDEN-08: --verilog is incompatible with --dump-* flags
        if verilog and (dump_ast or dump_ir or dump_tree):
            dump_flags = []
            if dump_ast:
                dump_flags.append("--dump-ast")
            if dump_ir:
                dump_flags.append("--dump-ir")
            if dump_tree:
                dump_flags.append("--dump-tree")
            raise click.UsageError(
                f"--verilog cannot be combined with {'/'.join(dump_flags)}. "
                "Dump output is always in SystemVerilog mode. "
                "Run --verilog separately without dump flags for V2001-style RTL."
            )

        ast = invoke_slang(Path(input_file), slang_path)

        # --dump-ast: print raw JSON AST and exit
        if dump_ast:
            click.echo(json.dumps(ast, indent=2))
            sys.exit(0)

        # Import all assertions
        assertions = import_all_assertions(ast)

        # --property filter: select matching assertion
        if property_name is not None:
            # HARDEN-06: three match modes — index, source-line, label
            if property_name.isdigit():
                # Mode 1: numeric → 1-based index
                idx = int(property_name)
                if 1 <= idx <= len(assertions):
                    assertions = [assertions[idx - 1]]
                else:
                    raise PropertyNotFound(
                        message=f"property index {idx} out of range (1..{len(assertions)})",
                        property_name=property_name,
                        available=[str(i) for i in range(1, len(assertions) + 1)],
                    )
            elif property_name.startswith("@") and property_name[1:].isdigit():
                # Mode 2: @N → source line
                line_num = int(property_name[1:])
                matched = []
                for node, clock, text, label in assertions:
                    sl = getattr(node, "source_loc", None)
                    if sl is not None and sl.line == line_num:
                        matched.append((node, clock, text, label))
                if not matched:
                    available_lines = sorted(set(
                        str(getattr(n, "source_loc").line)
                        for n, _, _, _ in assertions
                        if getattr(n, "source_loc", None) is not None
                    ))
                    raise PropertyNotFound(
                        message=f"no assertion found at line {line_num}",
                        property_name=property_name,
                        available=available_lines,
                    )
                assertions = matched
            else:
                # Mode 3: label name exact match
                matched = [
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

            # --verify: run yosys formal equivalence check
            if verify_flag and not no_optimize:
                passed, yosys_output = check_optimizer_pass(
                    unoptimized_checker, checker_node
                )
                click.echo(yosys_output)
                if not passed:
                    click.echo(
                        "ERROR: Formal equivalence check FAILED — "
                        "optimized RTL is not equivalent to unoptimized RTL.",
                        err=True,
                    )
                    sys.exit(1)
                click.echo("PASS: Formal equivalence check — optimized RTL is equivalent.")

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

            # HARDEN-07: resolve output mode
            out_path_str = _resolve_output_mode(
                output, multi_prop=bool(checker_node.children)
            )
            if checker_node.children:
                modules = emit_all(
                    checker_node,
                    verilog_mode=verilog,
                    allow_experimental_multiclock=experimental_multiclock,
                )
                out_dir = Path(out_path_str) if out_path_str else Path(".")
                write_output_dir(modules, out_dir, force=force)
            else:
                sv_text = emit(checker_node, verilog_mode=verilog)
                out_path = Path(out_path_str) if out_path_str else None
                write_output(sv_text, out_path, force=force)
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
                # HARDEN-05: compute unoptimized_checker per-assertion
                unopt = checker_node
                if not no_optimize:
                    checker_node = optimize(checker_node)

                # --verify: run formal equivalence check per assertion
                if verify_flag and not no_optimize:
                    passed, yosys_output = check_optimizer_pass(unopt, checker_node)
                    click.echo(yosys_output)
                    if not passed:
                        click.echo(
                            "ERROR: Formal equivalence check FAILED for "
                            f"assertion '{label or '<unlabeled>'}' — "
                            "optimized RTL is not equivalent to unoptimized RTL.",
                            err=True,
                        )
                        sys.exit(1)
                    click.echo(
                        f"PASS: Formal equivalence check for '{label or '<unlabeled>'}'."
                    )

                if dump_tree:
                    from sva2rtl.composer import compute_hash_map
                    from sva2rtl.debug import format_dump_tree

                    hash_map = compute_hash_map(checker_node)
                    click.echo(
                        format_dump_tree(
                            raw_node,
                            checker_node,
                            hash_map,
                            unoptimized_checker=unopt if not no_optimize else None,
                        )
                    )
                    continue

                modules = emit_all(
                    checker_node,
                    verilog_mode=verilog,
                    allow_experimental_multiclock=experimental_multiclock,
                )
                merge_module_outputs(all_modules, modules)

            if dump_tree:
                sys.exit(0)

            if all_modules:
                # HARDEN-07: resolve output mode
                out_path_str = _resolve_output_mode(output, multi_prop=True)
                out_dir = Path(out_path_str) if out_path_str else Path(".")
                write_output_dir(all_modules, out_dir, force=force)

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

    except click.UsageError:
        raise

    except Exception as exc:  # noqa: BLE001
        click.echo(f"internal error: {exc}", err=True)
        sys.exit(1)
