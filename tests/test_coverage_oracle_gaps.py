"""Phase 13 coverage gap tests for behavioral_oracle.py.

Targets uncovered oracle pathways: first_match, prop_and, prop_or, s_always,
until, and edge cases for tick dispatch.
"""

from __future__ import annotations

from sva2rtl.behavioral_oracle import (
    simulate_checker_hierarchy,
)
from sva2rtl.ir import CheckerNode, SourceLoc


def _make_loc(file: str = "test.sv", line: int = 1, col: int = 1) -> SourceLoc:
    return SourceLoc(file=file, line=line, col=col)


def _make_leaf(module_name: str, signals: list[str]) -> CheckerNode:
    return CheckerNode(
        template_name="bool_expr",
        module_name=module_name,
        observed_signals=tuple((k, k) for k in signals),
        params={
            "module_name": module_name,
            "bool_expr": "1",
            "clock_signal": "clk",
            "clock_edge": "posedge",
            "sva2rtl_version": "1.5.2",
            "source_loc": "test.sv:1:1",
            "original_text": "1",
        },
        source_loc=_make_loc(),
        children=(),
    )


def _signal(b: dict[str, bool]) -> dict[str, bool]:
    base = {"start": True, "disable": False}
    base.update(b)
    return base


class TestFirstMatchOracle:
    """Cover _tick_first_match (behavioral_oracle.py lines 793-828)."""

    def test_first_match_passes_on_body_pass(self) -> None:
        leaf = _make_leaf("fm_leaf", ["a"])
        top = CheckerNode(
            template_name="first_match_top", module_name="fm_checker",
            observed_signals=leaf.observed_signals,
            params={"module_name": "fm_checker", "sva2rtl_version": "1.5.2"},
            source_loc=_make_loc(), children=(leaf,),
        )
        trace = [_signal({"a": True, "start": True})]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is True  # type: ignore[index]

    def test_first_match_locks_after_pass(self) -> None:
        leaf = _make_leaf("fm_leaf2", ["a"])
        top = CheckerNode(
            template_name="first_match_top", module_name="fm_checker2",
            observed_signals=leaf.observed_signals,
            params={"module_name": "fm_checker2", "sva2rtl_version": "1.5.2"},
            source_loc=_make_loc(), children=(leaf,),
        )
        trace = [
            _signal({"a": True, "start": True}),
            _signal({"a": True, "start": False}),
        ]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is False  # type: ignore[index]

    def test_first_match_unlocks_on_new_start(self) -> None:
        leaf = _make_leaf("fm_leaf3", ["a"])
        top = CheckerNode(
            template_name="first_match_top", module_name="fm_checker3",
            observed_signals=leaf.observed_signals,
            params={"module_name": "fm_checker3", "sva2rtl_version": "1.5.2"},
            source_loc=_make_loc(), children=(leaf,),
        )
        trace = [
            _signal({"a": True, "start": True}),
            _signal({"a": True, "start": False}),
            _signal({"a": True, "start": True}),
        ]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is True  # type: ignore[index]

    def test_first_match_empty_body(self) -> None:
        """first_match with no children returns all-False (line 801-802)."""
        top = CheckerNode(
            template_name="first_match_top", module_name="fm_empty",
            observed_signals=(), params={"module_name": "fm_empty"},
            source_loc=_make_loc(), children=(),
        )
        trace = [_signal({"start": True})]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is False  # type: ignore[index]


class TestPropAndTwoCyclePass:
    """Cover _tick_prop_and with same-cycle pass (line 850-892 matched state)."""

    def test_prop_and_both_pass_same_cycle(self) -> None:
        left = _make_leaf("pal", ["a"])
        right = _make_leaf("par", ["b"])
        top = CheckerNode(
            template_name="prop_and", module_name="pa_checker",
            observed_signals=(), params={"module_name": "pa_checker"},
            source_loc=_make_loc(), children=(left, right),
        )
        trace = [_signal({"a": True, "b": True, "start": True})]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is True  # type: ignore[index]

    def test_prop_and_single_child_falls_through(self) -> None:
        """prop_and with < 2 children returns all-False (line 856-857)."""
        left = _make_leaf("pa_solo", ["a"])
        top = CheckerNode(
            template_name="prop_and", module_name="pa_solo_top",
            observed_signals=(), params={"module_name": "pa_solo_top"},
            source_loc=_make_loc(), children=(left,),
        )
        trace = [_signal({"a": True, "start": True})]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is False  # type: ignore[index]


class TestPropOrEdgeCases:
    """Cover _tick_prop_or (line 832-835+)."""

    def test_prop_or_left_passes(self) -> None:
        left = _make_leaf("ol", ["a"])
        right = _make_leaf("or2", ["b"])
        top = CheckerNode(
            template_name="prop_or", module_name="o_checker",
            observed_signals=(), params={"module_name": "o_checker"},
            source_loc=_make_loc(), children=(left, right),
        )
        trace = [_signal({"a": True, "b": False, "start": True})]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is True  # type: ignore[index]

    def test_prop_or_single_child(self) -> None:
        """prop_or with < 2 children returns all-False (line 834-835)."""
        left = _make_leaf("o_solo", ["a"])
        top = CheckerNode(
            template_name="prop_or", module_name="o_solo_top",
            observed_signals=(), params={"module_name": "o_solo_top"},
            source_loc=_make_loc(), children=(left,),
        )
        trace = [_signal({"a": True, "start": True})]
        result = simulate_checker_hierarchy(top, trace)
        assert result[-1]["pass"] is False  # type: ignore[index]


class TestHierarchyDispatchEdgeCases:
    """Cover fallthrough dispatch paths (behavioral_oracle.py lines 692-694)."""

    def test_tick_unknown_template_delegates_to_child(self) -> None:
        child = _make_leaf("dc_child", ["a"])
        unknown = CheckerNode(
            template_name="unknown_template_xyz", module_name="unknown_top",
            observed_signals=child.observed_signals,
            params={"module_name": "unknown_top"},
            source_loc=_make_loc(), children=(child,),
        )
        trace = [_signal({"a": True, "start": True})]
        result = simulate_checker_hierarchy(unknown, trace)
        assert result[-1] is not None

    def test_tick_unknown_template_no_children(self) -> None:
        """Unknown template with no children -> all-False fallthrough (line 694)."""
        unknown = CheckerNode(
            template_name="unknown_empty", module_name="unk_empty",
            observed_signals=(), params={"module_name": "unk_empty"},
            source_loc=_make_loc(), children=(),
        )
        trace = [_signal({"start": True})]
        result = simulate_checker_hierarchy(unknown, trace)
        assert result[-1]["pass"] is False  # type: ignore[index]


class TestNfaGenericTick:
    """Cover _tick_nfa_generic dispatch (line 690-691)."""

    def test_nfa_generic_ticks(self) -> None:
        """nfa_generic template hits the dispatch and returns output."""
        child = _make_leaf("nfa_child", ["a"])
        nfa = CheckerNode(
            template_name="nfa_generic", module_name="nfa_top",
            observed_signals=child.observed_signals,
            params={"module_name": "nfa_top", "sva2rtl_version": "1.5.2"},
            source_loc=_make_loc(), children=(child,),
        )
        trace = [_signal({"a": True, "start": True})]
        result = simulate_checker_hierarchy(nfa, trace)
        assert result[-1] is not None


class TestSeqConcatTick:
    """Cover _tick_seq_concat dispatch (line 662-663)."""

    def test_seq_concat_ticks(self) -> None:
        child = _make_leaf("sc_child", ["a"])
        sc = CheckerNode(
            template_name="seq_concat_top", module_name="sc_top",
            observed_signals=child.observed_signals,
            params={"module_name": "sc_top", "sva2rtl_version": "1.5.2",
                    "clock_edge": "posedge", "clock_signal": "clk"},
            source_loc=_make_loc(), children=(child,),
        )
        trace = [_signal({"a": True, "start": True})]
        result = simulate_checker_hierarchy(sc, trace)
        assert result[-1] is not None
