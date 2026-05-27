"""Behavioral reference oracle for SVA sequential operator semantics.

A minimal Python class that models SVA sequential operator semantics cycle-by-
cycle.  Used as test oracle to validate that generated RTL architectures produce
semantically correct pass/fail outputs matching IEEE 1800 definitions.

This is NOT a full simulation — it is a pure-Python reference implementation
that processes stimulus traces and produces expected pass/fail/active/overflow
output for comparison.

Supported operators:
    - ``"delay_fixed"``    — ``##N`` (fixed delay)
    - ``"delay_range"``    — ``##[M:N]`` (range delay)
    - ``"implication_overlap"``    — ``|->``
    - ``"implication_nonoverlap"`` — ``|=>``
"""

from __future__ import annotations

from typing import Any


class SVABehavioralSim:
    """Pure-Python behavioral model of SVA sequential operators.

    Parameters
    ----------
    kind:
        Operator kind; one of ``"delay_fixed"``, ``"delay_range"``,
        ``"implication_overlap"``, ``"implication_nonoverlap"``.
    params:
        Operator parameters dict.  Required keys depend on ``kind``:

        * ``"delay_fixed"``  / ``"delay_range"``:
          ``delay_min: int``, ``delay_max: int``
        * ``"implication_overlap"`` / ``"implication_nonoverlap"``:
          ``bv_width: int``
    """

    def __init__(self, kind: str, params: dict[str, Any]) -> None:
        _valid_kinds = {
            "delay_fixed",
            "delay_range",
            "implication_overlap",
            "implication_nonoverlap",
            "rep_consecutive",
        }
        if kind not in _valid_kinds:
            raise ValueError(f"Unknown kind '{kind}'; must be one of {_valid_kinds}")

        self._kind = kind
        self._params = params

        # ── Delay-operator state ───────────────────────────────────────────
        self._counter: int = 0       # counts cycles since start
        self._running: bool = False  # delay evaluation in progress

        # ── Repetition state ──────────────────────────────────────────────
        self._rep_count: int = 0
        self._rep_running: bool = False

        # ── Implication / bit-vector state ────────────────────────────────
        bv_width: int = int(params.get("bv_width", 1))
        self._bv_width: int = bv_width
        self._bv: int = 0            # Python int used as BV_WIDTH-bit shift reg
        self._overflow_flag: bool = False
        self._ant_pass_delayed: bool = False  # 1-cycle pipeline for |=>

        # ── Shared ────────────────────────────────────────────────────────
        self._attempt_fired: bool = False

    def reset(self) -> None:
        """Clear all internal state (models synchronous rst_n assertion)."""
        self._counter = 0
        self._running = False
        self._rep_count = 0
        self._rep_running = False
        self._bv = 0
        self._overflow_flag = False
        self._ant_pass_delayed = False
        self._attempt_fired = False

    def tick(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Advance the model by one clock cycle.

        Parameters
        ----------
        signals:
            Signal values for this cycle.  Expected keys depend on ``kind``:

            * Delay operators: ``"start": bool``
            * Implication operators: ``"ant_pass": bool``, ``"con_pass": bool``

        Returns
        -------
        dict with keys: ``"active"``, ``"pass"``, ``"fail"``, ``"overflow"``
        """
        if self._kind in ("delay_fixed", "delay_range"):
            return self._tick_delay(signals)
        elif self._kind == "implication_overlap":
            return self._tick_overlap(signals)
        elif self._kind == "rep_consecutive":
            return self._tick_rep_consecutive(signals)
        else:  # implication_nonoverlap
            return self._tick_nonoverlap(signals)

    # ── Delay operator model ───────────────────────────────────────────────

    def _tick_delay(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model ##N / ##[M:N] semantics."""
        start: bool = bool(signals.get("start", False))
        delay_min: int = int(self._params.get("delay_min", 0))
        delay_max: int = int(self._params.get("delay_max", 0))

        # ── ##0 special case: combinational pass-through ──────────────────
        if delay_min == 0 and delay_max == 0:
            if start:
                self._attempt_fired = True
            return {
                "active": start,
                "pass": start,
                "fail": False,
                "overflow": False,
            }

        # ── Counter-based delay ───────────────────────────────────────────
        # Capture pre-tick state
        was_running = self._running
        prev_count = self._counter

        # State update (models always_ff behavior)
        if start:
            self._counter = 0
            self._running = True
            self._attempt_fired = True
        elif was_running:
            if prev_count >= delay_max:
                self._running = False
                self._counter = 0
            else:
                self._counter = prev_count + 1

        # Output based on NEW state
        cur_running = self._running
        cur_count = self._counter

        # If start just fired, count is 0 and running is True
        if start:
            active = True
            chk_count = 0
        else:
            active = cur_running
            chk_count = cur_count

        # pass = running and count in [delay_min, delay_max]
        # But we model registered outputs: pass reflects the state that
        # was latched at the END of this cycle.
        # For a counter starting at 0 on start:
        #   cycle 0 (start): count=0, pass iff delay_min==0
        #   cycle 1: count=1, pass iff 1 in [delay_min, delay_max]
        pass_val = active and (chk_count >= delay_min) and (chk_count <= delay_max)

        return {
            "active": active,
            "pass": pass_val,
            "fail": False,
            "overflow": False,
        }

    # ── Consecutive repetition model ([*M:N]) ─────────────────────────────

    def _tick_rep_consecutive(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model expr[*M:N] semantics: count consecutive cycles where sig is true.

        start+sig on a cycle begins counting (count=1, running=True).
        Each subsequent cycle where sig is true increments the counter (capped at rep_max).
        Any cycle where sig is false while running clears the state (broken sequence).
        pass = running and sig and count in [rep_min, rep_max]
        fail = running and not sig and count < rep_min
        """
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))
        rep_min: int = int(self._params.get("rep_min", 1))
        rep_max: int = int(self._params.get("rep_max", 1))

        if start and sig:
            self._rep_running = True
            self._rep_count = 1
            self._attempt_fired = True
        elif start and not sig:
            # start with sig=False: start attempt fires but immediately breaks
            self._rep_running = True
            self._rep_count = 0
            self._attempt_fired = True
        elif self._rep_running and sig:
            if self._rep_count < rep_max:
                self._rep_count += 1
        elif self._rep_running and not sig:
            # sequence broken
            pass  # evaluate fail before clearing below

        pass_val = (
            self._rep_running and sig
            and self._rep_count >= rep_min
            and self._rep_count <= rep_max
        )
        fail_val = self._rep_running and not sig and self._rep_count < rep_min
        active_val = self._rep_running

        # Clear running state on broken sequence (after computing fail)
        if self._rep_running and not sig:
            self._rep_running = False
            self._rep_count = 0

        return {
            "active": active_val,
            "pass": pass_val,
            "fail": fail_val,
            "overflow": False,
        }

    # ── Overlapping implication model (|->)  ──────────────────────────────

    def _tick_overlap(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model |-> semantics with shift-register bit-vector.

        The antecedent pass is inserted into bit[MSB] on the same cycle it
        fires.  All bits shift right each cycle.  The consequent is evaluated
        when bv[MSB] is set.
        """
        ant_pass: bool = bool(signals.get("ant_pass", False))
        con_pass: bool = bool(signals.get("con_pass", False))

        if ant_pass:
            self._attempt_fired = True

        # Overflow: antecedent fires while ALL BV_WIDTH bit positions occupied
        bv_full = (self._bv == (1 << self._bv_width) - 1)
        overflow_event = ant_pass and bv_full and not self._overflow_flag

        if self._overflow_flag:
            # HARD HALT: freeze everything, only reset clears
            return {
                "active": False,
                "pass": False,
                "fail": False,
                "overflow": True,
            }

        if overflow_event:
            self._overflow_flag = True
            return {
                "active": False,
                "pass": False,
                "fail": True,   # overflow fires → fail on same cycle
                "overflow": True,
            }

        # Normal operation: shift BV right, insert ant_pass at MSB
        # bv shifts right (bits age), new thread enters at position BV_WIDTH-1
        new_bv = (self._bv >> 1) | ((1 << (self._bv_width - 1)) if ant_pass else 0)

        # Evaluation: oldest thread (bv[MSB] of OLD bv) matures this cycle
        oldest_bit = (self._bv >> (self._bv_width - 1)) & 1

        # pass/fail are based on whether the oldest thread matured
        pass_val = bool(oldest_bit) and con_pass
        fail_val = bool(oldest_bit) and not con_pass

        # active = any thread pending (including new one just inserted)
        active = bool(new_bv != 0)

        # Commit new state
        self._bv = new_bv

        return {
            "active": active,
            "pass": pass_val,
            "fail": fail_val,
            "overflow": False,
        }

    # ── Non-overlapping implication model (|=>)  ──────────────────────────

    def _tick_nonoverlap(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model |=> semantics: antecedent pass delayed 1 cycle before insertion."""
        ant_pass: bool = bool(signals.get("ant_pass", False))
        con_pass: bool = bool(signals.get("con_pass", False))

        if ant_pass:
            self._attempt_fired = True

        # Use the DELAYED antecedent pass for this cycle's BV insertion
        delayed_ant = self._ant_pass_delayed
        # Update delay register for next cycle
        self._ant_pass_delayed = ant_pass

        # Overflow: delayed antecedent fires while all BV positions occupied
        bv_full = (self._bv == (1 << self._bv_width) - 1)
        overflow_event = delayed_ant and bv_full and not self._overflow_flag

        if self._overflow_flag:
            return {
                "active": False,
                "pass": False,
                "fail": False,
                "overflow": True,
            }

        if overflow_event:
            self._overflow_flag = True
            return {
                "active": False,
                "pass": False,
                "fail": True,
                "overflow": True,
            }

        # Normal operation: shift BV right, insert delayed_ant at MSB
        oldest_bit = (self._bv >> (self._bv_width - 1)) & 1
        new_bv = (self._bv >> 1) | ((1 << (self._bv_width - 1)) if delayed_ant else 0)

        pass_val = bool(oldest_bit) and con_pass
        fail_val = bool(oldest_bit) and not con_pass
        active = bool(new_bv != 0) or bool(delayed_ant)

        self._bv = new_bv

        return {
            "active": active,
            "pass": pass_val,
            "fail": fail_val,
            "overflow": False,
        }
