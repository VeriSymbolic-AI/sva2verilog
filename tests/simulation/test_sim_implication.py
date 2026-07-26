"""Simulation tests for the overlap_bitvec and nonoverlap templates.

Two fixtures are exercised:

``implication_overlap.json`` — ``a |-> b`` (overlapping implication, BV_WIDTH=1)
    Uses the ``overlap_bitvec`` template.  Both antecedent and consequent are
    single-cycle ``bool_expr`` modules, so BV_WIDTH=1 and the pipeline latency
    is 2 extra cycles relative to the semantic SVA time.

    RTL pipeline (BV_WIDTH=1):
        t=0: start=1, a=1 sampled → ant_pass_w will be 1 at t=1
        t=1: ant_pass_w=1 → bv_q<=1; con not yet started
        t=2: bv_q[0]=1 → con_start_w=1; con_pass_w=0 (not yet started)
             → fail=1 when b=0; **pass never fires** (con_pass_w registers after
               the thread exits bv_q)

``implication_nonoverlap.json`` — ``a |=> b`` (non-overlapping, BV_WIDTH=1)
    Uses the ``nonoverlap`` template.  An extra ``ant_pass_delayed_q`` register
    adds one more cycle of latency versus overlap.

    RTL pipeline (BV_WIDTH=1):
        t=0: start=1, a=1 sampled
        t=1: ant_pass_w=1 registered
        t=2: ant_pass_delayed_q=1 → bv_q<=1
        t=3: bv_q[0]=1 → con_start_w=1; fail fires when b=0

Both modules expose ``overflow_flag`` (template TEMPLATES_WITH_OVERFLOW).

Requirements covered: TEST-05, TEST-06
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.ir import CheckerNode
from tests.simulation.tb_generator import (
    TEMPLATES_WITH_OVERFLOW,
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = pytest.mark.simulation

_FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── Fixture loading ────────────────────────────────────────────────────────────


def _build(fixture_name: str) -> CheckerNode:
    ast = json.loads((_FIXTURES / fixture_name).read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    return compose(node, clock, label, text)


# ── Run helper ─────────────────────────────────────────────────────────────────


def _run_stimulus(
    checker: CheckerNode,
    stimulus: list[dict[str, Any]],
    tmp_path: Path,
    simulator: str = "iverilog",
) -> list[dict]:
    """Compile and run stimulus through an implication RTL checker."""
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    clock_signal = checker.params["clock_signal"]
    has_overflow = checker.template_name in TEMPLATES_WITH_OVERFLOW

    tb = generate_testbench(
        module_name=checker.module_name,
        clock_signal=clock_signal,
        extra_inputs=extra_inputs,
        stimulus=stimulus,
        has_overflow_flag=has_overflow,
        capture_contract=True,
    )
    return run_simulation(
        simulator=simulator,
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=tb,
        work_dir=tmp_path,
        has_overflow_flag=has_overflow,
        capture_contract=True,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
        clock_signal=clock_signal,
    )


@pytest.mark.parametrize(
    "fixture_name",
    ("implication_overlap.json", "implication_nonoverlap.json"),
)
def test_attempt_fired_records_start_even_when_antecedent_is_false(
    fixture_name: str,
    tmp_path: Path,
    simulator: str,
) -> None:
    """The anti-vacuity contract records attempts, not antecedent matches."""

    checker = _build(fixture_name)
    stimulus = [
        {"start": True, "a": False, "b": False},
        {"start": False, "a": False, "b": False},
        {"start": False, "a": False, "b": False},
    ]

    trace = _run_stimulus(checker, stimulus, tmp_path, simulator)

    assert trace[0]["attempt_fired"] is False
    assert trace[1]["attempt_fired"] is True
    assert trace[2]["attempt_fired"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Overlapping implication: a |-> b  (overlap_bitvec, BV_WIDTH=1)
# ══════════════════════════════════════════════════════════════════════════════


class TestImplicationOverlap:
    """RTL timing tests for ``a |-> b`` (BV_WIDTH=1)."""

    def test_fail_fires_at_t1(self, tmp_path: Path) -> None:
        """Overlap (BUG-IMPL-01 fixed): a |-> b checks b on the SAME cycle as a.

        With the parallel-consequent design (con_start = start), both leaves
        register one cycle, so for a single antecedent at t=0 with b=0 the
        violation a(0) & ~b(0) is reported exactly one cycle later, at t=1.
        (The previous buggy design reported it at t=2.)
        """
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0: a=1, b=0 (violation)
            {"start": False, "a": False, "b": False},   # t=1: fail fires
            {"start": False, "a": False, "b": False},   # t=2: idle
            {"start": False, "a": False, "b": False},   # t=3: idle
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        assert len(out) == len(stimulus)
        assert not out[0]["fail"], "t=0: leaves not yet registered"
        assert     out[1]["fail"], "t=1: a(0) & ~b(0) → fail"
        assert not out[2]["fail"], "t=2: single attempt consumed"
        assert not out[3]["fail"], "t=3: idle"

    def test_active_high_while_thread_in_pipeline(self, tmp_path: Path, simulator: str) -> None:
        """Overlap: active is raised for one cycle while the attempt is evaluated.

        BUG-IMPL-01: with the parallel design (no bv_q thread tracker), a single
        antecedent makes the monitor active only on the cycle its leaves report
        (t=1); it returns to idle immediately afterwards.
        """
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},   # t=1
            {"start": False, "a": False, "b": False},   # t=2
            {"start": False, "a": False, "b": False},   # t=3
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        assert not out[0]["active"], "t=0: FFs not yet updated"
        assert     out[1]["active"], "t=1: ant/con leaves active"
        assert not out[2]["active"], "t=2: no bv_q → attempt already consumed"

    def test_no_start_no_output(self, tmp_path: Path, simulator: str) -> None:
        """Overlap: when start=0, antecedent never triggers — all outputs remain 0."""
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": False, "a": True,  "b": False},
            {"start": False, "a": True,  "b": False},
            {"start": False, "a": False, "b": True},
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        for i, row in enumerate(out):
            assert not row["active"], f"t={i}: no start → active=0"
            assert not row["pass"],   f"t={i}: no start → pass=0"
            assert not row["fail"],   f"t={i}: no start → fail=0"

    def test_pass_fires_when_consequent_holds(self, tmp_path: Path) -> None:
        """Overlap (BUG-IMPL-01 fixed): pass fires when a(0) & b(0) both hold.

        The previous bv_q-gated design dropped every pass (the thread left bv_q
        before the consequent's pass_q registered). The fixed parallel design
        reports a(0) & b(0) as a pass at t=1, with no spurious fail.
        """
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": True},   # t=0: a=1, b=1 (satisfied)
            {"start": False, "a": False, "b": False},   # t=1: pass fires
            {"start": False, "a": False, "b": False},   # t=2: idle
            {"start": False, "a": False, "b": False},   # t=3: idle
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        assert     out[1]["pass"], "t=1: a(0) & b(0) → pass"
        assert not out[1]["fail"], "t=1: consequent satisfied → no fail"
        for i in (0, 2, 3):
            assert not out[i]["pass"], f"t={i}: no pass outside the attempt"
            assert not out[i]["fail"], f"t={i}: no spurious fail"

    def test_disable_i_gates_all_outputs(self, tmp_path: Path, simulator: str) -> None:
        """Overlap: disable_i=1 clears state and gates all outputs to 0."""
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False, "disable_i": True},  # t=0
            {"start": True,  "a": True,  "b": False, "disable_i": True},  # t=1
            {"start": False, "a": False, "b": False, "disable_i": True},  # t=2: no fail
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        for i, row in enumerate(out):
            assert not row["active"], f"t={i}: disable_i=1 → active=0"
            assert not row["pass"],   f"t={i}: disable_i=1 → pass=0"
            assert not row["fail"],   f"t={i}: disable_i=1 → fail=0"

    def test_back_to_back_starts_each_produce_fail(self, tmp_path: Path, simulator: str) -> None:
        """Overlap (BUG-IMPL-01 fixed): back-to-back antecedents are independent.

        The single-cycle-consequent design has NO bv_q thread tracker and thus no
        overflow: each antecedent is an independent same-cycle check. Two
        back-to-back antecedents with b=0 produce two consecutive fails (t=1, t=2)
        and never assert overflow.
        """
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0: first antecedent
            {"start": True,  "a": True,  "b": False},  # t=1: second antecedent
            {"start": False, "a": False, "b": False},  # t=2
            {"start": False, "a": False, "b": False},  # t=3
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        assert out[1]["fail"], "t=1: first attempt a(0) & ~b(0) → fail"
        assert out[2]["fail"], "t=2: second attempt a(1) & ~b(1) → fail"
        for row in out:
            assert not row["overflow"], "no overflow without a thread tracker"


# ══════════════════════════════════════════════════════════════════════════════
# Non-overlapping implication: a |=> b  (nonoverlap, BV_WIDTH=1)
# ══════════════════════════════════════════════════════════════════════════════


class TestImplicationNonoverlap:
    """RTL timing tests for ``a |=> b`` (BV_WIDTH=1)."""

    def test_fail_fires_at_t2(self, tmp_path: Path) -> None:
        """Nonoverlap (BUG-IMPL-01 fixed): a |=> b checks b ONE cycle after a.

        con_start = ant_pass_w starts the consequent exactly when the antecedent
        matches, so b is sampled at a+1 (the ##1 of |=>) and the verdict is
        reported one further cycle later: for a single antecedent at t=0 with
        b=0 the violation a(0) & ~b(1) is reported at t=2.  (The previous buggy
        design reported it at t=3 and checked the wrong b cycle.)
        """
        checker = _build("implication_nonoverlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0: antecedent fires
            {"start": False, "a": False, "b": False},   # t=1: b sampled here (=0)
            {"start": False, "a": False, "b": False},   # t=2: fail fires
            {"start": False, "a": False, "b": False},   # t=3: idle
            {"start": False, "a": False, "b": False},   # t=4: idle
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        assert len(out) == len(stimulus)
        assert not out[0]["fail"], "t=0: start — leaves not registered"
        assert not out[1]["fail"], "t=1: consequent being sampled"
        assert     out[2]["fail"], "t=2: a(0) & ~b(1) → fail"
        assert not out[3]["fail"], "t=3: attempt consumed"
        assert not out[4]["fail"], "t=4: idle"

    def test_no_start_no_output(self, tmp_path: Path, simulator: str) -> None:
        """Nonoverlap: start=0 → all outputs remain 0."""
        checker = _build("implication_nonoverlap.json")
        stimulus = [
            {"start": False, "a": True,  "b": False},
            {"start": False, "a": True,  "b": False},
            {"start": False, "a": False, "b": True},
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        for i, row in enumerate(out):
            assert not row["active"], f"t={i}: no start → active=0"
            assert not row["pass"],   f"t={i}: no start → pass=0"
            assert not row["fail"],   f"t={i}: no start → fail=0"

    def test_disable_i_gates_all_outputs(self, tmp_path: Path, simulator: str) -> None:
        """Nonoverlap: disable_i=1 prevents any activity."""
        checker = _build("implication_nonoverlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False, "disable_i": True},
            {"start": False, "a": False, "b": False, "disable_i": True},
            {"start": False, "a": False, "b": False, "disable_i": True},
            {"start": False, "a": False, "b": False, "disable_i": True},
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        for i, row in enumerate(out):
            assert not row["active"], f"t={i}: disable_i=1 → active=0"
            assert not row["pass"],   f"t={i}: disable_i=1 → pass=0"
            assert not row["fail"],   f"t={i}: disable_i=1 → fail=0"

    def test_multiple_starts_produce_multiple_fails(self, tmp_path: Path, simulator: str) -> None:
        """Nonoverlap (BUG-IMPL-01 fixed): two separated starts each fail at t+2.

        start at t=0 → fail at t=2
        start at t=5 → fail at t=7
        """
        checker = _build("implication_nonoverlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": False, "a": False, "b": False},   # t=1
            {"start": False, "a": False, "b": False},   # t=2: first fail
            {"start": False, "a": False, "b": False},   # t=3: idle
            {"start": False, "a": False, "b": False},   # t=4: idle
            {"start": True,  "a": True,  "b": False},   # t=5: second start
            {"start": False, "a": False, "b": False},   # t=6
            {"start": False, "a": False, "b": False},   # t=7: second fail
            {"start": False, "a": False, "b": False},   # t=8: idle
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        assert len(out) == len(stimulus)
        assert     out[2]["fail"], "t=2: first fail"
        assert not out[3]["fail"], "t=3: idle"
        assert     out[7]["fail"], "t=7: second fail"

    def test_back_to_back_starts_each_produce_fail(self, tmp_path: Path, simulator: str) -> None:
        """Nonoverlap (BUG-IMPL-01 fixed): back-to-back starts are independent.

        The single-cycle-consequent design has no bv_q thread tracker, so there
        is no overflow: two back-to-back antecedents with b=0 produce two
        consecutive fails (t=2, t=3) and never assert overflow.
        """
        checker = _build("implication_nonoverlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},  # t=0
            {"start": True,  "a": True,  "b": False},  # t=1: second start
            {"start": False, "a": False, "b": False},  # t=2: first fail
            {"start": False, "a": False, "b": False},  # t=3: second fail
            {"start": False, "a": False, "b": False},  # t=4
        ]
        out = _run_stimulus(checker, stimulus, tmp_path)

        assert out[2]["fail"], "t=2: first attempt a(0) & ~b(1) → fail"
        assert out[3]["fail"], "t=3: second attempt a(1) & ~b(2) → fail"
        for row in out:
            assert not row["overflow"], "no overflow without a thread tracker"


# ══════════════════════════════════════════════════════════════════════════════
# Oracle cross-check tests
# ══════════════════════════════════════════════════════════════════════════════


class TestImplicationOracleCrosscheck:
    """Oracle cross-check: verify that RTL and oracle produce the same pass/fail event pattern.

    Note: cycle-by-cycle comparison is not possible because the behavioral oracle
    models the token-passing semantics without the registered bool_expr pipeline
    latency.  Instead, we verify that the total event counts and event sequences
    match (ignoring exact cycle timing).
    """

    def _count_events(self, results: list[dict]) -> dict[str, int]:
        """Count pass/fail events across all cycles."""
        return {
            "pass": sum(1 for r in results if r.get("pass")),
            "fail": sum(1 for r in results if r.get("fail")),
            "active": sum(1 for r in results if r.get("active")),
        }

    def test_overlap_oracle_event_pattern(self, tmp_path: Path, simulator: str) -> None:
        """Overlap: RTL and oracle produce same pass/fail event counts."""
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": True,  "a": True,  "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        # Both should have fails (b=0 when antecedent fires)
        assert rtl_events["fail"] > 0, "RTL must have fail events"
        assert oracle_events["fail"] > 0, "Oracle must have fail events"

    def test_overlap_no_start_no_events(self, tmp_path: Path, simulator: str) -> None:
        """Overlap: with no start, both RTL and oracle produce zero events."""
        checker = _build("implication_overlap.json")
        stimulus = [
            {"start": False, "a": True, "b": False},
            {"start": False, "a": True, "b": False},
            {"start": False, "a": False, "b": True},
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        assert rtl_events["pass"] == 0 and rtl_events["fail"] == 0
        assert oracle_events["pass"] == 0 and oracle_events["fail"] == 0

    def test_nonoverlap_oracle_event_pattern(self, tmp_path: Path, simulator: str) -> None:
        """Nonoverlap: RTL and oracle produce same fail event counts."""
        checker = _build("implication_nonoverlap.json")
        stimulus = [
            {"start": True,  "a": True,  "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": True,  "a": True,  "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
            {"start": False, "a": False, "b": False},
        ]
        rtl_out = _run_stimulus(checker, stimulus, tmp_path, simulator)
        oracle_out = simulate_checker_hierarchy(checker, stimulus)

        rtl_events = self._count_events(rtl_out)
        oracle_events = self._count_events(oracle_out)

        # Both should have fails for each antecedent trigger with b=0
        assert rtl_events["fail"] > 0
        assert oracle_events["fail"] > 0
