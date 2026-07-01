"""Tests for v1.4.1 Part B — multi-clock path-one.

Phase B1 coverage (clock-domain IR + frontend):
- MC-01/02/03 (frontend): nested ``@(clk) ...`` boundaries import to ``ClockedSeq``
  IR nodes carrying the per-domain clock, for sequence / implication / multi-stage.
- MC-05 (honesty): blacklist forms raise — overlapping ``|->`` across clocks
  (UnsupportedConstruct); cross-clock ``##N!=1`` (slang rejects → SvaCompileError).
- MC-06: single-clock import is unchanged (no ClockedSeq for single-clock).

slang 11.0.0 represents a clock-domain switch as a nested ``Clocking`` node (see
tools/audit/probe_multiclock_ast.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.errors import SvaCompileError, UnsupportedConstruct
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import (
    CheckerNode,
    ClockedSeq,
    PropImplication,
    SeqConcat,
    SVANode,
)
from sva2rtl.normalizer import normalize


def _import(prop: str) -> SVANode:
    """Import an inline multi-clock property and return its root IR node."""
    src = Path("/tmp/_mc_test.sv")
    src.write_text(
        "module m(input logic clk1, clk2, clk3, a, b, c);\n"
        f"  ap: assert property ({prop});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    ast = invoke_slang(src, "slang")
    node, _clock, _text, _label = import_assertion(ast)
    return node


def _find_clocked(node: SVANode) -> list[ClockedSeq]:
    """Collect all ClockedSeq nodes in an IR subtree."""
    found: list[ClockedSeq] = []

    def walk(n: object) -> None:
        if isinstance(n, ClockedSeq):
            found.append(n)
        for attr in ("elements", "children"):
            for child in getattr(n, attr, ()) or ():
                walk(child)
        for attr in ("body", "left", "right", "antecedent", "consequent",
                     "condition", "inner", "outer", "true_branch", "false_branch"):
            child = getattr(n, attr, None)
            if isinstance(child, SVANode):
                walk(child)

    walk(node)
    return found


# ── MC-01 multi-clock sequence ─────────────────────────────────────────────


def test_two_clock_sequence_imports_clocked_seq() -> None:
    root = _import("@(posedge clk1) a ##1 @(posedge clk2) b")
    assert isinstance(root, SeqConcat)
    clocked = _find_clocked(root)
    assert len(clocked) == 1
    assert clocked[0].clock.signal == "clk2"
    assert clocked[0].clock.edge == "posedge"


def test_three_clock_chain_imports_two_switches() -> None:
    root = _import(
        "@(posedge clk1) a ##1 @(posedge clk2) b ##1 @(posedge clk3) c"
    )
    clocked = _find_clocked(root)
    signals = sorted(c.clock.signal for c in clocked)
    assert signals == ["clk2", "clk3"]


# ── MC-02 multi-clock implication ──────────────────────────────────────────


def test_two_clock_implication_consequent_clocked() -> None:
    root = _import("@(posedge clk1) a |=> @(posedge clk2) b")
    assert isinstance(root, PropImplication)
    assert not root.overlapping
    assert isinstance(root.consequent, ClockedSeq)
    assert root.consequent.clock.signal == "clk2"


def test_two_clock_implication_composes() -> None:
    """Multi-clock implication composes to mc_seq_top with ant+sync+con children."""
    from sva2rtl.ast_importer import import_assertion as ia  # noqa: F811
    from sva2rtl.composer import compose  # noqa: F811
    from sva2rtl.frontend import invoke_slang as isl  # noqa: F811

    src = Path("/tmp/_mc_impl_t.sv")
    src.write_text(
        "module m(input logic clk1, clk2, a, b);\n"
        "  ap: assert property (@(posedge clk1) a |=> @(posedge clk2) b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    ast = isl(src, "slang")
    node, clock, text, label = ia(ast)
    node = normalize(node)
    ck = compose(node, clock, label, text)
    assert ck.template_name == "mc_seq_top"
    assert ck.params["clocks"] == "clk1,clk2"
    assert len(ck.children) == 3  # ant + sync + con


def test_multi_stage_composes() -> None:
    """3-clock chain composes with two syncs and per-domain sub-checkers."""
    from sva2rtl.ast_importer import import_assertion as ia  # noqa: F811
    from sva2rtl.composer import compose  # noqa: F811
    from sva2rtl.frontend import invoke_slang as isl  # noqa: F811

    src = Path("/tmp/_mc_3s_t.sv")
    src.write_text(
        "module m(input logic clk1, clk2, clk3, a, b, c);\n"
        "  ap: assert property (@(posedge clk1) a ##1 @(posedge clk2) b "
        "##1 @(posedge clk3) c);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    ast = isl(src, "slang")
    node, clock, text, label = ia(ast)
    node = normalize(node)
    ck = compose(node, clock, label, text)
    syncs = [c for c in _all_children(ck) if c.template_name == "sync_2dff"]
    assert len(syncs) >= 2, f"expected 2+ syncs, got {len(syncs)}"


def _all_children(ck: CheckerNode) -> list[CheckerNode]:  # type: ignore[no-untyped-def]
    result = list(ck.children)
    for child in ck.children:
        result.extend(_all_children(child))  # type: ignore[arg-type]
    return result


# ── MC-05 blacklist (honesty-first) ────────────────────────────────────────


def test_overlapping_implication_cross_clock_rejected() -> None:
    with pytest.raises(UnsupportedConstruct, match="overlapping implication"):
        _import("@(posedge clk1) a |-> @(posedge clk2) b")


def test_cross_clock_delay_n_neq_1_rejected_by_slang() -> None:
    # IEEE-1800 forbids ##N (N!=1) across a clock boundary; slang errors out,
    # surfacing as SvaCompileError from the frontend.
    with pytest.raises(SvaCompileError):
        _import("@(posedge clk1) a ##2 @(posedge clk2) b")


# ── MC-06 single-clock unchanged ───────────────────────────────────────────


def test_single_clock_has_no_clocked_seq() -> None:
    root = _import("@(posedge clk1) a ##1 b")
    assert _find_clocked(root) == []


# ── normalizer pass-through ────────────────────────────────────────────────


def test_normalize_clocked_seq_idempotent() -> None:
    root = _import("@(posedge clk1) a ##1 @(posedge clk2) b")
    once = normalize(root)
    assert normalize(once) == once
    assert len(_find_clocked(once)) == 1


# ── B4.1 structural checks ──────────────────────────────────────────────────


def test_sync_2dff_instantiated_in_multi_clock_output() -> None:
    """Multi-clock emit includes the 2-DFF synchronizer module."""
    from sva2rtl.ast_importer import import_assertion as ia  # noqa: F811
    from sva2rtl.composer import compose  # noqa: F811
    from sva2rtl.emitter import emit_all  # noqa: F811
    from sva2rtl.frontend import invoke_slang as isl  # noqa: F811

    src = Path("/tmp/_mc_struct.sv")
    src.write_text(
        "module m(input logic clk1, clk2, a, b);\n"
        "  ap: assert property (@(posedge clk1) a ##1 @(posedge clk2) b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    ast = isl(src, "slang")
    node, clock, text, label = ia(ast)
    node = normalize(node)
    ck = compose(node, clock, label, text)
    modules = emit_all(ck)
    # The sync_2dff module MUST be present in the emitted set.
    sync_mods = [m for m in modules if "TRUSTED COMPONENT" in modules[m]]
    assert len(sync_mods) == 1, f"expected 1 sync_2dff module, got {sync_mods}"
    # The top module MUST wire token_i / token_o correctly.
    top_sv = modules[ck.module_name]
    assert "token_i" in top_sv and "token_o" in top_sv, "top must wire sync token"


def test_sync_latency_2_dst_cycles() -> None:
    """2-DFF synchronizer adds exactly 2 dst-clock cycles of latency."""
    # Two flip-flops in series = 2 dst-clock cycles from token_i to token_o
    check = (
        "sync0_q <= token_i",
        "sync1_q <= sync0_q",
        "token_o = sync1_q",
    )
    from sva2rtl.ast_importer import import_assertion as ia  # noqa: F811
    from sva2rtl.composer import compose  # noqa: F811
    from sva2rtl.emitter import emit_all  # noqa: F811
    from sva2rtl.frontend import invoke_slang as isl  # noqa: F811

    src = Path("/tmp/_mc_sync2.sv")
    src.write_text(
        "module m(input logic clk1, clk2, a, b);\n"
        "  ap: assert property (@(posedge clk1) a ##1 @(posedge clk2) b);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    ast = isl(src, "slang")
    node, clock, text, label = ia(ast)
    node = normalize(node)
    ck = compose(node, clock, label, text)
    modules = emit_all(ck)
    sync_sv = [v for v in modules.values() if "TRUSTED COMPONENT" in v][0]
    for pattern in check:
        assert pattern in sync_sv, f"sync module must contain: {pattern}"
