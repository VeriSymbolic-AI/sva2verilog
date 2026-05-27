"""IR normalization pass — canonicalize SVA IR before composition.

Pure IR-to-IR preprocessing pass that runs as a standalone pre-pass before
``compose()``.  Bottom-up single-pass traversal (O(n) on tree size): each
node is visited after its children are normalized.

Guarantees:
- **Idempotent:** ``normalize(normalize(x)) == normalize(x)``
- **Semantic-preserving:** All rules are IEEE 1800-2017 identity transformations
- **Golden-file safe:** Does NOT desugar standalone ``PropImplication(overlapping=False)``

Rules applied:
- ``[*1]`` identity removal: ``SeqRepetition(min=1, max=1)`` -> inner expression
- ``SeqConcat`` flattening: nested ``SeqConcat`` children are spliced into parent
- ``PropImplication``: children are recursively normalized but the node itself
  is never transformed (D-05: golden file parity)
"""

from __future__ import annotations

from sva2rtl.ir import (
    BoolExpr,
    DisableIff,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SignalFunc,
    SVANode,
)


def normalize(node: SVANode) -> SVANode:
    """Normalize an SVA IR tree to canonical form.

    Pure IR -> IR transformation.  Bottom-up single pass.
    Idempotent: ``normalize(normalize(x)) == normalize(x)``.

    Parameters
    ----------
    node
        Root of the SVA IR subtree to normalize.

    Returns
    -------
    SVANode
        Canonical form of the input tree.
    """
    match node:
        # Leaf nodes — no children to recurse into
        case BoolExpr():
            return node
        case SignalFunc():
            return node

        # Compound nodes — recurse into children first, then normalize self
        case SeqConcat():
            new_elements = tuple(normalize(e) for e in node.elements)
            return _normalize_node(
                SeqConcat(
                    elements=new_elements,
                    delays=node.delays,
                    source_loc=node.source_loc,
                )
            )

        case SeqRepetition():
            new_expr = normalize(node.expr)
            return _normalize_node(
                SeqRepetition(
                    expr=new_expr,
                    rep_min=node.rep_min,
                    rep_max=node.rep_max,
                    source_loc=node.source_loc,
                )
            )

        case PropImplication():
            new_ant = normalize(node.antecedent)
            new_con = normalize(node.consequent)
            return _normalize_node(
                PropImplication(
                    antecedent=new_ant,
                    consequent=new_con,
                    overlapping=node.overlapping,
                    source_loc=node.source_loc,
                )
            )

        case DisableIff():
            new_body = normalize(node.body)
            return _normalize_node(
                DisableIff(
                    condition=node.condition,
                    body=new_body,
                    source_loc=node.source_loc,
                )
            )

        case _:
            return node


def _normalize_node(node: SVANode) -> SVANode:
    """Apply normalization rules to a single node (children already normalized).

    Dispatches on node type and applies the appropriate canonicalization rule.
    Returns the node unchanged if no rule applies.
    """
    match node:
        case SeqRepetition(rep_min=1, rep_max=1):
            # [*1] identity removal — trivial repetition adds no temporal semantics
            return node.expr

        case SeqConcat():
            return _flatten_concat(node)

        case PropImplication():
            # D-05: Do NOT desugar PropImplication(overlapping=False) to |-> ##1.
            # This preserves golden file parity — |=> desugaring is deferred to
            # Phase 5+ or when |=> appears nested in complex compositions.
            return node

        case DisableIff():
            return node

        case BoolExpr():
            return node

        case SignalFunc():
            return node

        case _:
            return node


def _flatten_concat(node: SeqConcat) -> SeqConcat:
    """Flatten nested SeqConcat children into a single flat sequence.

    Given ``SeqConcat(elements=[a, SeqConcat(elements=[b, c], delays=[(3,3)])])``
    with outer ``delays=[(2,2)]``, produces
    ``SeqConcat(elements=[a, b, c], delays=[(2,2), (3,3)])``.

    If no nested SeqConcat is found, returns the node unchanged.
    """
    has_nested = any(isinstance(e, SeqConcat) for e in node.elements)
    if not has_nested:
        return node

    new_elements: list[SVANode] = []
    new_delays: list[tuple[int, int]] = []

    for i, elem in enumerate(node.elements):
        if isinstance(elem, SeqConcat):
            # Splice inner elements and delays into the parent
            new_elements.extend(elem.elements)
            # The delay connecting the outer to the inner's first element
            # is already at position i-1 in the outer delays (already added).
            # Add the inner's delays to connect the inner's elements.
            new_delays.extend(elem.delays)
        else:
            new_elements.append(elem)

        # Add the outer delay connecting this element to the next
        # (only if not the last element)
        if i < len(node.delays):
            # If the current element was a SeqConcat, the outer delay connects
            # the last element of the inner concat to the next outer element.
            # If not, it connects this element to the next.
            if not isinstance(elem, SeqConcat):
                new_delays.append(node.delays[i])
            else:
                # The outer delay at position i connects the last element of
                # the inlined inner concat to the next outer element.
                new_delays.append(node.delays[i])

    return SeqConcat(
        elements=tuple(new_elements),
        delays=tuple(new_delays),
        source_loc=node.source_loc,
    )
