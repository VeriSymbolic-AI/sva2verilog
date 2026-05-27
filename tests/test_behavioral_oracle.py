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

from sva2rtl.behavioral_oracle import SVABehavioralSim

# ── Helper ────────────────────────────────────────────────────────────────────


def _run(sim: SVABehavioralSim, stimuli: list[dict[str, bool]]) -> list[dict[str, bool]]:
    """Drive the oracle through a list of per-cycle stimulus dicts.

    Returns a list of output dicts (one per cycle) in the same order as stimuli.
    """
    return [sim.tick(s) for s in stimuli]


# ── Delay oracle tests ────────────────────────────────────────────────────────


def test_oracle_delay_fixed_3() -> None:
    """TEST-06: ##3 — start at cycle 0 → pass at cycle 4 only.

    The oracle outputs are derived from OLD registered state (combinational RTL):
    Cycle 0 (start): old_running=False → active=False, pass=False
    Cycle 1: old_count=0 → active=True, pass=False (0 < 3)
    Cycle 2: old_count=1 → active=True, pass=False (1 < 3)
    Cycle 3: old_count=2 → active=True, pass=False (2 < 3)
    Cycle 4: old_count=3 == delay_min → active=True, pass=True
    Cycle 5: old_running=False (expired) → active=False, pass=False
    """
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 3, "delay_max": 3})
    outputs = _run(sim, [
        {"start": True},   # tick 0
        {"start": False},  # tick 1
        {"start": False},  # tick 2
        {"start": False},  # tick 3
        {"start": False},  # tick 4  → pass
        {"start": False},  # tick 5  → inactive
    ])
    assert not outputs[0]["pass"], "tick 0: old_running=False → no pass"
    assert not outputs[1]["pass"], "tick 1: old_count=0 < 3 → no pass"
    assert not outputs[2]["pass"], "tick 2: old_count=1 < 3 → no pass"
    assert not outputs[3]["pass"], "tick 3: old_count=2 < 3 → no pass"
    assert outputs[4]["pass"],     "tick 4: old_count=3 == delay_min → pass"
    assert not outputs[5]["pass"], "tick 5: counter expired, no pass"

    # active: start cycle sees old_running=False; ticks 1–4 see old_running=True
    assert not outputs[0]["active"], "tick 0: start fires but old_running=False"
    assert outputs[1]["active"], "tick 1: active (running)"
    assert outputs[2]["active"], "tick 2: active (running)"
    assert outputs[3]["active"], "tick 3: active (running)"
    assert outputs[4]["active"], "tick 4: active at pass point"
    assert not outputs[5]["active"], "tick 5: inactive after window expired"


def test_oracle_delay_range_2_5() -> None:
    """TEST-06: ##[2:5] — start at cycle 0 → pass at cycles 3, 4, 5, 6.

    Outputs are from OLD registered state; start cycle has old_running=False so
    pass=False.  Pass window opens one cycle later than the raw counter value.
    """
    sim = SVABehavioralSim("delay_range", {"delay_min": 2, "delay_max": 5})
    outputs = _run(sim, [{"start": i == 0} for i in range(8)])
    #                            tick: 0      1      2      3     4     5     6     7
    expected_pass: list[bool] = [False, False, False, True, True, True, True, False]
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
    """TEST-06: ##2 — second start overwrites counter, restarting the window.

    With OLD-state outputs the pass fires one cycle later than the raw counter:
    After second start at tick 2, pass fires at tick 5 (old_count=2 == delay_min).
    """
    sim = SVABehavioralSim("delay_fixed", {"delay_min": 2, "delay_max": 2})
    # First start at tick 0
    sim.tick({"start": True})   # tick 0: running=True, counter=0
    sim.tick({"start": False})  # tick 1: counter→1
    # Second start at tick 2 — should RESTART counter
    out2 = sim.tick({"start": True})   # tick 2: old_count=1, counter reset to 0
    # After restart, pass should fire 3 more cycles later (old_count=2 == delay_min)
    out3 = sim.tick({"start": False})  # tick 3: old_count=0 < 2 → no pass
    out4 = sim.tick({"start": False})  # tick 4: old_count=1 < 2 → no pass
    out5 = sim.tick({"start": False})  # tick 5: old_count=2 == delay_min → pass
    assert not out2["pass"], "restart tick: old_count=1 < delay_min=2"
    assert not out3["pass"], "1 cycle after restart: old_count=0 < delay_min=2"
    assert not out4["pass"], "2 cycles after restart: old_count=1 < delay_min=2"
    assert out5["pass"],     "3 cycles after restart: old_count=2 → pass"


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


# ── Invalid kind guard ────────────────────────────────────────────────────────


def test_oracle_invalid_kind_raises() -> None:
    """Constructor raises ValueError for unknown operator kind."""
    with pytest.raises(ValueError, match="Unknown kind"):
        SVABehavioralSim("bogus_op", {})
