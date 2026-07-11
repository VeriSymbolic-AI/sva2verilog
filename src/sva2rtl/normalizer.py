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
- ``##0`` warning: when a zero-delay fusion is detected between two BoolExpr
  leaves, emit a warning suggesting ``a && b`` for true same-cycle conjunction
  (the registered-leaf token-passing pipeline retains +1 cycle separation for ##0)
"""

from __future__ import annotations

import logging

from sva2rtl.errors import SvaCompileError
from sva2rtl.ir import (
    BoolExpr,
    ClockedSeq,
    DisableIff,
    PropBoundedAlways,
    PropBoundedEventually,
    PropIfElse,
    PropImplication,
    PropNot,
    PropUntil,
    SeqAnd,
    SeqConcat,
    SeqFirstMatch,
    SeqGotoRep,
    SeqIntersect,
    SeqNonconsecRep,
    SeqOr,
    SeqRepetition,
    SeqThroughout,
    SeqWithin,
    SignalFunc,
    SVANode,
)

_LOG = logging.getLogger(__name__)


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

        case SeqFirstMatch():
            new_body = normalize(node.body)
            return _normalize_node(
                SeqFirstMatch(body=new_body, source_loc=node.source_loc)
            )

        case SeqGotoRep():
            new_expr = normalize(node.expr)
            return _normalize_node(SeqGotoRep(
                expr=new_expr, rep_min=node.rep_min, rep_max=node.rep_max,
                source_loc=node.source_loc,
            ))

        case SeqNonconsecRep():
            new_expr = normalize(node.expr)
            return _normalize_node(SeqNonconsecRep(
                expr=new_expr, rep_min=node.rep_min, rep_max=node.rep_max,
                source_loc=node.source_loc,
            ))

        case SeqOr():
            new_left = normalize(node.left)
            new_right = normalize(node.right)
            return _normalize_node(
                SeqOr(left=new_left, right=new_right, source_loc=node.source_loc)
            )
        case SeqAnd():
            new_left = normalize(node.left)
            new_right = normalize(node.right)
            return _normalize_node(
                SeqAnd(left=new_left, right=new_right, source_loc=node.source_loc)
            )
        case SeqIntersect():
            new_left = normalize(node.left)
            new_right = normalize(node.right)
            return _normalize_node(
                SeqIntersect(left=new_left, right=new_right, source_loc=node.source_loc)
            )
        case SeqWithin():
            new_inner = normalize(node.inner)
            new_outer = normalize(node.outer)
            return _normalize_node(
                SeqWithin(inner=new_inner, outer=new_outer, source_loc=node.source_loc)
            )
        case SeqThroughout():
            new_cond = normalize(node.condition)
            new_body = normalize(node.body)
            return _normalize_node(
                SeqThroughout(condition=new_cond, body=new_body, source_loc=node.source_loc)
            )
        case PropNot():
            new_body = normalize(node.body)
            return _normalize_node(PropNot(body=new_body, source_loc=node.source_loc))
        case PropBoundedEventually():
            new_body = normalize(node.body)
            return _normalize_node(
                PropBoundedEventually(
                    body=new_body,
                    lo=node.lo,
                    hi=node.hi,
                    strong=node.strong,
                    source_loc=node.source_loc,
                )
            )
        case PropBoundedAlways():
            new_body = normalize(node.body)
            return _normalize_node(
                PropBoundedAlways(
                    body=new_body,
                    lo=node.lo,
                    hi=node.hi,
                    strong=node.strong,
                    source_loc=node.source_loc,
                )
            )
        case PropUntil():
            new_left = normalize(node.left)
            new_right = normalize(node.right)
            return _normalize_node(
                PropUntil(
                    left=new_left,
                    right=new_right,
                    with_=node.with_,
                    source_loc=node.source_loc,
                )
            )
        case ClockedSeq():
            new_body = normalize(node.body)
            return _normalize_node(
                ClockedSeq(
                    clock=node.clock,
                    body=new_body,
                    source_loc=node.source_loc,
                )
            )
        case PropIfElse():
            new_cond = normalize(node.condition)
            new_true = normalize(node.true_branch)
            new_false = normalize(node.false_branch) if node.false_branch is not None else None
            return _normalize_node(
                PropIfElse(
                    condition=new_cond,
                    true_branch=new_true,
                    false_branch=new_false,
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
            flattened = _flatten_concat(node)
            result = _handle_fusion_delay(flattened)
            if isinstance(result, BoolExpr):
                return result
            return result

        case PropImplication():
            # D-05: Do NOT desugar PropImplication(overlapping=False) to |-> ##1.
            return node

        case DisableIff():
            return node

        case SeqFirstMatch():
            return node

        case SeqGotoRep():
            return node

        case SeqNonconsecRep():
            return node
        case SeqOr():
            return node
        case SeqAnd():
            return node
        case SeqIntersect():
            return node
        case SeqWithin():
            return node
        case SeqThroughout():
            return node
        case PropNot():
            return node
        case PropIfElse():
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
            new_delays.append(node.delays[i])

    return SeqConcat(
        elements=tuple(new_elements),
        delays=tuple(new_delays),
        source_loc=node.source_loc,
    )


def _handle_fusion_delay(node: SVANode) -> SVANode:
    """Handle ``##0`` (fusion delay) in SeqConcat.

    For two BoolExpr leaves connected by ``##0``, rewrites them into a single
    merged ``BoolExpr`` using ``&&`` (semantically correct same-cycle fusion).

    For non-BoolExpr operands or mixed operand types connected by ``##0``,
    raises ``SvaCompileError`` with a suggestion. The registered-leaf pipeline
    cannot express true same-cycle fusion for complex operands.

    Returns the (possibly rewritten) node.
    """
    if not isinstance(node, SeqConcat) or len(node.delays) == 0:
        return node

    new_elements = list(node.elements)
    new_delays = list(node.delays)

    i = 0
    while i < len(new_delays):
        d_min, d_max = new_delays[i]
        if d_min == 0 and d_max == 0:
            left = new_elements[i]
            right = new_elements[i + 1]

            if isinstance(left, BoolExpr) and isinstance(right, BoolExpr):
                # Rewrite: merge two BoolExpr into one with &&
                merged_text = f"({left.text}) && ({right.text})"
                # Attempt to merge structured BoolNode payloads; fall back to
                # text-only if BoolBinary has incompatible interface (source_loc).
                merged_expr = None
                if left.expr is not None and right.expr is not None:
                    try:
                        from sva2rtl.ir import BoolBinary as _BoolBin  # noqa: N814
                        # Pass source_loc so the structured payload merges
                        # correctly (BoolBinary inherits source_loc from
                        # SVANode). Previously this call omitted source_loc,
                        # causing TypeError → silent text-only fallback that
                        # left the structured bool_semantic payload as None.
                        merged_expr = _BoolBin(
                            op="and", left=left.expr, right=right.expr,
                            source_loc=left.source_loc,
                        )
                    except (TypeError, ImportError):
                        # Stale cached build with extra field — keep text-only
                        _LOG.debug("BoolBinary merge skipped — fallback to text-only")

                merged = BoolExpr(
                    text=merged_text,
                    expr=merged_expr,
                    source_loc=node.source_loc,
                )
                new_elements[i] = merged
                new_elements.pop(i + 1)
                new_delays.pop(i)
                # Don't increment i — re-check current position for another ##0
                continue
            else:
                raise SvaCompileError(
                    message=(
                        f"##0 fusion delay at {node.source_loc} is not supported "
                        f"for non-boolean or mixed operand types. The registered-leaf "
                        f"pipeline cannot express same-cycle fusion for complex operands. "
                        f"For boolean operands, use 'a && b' instead of 'a ##0 b'."
                    ),
                    source_loc=node.source_loc,
                )
        i += 1

    if len(new_elements) == 1 and len(new_delays) == 0:
        return new_elements[0]

    return SeqConcat(
        elements=tuple(new_elements),
        delays=tuple(new_delays),
        source_loc=node.source_loc,
    )


def _warn_fusion_delay(node: SeqConcat) -> None:
    """[deprecated — superseded by _handle_fusion_delay]"""
    _handle_fusion_delay(node)
