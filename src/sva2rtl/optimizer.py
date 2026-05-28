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
import logging
from collections.abc import Callable

from sva2rtl.composer import structural_hash
from sva2rtl.ir import CheckerNode

_LOG = logging.getLogger(__name__)


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
    """Common subexpression elimination — deduplicate identical subtrees.

    Identifies subtrees with identical ``structural_hash`` values and
    replaces all occurrences after the first with a single canonical
    ``CheckerNode`` whose ``module_name`` carries the ``sva_cse_`` prefix.
    The emitter already deduplicates module *definitions* by ``module_name``
    (``_emit_recursive`` uses a ``results`` dict keyed by module name), so
    giving all duplicate nodes the same canonical name naturally produces one
    emitted ``.sv`` file with multiple instantiations.

    All nodes with the same structural hash become the **same Python object**
    in the rebuilt tree (Python object identity: ``id(a) == id(b)``).  This
    enables downstream emitter seen-sets to detect sharing by identity as well
    as by module name.

    Root-level protection: the root node is never renamed or replaced, even if
    its structural hash matches a descendant.

    Sanity check: if two nodes share the same ``cse_origin`` tag (from Phase 3
    named-sequence expansion) but have *different* structural hashes, a warning
    is logged (indicates a named-sequence expansion bug, not a CSE bug).

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree returned by ``compose()``.

    Returns
    -------
    CheckerNode
        Rebuilt tree with shared canonical nodes for all duplicate subtrees.
        Returned unchanged (same object) if no duplicates exist.
    """
    # Step 1: walk tree, group nodes by structural hash
    hash_groups = _build_hash_groups(root)
    root_hash = structural_hash(root)

    # Step 2: identify merge candidates (2+ occurrences, not root)
    merge_hashes: set[str] = {
        h
        for h, nodes in hash_groups.items()
        if len(nodes) >= 2 and h != root_hash
    }

    if not merge_hashes:
        return root

    # Step 3: build canonical map  hash → canonical CheckerNode (CSE-named)
    canonical_map: dict[str, CheckerNode] = {}
    for h in merge_hashes:
        representative = hash_groups[h][0]
        canonical_name = _cse_canonical_name(representative)
        canonical_map[h] = dataclasses.replace(representative, module_name=canonical_name)

    # Step 4: sanity-check cse_origin field (D-05)
    origin_hash: dict[str, str] = {}  # cse_origin → structural hash
    for h, nodes in hash_groups.items():
        for node in nodes:
            if node.cse_origin is not None:
                prev = origin_hash.get(node.cse_origin)
                if prev is not None and prev != h:
                    _LOG.warning(
                        "CSE sanity: nodes with cse_origin=%r have different "
                        "structural hashes (%s vs %s) — possible named-sequence "
                        "expansion bug",
                        node.cse_origin,
                        prev,
                        h,
                    )
                origin_hash[node.cse_origin] = h

    # Step 5: rebuild tree, sharing canonical nodes for all duplicate subtrees
    rebuilt_canonical: dict[str, CheckerNode] = {}
    return _rebuild_with_cse(root, canonical_map, root_hash, rebuilt_canonical)


def counter_merge(root: CheckerNode) -> CheckerNode:
    """Counter sharing across identical delay parameters.

    Shares a single counter module across multiple ``concat_delay`` consumers
    that have the same ``(delay_min, delay_max)`` tuple AND the same
    ``structural_hash`` (i.e., same clock and all params match).

    **MVP conservative approach (Phase 5.2):** only merges counters with
    identical structural hashes.  Since ``cse()`` runs before this pass and
    already handles all same-hash nodes, ``counter_merge`` is effectively a
    safety-net no-op for single-property trees.  Its primary value is for
    future cross-property sharing (D-11) where two separate root trees share a
    counter that ``cse()`` can't see (because CSE operates per-root).

    Counter nodes that are already unified by CSE (same ``module_name``) are
    left untouched.  Counters with different ``(delay_min, delay_max)`` values
    are never merged.

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree.

    Returns
    -------
    CheckerNode
        Rebuilt tree with shared counter modules where applicable.
        Returned unchanged if no merge opportunities exist (common case).
    """
    # Collect all concat_delay nodes
    delay_nodes: list[CheckerNode] = []
    _collect_by_template(root, "concat_delay", delay_nodes)

    if not delay_nodes:
        return root

    # Group by structural hash (conservative — only merge identical counters)
    hash_to_nodes: dict[str, list[CheckerNode]] = {}
    for node in delay_nodes:
        h = structural_hash(node)
        if h not in hash_to_nodes:
            hash_to_nodes[h] = []
        hash_to_nodes[h].append(node)

    # Find groups where CSE hasn't already unified them (different module_names)
    canonical_map: dict[str, CheckerNode] = {}
    for h, nodes in hash_to_nodes.items():
        if len(nodes) < 2:
            continue
        module_names = {n.module_name for n in nodes}
        if len(module_names) == 1:
            # All already share the same module_name (CSE handled it)
            continue
        # CSE missed these — give them a canonical counter name
        representative = nodes[0]
        min_v = representative.params.get("delay_min", "0")
        max_v = representative.params.get("delay_max", "0")
        canonical_name = f"sva_cse_counter_{min_v}_{max_v}"
        canonical_map[h] = dataclasses.replace(representative, module_name=canonical_name)

    if not canonical_map:
        return root

    # Rebuild tree substituting canonical counter nodes
    root_hash = structural_hash(root)
    rebuilt_canonical: dict[str, CheckerNode] = {}
    return _rebuild_with_cse(root, canonical_map, root_hash, rebuilt_canonical)


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


def _build_hash_groups(root: CheckerNode) -> dict[str, list[CheckerNode]]:
    """Walk tree recursively, returning a dict[structural_hash → [nodes]].

    Every node in the tree (including root) is grouped by its structural hash.
    Nodes with the same hash are CSE merge candidates.

    Parameters
    ----------
    root
        Root of the ``CheckerNode`` tree.

    Returns
    -------
    dict[str, list[CheckerNode]]
        Mapping from 8-char hex structural hash to the list of nodes sharing
        that hash.
    """
    groups: dict[str, list[CheckerNode]] = {}

    def _walk(node: CheckerNode) -> None:
        h = structural_hash(node)
        if h not in groups:
            groups[h] = []
        groups[h].append(node)
        for child in node.children:
            _walk(child)

    _walk(root)
    return groups


def _cse_canonical_name(node: CheckerNode) -> str:
    """Compute a stable CSE canonical ``module_name`` for *node* (D-08).

    Format: ``sva_cse_{template_name}_{key_params}``

    Mappings:
    - ``concat_delay``    → ``sva_cse_concat_delay_{delay_min}_{delay_max}``
    - ``rep_consecutive`` → ``sva_cse_rep_consecutive_{rep_min}_{rep_max}``
    - ``bool_expr``       → ``sva_cse_bool_expr_{hash8}``  (hash as disambiguator)
    - everything else     → ``sva_cse_{template_name}_{hash8}``

    Parameters
    ----------
    node
        Representative node for the CSE group.

    Returns
    -------
    str
        Canonical CSE module name string.
    """
    tmpl = node.template_name
    if tmpl == "concat_delay":
        min_v = node.params.get("delay_min", "0")
        max_v = node.params.get("delay_max", "0")
        return f"sva_cse_concat_delay_{min_v}_{max_v}"
    if tmpl == "rep_consecutive":
        min_v = node.params.get("rep_min", "0")
        max_v = node.params.get("rep_max", "0")
        return f"sva_cse_rep_consecutive_{min_v}_{max_v}"
    if tmpl == "bool_expr":
        h = structural_hash(node)
        return f"sva_cse_bool_expr_{h}"
    h = structural_hash(node)
    return f"sva_cse_{tmpl}_{h}"


def _rebuild_with_cse(
    node: CheckerNode,
    canonical_map: dict[str, CheckerNode],
    root_hash: str,
    rebuilt_canonical: dict[str, CheckerNode],
) -> CheckerNode:
    """Recursively rebuild *node*, substituting canonical objects for duplicates.

    For any node whose structural hash appears in *canonical_map*, the
    canonical node (with CSE-prefixed module_name) is returned instead.  The
    *rebuilt_canonical* dict caches each canonical result so that every
    occurrence with the same hash returns the **same Python object** — enabling
    ``id(a) == id(b)`` identity for all CSE-merged nodes.

    The root node (identified by *root_hash*) is never replaced.

    Parameters
    ----------
    node
        Current node to process.
    canonical_map
        Mapping from structural hash → initial canonical CheckerNode (CSE name,
        original children).
    root_hash
        Structural hash of the tree root; nodes with this hash are not replaced.
    rebuilt_canonical
        Cache of hash → final rebuilt canonical (with CSE-rebuilt children).
        Mutable; accumulates results across the recursion.

    Returns
    -------
    CheckerNode
        The rebuilt (possibly canonical) node.
    """
    h = structural_hash(node)

    # Root node: never replace; but still rebuild its children
    if h == root_hash:
        new_children = tuple(
            _rebuild_with_cse(c, canonical_map, root_hash, rebuilt_canonical)
            for c in node.children
        )
        if new_children != node.children:
            return dataclasses.replace(node, children=new_children)
        return node

    # CSE candidate: return (and cache) the canonical node with rebuilt children
    if h in canonical_map:
        if h in rebuilt_canonical:
            # Return the exact same Python object as all previous encounters
            return rebuilt_canonical[h]
        canonical = canonical_map[h]
        new_children = tuple(
            _rebuild_with_cse(c, canonical_map, root_hash, rebuilt_canonical)
            for c in canonical.children
        )
        if new_children != canonical.children:
            result = dataclasses.replace(canonical, children=new_children)
        else:
            result = canonical
        rebuilt_canonical[h] = result
        return result

    # Regular non-CSE node: rebuild children only
    new_children = tuple(
        _rebuild_with_cse(c, canonical_map, root_hash, rebuilt_canonical)
        for c in node.children
    )
    if new_children != node.children:
        return dataclasses.replace(node, children=new_children)
    return node


def _collect_by_template(
    node: CheckerNode,
    template_name: str,
    out: list[CheckerNode],
) -> None:
    """Collect all nodes with *template_name* from the tree into *out*."""
    if node.template_name == template_name:
        out.append(node)
    for child in node.children:
        _collect_by_template(child, template_name, out)


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
