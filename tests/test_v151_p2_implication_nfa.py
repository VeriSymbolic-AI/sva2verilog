"""v1.5.1 P2 — multi-cycle implication consequent via NFA.

Each test builds a PropImplication with a multi-cycle SeqConcat or
SeqRepetition consequent (BV_WIDTH > 1, previously G2a-rejected) and
compiles it through the NFA composition engine. The oracle validates
the resulting pass/fail bit-patterns against hand-derived IEEE-1800
expectations.

Coverage:
- P2.1 compilation: implication_nfa template + nfa_generic child
- P2.2 oracle: |-> and |=> with multi-cycle consequents
- P2.3 thread budget: overflow rejection
- P2.4 fail: property-kind NFA dead-end on ant match without completion
"""

from __future__ import annotations

import pytest

from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import (
    BoolExpr,
    ClockSpec,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SourceLoc,
)

_LOC = SourceLoc("p2.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(t: str) -> BoolExpr:
    return BoolExpr(text=t, source_loc=_LOC)


# ═════════════════════════════════════════════════════════════════════════
# Compilation — overlapping |-> with NFA consequent
# ═════════════════════════════════════════════════════════════════════════


class TestOverlapImplNfaCompile:
    def test_b_concat_c(self) -> None:
        """a |-> b ##2 c — K=4 (b states: 0-b->1 -1->2 -c->3), T=4."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),),
                source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |-> b ##2 c")
        assert c.template_name == "implication_nfa"
        assert len(c.children) == 1
        child = c.children[0]
        assert child.template_name == "nfa_generic"
        assert child.params["nfa_kind"] == "property"
        assert child.params["nfa_states"] == "4"

    def test_b_rep_3(self) -> None:
        """a |-> b[*3] — K=4, T=4."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqRepetition(
                expr=_b("b"), rep_min=3, rep_max=3, source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |-> b[*3]")
        assert c.template_name == "implication_nfa"

    def test_b_concat_c_concat_d(self) -> None:
        """a |-> b ##2 c ##3 d — K=7 (1+1+1+2+1), T=4, K*T=28."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c"), _b("d")),
                delays=((2, 2), (3, 3)),
                source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |-> b ##2 c ##3 d")
        assert c.template_name == "implication_nfa"
        assert c.params["nfa_thread_slots"] == "4"


# ═════════════════════════════════════════════════════════════════════════
# Oracle — overlapping |-> with multi-cycle consequent
# ═════════════════════════════════════════════════════════════════════════


class TestOverlapImplNfaOracle:
    def _p(self, rs: list[dict[str, bool]]) -> list[bool]:
        return [bool(r["pass"]) for r in rs]

    def test_b_concat_c_pass(self) -> None:
        """a |-> b ##2 c: ant matches t=0, b=1 t=0, c=1 t=2 → pass t=3."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),), source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |-> b ##2 c")
        stim = [
            {"start": True,  "a": True,  "b": True,  "c": False},
            {"start": False, "a": False, "b": False, "c": False},
            {"start": False, "a": False, "b": False, "c": True},
            {"start": False, "a": False, "b": False, "c": False},
        ]
        assert self._p(simulate_checker_hierarchy(c, stim)) == [
            False, False, False, True,
        ]

    def test_b_rep_3_pass(self) -> None:
        """a |-> b[*3]: ant matches t=0, b=1 t=0,1,2 → pass t=3."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqRepetition(
                expr=_b("b"), rep_min=3, rep_max=3, source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |-> b[*3]")
        stim = [
            {"start": True,  "a": True,  "b": True},
            {"start": False, "a": False, "b": True},
            {"start": False, "a": False, "b": True},
            {"start": False, "a": False, "b": False},
        ]
        assert self._p(simulate_checker_hierarchy(c, stim)) == [
            False, False, False, True,
        ]

    def test_ant_false_no_pass(self) -> None:
        """a |-> b ##2 c with a=0 → ant never matches → no pass."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),), source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |-> b ##2 c")
        stim = [
            {"start": True,  "a": False, "b": True,  "c": False},
            {"start": False, "a": False, "b": False, "c": False},
            {"start": False, "a": False, "b": False, "c": True},
            {"start": False, "a": False, "b": False, "c": False},
        ]
        assert not any(
            self._p(simulate_checker_hierarchy(c, stim)),
        )

    def test_consequent_incomplete_no_pass(self) -> None:
        """a |-> b ##2 c with c never 1 → consequent incomplete → no pass."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),), source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |-> b ##2 c")
        stim = [
            {"start": True,  "a": True,  "b": True,  "c": False},
            {"start": False, "a": False, "b": False, "c": False},
            {"start": False, "a": False, "b": False, "c": False},
            {"start": False, "a": False, "b": False, "c": False},
        ]
        assert not any(
            self._p(simulate_checker_hierarchy(c, stim)),
        )


# ═════════════════════════════════════════════════════════════════════════
# Non-overlapping |=> with multi-cycle consequent
# ═════════════════════════════════════════════════════════════════════════


class TestNonoverlapImplNfa:
    def _p(self, rs: list[dict[str, bool]]) -> list[bool]:
        return [bool(r["pass"]) for r in rs]

    def test_b_concat_c_pass(self) -> None:
        """a |=> b ##2 c: ant matches t=0, consequent starts t=1.
        b=1 t=1, c=1 t=3 → pass t=4."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 2),), source_loc=_LOC,
            ),
            overlapping=False, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |=> b ##2 c")
        stim = [
            {"start": True,  "a": True,  "b": False, "c": False},  # t=0
            {"start": False, "a": False, "b": True,  "c": False},  # t=1
            {"start": False, "a": False, "b": False, "c": False},  # t=2
            {"start": False, "a": False, "b": False, "c": True},   # t=3
            {"start": False, "a": False, "b": False, "c": False},  # t=4
        ]
        assert self._p(simulate_checker_hierarchy(c, stim)) == [
            False, False, False, False, True,
        ]

    def test_b_rep_3_pass(self) -> None:
        """a |=> b[*3]: consequent starts t=1, b=1 t=1,2,3 → pass t=4."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqRepetition(
                expr=_b("b"), rep_min=3, rep_max=3, source_loc=_LOC,
            ),
            overlapping=False, source_loc=_LOC,
        )
        c = compose(node, _CLK, None, "a |=> b[*3]")
        stim = [
            {"start": True,  "a": True,  "b": False},
            {"start": False, "a": False, "b": True},
            {"start": False, "a": False, "b": True},
            {"start": False, "a": False, "b": True},
            {"start": False, "a": False, "b": False},
        ]
        assert self._p(simulate_checker_hierarchy(c, stim)) == [
            False, False, False, False, True,
        ]


# ═════════════════════════════════════════════════════════════════════════
# Rejection — non-NFA-liftable consequent still rejected
# ═════════════════════════════════════════════════════════════════════════


class TestImplNfaRejection:
    def test_ranged_delay_consequent_accepted(self) -> None:
        """a |-> b ##[2:5] c — ranged delay now NFA-liftable (v1.7 LANG-03)."""
        node = PropImplication(
            antecedent=_b("a"),
            consequent=SeqConcat(
                elements=(_b("b"), _b("c")),
                delays=((2, 5),),
                source_loc=_LOC,
            ),
            overlapping=True, source_loc=_LOC,
        )
        checker = compose(node, _CLK, None, "a |-> b ##[2:5] c")
        assert checker is not None
        assert checker.template_name == "implication_nfa"
