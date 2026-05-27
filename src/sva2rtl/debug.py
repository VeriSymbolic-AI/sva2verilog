"""Debug utilities for the sva2rtl compiler pipeline.

Provides ``format_dump_tree()`` for the ``--dump-tree`` CLI flag: a structured
text representation of the pre-normalized IR and the post-composition
CheckerNode tree with structural hashes.
"""

from __future__ import annotations

from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    DisableIff,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SignalFunc,
    SVANode,
)

# Params excluded from dump display (positional/presentation metadata)
_DISPLAY_EXCLUDE: frozenset[str] = frozenset(
    {"module_name", "source_loc", "sva2rtl_version", "original_text"}
)


def format_dump_tree(
    ir_node: SVANode,
    checker: CheckerNode,
    hash_map: dict[str, str],
) -> str:
    """Format a structured dump of the IR tree and composition tree.

    Returns a formatted string with two sections:

    1. ``=== Pre-normalized IR ===`` — recursive repr-like dump of the SVANode
       tree showing type name and key fields.

    2. ``=== Composition Tree ===`` — recursive dump of the CheckerNode tree
       showing module name, template, structural hash, and semantic params.

    Parameters
    ----------
    ir_node
        The pre-normalized SVA IR tree (before ``normalize()`` was applied).
    checker
        The composed CheckerNode tree (after ``normalize() -> compose()``).
    hash_map
        Mapping from module_name to 8-char hex structural hash (from
        ``compute_hash_map()``).

    Returns
    -------
    str
        Formatted multi-line string suitable for printing to stdout.
    """
    lines: list[str] = []
    lines.append("=== Pre-normalized IR ===")
    lines.append(_format_ir(ir_node, indent=0))
    lines.append("")
    lines.append("=== Composition Tree ===")
    lines.append(_format_checker(checker, hash_map, indent=0))
    return "\n".join(lines)


def _format_ir(node: SVANode, indent: int) -> str:
    """Recursively format an SVANode tree as indented text.

    Each node shows its type name and key fields.  Indentation increases
    by 2 spaces per nesting level.
    """
    prefix = " " * indent
    lines: list[str] = []

    match node:
        case BoolExpr():
            lines.append(f'{prefix}BoolExpr("{node.text}")')

        case SignalFunc():
            lines.append(
                f"{prefix}SignalFunc({node.func_name}, signal={node.signal}, depth={node.depth})"
            )

        case SeqConcat():
            delays_str = ", ".join(
                f"({d[0]},{d[1]})" for d in node.delays
            )
            lines.append(f"{prefix}SeqConcat(delays=[{delays_str}])")
            for elem in node.elements:
                lines.append(_format_ir(elem, indent + 2))

        case SeqRepetition():
            lines.append(
                f"{prefix}SeqRepetition(rep_min={node.rep_min}, rep_max={node.rep_max})"
            )
            lines.append(_format_ir(node.expr, indent + 2))

        case PropImplication():
            overlap_str = "overlapping" if node.overlapping else "non-overlapping"
            lines.append(f"{prefix}PropImplication({overlap_str})")
            lines.append(f"{prefix}  antecedent:")
            lines.append(_format_ir(node.antecedent, indent + 4))
            lines.append(f"{prefix}  consequent:")
            lines.append(_format_ir(node.consequent, indent + 4))

        case DisableIff():
            if isinstance(node.condition, BoolExpr):
                cond_text = node.condition.text
            else:
                cond_text = type(node.condition).__name__
            lines.append(f"{prefix}DisableIff(condition={cond_text})")
            lines.append(f"{prefix}  body:")
            lines.append(_format_ir(node.body, indent + 4))

        case _:
            lines.append(f"{prefix}{type(node).__name__}()")

    return "\n".join(lines)


def _format_checker(
    node: CheckerNode,
    hash_map: dict[str, str],
    indent: int,
) -> str:
    """Recursively format a CheckerNode tree as indented text.

    Each node shows: ``CheckerNode: <module_name> (<template>) [hash:<8hex>]``
    followed by semantic params (excluding volatile metadata) and children.
    Indentation increases by 2 spaces per nesting level.
    """
    prefix = " " * indent
    lines: list[str] = []

    node_hash = hash_map.get(node.module_name, "????????")
    lines.append(
        f"{prefix}CheckerNode: {node.module_name} ({node.template_name}) [hash:{node_hash}]"
    )

    # Show semantic params (filter out display-excluded keys)
    for k, v in sorted(node.params.items()):
        if k not in _DISPLAY_EXCLUDE:
            lines.append(f"{prefix}  {k}: {v}")

    # Recurse into children
    for child in node.children:
        lines.append(_format_checker(child, hash_map, indent + 2))

    return "\n".join(lines)
