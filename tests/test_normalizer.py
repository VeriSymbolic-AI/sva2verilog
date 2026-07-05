"""Unit tests for src/sva2rtl/normalizer.py."""

from __future__ import annotations

from sva2rtl.ir import (
    BoolExpr,
    DisableIff,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SignalFunc,
    SourceLoc,
)
from sva2rtl.normalizer import normalize

# ── Helpers ───────────────────────────────────────────────────────────────


def _make_loc(
    file: str = "test.sv", line: int = 1, col: int = 1
) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _make_bool(text: str = "a") -> BoolExpr:
    return BoolExpr(text=text, source_loc=_make_loc())


def _make_concat(
    elements: tuple[BoolExpr | SeqConcat, ...],
    delays: tuple[tuple[int, int], ...],
) -> SeqConcat:
    return SeqConcat(elements=elements, delays=delays, source_loc=_make_loc())


def _make_rep(expr: BoolExpr | SeqConcat, rep_min: int, rep_max: int) -> SeqRepetition:
    return SeqRepetition(expr=expr, rep_min=rep_min, rep_max=rep_max, source_loc=_make_loc())


# -- Identity tests: canonical forms pass through unchanged ----------------


def test_normalize_bool_expr_identity() -> None:
    """BoolExpr passes through normalize unchanged."""
    node = _make_bool("a && b")
    result = normalize(node)
    assert result == node


def test_normalize_flat_seq_concat_identity() -> None:
    """Flat SeqConcat (no nested concats) passes through unchanged."""
    a = _make_bool("a")
    b = _make_bool("b")
    node = _make_concat((a, b), ((2, 2),))
    result = normalize(node)
    assert isinstance(result, SeqConcat)
    assert result.elements == (a, b)
    assert result.delays == ((2, 2),)


def test_normalize_seq_repetition_non_trivial_identity() -> None:
    """SeqRepetition with min!=1 or max!=1 passes through unchanged."""
    node = _make_rep(_make_bool("a"), 3, 5)
    result = normalize(node)
    assert isinstance(result, SeqRepetition)
    assert result.rep_min == 3
    assert result.rep_max == 5


def test_normalize_signal_func_identity() -> None:
    """SignalFunc passes through normalize unchanged."""
    node = SignalFunc(
        func_name="rose", signal="req", depth=1, source_loc=_make_loc()
    )
    result = normalize(node)
    assert result == node


def test_normalize_prop_implication_overlapping_identity() -> None:
    """PropImplication(overlapping=True) passes through unchanged."""
    a = _make_bool("a")
    b = _make_bool("b")
    node = PropImplication(
        antecedent=a, consequent=b, overlapping=True, source_loc=_make_loc()
    )
    result = normalize(node)
    assert isinstance(result, PropImplication)
    assert result.overlapping is True


def test_normalize_prop_implication_nonoverlapping_identity() -> None:
    """PropImplication(overlapping=False) passes through unchanged (D-05)."""
    a = _make_bool("a")
    b = _make_bool("b")
    node = PropImplication(
        antecedent=a, consequent=b, overlapping=False, source_loc=_make_loc()
    )
    result = normalize(node)
    assert isinstance(result, PropImplication)
    assert result.overlapping is False


def test_normalize_disable_iff_identity() -> None:
    """DisableIff with canonical body passes through structurally unchanged."""
    cond = _make_bool("!rst_n")
    body = _make_bool("a")
    node = DisableIff(condition=cond, body=body, source_loc=_make_loc())
    result = normalize(node)
    assert isinstance(result, DisableIff)
    assert result.condition == cond
    assert result.body == body


# -- Rule tests: normalization transforms ----------------------------------


def test_normalize_rep_one_removal() -> None:
    """[*1] identity removal returns the inner expression."""
    inner = _make_bool("a")
    node = _make_rep(inner, 1, 1)
    result = normalize(node)
    assert isinstance(result, BoolExpr)
    assert result.text == "a"


def test_normalize_nested_seq_concat_flattens() -> None:
    """Nested SeqConcat is flattened to a single flat sequence."""
    a = _make_bool("a")
    b = _make_bool("b")
    c = _make_bool("c")
    inner = _make_concat((b, c), ((3, 3),))
    outer = _make_concat((a, inner), ((2, 2),))
    result = normalize(outer)
    assert isinstance(result, SeqConcat)
    assert result.elements == (a, b, c)
    assert result.delays == ((2, 2), (3, 3))


def test_normalize_three_level_nesting_flattens() -> None:
    """Three-level nested SeqConcat flattens in single pass (bottom-up)."""
    a = _make_bool("a")
    b = _make_bool("b")
    c = _make_bool("c")
    d = _make_bool("d")
    innermost = _make_concat((c, d), ((4, 4),))
    middle = _make_concat((b, innermost), ((3, 3),))
    outer = _make_concat((a, middle), ((2, 2),))
    result = normalize(outer)
    assert isinstance(result, SeqConcat)
    assert result.elements == (a, b, c, d)
    assert result.delays == ((2, 2), (3, 3), (4, 4))


def test_normalize_rep_one_wrapping_concat_both_rules_fire() -> None:
    """[*1] wrapping a SeqConcat: unwraps the repetition, inner concat kept."""
    a = _make_bool("a")
    b = _make_bool("b")
    inner_concat = _make_concat((a, b), ((1, 1),))
    wrapped = _make_rep(inner_concat, 1, 1)
    result = normalize(wrapped)
    # [*1] unwrapped → inner_concat (which is already flat)
    assert isinstance(result, SeqConcat)
    assert result.elements == (a, b)
    assert result.delays == ((1, 1),)


def test_normalize_prop_implication_children_recursively_normalized() -> None:
    """PropImplication children are recursively normalized."""
    a = _make_bool("a")
    # Consequent has a [*1] that should be removed
    b = _make_bool("b")
    rep_b = _make_rep(b, 1, 1)
    node = PropImplication(
        antecedent=a, consequent=rep_b, overlapping=True, source_loc=_make_loc()
    )
    result = normalize(node)
    assert isinstance(result, PropImplication)
    # The [*1] in the consequent should have been removed
    assert isinstance(result.consequent, BoolExpr)
    assert result.consequent.text == "b"


# -- Idempotency tests ----------------------------------------------------


def test_normalize_idempotent_nested_concat() -> None:
    """normalize(normalize(node)) == normalize(node) for nested SeqConcat."""
    a = _make_bool("a")
    b = _make_bool("b")
    c = _make_bool("c")
    inner = _make_concat((b, c), ((3, 3),))
    outer = _make_concat((a, inner), ((2, 2),))
    once = normalize(outer)
    twice = normalize(once)
    assert once == twice


def test_normalize_idempotent_rep_one() -> None:
    """normalize(normalize(node)) == normalize(node) for [*1] removal."""
    inner = _make_bool("x")
    node = _make_rep(inner, 1, 1)
    once = normalize(node)
    twice = normalize(once)
    assert once == twice


# -- Edge cases ------------------------------------------------------------


def test_normalize_single_element_concat_unchanged() -> None:
    """SeqConcat with single element and no delays passes through unchanged."""
    a = _make_bool("a")
    node = SeqConcat(elements=(a,), delays=(), source_loc=_make_loc())
    result = normalize(node)
    assert isinstance(result, SeqConcat)
    assert result.elements == (a,)
    assert result.delays == ()


def test_normalize_disable_iff_nested_concat_body_flattened() -> None:
    """DisableIff with nested SeqConcat body gets body flattened."""
    cond = _make_bool("!rst_n")
    a = _make_bool("a")
    b = _make_bool("b")
    c = _make_bool("c")
    inner = _make_concat((b, c), ((2, 2),))
    body = _make_concat((a, inner), ((1, 1),))
    node = DisableIff(condition=cond, body=body, source_loc=_make_loc())
    result = normalize(node)
    assert isinstance(result, DisableIff)
    assert isinstance(result.body, SeqConcat)
    assert result.body.elements == (a, b, c)
    assert result.body.delays == ((1, 1), (2, 2))


def test_normalize_seq_repetition_nested_concat_inner_flattened() -> None:
    """SeqRepetition containing nested concat gets inner concat flattened."""
    a = _make_bool("a")
    b = _make_bool("b")
    c = _make_bool("c")
    inner = _make_concat((b, c), ((2, 2),))
    nested_concat = _make_concat((a, inner), ((1, 1),))
    node = _make_rep(nested_concat, 2, 4)
    result = normalize(node)
    assert isinstance(result, SeqRepetition)
    assert result.rep_min == 2
    assert result.rep_max == 4
    assert isinstance(result.expr, SeqConcat)
    assert result.expr.elements == (a, b, c)
    assert result.expr.delays == ((1, 1), (2, 2))
