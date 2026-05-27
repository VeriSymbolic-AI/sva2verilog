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
            "rose",
            "fell",
            "stable",
            "past",
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

        # ── Signal function state ─────────────────────────────────────────
        self._sig_prev: bool = False
        depth: int = int(params.get("depth", 1))
        self._past_shift: list[bool] = [False] * max(depth, 1)

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
        self._sig_prev = False
        self._past_shift = [False] * len(self._past_shift)
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
            * Any kind: ``"disable": bool`` — models synchronous disable_i:
              clears all state and returns all-zero outputs (same as rst_n
              assertion but without clearing attempt_fired permanently).

        Returns
        -------
        dict with keys: ``"active"``, ``"pass"``, ``"fail"``, ``"overflow"``
        """
        # ── Synchronous disable: mirrors disable_i in the RTL templates ──────
        if bool(signals.get("disable", False)):
            self.reset()
            return {"active": False, "pass": False, "fail": False, "overflow": False}

        if self._kind in ("delay_fixed", "delay_range"):
            return self._tick_delay(signals)
        elif self._kind == "implication_overlap":
            return self._tick_overlap(signals)
        elif self._kind == "rep_consecutive":
            return self._tick_rep_consecutive(signals)
        elif self._kind == "rose":
            return self._tick_rose(signals)
        elif self._kind == "fell":
            return self._tick_fell(signals)
        elif self._kind == "stable":
            return self._tick_stable(signals)
        elif self._kind == "past":
            return self._tick_past(signals)
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
        # Capture OLD state BEFORE any update — mirrors RTL combinational
        # outputs reading registered (pre-NBA) values at posedge clk.
        old_running = self._running
        old_count = self._counter

        # State update (models always_ff NBA behavior)
        if start:
            self._counter = 0
            self._running = True
            self._attempt_fired = True
        elif old_running:
            if old_count >= delay_max:
                self._running = False
                self._counter = 0
            else:
                self._counter = old_count + 1

        # Outputs derived from OLD registered state (combinational in RTL):
        #   active = running_q (old)
        #   pass   = running_q && count_q in [delay_min, delay_max] (old)
        # On the start cycle old_running is False, so active=False, pass=False.
        # Pass first fires at the cycle where old_count == delay_min (i.e.,
        # delay_min cycles after start).
        active_val = old_running
        pass_val = old_running and (old_count >= delay_min) and (old_count <= delay_max)

        return {
            "active": active_val,
            "pass": pass_val,
            "fail": False,
            "overflow": False,
        }

    # ── Consecutive repetition model ([*M:N]) ─────────────────────────────

    def _tick_rep_consecutive(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model expr[*M:N] semantics: count consecutive cycles where sig is true.

        Mirrors RTL combinational outputs from OLD registered state:

        RTL ``always_ff`` only starts running on ``(start && sig_eval)``; a
        start with sig=False fires ``attempt_fired`` but does NOT set
        ``running_q`` (unlike the old Python model which set running=True with
        count=0).

        Outputs are combinational from OLD state + CURRENT sig:
          pass   = running_q(old) && sig && count_q(old) in [rep_min, rep_max]
          fail   = running_q(old) && !sig && count_q(old) < rep_min
          active = running_q(old)
        """
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))
        rep_min: int = int(self._params.get("rep_min", 1))
        rep_max: int = int(self._params.get("rep_max", 1))

        # Capture OLD state BEFORE any update
        old_running = self._rep_running
        old_count = self._rep_count

        # State update — mirrors RTL always_ff: only (start && sig) starts run
        if start and sig:
            self._rep_running = True
            self._rep_count = 1
            self._attempt_fired = True
        elif start and not sig:
            # Attempt fires but sequence immediately broken; RTL does NOT set
            # running_q=1 when start fires without sig.
            self._attempt_fired = True
        elif old_running and sig:
            if old_count < rep_max:
                self._rep_count = old_count + 1
        elif old_running and not sig:
            # Sequence broken — clear running
            self._rep_running = False
            self._rep_count = 0

        # Outputs derived from OLD registered state (combinational in RTL)
        pass_val = (
            old_running and sig
            and old_count >= rep_min
            and old_count <= rep_max
        )
        fail_val = old_running and not sig and old_count < rep_min
        active_val = old_running

        return {
            "active": active_val,
            "pass": pass_val,
            "fail": fail_val,
            "overflow": False,
        }

    # ── Signal function models ($rose, $fell, $stable, $past) ────────────

    def _tick_rose(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model $rose(sig): pass when sig transitions 0->1."""
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))

        # Detect BEFORE updating prev (models same-cycle registered compare)
        rose_detect = sig and not self._sig_prev
        self._sig_prev = sig

        if start:
            self._attempt_fired = True

        pass_val = start and rose_detect
        fail_val = start and not rose_detect
        return {"active": start, "pass": pass_val, "fail": fail_val, "overflow": False}

    def _tick_fell(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model $fell(sig): pass when sig transitions 1->0."""
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))

        fell_detect = not sig and self._sig_prev
        self._sig_prev = sig

        if start:
            self._attempt_fired = True

        pass_val = start and fell_detect
        fail_val = start and not fell_detect
        return {"active": start, "pass": pass_val, "fail": fail_val, "overflow": False}

    def _tick_stable(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model $stable(sig): pass when sig is unchanged from previous cycle."""
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))

        stable_detect = sig == self._sig_prev
        self._sig_prev = sig

        if start:
            self._attempt_fired = True

        pass_val = start and stable_detect
        fail_val = start and not stable_detect
        return {"active": start, "pass": pass_val, "fail": fail_val, "overflow": False}

    def _tick_past(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model $past(sig, N): pass when the value of sig N cycles ago was true.

        The shift register stores the last N values; index 0 is the oldest.
        On each tick: pop the oldest, push current sig at the front.
        past_value = the oldest sample (the one captured N cycles ago).
        """
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))

        # Oldest sample = index 0 (FIFO order: [oldest, ..., newest])
        # Actually we store [newest_at_[0], ..., oldest_at_[-1]] → shift left, oldest at end
        # Implementation: shift_q[-1] = oldest; insert sig at position 0
        past_value = self._past_shift[-1]

        # Shift right: drop oldest, push new sig at position 0
        self._past_shift = [sig] + self._past_shift[:-1]

        if start:
            self._attempt_fired = True

        pass_val = start and past_value
        fail_val = start and not past_value
        return {"active": start, "pass": pass_val, "fail": fail_val, "overflow": False}

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
