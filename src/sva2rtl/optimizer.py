"""RTL optimization passes — area-efficient transformations on the CheckerNode tree.

Pure CheckerNode-to-CheckerNode preprocessing passes that run after ``compose()``
and before ``emit()``.  Bottom-up single-pass traversal (O(n) on tree size) for
each pass: each node is visited after its children are transformed.

Guarantees:
- **Idempotent after convergence:** ``optimize(optimize(x))`` has the same
  ``structural_hash`` as ``optimize(x)``
- **Semantic-preserving:** All rules are hardware-equivalent transformations;
  simulation oracle parity tests validate correctness
- **Golden-file safe:** Optimizer is a no-op for trees without optimizable patterns

Pass pipeline (fixed order per D-03):
    constant_fold -> concat_merge -> cse -> counter_merge -> dead_node

After all passes complete, the tree is re-run once more if the structural hash
changed (max 2 total iterations, D-03).  This catches cascading opportunities
(e.g., concat_merge may expose new constant_fold candidates).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from sva2rtl.composer import structural_hash
from sva2rtl.ir import CheckerNode


def optimize(root: CheckerNode) -> CheckerNode:
    """Run the full optimization pipeline on a composed CheckerNode tree.

    Orchestrates five passes in fixed order: constant_fold, concat_merge,
    cse, counter_merge, dead_node.  If the tree changes after the first run
    (detected via structural_hash comparison), the full pipeline runs once
    more (maximum 2 total iterations, D-03).

    Parameters
    ----------
    root
        The root ``CheckerNode`` returned by ``compose()``.

    Returns
    -------
    CheckerNode
        The optimized tree.  Structurally identical to ``root`` if no
        optimization opportunities exist.
    """
    max_iterations = 2
    for _ in range(max_iterations):
        before_hash = structural_hash(root)
        root = constant_fold(root)
        root = concat_merge(root)
        root = cse(root)
        root = counter_merge(root)
        root = dead_node(root)
        after_hash = structural_hash(root)
        if before_hash == after_hash:
            # Tree reached a fixed point — no further improvement possible
            break
    return root


# ── Pass implementations ──────────────────────────────────────────────────


def constant_fold(root: CheckerNode) -> CheckerNode:
    """Propagate literal boolean constants through the CheckerNode tree.

    Rules applied (MVP, Phase 5):
    - ``bool_expr`` node with ``params["bool_expr"]`` equal to ``"1'b1"`` or
      ``"1"`` is tagged as constant-true (sets ``params["_const_true"]="1"``).
    - ``bool_expr`` node with ``params["bool_expr"]`` equal to ``"1'b0"`` or
      ``"0"`` is tagged as constant-false (sets ``params["_const_false"]="1"``).

    Constant-false tags are consumed by the ``dead_node`` pass (Phase 5.3).
    Returns the tree unchanged if no literal boolean constants are found.

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree to fold.

    Returns
    -------
    CheckerNode
        Partially constant-folded tree.
    """

    def _fold(node: CheckerNode) -> CheckerNode:
        if node.template_name == "bool_expr":
            expr = node.params.get("bool_expr", "")
            if expr in ("1'b1", "1"):
                new_params = {**node.params, "_const_true": "1"}
                return dataclasses.replace(node, params=new_params)
            if expr in ("1'b0", "0"):
                new_params = {**node.params, "_const_false": "1"}
                return dataclasses.replace(node, params=new_params)
        return node

    return _walk_bottom_up(root, _fold)


def concat_merge(root: CheckerNode) -> CheckerNode:
    """Merge adjacent concat_delay nodes within seq_concat_top nodes.

    Finds ``seq_concat_top`` nodes whose children contain directly adjacent
    pairs of ``concat_delay`` nodes and replaces each such pair with a single
    merged ``concat_delay`` node:

        ##3 ##2  →  ##5   (delay_min/max add; cnt_width recomputed)

    Only directly adjacent ``concat_delay`` nodes are merged — ``bool_expr``
    nodes between two delays prevent the merge (the intervening check is
    semantically necessary).

    Three or more consecutive ``concat_delay`` nodes are merged greedily
    left-to-right (e.g., ##1 ##2 ##3 → ##3 ##3 → ##6 in two passes, or
    ##6 in a single left-to-right scan of this pass).

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree.

    Returns
    -------
    CheckerNode
        Tree with adjacent delays merged.  Returned unchanged if no
        ``seq_concat_top`` nodes exist or no adjacent delays are found.
    """

    def _merge_children(
        children: tuple[CheckerNode, ...],
    ) -> tuple[CheckerNode, ...]:
        """Merge adjacent concat_delay pairs in a children tuple."""
        if len(children) < 2:
            return children

        result: list[CheckerNode] = []
        i = 0
        while i < len(children):
            node = children[i]
            if (
                node.template_name == "concat_delay"
                and i + 1 < len(children)
                and children[i + 1].template_name == "concat_delay"
            ):
                # Merge this pair
                next_node = children[i + 1]
                merged_min = int(node.params["delay_min"]) + int(
                    next_node.params["delay_min"]
                )
                merged_max = int(node.params["delay_max"]) + int(
                    next_node.params["delay_max"]
                )
                # cnt_width = ceil(log2(merged_max + 1)), minimum 1 bit
                cnt_width = max(1, merged_max.bit_length())
                merged_params: dict[str, str] = {
                    **node.params,
                    "delay_min": str(merged_min),
                    "delay_max": str(merged_max),
                    "cnt_width": str(cnt_width),
                }
                merged_name = f"sva_delay_{merged_min}_{merged_max}"
                merged_node = dataclasses.replace(
                    node,
                    module_name=merged_name,
                    params=merged_params,
                )
                result.append(merged_node)
                i += 2  # consume both children
            else:
                result.append(node)
                i += 1

        return tuple(result)

    def _merge_node(node: CheckerNode) -> CheckerNode:
        if node.template_name != "seq_concat_top":
            return node
        new_children = _merge_children(node.children)
        if new_children == node.children:
            return node
        return dataclasses.replace(node, children=new_children)

    return _walk_bottom_up(root, _merge_node)


def cse(root: CheckerNode) -> CheckerNode:
    """Common subexpression elimination — stub (Phase 5.2).

    Identifies subtrees with identical structural hashes and replaces
    duplicates with references to a single shared instance.  Not yet
    implemented; returns the tree unchanged.

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree.

    Returns
    -------
    CheckerNode
        Unchanged tree (stub implementation).
    """
    return root


def counter_merge(root: CheckerNode) -> CheckerNode:
    """Counter sharing across identical delay parameters — stub (Phase 5.2).

    Shares a single counter module across multiple consumers that need the
    same ``(delay_min, delay_max)`` window.  Not yet implemented; returns
    the tree unchanged.

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree.

    Returns
    -------
    CheckerNode
        Unchanged tree (stub implementation).
    """
    return root


def dead_node(root: CheckerNode) -> CheckerNode:
    """Dead node elimination — stub (Phase 5.3).

    Prunes unreachable nodes identified by ``constant_fold`` (nodes tagged
    with ``_const_false``).  Not yet implemented; returns the tree unchanged.

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree.

    Returns
    -------
    CheckerNode
        Unchanged tree (stub implementation).
    """
    return root


# ── Internal helpers ──────────────────────────────────────────────────────


def _walk_bottom_up(
    node: CheckerNode, fn: Callable[[CheckerNode], CheckerNode]
) -> CheckerNode:
    """Recursively apply *fn* to every node bottom-up.

    Children are transformed first; then *fn* is applied to the (potentially
    updated) parent.  Uses ``dataclasses.replace()`` to construct new nodes
    only when children actually change, preserving Python object identity for
    unchanged subtrees.

    Parameters
    ----------
    node
        The current ``CheckerNode`` to transform.
    fn
        A pure function that takes a ``CheckerNode`` and returns a
        (possibly new) ``CheckerNode``.

    Returns
    -------
    CheckerNode
        The transformed node.
    """
    if not node.children:
        # Leaf node — apply fn directly
        return fn(node)

    new_children = tuple(_walk_bottom_up(child, fn) for child in node.children)
    if new_children != node.children:
        node = dataclasses.replace(node, children=new_children)
    return fn(node)
