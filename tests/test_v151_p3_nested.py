"""v1.5.1 P3 — nested NFA composition end-to-end tests.

Nesting: inner operator(s) compose into an NFA first; the outer operator
then calls product construction on the pre-composed NFA data.

Coverage:
- P3.1 recursive composition: intersect-within / intersect chain /
  throughout body / within with all-bool operands → all produce
  nfa_generic templates.
- P3.2 oracle: hand-derived pass vectors for nested shapes.
- P3.3 K budget: K ≤ 32 always enforced.
"""

from __future__ import annotations

import pytest

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    SeqIntersect,
    SeqRepetition,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
)

_LOC = SourceLoc("p3.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


# ═════════════════════════════════════════════════════════════════════════
# Compile-time — nested shapes produce nfa_generic
# ═════════════════════════════════════════════════════════════════════════


class TestNestedCompile:
    def test_intersect_within_bool(self) -> None:
        """(a intersect b) within c — K=2*(4+2)=12."""
        node = SeqWithin(
            inner=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            outer=_b("c"), source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "(a intersect b) within c")
        assert c.template_name == "nfa_generic"
        assert c.params["nfa_states"] == "12"

    def test_intersect_chain(self) -> None:
        """(a intersect b) intersect c — K=4×2=8."""
        node = SeqIntersect(
            left=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            right=_b("c"), source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "(a intersect b) intersect c")
        assert c.template_name == "nfa_generic"

    def test_throughout_body_nested(self) -> None:
        """en throughout (a intersect b) — body is 4-state intersect,
        cond gates each transition. K=4."""
        node = SeqThroughout(
            condition=_b("en"),
            body=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "en throughout (a intersect b)")
        assert c.template_name == "nfa_generic"
        assert c.params["nfa_states"] == "4"

    def test_deep_nested(self) -> None:
        """(a intersect b) within (c[*3]) — waiting/running/done K=24."""
        node = SeqWithin(
            inner=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            outer=SeqRepetition(
                expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC,
            ),
            source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "(a intersect b) within (c[*3])")
        assert c.template_name == "nfa_generic"
        # 4 outer states * (4 inner states + waiting/done phases) = 24
        assert c.params["nfa_states"] == "24"


# ═════════════════════════════════════════════════════════════════════════
# Oracle — hand-derived pass vectors
# ═════════════════════════════════════════════════════════════════════════


class TestNestedOracle:
    def _p(self, rs: list[dict[str, bool]]) -> list[bool]:
        return [bool(r["pass"]) for r in rs]

    def test_intersect_within_bool_pass(self) -> None:
        """(a intersect b) within c.

        Inner (a∩b): both a & b same cycle.
        Outer c: alive iff c=1 same cycle.
        Both inner accept AND outer alive at same cycle → pass.
        So pass iff start=1 & a=1 & b=1 & c=1 same cycle.
        """
        node = SeqWithin(
            inner=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            outer=_b("c"), source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "(a intersect b) within c")
        stim = [
            {"start": True,  "a": True,  "b": True,  "c": True},
            {"start": False, "a": False, "b": False, "c": False},
        ]
        passes = self._p(simulate_checker_hierarchy(c, stim))
        assert any(passes)

    def test_intersect_within_bool_fail_on_c_absent(self) -> None:
        node = SeqWithin(
            inner=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            outer=_b("c"), source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "(a intersect b) within c")
        stim = [
            {"start": True,  "a": True,  "b": True,  "c": False},
        ]
        passes = self._p(simulate_checker_hierarchy(c, stim))
        assert not any(passes)

    def test_throughout_intersect_pass(self) -> None:
        """en throughout (a intersect b): body completes same cycle
        iff a & b & en all hold start cycle."""
        node = SeqThroughout(
            condition=_b("en"),
            body=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "en throughout (a intersect b)")
        stim = [
            {"start": True,  "en": True,  "a": True,  "b": True},
            {"start": False, "en": False, "a": False, "b": False},
        ]
        passes = self._p(simulate_checker_hierarchy(c, stim))
        assert any(passes)

    def test_throughout_intersect_en0_no_pass(self) -> None:
        node = SeqThroughout(
            condition=_b("en"),
            body=SeqIntersect(
                left=_b("a"), right=_b("b"), source_loc=_LOC,
            ),
            source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "en throughout (a intersect b)")
        stim = [
            {"start": True,  "en": False, "a": True,  "b": True},
        ]
        passes = self._p(simulate_checker_hierarchy(c, stim))
        assert not any(passes)


# ═════════════════════════════════════════════════════════════════════════
# K budget — compile-time enforcement
# ═════════════════════════════════════════════════════════════════════════


class TestKBudget:
    def test_k32_exactly_passes(self) -> None:
        """c[*15] intersect c[*15] → K=16×16=256 > 32 → rejected.

        We use two short chains: b ##1 c ##2 d (K=5) within
        c[*6] (K=7) → K=5×7=35 also > 32.

        Simpler: b ##14 c (K=16) is already one operand.
        Two of these → K=16×16=256 → rejected.
        """
        long_rep = SeqRepetition(
            expr=_b("x"), rep_min=4, rep_max=4, source_loc=_LOC,
        )  # K=5
        # 5 × 5 = 25 ≤ 32 — passes
        node = SeqIntersect(
            left=long_rep, right=long_rep, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "(x[*4]) intersect (x[*4])")
        assert checker.params["nfa_states"] == "25"

    def test_k33_rejected(self) -> None:
        """x[*5] intersect x[*5] → K=6×6=36 > 32 → rejected."""
        r5 = SeqRepetition(
            expr=_b("x"), rep_min=5, rep_max=5, source_loc=_LOC,
        )
        node = SeqIntersect(
            left=r5, right=r5, source_loc=_LOC,
        )
        with pytest.raises(UnsupportedConstruct, match="K·T > 32"):
            compose(node, _CLK, None, "(x[*5]) intersect (x[*5])")

    def test_k32_deep_nest_rejected(self) -> None:
        """Deep nesting exceeds budget: x[*3] intersect x[*3] (K=16)
        within y[*3] (K=4) → K=16×4=64 > 32."""
        inner = SeqIntersect(
            left=SeqRepetition(
                expr=_b("x"), rep_min=3, rep_max=3, source_loc=_LOC,
            ),
            right=SeqRepetition(
                expr=_b("x"), rep_min=3, rep_max=3, source_loc=_LOC,
            ),
            source_loc=_LOC,
        )  # K = 4 × 4 = 16
        outer = SeqRepetition(
            expr=_b("y"), rep_min=3, rep_max=3, source_loc=_LOC,
        )  # K = 4
        node = SeqWithin(inner=inner, outer=outer, source_loc=_LOC)
        with pytest.raises(UnsupportedConstruct, match="K"):
            compose(node, _CLK, None, "nested K=64 > 32")

    def test_workaround_message_in_error(self) -> None:
        r5 = SeqRepetition(
            expr=_b("x"), rep_min=5, rep_max=5, source_loc=_LOC,
        )
        node = SeqIntersect(left=r5, right=r5, source_loc=_LOC)
        with pytest.raises(UnsupportedConstruct) as ei:
            compose(node, _CLK, None, "(x[*5]) intersect (x[*5])")
        assert "split the property" in str(ei.value).lower()
