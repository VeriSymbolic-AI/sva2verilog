"""Representative generated RTL cases for synthesis and lint gates.

This module is intentionally test-local.  It maps supported construct families
to concrete monitor generators so external-tool gates can exercise emitted RTL
without turning the tests into a duplicate of ``SUPPORT_MATRIX.md``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import (
    BoolExpr,
    CheckerNode,
    ClockedSeq,
    ClockSpec,
    SeqConcat,
    SeqIntersect,
    SeqRepetition,
    SeqThroughout,
    SeqWithin,
    SourceLoc,
    SVANode,
)
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_FIXTURES = Path(__file__).parent / "fixtures"
_LOC = SourceLoc("generated_rtl_cases.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)
_CLK2 = ClockSpec(edge="posedge", signal="clk2", source_loc=_LOC)


@dataclass(frozen=True)
class GeneratedMonitorCase:
    """One representative generated monitor used by external RTL gates.

    ``families`` describe emitted template mechanisms; ``matrix_rows`` name the
    evidence rows that may cite this case after a gate has actually passed.
    Exclusion fields are explicit non-evidence notes for tool-specific gaps.
    """

    case_id: str
    description: str
    build: Callable[[], CheckerNode]
    families: tuple[str, ...]
    matrix_rows: tuple[str, ...]
    yosys_exclusion_reason: str = ""
    lint_exclusion_reason: str = ""
    trusted_boundary_reason: str = ""


@dataclass(frozen=True)
class EmittedMonitorCase:
    """Emitted modules plus metadata for one generated case."""

    case: GeneratedMonitorCase
    top_module: str
    modules: dict[str, str]


def _b(text: str) -> BoolExpr:
    return BoolExpr(text=text, source_loc=_LOC)


def _build_json_fixture(name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    return optimize(compose(node, clock, label if label is not None else "synth", text))


def _build(node: SVANode, label: str, text: str) -> CheckerNode:
    return optimize(compose(normalize(node), _CLK, label, text))


def _seq_a_delay_b(delay_min: int, delay_max: int) -> SeqConcat:
    return SeqConcat(
        elements=(_b("a"), _b("b")),
        delays=((delay_min, delay_max),),
        source_loc=_LOC,
    )


def _rep_c3() -> SeqRepetition:
    return SeqRepetition(expr=_b("c"), rep_min=3, rep_max=3, source_loc=_LOC)


def _build_nfa_intersect() -> CheckerNode:
    node = SeqIntersect(
        left=_seq_a_delay_b(2, 2),
        right=_rep_c3(),
        source_loc=_LOC,
    )
    return _build(node, "synth_nfa_intersect", "(a ##2 b) intersect (c[*3])")


def _build_nfa_within() -> CheckerNode:
    node = SeqWithin(inner=_b("a"), outer=_rep_c3(), source_loc=_LOC)
    return _build(node, "synth_nfa_within", "a within (c[*3])")


def _build_nfa_throughout() -> CheckerNode:
    node = SeqThroughout(
        condition=_b("en"),
        body=_seq_a_delay_b(2, 2),
        source_loc=_LOC,
    )
    return _build(node, "synth_nfa_throughout", "en throughout (a ##2 b)")


def _build_multiclock_boundary() -> CheckerNode:
    node = SeqConcat(
        elements=(
            _b("a"),
            ClockedSeq(clock=_CLK2, body=_b("b"), source_loc=_LOC),
        ),
        delays=((1, 1),),
        source_loc=_LOC,
    )
    return _build(node, "synth_multiclock", "@(posedge clk) a ##1 @(posedge clk2) b")


def _all_cases() -> tuple[GeneratedMonitorCase, ...]:
    return (
        GeneratedMonitorCase(
            "bool_expr",
            "structured boolean expression leaf",
            lambda: _build_json_fixture("bool_complex.json"),
            ("boolean", "bool_expr"),
            ("Boolean leaf / scalar boolean expression",),
        ),
        GeneratedMonitorCase(
            "sampled_rose",
            "sampled value edge detector",
            lambda: _build_json_fixture("rose.json"),
            ("sampled_value", "rose"),
            ("Sampled value functions",),
        ),
        GeneratedMonitorCase(
            "sampled_past",
            "sampled value shift register",
            lambda: _build_json_fixture("past.json"),
            ("sampled_value", "past"),
            ("Sampled value functions",),
        ),
        GeneratedMonitorCase(
            "delay_fixed",
            "fixed delay sequence",
            lambda: _build_json_fixture("delay_fixed.json"),
            ("delay", "fixed_delay", "seq_concat_top", "concat_delay"),
            ("##N fixed delay",),
        ),
        GeneratedMonitorCase(
            "delay_range",
            "bounded delay sequence",
            lambda: _build_json_fixture("delay_range.json"),
            ("delay", "bounded_delay", "seq_concat_top", "concat_delay"),
            ("##[M:N] bounded delay",),
        ),
        GeneratedMonitorCase(
            "delay_zero",
            "zero-delay boundary monitor",
            lambda: _build_json_fixture("delay_zero.json"),
            ("delay", "zero_delay", "seq_concat_top"),
            ("##0 same-cycle fusion limitation",),
        ),
        GeneratedMonitorCase(
            "implication_overlap",
            "overlapping implication",
            lambda: _build_json_fixture("implication_overlap.json"),
            ("implication", "overlap"),
            ("|-> overlapping implication",),
        ),
        GeneratedMonitorCase(
            "implication_nonoverlap",
            "non-overlapping implication",
            lambda: _build_json_fixture("implication_nonoverlap.json"),
            ("implication", "nonoverlap"),
            ("|=> non-overlapping implication",),
        ),
        GeneratedMonitorCase(
            "rep_fixed",
            "fixed consecutive repetition",
            lambda: _build_json_fixture("rep_fixed.json"),
            ("repetition", "rep_consecutive", "fixed_repetition"),
            ("[*N] fixed consecutive repetition",),
        ),
        GeneratedMonitorCase(
            "rep_range",
            "bounded consecutive repetition",
            lambda: _build_json_fixture("rep_range.json"),
            ("repetition", "rep_consecutive", "ranged_repetition"),
            ("[*M:N] bounded consecutive repetition",),
        ),
        GeneratedMonitorCase(
            "goto_rep",
            "fixed goto repetition",
            lambda: _build_json_fixture("goto_rep.json"),
            ("repetition", "goto_rep"),
            ("[->N] fixed goto repetition",),
        ),
        GeneratedMonitorCase(
            "nonconsec_rep",
            "fixed nonconsecutive repetition",
            lambda: _build_json_fixture("nonconsec_rep.json"),
            ("repetition", "nonconsec_rep"),
            ("[=N] fixed nonconsecutive repetition",),
        ),
        GeneratedMonitorCase(
            "first_match",
            "first_match wrapper",
            lambda: _build_json_fixture("first_match.json"),
            ("first_match", "first_match_top"),
            ("first_match",),
        ),
        GeneratedMonitorCase(
            "disable_iff",
            "disable iff wrapper over implication body",
            lambda: _build_json_fixture("disable_iff.json"),
            ("disable_iff", "disable_iff_top"),
            ("disable iff",),
        ),
        GeneratedMonitorCase(
            "named_sequence",
            "expanded named sequence reference",
            lambda: _build_json_fixture("named_seq.json"),
            ("named_sequence", "seq_concat_top"),
            ("Named sequences",),
        ),
        GeneratedMonitorCase(
            "prop_and",
            "property and composition",
            lambda: _build_json_fixture("v13_and_seq.json"),
            ("property_composition", "prop_and"),
            ("Sequence and / or",),
        ),
        GeneratedMonitorCase(
            "prop_or",
            "property or composition",
            lambda: _build_json_fixture("v13_or_seq.json"),
            ("property_composition", "prop_or"),
            ("Sequence and / or",),
        ),
        GeneratedMonitorCase(
            "prop_not",
            "property not composition",
            lambda: _build_json_fixture("v13_prop_not.json"),
            ("property_composition", "prop_not"),
            ("Property not",),
        ),
        GeneratedMonitorCase(
            "prop_if_else",
            "property if else composition",
            lambda: _build_json_fixture("v13_if_else_prop.json"),
            ("property_composition", "prop_if_else"),
            ("Property if...else",),
        ),
        GeneratedMonitorCase(
            "s_eventually",
            "bounded eventually liveness monitor",
            lambda: _build_json_fixture("s_eventually_1_3.json"),
            ("bounded_liveness", "s_eventually"),
            ("Bounded liveness",),
        ),
        GeneratedMonitorCase(
            "always_range",
            "bounded always liveness monitor",
            lambda: _build_json_fixture("always_1_3.json"),
            ("bounded_liveness", "s_always"),
            ("Bounded liveness",),
        ),
        GeneratedMonitorCase(
            "weak_until",
            "weak until safety monitor",
            lambda: _build_json_fixture("until_ab.json"),
            ("bounded_liveness", "until"),
            ("Bounded liveness",),
        ),
        GeneratedMonitorCase(
            "nfa_intersect",
            "NFA generic intersect with multi-cycle operands",
            _build_nfa_intersect,
            ("nfa_generic", "intersect"),
            ("intersect / within / throughout with NFA-liftable operands",),
        ),
        GeneratedMonitorCase(
            "nfa_within",
            "NFA generic within with repetition envelope",
            _build_nfa_within,
            ("nfa_generic", "within"),
            ("intersect / within / throughout with NFA-liftable operands",),
        ),
        GeneratedMonitorCase(
            "nfa_throughout",
            "NFA generic throughout with multi-cycle body",
            _build_nfa_throughout,
            ("nfa_generic", "throughout"),
            ("intersect / within / throughout with NFA-liftable operands",),
        ),
        GeneratedMonitorCase(
            "multiclock_boundary",
            "multi-clock synchronizer trusted boundary",
            _build_multiclock_boundary,
            ("multi_clock", "sync_2dff", "trusted_boundary"),
            ("Multi-clock path-one split/synchronize forms",),
            trusted_boundary_reason=(
                "Tool acceptance checks generated synchronizer RTL structure only; "
                "CDC and metastability proof remains out of scope."
            ),
        ),
    )


def all_generated_monitor_cases() -> tuple[GeneratedMonitorCase, ...]:
    """Return all representative cases in stable test order."""
    return _all_cases()


def yosys_generated_monitor_cases() -> tuple[GeneratedMonitorCase, ...]:
    """Return generated cases eligible for the Yosys smoke gate."""
    return tuple(c for c in all_generated_monitor_cases() if not c.yosys_exclusion_reason)


def lint_generated_monitor_cases() -> tuple[GeneratedMonitorCase, ...]:
    """Return generated cases eligible for the Verilator lint gate."""
    return tuple(c for c in all_generated_monitor_cases() if not c.lint_exclusion_reason)


def emit_generated_case(
    case: GeneratedMonitorCase,
    *,
    verilog_mode: bool = False,
) -> EmittedMonitorCase:
    """Build and emit one generated monitor case."""
    checker = case.build()
    modules = emit_all(checker, verilog_mode=verilog_mode)
    return EmittedMonitorCase(case=case, top_module=checker.module_name, modules=modules)


def write_generated_modules(
    root: Path,
    case: GeneratedMonitorCase,
    *,
    verilog_mode: bool = False,
) -> tuple[EmittedMonitorCase, list[Path]]:
    """Write emitted modules for *case* under *root* and return file paths."""
    emitted = emit_generated_case(case, verilog_mode=verilog_mode)
    case_dir = root / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for module_name, sv_text in emitted.modules.items():
        path = case_dir / f"{module_name}.sv"
        path.write_text(sv_text, encoding="utf-8")
        paths.append(path)
    return emitted, paths
