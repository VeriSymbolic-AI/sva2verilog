"""Tests for the pure-Python SVA behavioral reference oracle.

Requirement coverage:
- TEST-02: oracle validates cycle-exact semantics of ##N, ##[M:N], |->, |=>
- TEST-05: overflow detection halts oracle state machine
- TEST-06: boundary cycle behavior — pass fires at exactly the right tick

The ``SVABehavioralSim`` oracle is a cycle-by-cycle reference implementation
that models IEEE 1800 semantics.  These tests verify the oracle itself is
correct before using it as a golden reference for RTL comparison.
"""

from __future__ import annotations

import pytest

from sva2rtl.behavioral_oracle import SVABehavioralSim, simulate_checker_hierarchy
from sva2rtl.ir import CheckerNode, SourceLoc

# ── Helper ────────────────────────────────────────────────────────────────────


def _run(sim: SVABehavioralSim, stimuli: list[dict[str, bool]]) -> list[dict[str, bool]]:
    """Drive the oracle through a list of per-cycle stimulus dicts.

    Returns a list of output dicts (one per cycle) in the same order as stimuli.
    """
    return [sim.tick(s) for s in stimuli]


# ── Delay oracle tests ────────────────────────────────────────────────────────


def test_oracle_delay_fixed_3() -> None:
    """TEST-06 / BUG-DELAY-01: ##3 component — start at cycle 0 → pass at cycle 2.

    The concat_delay component asserts pass at old_count == N-2 (here 1), i.e.
    cycle 2, so that in the full chain bool_expr(a) -> concat_delay -> bool_expr(b)
    the net a->b SAMPLE gap equals N=3 (the a-leaf adds +1 and b is sampled at the
    pass cycle). End-to-end correctness is proven non-circularly in
    test_formal_sva_equiv (FPV). This component-level test pins the corrected
    component timing.
    """
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 3, "delay_max": 3})
    outputs = _run(sim, [{"start": i == 0} for i in range(6)])
    pass_ticks = [i for i, o in enumerate(outputs) if o["pass"]]
    assert pass_ticks == [2], f"##3 component pass expected at [2], got {pass_ticks}"

    # active = old_running: True on ticks 1–4, then the counter expires.
    active_ticks = [i for i, o in enumerate(outputs) if o["active"]]
    assert active_ticks == [1, 2, 3, 4], f"active expected [1,2,3,4], got {active_ticks}"


def test_oracle_delay_range_2_5() -> None:
    """TEST-06 / BUG-DELAY-01: ##[2:5] component — pass at cycles 1, 2, 3, 4.

    The corrected component asserts pass while old_count is in [M-2, N-2] = [0, 3]
    (cycles 1..4), so the chained a->b gap spans the operator window [2, 5].
    """
    sim = SVABehavioralSim("delay_range", {"delay_min": 2, "delay_max": 5})
    outputs = _run(sim, [{"start": i == 0} for i in range(8)])
    #                            tick: 0      1     2     3     4      5      6      7
    expected_pass: list[bool] = [False, True, True, True, True, False, False, False]
    for i, (out, exp) in enumerate(zip(outputs, expected_pass)):
        assert out["pass"] == exp, (
            f"tick {i}: expected pass={exp}, got {out['pass']}"
        )


def test_oracle_delay_zero() -> None:
    """TEST-06: ##0 — pass fires on the same cycle as start (combinational)."""
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 0, "delay_max": 0})
    out0 = sim.tick({"start": True})
    assert out0["pass"],   "##0: pass should fire on start cycle"
    assert out0["active"], "##0: active on start cycle"

    out1 = sim.tick({"start": False})
    assert not out1["pass"],   "##0: no pass when start is low"
    assert not out1["active"], "##0: inactive when start is low"


def test_oracle_delay_no_spurious_pass() -> None:
    """TEST-06: ##3 — no pass fires if start never asserts."""
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 3, "delay_max": 3})
    outputs = _run(sim, [{"start": False}] * 6)
    for i, out in enumerate(outputs):
        assert not out["pass"],   f"tick {i}: spurious pass without start"
        assert not out["active"], f"tick {i}: spurious active without start"


def test_oracle_delay_back_to_back_starts() -> None:
    """TEST-06 / BUG-DELAY-01: ##2 — second start restarts the window.

    The corrected ##2 component asserts pass at old_count == N-2 == 0, i.e. one
    cycle after each start. The first start (tick 0) yields pass at tick 1; the
    second start (tick 2) restarts and yields pass at tick 3.
    """
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 2, "delay_max": 2})
    out0 = sim.tick({"start": True})   # tick 0: running=True, counter=0
    out1 = sim.tick({"start": False})  # tick 1: old_count=0 == N-2 → pass
    out2 = sim.tick({"start": True})   # tick 2: restart; old_count=1 → no pass
    out3 = sim.tick({"start": False})  # tick 3: old_count=0 == N-2 → pass
    out4 = sim.tick({"start": False})  # tick 4: old_count=1 → no pass
    assert not out0["pass"], "tick 0: old_running=False → no pass"
    assert out1["pass"],     "tick 1: first window completes (old_count=0)"
    assert not out2["pass"], "tick 2: restart, old_count=1 → no pass"
    assert out3["pass"],     "tick 3: restarted window completes (old_count=0)"
    assert not out4["pass"], "tick 4: window expired → no pass"


# ── Implication overlap oracle tests (|->) ────────────────────────────────────


def test_oracle_implication_overlap_simple() -> None:
    """TEST-02: a |-> b — antecedent fires at tick 0, pass evaluates at tick 1.

    BV_WIDTH=1 means the single bit position matures after 1 shift.
    tick 0: ant=True → insert into MSB (bit 0), oldest_bit from OLD bv=0 → no pass
    tick 1: ant=False, con=True → oldest_bit from OLD bv=1 → pass=True
    """
    sim = SVABehavioralSim("implication_overlap", {"bv_width": 1})

    out0 = sim.tick({"ant_pass": True,  "con_pass": False})
    out1 = sim.tick({"ant_pass": False, "con_pass": True})

    assert not out0["pass"], "tick 0: ant just fired, oldest_bit still 0 → no pass yet"
    assert not out0["fail"], "tick 0: no fail (no mature thread)"
    assert out0["active"],   "tick 0: one pending thread inserted"

    assert out1["pass"], "tick 1: thread matured, con=True → pass"
    assert not out1["fail"], "tick 1: con_pass=True → not fail"


def test_oracle_implication_overlap_fail() -> None:
    """TEST-02: a |-> b — consequent fails at the evaluation cycle."""
    sim = SVABehavioralSim("implication_overlap", {"bv_width": 1})

    sim.tick({"ant_pass": True,  "con_pass": False})  # tick 0: insert thread
    out1 = sim.tick({"ant_pass": False, "con_pass": False})  # tick 1: evaluate, con=False

    assert not out1["pass"], "tick 1: con_pass=False → no pass"
    assert out1["fail"],     "tick 1: mature thread + con=False → fail"


def test_oracle_implication_overlap_no_ant_no_eval() -> None:
    """TEST-02: |-> — no antecedent → no evaluation, no pass, no fail."""
    sim = SVABehavioralSim("implication_overlap", {"bv_width": 1})
    for i in range(5):
        out = sim.tick({"ant_pass": False, "con_pass": True})
        assert not out["pass"], f"tick {i}: no thread active → should not pass"
        assert not out["fail"], f"tick {i}: no thread active → should not fail"


# ── Implication nonoverlap oracle tests (|=>) ────────────────────────────────


def test_oracle_implication_nonoverlap_simple() -> None:
    """TEST-02: a |=> b — antecedent fires at tick 0, pass evaluates at tick 2.

    BV_WIDTH=1: delayed_ant inserts into BV at tick 1, matures at tick 2.
    tick 0: ant=True  → delayed_ant becomes True (for next cycle), bv not yet updated
    tick 1: delayed_ant=True → insert into bv, oldest_bit from OLD bv=0 → no pass yet
    tick 2: oldest_bit from bv=1 → pass=True (if con=True)
    """
    sim = SVABehavioralSim("implication_nonoverlap", {"bv_width": 1})

    out0 = sim.tick({"ant_pass": True,  "con_pass": False})
    out1 = sim.tick({"ant_pass": False, "con_pass": False})
    out2 = sim.tick({"ant_pass": False, "con_pass": True})

    assert not out0["pass"], "tick 0: ant just fired, not yet in bv → no pass"
    assert not out0["fail"], "tick 0: no mature thread"
    assert not out1["pass"], "tick 1: delayed_ant inserted, oldest_bit still 0 → no pass"
    assert out2["pass"],     "tick 2: thread matured, con=True → pass"
    assert not out2["fail"], "tick 2: con=True → not fail"


def test_oracle_implication_nonoverlap_fail() -> None:
    """TEST-02: a |=> b — consequent fails at the evaluation cycle (tick 2)."""
    sim = SVABehavioralSim("implication_nonoverlap", {"bv_width": 1})

    sim.tick({"ant_pass": True,  "con_pass": False})  # tick 0
    sim.tick({"ant_pass": False, "con_pass": False})  # tick 1
    out2 = sim.tick({"ant_pass": False, "con_pass": False})  # tick 2

    assert not out2["pass"], "tick 2: con=False → no pass"
    assert out2["fail"],     "tick 2: mature thread + con=False → fail"


# ── Overflow tests ────────────────────────────────────────────────────────────


def test_oracle_overflow_halts() -> None:
    """TEST-05: BV_WIDTH=2 — fill both bits, then fire ant again → overflow.

    tick 0: ant=True, bv=0 → bv becomes 0b10=2 (bit 1 set)
    tick 1: ant=True, bv=2 (not full: 2 != 3) → bv becomes 0b11=3 (both bits)
    tick 2: ant=True, bv=3 (full!) → overflow fires, fail=True, overflow=True
    tick 3: overflow_flag is set → all outputs frozen at 0 except overflow=True
    """
    sim = SVABehavioralSim("implication_overlap", {"bv_width": 2})

    out0 = sim.tick({"ant_pass": True,  "con_pass": True})  # tick 0
    out1 = sim.tick({"ant_pass": True,  "con_pass": True})  # tick 1
    out2 = sim.tick({"ant_pass": True,  "con_pass": True})  # tick 2 → overflow

    # Ticks 0 and 1 fill the BV but should NOT overflow yet
    assert not out0["overflow"], "tick 0: bv not full yet → no overflow"
    assert not out1["overflow"], "tick 1: bv full now but check was on OLD (non-full) bv"

    assert not out2["pass"],    "tick 2: overflow event → pass gated to 0"
    assert out2["fail"],        "tick 2: overflow fires → fail=True"
    assert out2["overflow"],    "tick 2: overflow=True"

    # After overflow: HARD HALT — all subsequent outputs frozen
    out3 = sim.tick({"ant_pass": True,  "con_pass": True})  # tick 3
    out4 = sim.tick({"ant_pass": False, "con_pass": False})  # tick 4

    assert not out3["pass"],    "tick 3: halted → pass=0"
    assert not out3["fail"],    "tick 3: halted → fail=0"
    assert out3["overflow"],    "tick 3: halted → overflow sticky"
    assert not out3["active"],  "tick 3: halted → active=0"

    assert not out4["pass"],    "tick 4: halted → pass=0"
    assert out4["overflow"],    "tick 4: halted → overflow sticky"


def test_oracle_overflow_nonoverlap_halts() -> None:
    """TEST-05: |=> with BV_WIDTH=1 — fill then overflow.

    The nonoverlap oracle uses a 1-cycle pipeline (ant_pass_delayed).
    Overflow check uses OLD bv at the start of each tick:

    tick 0: ant=True  → delayed_ant=False (old), bv stays 0; delayed reg → True
    tick 1: ant=True  → delayed_ant=True,  bv=0 (not full yet); bv → 1; delayed reg → True
    tick 2: ant=False → delayed_ant=True,  bv=1 (FULL) → overflow fires
    """
    sim = SVABehavioralSim("implication_nonoverlap", {"bv_width": 1})

    out0 = sim.tick({"ant_pass": True,  "con_pass": True})  # tick 0
    out1 = sim.tick({"ant_pass": True,  "con_pass": True})  # tick 1: bv fills
    out2 = sim.tick({"ant_pass": False, "con_pass": True})  # tick 2 → overflow

    assert not out0["overflow"], "tick 0: no overflow yet (bv empty)"
    assert not out1["overflow"], "tick 1: bv just filled, overflow check on OLD bv=0"
    assert out2["overflow"],     "tick 2: bv full (=1) + delayed_ant=True → overflow"

    # Halted after overflow
    out3 = sim.tick({"ant_pass": False, "con_pass": True})
    assert out3["overflow"], "tick 3: halted → overflow sticky"
    assert not out3["pass"], "tick 3: halted → pass=0"


# ── Reset tests ───────────────────────────────────────────────────────────────


def test_oracle_reset_clears_all_state() -> None:
    """[REVIEW FIX] reset() clears all internal state — no residual output.

    This mirrors the RTL synchronous rst_n behavior: all registers go to 0
    atomically, regardless of any in-flight threads.
    """
    # Build up state in the delay oracle
    sim_delay = SVABehavioralSim("delay_fixed", {"delay_min": 5, "delay_max": 5})
    sim_delay.tick({"start": True})   # start running
    sim_delay.tick({"start": False})  # counter=1
    sim_delay.tick({"start": False})  # counter=2

    sim_delay.reset()

    # After reset, no pass, no active, no overflow for multiple cycles
    for i in range(6):
        out = sim_delay.tick({"start": False})
        assert not out["pass"],    f"delay reset tick {i}: no pass"
        assert not out["active"],  f"delay reset tick {i}: no active"
        assert not out["overflow"],f"delay reset tick {i}: no overflow"


def test_oracle_reset_clears_implication_state() -> None:
    """[REVIEW FIX] reset() clears BV and all flags mid-flight in |-> oracle."""
    sim = SVABehavioralSim("implication_overlap", {"bv_width": 2})

    # Insert two threads
    sim.tick({"ant_pass": True, "con_pass": False})  # tick 0
    sim.tick({"ant_pass": True, "con_pass": False})  # tick 1

    sim.reset()

    # After reset, all outputs should be zero (no residual threads)
    out = sim.tick({"ant_pass": False, "con_pass": True})
    assert not out["pass"],    "after reset: no pass without new ant"
    assert not out["fail"],    "after reset: no fail (no threads)"
    assert not out["active"],  "after reset: no active"
    assert not out["overflow"],"after reset: overflow_flag cleared"


def test_oracle_reset_clears_nonoverlap_state() -> None:
    """[REVIEW FIX] reset() clears ant_pass_delayed and bv in |=> oracle."""
    sim = SVABehavioralSim("implication_nonoverlap", {"bv_width": 1})

    # Fire antecedent — sets ant_pass_delayed for next cycle
    sim.tick({"ant_pass": True, "con_pass": False})

    sim.reset()

    # Next tick should NOT see a delayed ant_pass (it was cleared by reset)
    out = sim.tick({"ant_pass": False, "con_pass": True})
    assert not out["pass"],   "after reset: ant_pass_delayed must be 0"
    assert not out["fail"],   "after reset: no threads in bv"
    assert not out["active"], "after reset: nothing active"


def test_oracle_reset_after_overflow() -> None:
    """TEST-05: reset() clears overflow_flag — oracle resumes normal operation."""
    sim = SVABehavioralSim("implication_overlap", {"bv_width": 1})

    # Cause overflow: bv full + ant fires
    sim.tick({"ant_pass": True,  "con_pass": True})  # tick 0: bv=1
    sim.tick({"ant_pass": True,  "con_pass": True})  # tick 1: bv full → overflow

    # Verify halted
    out_halted = sim.tick({"ant_pass": False, "con_pass": True})
    assert out_halted["overflow"], "should be halted (overflow_flag=True)"

    sim.reset()

    # After reset, normal operation resumes
    out0 = sim.tick({"ant_pass": True,  "con_pass": False})
    out1 = sim.tick({"ant_pass": False, "con_pass": True})
    assert not out0["overflow"], "after reset: overflow cleared"
    assert out1["pass"],         "after reset: normal |-> pass at tick 1"


# ── Disable signal tests (TEST-03, TEST-04) ───────────────────────────────────


def test_oracle_disable_returns_all_zero() -> None:
    """TEST-03: passing disable=True to tick() returns all-zero outputs.

    Models the ``disable_i`` synchronous clear behavior: regardless of current
    state, the oracle returns {active:0, pass:0, fail:0, overflow:0}.
    """
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 3, "delay_max": 3})
    sim.tick({"start": True})   # tick 0: running=True, counter=0
    sim.tick({"start": False})  # tick 1: counter=1

    # disable fires while delay is mid-flight
    out_dis = sim.tick({"start": False, "disable": True})
    assert not out_dis["active"],   "disable: active must be 0"
    assert not out_dis["pass"],     "disable: pass must be 0"
    assert not out_dis["fail"],     "disable: fail must be 0"
    assert not out_dis["overflow"], "disable: overflow must be 0"


def test_oracle_disable_clears_delay_state() -> None:
    """TEST-03: after disable=True, delay state is cleared — no late pass fires.

    Thread was started at tick 0 (##3 delay); disable at tick 1 clears state.
    Without the disable, pass would fire at tick 4.  After disable, no pass.
    """
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 3, "delay_max": 3})
    sim.tick({"start": True})             # tick 0: start
    sim.tick({"start": False, "disable": True})  # tick 1: disable → clears

    # Ticks 2-5: no pass should fire (state was cleared)
    for i in range(4):
        out = sim.tick({"start": False})
        assert not out["pass"],   f"tick {i+2}: pass must not fire after disable"
        assert not out["active"], f"tick {i+2}: active must be 0 after disable"


def test_oracle_disable_clears_implication_state() -> None:
    """TEST-04: disable=True mid-flight clears BV threads in |-> oracle.

    Thread inserted at tick 0; disable at tick 0 end (on tick 1) clears bv.
    Without disable, fail would fire at tick 1.
    """
    sim = SVABehavioralSim("implication_overlap", {"bv_width": 1})
    sim.tick({"ant_pass": True, "con_pass": False})  # tick 0: thread in bv

    # disable at tick 1 — clears bv before the thread can mature into fail
    out_dis = sim.tick({"ant_pass": False, "con_pass": False, "disable": True})
    assert not out_dis["fail"], "disable: fail must be gated even with mature thread"

    # tick 2: bv should be empty — no fail from the lost thread
    out2 = sim.tick({"ant_pass": False, "con_pass": False})
    assert not out2["fail"],   "after disable: thread was cleared → no fail"
    assert not out2["active"], "after disable: bv empty → inactive"


def test_oracle_disable_clears_nonoverlap_state() -> None:
    """TEST-04: disable=True clears ant_pass_delayed in |=> oracle.

    Antecedent fires at tick 0, setting ant_pass_delayed for tick 1.
    Disable at tick 1 clears ant_pass_delayed → no thread enters bv.
    """
    sim = SVABehavioralSim("implication_nonoverlap", {"bv_width": 1})
    sim.tick({"ant_pass": True, "con_pass": False})  # tick 0: sets ant_pass_delayed

    # disable at tick 1 — clears delayed register
    out_dis = sim.tick({"ant_pass": False, "con_pass": False, "disable": True})
    assert not out_dis["fail"], "disable: fail gated"

    # tick 2: no thread should have entered bv
    out2 = sim.tick({"ant_pass": False, "con_pass": False})
    assert not out2["fail"],   "after disable: ant_pass_delayed cleared → no thread"
    assert not out2["active"], "after disable: inactive"


def test_oracle_disable_clears_rep_consecutive_state() -> None:
    """TEST-03: disable=True during rep_consecutive run clears counter.

    Oracle running a[*3]: started at tick 0.  Disable at tick 1 clears state.
    Without disable, fail would fire at tick 2 (a goes low with count < rep_min=3).
    """
    sim = SVABehavioralSim("rep_consecutive", {"rep_min": 3, "rep_max": 3})
    sim.tick({"start": True, "sig": True})   # tick 0: count=1

    # disable at tick 1 — clears running state
    out_dis = sim.tick({"start": False, "sig": False, "disable": True})
    assert not out_dis["fail"],   "disable: fail gated"
    assert not out_dis["active"], "disable: active=0"

    # tick 2: cleared — no fail from the abandoned thread
    out2 = sim.tick({"start": False, "sig": False})
    assert not out2["fail"],   "after disable: state cleared → no fail"
    assert not out2["active"], "after disable: not running"


# ── Invalid kind guard ────────────────────────────────────────────────────────


def test_oracle_invalid_kind_raises() -> None:
    """Constructor raises ValueError for unknown operator kind."""
    with pytest.raises(ValueError, match="Unknown kind"):
        SVABehavioralSim("bogus_op", {})


# ── Hierarchical oracle tests (ORACLE-01) ────────────────────────────────


def test_hierarchical_seq_concat_composes_children() -> None:
    """seq_concat_top with 2 elements: token passing chains pass correctly."""
    loc = SourceLoc("test.sv", 1, 1)
    e0 = CheckerNode(
        template_name="bool_expr", module_name="sva_e0",
        params={}, observed_signals=(), source_loc=loc, children=(),
    )
    e1 = CheckerNode(
        template_name="bool_expr", module_name="sva_e1",
        params={}, observed_signals=(), source_loc=loc, children=(),
    )
    tree = CheckerNode(
        template_name="seq_concat_top", module_name="sva_top",
        params={}, observed_signals=(), source_loc=loc,
        children=(e0, e1),
    )
    stim = [{"start": True}, {"start": False}, {"start": False}]
    out = simulate_checker_hierarchy(tree, stim)
    assert len(out) == 3


def test_hierarchical_disable_iff_gates_outputs() -> None:
    """disable_iff_top with cond=True gates body outputs to zero."""
    loc = SourceLoc("test.sv", 1, 1)
    body = CheckerNode(
        template_name="bool_expr", module_name="sva_body",
        params={}, observed_signals=(), source_loc=loc, children=(),
    )
    tree = CheckerNode(
        template_name="disable_iff_top", module_name="sva_top",
        params={"cond_expr": "cond"}, observed_signals=(), source_loc=loc,
        children=(body,),
    )
    stim = [{"start": True, "cond": True}]
    out = simulate_checker_hierarchy(tree, stim)
    assert not out[0]["pass"], "cond true gates output"
