"""Formal-specific bounded obligation lowering.

The symbolic-witness backend proves one arbitrary antecedent attempt.  Because
the witness selector is unconstrained, formal proof is universal over every
possible selected attempt without allocating a fixed hardware thread per
overlapping start.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum

from sva2rtl import __version__
from sva2rtl.bool_semantics import (
    collect_bool_signal_types,
    rename_bool_signals,
    render_bool_expr,
)
from sva2rtl.composer import module_name_from_label
from sva2rtl.ir import (
    BoolConst,
    BoolExpr,
    CheckerNode,
    DisableIff,
    PropEventually,
    PropImplication,
    PropNexttime,
    PropStrongUntil,
    SeqConcat,
    SeqRepetition,
    SourceLoc,
    SVANode,
)


class ObligationKind(StrEnum):
    """Bounded obligation shapes supported by symbolic witness lowering."""

    EVENTUALLY = "eventually"
    CONSECUTIVE = "consecutive"


def _true_expr(source_loc: SourceLoc) -> BoolExpr:
    semantic = BoolConst(value=1, width=1, raw="1'b1", source_loc=source_loc)
    return BoolExpr(text="1'b1", expr=semantic, source_loc=source_loc)


def _unwrap_disable(node: SVANode) -> tuple[SVANode, BoolExpr | None]:
    if isinstance(node, DisableIff) and isinstance(node.condition, BoolExpr):
        return node.body, node.condition
    return node, None


def _delayed_bool(
    consequent: SVANode,
) -> tuple[ObligationKind, BoolExpr, int, int] | None:
    if isinstance(consequent, BoolExpr):
        return ObligationKind.EVENTUALLY, consequent, 0, 0
    if isinstance(consequent, PropNexttime) and isinstance(consequent.body, BoolExpr):
        return (
            ObligationKind.EVENTUALLY,
            consequent.body,
            consequent.cycles,
            consequent.cycles,
        )
    if isinstance(consequent, SeqConcat) and len(consequent.elements) == 2:
        first, second = consequent.elements
        if (
            len(consequent.delays) == 1
            and isinstance(first, BoolExpr)
            and isinstance(first.expr, BoolConst)
            and first.expr.value == 1
            and isinstance(second, BoolExpr)
        ):
            lo, hi = consequent.delays[0]
            return ObligationKind.EVENTUALLY, second, lo, hi
    if isinstance(consequent, SeqRepetition) and isinstance(consequent.expr, BoolExpr):
        return (
            ObligationKind.CONSECUTIVE,
            consequent.expr,
            consequent.rep_min,
            consequent.rep_max,
        )
    return None


def _typed_aliases(
    expressions: tuple[BoolExpr, ...],
) -> tuple[
    dict[str, str],
    tuple[tuple[str, str], ...],
    tuple[tuple[str, int], ...],
    tuple[tuple[str, bool], ...],
]:
    types: dict[str, tuple[int, bool]] = {}
    for expression in expressions:
        if expression.expr is None:
            return {}, (), (), ()
        for name, width, signed in collect_bool_signal_types(expression.expr):
            metadata = (width, signed)
            previous = types.get(name)
            if previous is not None and previous != metadata:
                return {}, (), (), ()
            types.setdefault(name, metadata)
    aliases = {name: f"obs_{index}" for index, name in enumerate(types)}
    observed = tuple((aliases[name], name) for name in types)
    widths = tuple((aliases[name], metadata[0]) for name, metadata in types.items())
    signedness = tuple((aliases[name], metadata[1]) for name, metadata in types.items())
    return aliases, observed, widths, signedness


def _render(expression: BoolExpr, aliases: dict[str, str]) -> str | None:
    if expression.expr is None:
        return None
    return render_bool_expr(rename_bool_signals(expression.expr, aliases))


def lower_bounded_implication(
    node: SVANode,
    *,
    label: str | None,
    original_text: str,
    clock_signal: str = "clk",
    clock_edge: str = "posedge",
) -> CheckerNode | None:
    """Lower a recognized bounded property to symbolic-witness metadata."""
    body, disable = _unwrap_disable(node)
    if isinstance(body, PropNexttime) and isinstance(body.body, BoolExpr):
        implication = PropImplication(
            antecedent=_true_expr(body.source_loc),
            consequent=body,
            overlapping=True,
            source_loc=body.source_loc,
        )
    elif isinstance(body, PropImplication):
        implication = body
    else:
        return None
    if not isinstance(implication.antecedent, BoolExpr):
        return None
    lowered = _delayed_bool(implication.consequent)
    if lowered is None:
        return None
    kind, condition, lo, hi = lowered
    if lo < 0 or hi < lo:
        return None
    start_offset = 0 if implication.overlapping else 1
    if kind is ObligationKind.EVENTUALLY:
        lo += start_offset
        hi += start_offset
        start_offset = 0

    expressions = (implication.antecedent, condition) + ((disable,) if disable else ())
    aliases, observed, widths, signedness = _typed_aliases(expressions)
    if not aliases and any(expression.expr is not None for expression in expressions):
        # Constant-only obligations legitimately have no aliases.
        if any(
            collect_bool_signal_types(expression.expr)
            for expression in expressions
            if expression.expr
        ):
            return None
    antecedent_text = _render(implication.antecedent, aliases)
    condition_text = _render(condition, aliases)
    disable_text = _render(disable, aliases) if disable is not None else "1'b0"
    if antecedent_text is None or condition_text is None or disable_text is None:
        return None

    module_name = module_name_from_label(label, original_text)
    counter_limit = max(hi, start_offset + lo, 1)
    counter_width = max(1, math.ceil(math.log2(counter_limit + 1)))
    return CheckerNode(
        template_name="formal_symbolic_witness",
        module_name=module_name,
        params={
            "module_name": module_name,
            "antecedent_expr": antecedent_text,
            "condition_expr": condition_text,
            "disable_expr": disable_text,
            "obligation_kind": kind.value,
            "min_cycles": str(lo),
            "max_cycles": str(hi),
            "start_offset": str(start_offset),
            "counter_width": str(counter_width),
            "clock_signal": clock_signal,
            "clock_edge": clock_edge,
            "source_loc": str(node.source_loc),
            "sva2rtl_version": __version__,
            "original_text": original_text,
        },
        observed_signals=observed,
        observed_signal_widths=widths,
        observed_signal_signedness=signedness,
        source_loc=node.source_loc,
    )


def lower_liveness_property(
    node: SVANode,
    *,
    label: str | None,
    original_text: str,
    clock_signal: str = "clk",
    clock_edge: str = "posedge",
) -> CheckerNode | None:
    """Lower the deliberately small true-liveness kernel to formal metadata."""
    body, disable = _unwrap_disable(node)
    antecedent: BoolExpr | None = None
    eventual: BoolExpr | None = None
    safety_left: BoolExpr | None = None
    safety_with = False
    start_offset = 0
    obligation_kind = "eventually"

    if isinstance(body, PropEventually) and isinstance(body.body, BoolExpr):
        eventual = body.body
    elif (
        isinstance(body, PropImplication)
        and isinstance(body.antecedent, BoolExpr)
        and isinstance(body.consequent, PropEventually)
        and isinstance(body.consequent.body, BoolExpr)
    ):
        antecedent = body.antecedent
        eventual = body.consequent.body
        start_offset = 0 if body.overlapping else 1
    elif (
        isinstance(body, PropStrongUntil)
        and isinstance(body.left, BoolExpr)
        and isinstance(body.right, BoolExpr)
    ):
        eventual = body.right
        safety_left = body.left
        safety_with = body.with_
        obligation_kind = "strong-until"
    else:
        return None

    expressions = (
        ((antecedent,) if antecedent is not None else ())
        + ((safety_left,) if safety_left is not None else ())
        + (eventual,)
        + ((disable,) if disable is not None else ())
    )
    aliases, observed, widths, signedness = _typed_aliases(expressions)
    rendered_eventual = _render(eventual, aliases)
    rendered_antecedent = (
        _render(antecedent, aliases) if antecedent is not None else "1'b1"
    )
    rendered_disable = _render(disable, aliases) if disable is not None else "1'b0"
    rendered_left = _render(safety_left, aliases) if safety_left is not None else None
    if (
        rendered_eventual is None
        or rendered_antecedent is None
        or rendered_disable is None
    ):
        return None
    safety_expr = ""
    if rendered_left is not None:
        safety_expr = (
            rendered_left
            if safety_with
            else f"(({rendered_left}) || ({rendered_eventual}))"
        )

    module_name = module_name_from_label(label, original_text)
    return CheckerNode(
        template_name="formal_liveness",
        module_name=module_name,
        params={
            "module_name": module_name,
            "antecedent_expr": rendered_antecedent,
            "eventual_expr": rendered_eventual,
            "disable_expr": rendered_disable,
            "safety_expr": safety_expr,
            "uses_witness": "1" if antecedent is not None else "0",
            "start_offset": str(start_offset),
            "obligation_kind": obligation_kind,
            "clock_signal": clock_signal,
            "clock_edge": clock_edge,
            "source_loc": str(node.source_loc),
            "sva2rtl_version": __version__,
            "original_text": original_text,
        },
        observed_signals=observed,
        observed_signal_widths=widths,
        observed_signal_signedness=signedness,
        source_loc=node.source_loc,
    )


def evaluate_symbolic_witness(
    antecedent: Sequence[bool],
    condition: Sequence[bool],
    kind: ObligationKind,
    lo: int,
    hi: int,
    selected_index: int,
) -> bool:
    """Reference outcome for one selected, fully observable attempt."""
    if selected_index < 0 or selected_index >= len(antecedent):
        raise ValueError("selected_index is outside the trace")
    if not antecedent[selected_index]:
        return True
    if kind is ObligationKind.EVENTUALLY:
        if selected_index + hi >= len(condition):
            return True
        return any(condition[selected_index + offset] for offset in range(lo, hi + 1))
    required = lo
    if required <= 0:
        return True
    if selected_index + required > len(condition):
        return True
    return all(condition[selected_index + offset] for offset in range(required))


def evaluate_all_attempts(
    antecedent: Sequence[bool],
    condition: Sequence[bool],
    kind: ObligationKind,
    lo: int,
    hi: int,
) -> bool:
    """Exhaustive bounded reference over every fully observable attempt."""
    if len(antecedent) != len(condition):
        raise ValueError("antecedent and condition traces must have equal length")
    horizon = hi if kind is ObligationKind.EVENTUALLY else max(0, lo - 1)
    return all(
        evaluate_symbolic_witness(antecedent, condition, kind, lo, hi, index)
        for index, fired in enumerate(antecedent)
        if fired and index + horizon < len(condition)
    )
