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

import re as _re_oracle
from collections.abc import Mapping
from typing import Any

from sva2rtl.bool_semantics import deserialize_bool_expr, eval_bool_expr


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
            "changed",
            "goto_rep",
            "nonconsec_rep",
        }
        if kind not in _valid_kinds:
            raise ValueError(f"Unknown kind '{kind}'; must be one of {_valid_kinds}")

        self._kind = kind
        self._params = params

        # ── Delay-operator state ───────────────────────────────────────────
        self._counter: int = 0  # counts cycles since start
        self._running: bool = False  # delay evaluation in progress

        # ── Repetition state ──────────────────────────────────────────────
        self._rep_count: int = 0
        self._rep_running: bool = False
        self._rep_passed: bool = False

        # ── Signal function state ─────────────────────────────────────────
        self._sig_prev: bool = False
        depth: int = int(params.get("depth", 1))
        self._past_shift: list[bool] = [False] * max(depth, 1)

        # ── Implication / bit-vector state ────────────────────────────────
        bv_width: int = int(params.get("bv_width", 1))
        self._bv_width: int = bv_width
        self._bv: int = 0  # Python int used as BV_WIDTH-bit shift reg
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
        self._rep_passed = False
        self._sig_prev = False
        self._past_shift = [False] * len(self._past_shift)
        self._bv = 0
        self._overflow_flag = False
        self._ant_pass_delayed = False
        self._attempt_fired = False

    @property
    def attempt_fired(self) -> bool:
        """Return whether this model has ever accepted an attempt since reset."""

        return self._attempt_fired

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
            attempt_fired = self._attempt_fired
            self.reset()
            self._attempt_fired = attempt_fired
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
        elif self._kind == "changed":
            return self._tick_changed(signals)
        elif self._kind == "goto_rep":
            return self._tick_goto_rep(signals)
        elif self._kind == "nonconsec_rep":
            return self._tick_nonconsec_rep(signals)
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

        # BUG-DELAY-01 corrected outputs. Derivation (from the chain contract,
        # NOT copied from the RTL comparator — see .planning/BUG-delay-spacing.md):
        # in the chain bool_expr(a) -> concat_delay -> bool_expr(b), the previous
        # element's match arrives as ``start`` one cycle after a was sampled, and
        # the next element samples its signal on the cycle concat_delay asserts
        # ``pass``. For the net a->b sample gap to equal the operator delay N, this
        # component must assert ``pass`` at start+(N-1). Since old_count == k is the
        # registered value visible at cycle start+1+k, a target cycle start+(N-1)
        # corresponds to old_count == N-2; a ranged delay [M,N] uses old_count in
        # [M-2, N-2]. A target AT the start cycle itself (when the window includes a
        # gap of 1, i.e. delay_min<=1<=delay_max) is produced combinationally from
        # the current ``start``. The fusion gap-0 case is the ##0 branch above; a
        # window whose lower bound is 0 cannot reach gap 0 through registered leaves
        # and so simply starts at gap 1 (documented limitation).
        cmin = max(delay_min - 2, 0)
        cmax = max(delay_max - 2, 0)
        pass_at_start = start and (delay_min <= 1) and (delay_max >= 1)
        pass_counter = (
            delay_max >= 2 and old_running and (old_count >= cmin) and (old_count <= cmax)
        )
        active_val = old_running
        pass_val = pass_at_start or pass_counter

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

        # State update — mirrors RTL always_ff.  A false expression cannot
        # start a new run, but it must still terminate an already-running
        # attempt even when a new ``start`` pulse arrives on the same cycle.
        if start:
            self._attempt_fired = True
        if start and sig:
            self._rep_running = True
            self._rep_count = 1
        elif old_running and sig:
            if old_count < rep_max:
                self._rep_count = old_count + 1
        elif old_running:
            # Sequence broken — clear running
            self._rep_running = False
            self._rep_count = 0

        # Outputs derived from OLD registered state (combinational in RTL)
        pass_val = old_running and sig and old_count >= rep_min and old_count <= rep_max
        fail_val = old_running and not sig and old_count < rep_min
        active_val = old_running

        return {
            "active": active_val,
            "pass": pass_val,
            "fail": fail_val,
            "overflow": False,
        }

    # ── Goto repetition model ([->N]) ─────────────────────────────────────

    def _tick_goto_rep(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model expr[->N] semantics: count non-consecutive occurrences.

        Counts cycles where sig=true. Passes immediately when count reaches
        rep_min..rep_max. Once passed, stays in pass state.
        """
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))
        rep_min: int = int(self._params.get("rep_min", 1))
        rep_max: int = int(self._params.get("rep_max", 1))

        old_count = self._rep_count
        old_running = self._rep_running
        old_passed = self._rep_passed

        hit_from_start = start and not old_running and not old_passed and sig and rep_min <= 1
        hit_from_running = old_running and not old_passed and sig and old_count >= rep_min - 1
        pass_val = old_passed or hit_from_start or hit_from_running
        if start:
            self._attempt_fired = True

        if pass_val:
            self._rep_passed = True
            self._rep_running = False
        elif start and not old_running:
            self._rep_running = True
            self._rep_count = 1 if sig else 0
            self._attempt_fired = True
        elif old_running and sig:
            if old_count < rep_max:
                self._rep_count = old_count + 1

        active_val = (start or old_running) and not pass_val

        return {
            "active": active_val,
            "pass": pass_val,
            "fail": False,
            "overflow": False,
        }

    # ── Non-consecutive repetition model ([=N]) ───────────────────────────

    def _tick_nonconsec_rep(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model expr[=N] semantics: count occurrences, relaxed tail.

        Counts cycles where sig=true. Passes when count >= rep_min.
        Unlike [->N], no tight completion requirement.
        """
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))
        rep_min: int = int(self._params.get("rep_min", 1))
        rep_max: int = int(self._params.get("rep_max", 1))

        old_count = self._rep_count
        old_running = self._rep_running
        old_passed = self._rep_passed

        hit_from_start = start and not old_running and not old_passed and sig and rep_min <= 1
        hit_from_running = old_running and not old_passed and sig and old_count >= rep_min - 1
        pass_val = old_passed or hit_from_start or hit_from_running
        if start:
            self._attempt_fired = True

        if pass_val:
            self._rep_passed = True
            self._rep_running = False
        elif start and not old_running:
            self._attempt_fired = True
            self._rep_running = True
            if sig and old_count < rep_max:
                self._rep_count = 1
        elif old_running and sig:
            if old_count < rep_max:
                self._rep_count = old_count + 1

        active_val = (start or old_running) and not pass_val

        return {
            "active": active_val,
            "pass": pass_val,
            "fail": False,
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

    def _tick_changed(self, signals: dict[str, bool]) -> dict[str, bool]:
        """Model $changed(sig): pass when sig differs from previous cycle."""
        start: bool = bool(signals.get("start", False))
        sig: bool = bool(signals.get("sig", False))

        changed_detect = sig != self._sig_prev
        self._sig_prev = sig

        if start:
            self._attempt_fired = True

        pass_val = start and changed_detect
        fail_val = start and not changed_detect
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

        NOTE (BUG-IMPL-01): this standalone token-passing model corresponds to
        the multi-cycle (sequence-consequent, BV_WIDTH>1) RTL path.  The
        single-cycle-consequent implication (BV_WIDTH==1) was switched to a
        parallel-consequent design whose correctness is established by the
        SymbiYosys formal-equivalence proofs in tests/test_formal_sva_equiv.py,
        not by this model.  This method is exercised only by the oracle's own
        unit tests (tests/test_behavioral_oracle.py); the hierarchical RTL
        cross-check uses ``_tick_implication``.
        """
        ant_pass: bool = bool(signals.get("ant_pass", False))
        con_pass: bool = bool(signals.get("con_pass", False))

        if ant_pass:
            self._attempt_fired = True

        # Overflow: antecedent fires while ALL BV_WIDTH bit positions occupied
        bv_full = self._bv == (1 << self._bv_width) - 1
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
                "fail": True,  # overflow fires → fail on same cycle
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
        """Model |=> semantics: antecedent pass delayed 1 cycle before insertion.

        NOTE (BUG-IMPL-01): like ``_tick_overlap``, this standalone token-passing
        model corresponds to the multi-cycle (BV_WIDTH>1) RTL path.  The
        single-cycle-consequent |=> (BV_WIDTH==1) now uses con_start=ant_pass_w
        (parallel consequent), proven correct in tests/test_formal_sva_equiv.py.
        This method is exercised only by the oracle's own unit tests.
        """
        ant_pass: bool = bool(signals.get("ant_pass", False))
        con_pass: bool = bool(signals.get("con_pass", False))

        if ant_pass:
            self._attempt_fired = True

        # Use the DELAYED antecedent pass for this cycle's BV insertion
        delayed_ant = self._ant_pass_delayed
        # Update delay register for next cycle
        self._ant_pass_delayed = ant_pass

        # Overflow: delayed antecedent fires while all BV positions occupied
        bv_full = self._bv == (1 << self._bv_width) - 1
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


# ── Hierarchical oracle: composes SVABehavioralSim instances ─────────────
# Appended to behavioral_oracle.py for Phase 4 (ORACLE-01).


def simulate_checker_hierarchy(
    tree: CheckerNode,
    stimulus: list[dict[str, bool]],
) -> list[dict[str, bool]]:
    """Simulate a composed checker tree cycle-by-cycle.

    Walks the CheckerNode hierarchy, instantiates SVABehavioralSim for each
    leaf template, and wires them according to the token-passing architecture
    (seq_concat_top, overlap_bitvec, disable_iff_top).
    """
    hier_sim = _HierarchicalSim(tree)
    return [hier_sim.tick(cycle) for cycle in stimulus]


_LEAF_TEMPLATES: frozenset[str] = frozenset(
    {
        "bool_expr",
        "concat_delay",
        "delay_fixed",
        "delay_range",
        "rep_consecutive",
        "rose",
        "fell",
        "stable",
        "past",
        "changed",
        "goto_rep",
        "nonconsec_rep",
        "overlap_bitvec",
        "nonoverlap",
    }
)

_TEMPLATE_ORACLE_MAP: dict[str, str] = {
    "bool_expr": "delay_fixed",
    "concat_delay": "delay_fixed",
    "delay_fixed": "delay_fixed",
    "delay_range": "delay_range",
    "rep_consecutive": "rep_consecutive",
    "rose": "rose",
    "fell": "fell",
    "stable": "stable",
    "past": "past",
    "changed": "changed",
    "goto_rep": "goto_rep",
    "nonconsec_rep": "nonconsec_rep",
    "overlap_bitvec": "implication_overlap",
    "nonoverlap": "implication_nonoverlap",
}


class _HierarchicalSim:
    """Internal: evaluates a checker tree by wiring child oracles."""

    def __init__(self, root: CheckerNode) -> None:
        self._root = root
        self._leaf_oracles: dict[str, SVABehavioralSim] = {}
        self._bool_leaf_state: dict[str, dict[str, bool]] = {}
        self._build_oracles(root)

    def _build_oracles(self, node: CheckerNode) -> None:
        tname = node.template_name
        if tname in _LEAF_TEMPLATES:
            params = _extract_oracle_params(node)
            self._leaf_oracles[node.module_name] = SVABehavioralSim(
                _TEMPLATE_ORACLE_MAP[tname], params
            )
        for child in node.children:
            self._build_oracles(child)

    def tick(self, signals: dict[str, bool]) -> dict[str, bool]:
        return self._tick_node(self._root, signals)

    def _tick_node(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        tname = node.template_name
        if tname == "bool_expr" and "bool_semantic" in node.params:
            return self._tick_bool_expr_semantic(node, signals)
        if tname in ("overlap_bitvec", "nonoverlap") and node.children:
            return self._tick_implication(node, signals, tname)
        if tname in _LEAF_TEMPLATES:
            oracle = self._leaf_oracles[node.module_name]
            return oracle.tick(_map_stimulus(tname, signals, node))
        if tname == "seq_concat_top":
            return self._tick_seq_concat(node, signals)
        if tname == "disable_iff_top":
            return self._tick_disable_iff(node, signals)
        if tname == "first_match_top":
            return self._tick_first_match(node, signals)
        if tname == "implication_nfa":
            return self._tick_implication_nfa(node, signals)
        if tname == "prop_or":
            return self._tick_prop_or(node, signals)
        if tname == "prop_and":
            return self._tick_prop_and(node, signals)
        if tname == "prop_intersect":
            return self._tick_prop_intersect(node, signals)
        if tname == "prop_within":
            return self._tick_prop_within(node, signals)
        if tname == "prop_throughout":
            return self._tick_prop_throughout(node, signals)
        if tname == "prop_not":
            return self._tick_prop_not(node, signals)
        if tname == "prop_if_else":
            return self._tick_prop_if_else(node, signals)
        if tname == "s_eventually":
            return self._tick_s_eventually(node, signals)
        if tname == "s_always":
            return self._tick_s_always(node, signals)
        if tname == "until":
            return self._tick_until_prop(node, signals)
        if tname == "nfa_generic":
            return self._tick_nfa_generic(node, signals)
        if node.children:
            return self._tick_node(node.children[0], signals)
        return {"pass": False, "fail": False, "active": False, "overflow": False}

    def _tick_bool_expr_semantic(
        self,
        node: CheckerNode,
        signals: dict[str, bool],
    ) -> dict[str, bool]:
        """Tick a structured bool_expr leaf with registered pass/fail outputs."""
        state = self._bool_leaf_state.setdefault(
            node.module_name,
            {"active": False, "pass": False, "fail": False},
        )
        out = {
            "active": state["active"],
            "pass": state["pass"],
            "fail": state["fail"],
            "overflow": False,
        }

        if bool(signals.get("disable", False)):
            state["active"] = False
            state["pass"] = False
            state["fail"] = False
            return {"active": False, "pass": False, "fail": False, "overflow": False}

        start = bool(signals.get("start", False))
        truth = _eval_bool_semantic_param(node, signals)
        if truth is None:
            # Fall back to observed-signal semantics (AND of all watched signals).
            sigs = [port for port, _ in node.observed_signals]
            if sigs:
                truth = all(bool(signals.get(s, False)) for s in sigs)
            else:
                truth = bool(signals.get("sig", True))
        state["active"] = start
        state["pass"] = start and truth
        state["fail"] = start and not truth
        return out

    def _tick_seq_concat(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        children = node.children
        prev_pass = False
        any_fail = False
        any_active = False
        for i, child in enumerate(children):
            child_sigs = dict(signals)
            child_sigs["start"] = signals.get("start", False) if i == 0 else prev_pass
            out = self._tick_node(child, child_sigs)
            prev_pass = out["pass"]
            if out["fail"]:
                any_fail = True
            if out["active"]:
                any_active = True
        return {"pass": prev_pass, "fail": any_fail, "active": any_active, "overflow": False}

    def _tick_disable_iff(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """Tick disable_iff_top: gate body outputs when disable is active.

        RTL semantics: ``effective_disable = disable_i | cond_result``
        where ``cond_result`` is the evaluated ``cond_expr`` (e.g. ``!rst_n``).
        When effective_disable is true: all outputs are 0 and body state is
        reset (mirrors RTL synchronous disable).

        v1.5.2 fix: previously only checked ``cond_expr`` signals, ignoring the
        external ``disable_i`` input. Also, the body was ticked with
        ``{"disable": True}`` but composite nodes (overlap_bitvec, seq_concat_top)
        do not propagate the ``"disable"`` key to leaf oracles — so leaf state
        was never reset and accumulated fail events leaked through.
        Now: on disable, walk the body tree and reset all leaf oracles, then
        return all-zero outputs without ticking the body.
        """
        body = node.children[0] if node.children else None
        if body is None:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        cond_semantic = node.params.get("cond_semantic")
        if cond_semantic is not None:
            cond_val = bool(eval_bool_expr(deserialize_bool_expr(cond_semantic), signals))
        else:
            # Compatibility path for legacy / hand-built CheckerNodes. New
            # compiler output always carries structured ``cond_semantic`` so
            # aliases, comparisons and compound expressions are not inferred
            # from fragile generated text.
            cond_text = node.params.get("cond_expr", "")
            cond_sigs = _re_oracle.findall(r"\b([a-zA-Z_]\w*)\b", cond_text)
            if cond_sigs:
                unwrapped = cond_text.lstrip(" (\t\r\n")
                is_negated = unwrapped.startswith(("!", "~"))
                if is_negated:
                    cond_val = any(not signals.get(s, False) for s in cond_sigs)
                else:
                    cond_val = all(signals.get(s, False) for s in cond_sigs)
            else:
                cond_val = signals.get("cond", False)

        disable_i = signals.get("disable_i", False)
        effective_disable = bool(disable_i) or cond_val

        if effective_disable:
            self._reset_subtree(body)
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        return self._tick_node(body, signals)

    def _reset_subtree(self, node: CheckerNode) -> None:
        """Reset all leaf oracles in a checker subtree."""
        tname = node.template_name
        if tname in _LEAF_TEMPLATES:
            oracle = self._leaf_oracles.get(node.module_name)
            if oracle is not None:
                oracle.reset()
            self._bool_leaf_state.pop(node.module_name, None)
        for child in node.children:
            self._reset_subtree(child)

    def _tick_first_match(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """Tick a first_match_top wrapper: gate outputs once body passes.

        On the cycle the body first passes, output is passed through and the
        node is locked.  All subsequent cycles return inactive/false until the
        next start fires, which resets the lock.
        """
        body = node.children[0] if node.children else None
        if body is None:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        out = self._tick_node(body, signals)

        key = node.module_name
        if not hasattr(self, "_fm_locked"):
            self._fm_locked: dict[str, bool] = {}

        # Reset lock on new start (new evaluation window)
        if signals.get("start", False):
            self._fm_locked[key] = False

        locked = self._fm_locked.get(key, False)

        # On the first pass cycle: pass through and set lock
        if out["pass"] and not locked:
            self._fm_locked[key] = True
            return out  # pass=1, fail=0 (body just completed)
        # Already locked: suppress everything
        if locked:
            return {
                "pass": False,
                "fail": False,
                "active": False,
                "overflow": out.get("overflow", False),
            }
        # Not yet passed, not locked: pass through body outputs
        return out

    # ── Phase 3: Complex sequence operator oracles (v1.3) ────────────────

    def _tick_prop_or(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """prop_or: pass on either match; fail only after both alternatives fail."""
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        lhs = self._tick_node(node.children[0], signals)
        rhs = self._tick_node(node.children[1], signals)

        key = node.module_name
        if not hasattr(self, "_or_state"):
            self._or_state: dict[str, dict[str, bool]] = {}
        if key not in self._or_state:
            self._or_state[key] = {"left_f": False, "right_f": False}
        st = self._or_state[key]

        if signals.get("disable", False):
            st["left_f"] = False
            st["right_f"] = False
            return {"pass": False, "fail": False, "active": False, "overflow": False}

        if signals.get("start", False) and not lhs["active"] and not rhs["active"]:
            st["left_f"] = False
            st["right_f"] = False

        pass_val = lhs["pass"] or rhs["pass"]
        fail_val = (lhs["fail"] and (rhs["fail"] or st["right_f"])) or (
            rhs["fail"] and (lhs["fail"] or st["left_f"])
        )

        if pass_val or fail_val:
            st["left_f"] = False
            st["right_f"] = False
        else:
            st["left_f"] = st["left_f"] or lhs["fail"]
            st["right_f"] = st["right_f"] or rhs["fail"]

        return {
            "pass": pass_val,
            "fail": fail_val,
            "active": lhs["active"] or rhs["active"],
            "overflow": lhs.get("overflow", False) or rhs.get("overflow", False),
        }

    def _tick_prop_and(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """prop_and: both must eventually pass; matches when the LATER one completes.

        IEEE 1800-2017: s1 and s2 — both start at the same time; the ``and``
        matches at the cycle where the last of the two sequences finishes.  We
        latch each side's pass so that ``body_pass`` fires on the cycle where
        the trailing side completes.

        Matched state is cleared when a new start fires and neither side is
        currently active (i.e. the previous evaluation has completed).
        """
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        lhs = self._tick_node(node.children[0], signals)
        rhs = self._tick_node(node.children[1], signals)

        key = node.module_name
        if not hasattr(self, "_and_state"):
            self._and_state: dict[str, dict[str, bool]] = {}
        if key not in self._and_state:
            self._and_state[key] = {"left_m": False, "right_m": False}
        st = self._and_state[key]

        if signals.get("disable", False):
            st["left_m"] = False
            st["right_m"] = False

        # Clear matched state on new start when previous evaluation is done
        if signals.get("start", False) and not lhs["active"] and not rhs["active"]:
            st["left_m"] = False
            st["right_m"] = False

        if lhs["pass"]:
            st["left_m"] = True
        if rhs["pass"]:
            st["right_m"] = True

        pass_val = (
            (lhs["pass"] and st["right_m"])
            or (rhs["pass"] and st["left_m"])
            or (lhs["pass"] and rhs["pass"])
        )
        return {
            "pass": pass_val,
            "fail": lhs["fail"] or rhs["fail"],
            "active": lhs["active"] or rhs["active"],
            "overflow": lhs.get("overflow", False) or rhs.get("overflow", False),
        }

    def _tick_prop_intersect(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """prop_intersect: both must pass at same cycle (intersection).

        RISK-02 (v1.5 G1): for boolean-atom operands the child oracle is
        vacuously ``pass=True`` because ``bool_expr`` is modelled as
        ``delay_fixed(0,0)``. To honour the actual operand values (per
        IEEE 1800 §16.9.7), we AND the sub-checker pass signals with an
        independently-derived boolean-leaf evaluation (``_eval_bool_leaf``)
        that reads the operand truth from the live stimulus. Non-boolexpr
        children see ``_eval_bool_leaf`` return True conservatively — the
        full NFA engine in G2 replaces this path for those cases.
        """
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        # RISK-03: explicit disable handling. Although disable propagates to leaf
        # oracles (which reset on disable), we return all-zero here as well so the
        # composed operator's semantics are unambiguous and consistent with
        # _tick_prop_and. Both children are still ticked to keep their state reset.
        if signals.get("disable", False):
            self._tick_node(node.children[0], signals)
            self._tick_node(node.children[1], signals)
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        lhs = self._tick_node(node.children[0], signals)
        rhs = self._tick_node(node.children[1], signals)
        # RISK-02 fix: honour operand truth for boolean-atom children.
        lhs_ok = _eval_bool_leaf(node.children[0], signals)
        rhs_ok = _eval_bool_leaf(node.children[1], signals)
        return {
            "pass": lhs["pass"] and rhs["pass"] and lhs_ok and rhs_ok,
            "fail": lhs["fail"] or rhs["fail"],
            "active": lhs["active"] and rhs["active"],
            "overflow": lhs.get("overflow", False) or rhs.get("overflow", False),
        }

    def _tick_prop_within(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """prop_within: inner pass while outer is still active.

        RISK-02 (v1.5 G1): mirroring the intersect fix, gate the pass
        signal by the actual boolean-atom truth of both inner and outer
        operands. IEEE 1800 §16.9.10 requires the inner-sequence match
        cycle to fall inside the outer window; for boolean atoms this
        reduces to "inner true AND outer true this cycle".
        """
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        # RISK-03: explicit disable handling (see _tick_prop_intersect).
        if signals.get("disable", False):
            self._tick_node(node.children[0], signals)
            self._tick_node(node.children[1], signals)
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        inner = self._tick_node(node.children[0], signals)
        outer = self._tick_node(node.children[1], signals)
        # RISK-02 fix: honour operand truth (see _tick_prop_intersect docstring).
        inner_ok = _eval_bool_leaf(node.children[0], signals)
        outer_ok = _eval_bool_leaf(node.children[1], signals)
        return {
            "pass": inner["pass"] and outer["active"] and inner_ok and outer_ok,
            "fail": inner["fail"] or outer["fail"],
            "active": inner["active"] or outer["active"],
            "overflow": inner.get("overflow", False) or outer.get("overflow", False),
        }

    def _tick_prop_throughout(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """prop_throughout: condition must hold throughout body sequence.

        Mirrors RTL template behaviour: cond checker is driven by
        ``_cond_start = start | body_active`` so it is re-evaluated on every
        cycle the body is active.  We also directly evaluate the cond
        expression against current signals because the boolean-expression
        oracle model always passes (it doesn't evaluate the actual boolean
        expression — see _eval_cond_expr).
        """
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}

        # RISK-03: explicit disable handling (see _tick_prop_intersect).
        if signals.get("disable", False):
            self._tick_node(node.children[0], signals)
            self._tick_node(node.children[1], signals)
            return {"pass": False, "fail": False, "active": False, "overflow": False}

        body = self._tick_node(node.children[1], signals)
        # Drive cond with _cond_start = start | body_active
        cond_sigs = dict(signals)
        cond_sigs["start"] = signals.get("start", False) or body["active"]
        cond = self._tick_node(node.children[0], cond_sigs)

        # Directly evaluate the cond expression so that a false condition
        # is detected (the boolexpr oracle always passes when started).
        cond_expr_ok = _eval_cond_expr(node.children[0], signals)

        return {
            "pass": body["pass"] and cond_expr_ok,
            "fail": body["fail"] or (body["active"] and not cond_expr_ok),
            "active": body["active"],
            "overflow": cond.get("overflow", False) or body.get("overflow", False),
        }

    def _tick_prop_not(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """prop_not: invert pass/fail of body."""
        body = node.children[0] if node.children else None
        if body is None:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        out = self._tick_node(body, signals)
        return {
            "pass": out["fail"],
            "fail": out["pass"],
            "active": out["active"],
            "overflow": out.get("overflow", False),
        }

    def _tick_prop_if_else(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """prop_if_else: multiplex between true/false branches."""
        # Evaluate condition from cond_expr in params
        cond_text = node.params.get("cond_expr", "")
        cond_sigs = _re_oracle.findall(r"\b([a-zA-Z_]\w*)\b", cond_text)
        cond_val = (
            all(signals.get(s, False) for s in cond_sigs)
            if cond_sigs
            else signals.get("cond", False)
        )
        if cond_val:
            return self._tick_node(node.children[0], signals)
        if len(node.children) > 1:
            return self._tick_node(node.children[1], signals)
        return {"pass": False, "fail": False, "active": False, "overflow": False}

    def _tick_s_eventually(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """Bounded eventually ``s_eventually [lo:hi] p``.

        Independent contract model (derived from IEEE 1800 semantics, NOT from the
        RTL template — RISK-01): armed at the ``start`` cycle t0 (offset 0), the
        operand p must hold at SOME offset k in [lo,hi].  Registered outputs
        (latency 1): PASS at t0 + k* + 1 where k* is the first in-window holding
        offset; FAIL at t0 + hi + 1 if no offset in [lo,hi] holds.  ``active`` is
        the registered ``armed`` state.  Operand truth is read from the live
        stimulus (single-signal operands modelled precisely; multi-signal truth is
        approximated, with correctness guaranteed by the sby BMC proof).
        """
        lo = int(node.params.get("lo", 0))
        hi = int(node.params.get("hi", 0))
        key = node.module_name
        if not hasattr(self, "_se_state"):
            self._se_state: dict[str, dict[str, object]] = {}
        st = self._se_state.setdefault(
            key, {"armed": False, "off": 0, "sat": False, "o_pass": False, "o_fail": False}
        )

        # Registered outputs: emit what was scheduled at the previous tick.
        out = {
            "pass": bool(st["o_pass"]),
            "fail": bool(st["o_fail"]),
            "active": bool(st["armed"]),
            "overflow": False,
        }
        nxt_pass = False
        nxt_fail = False

        p = self._eval_operand(node, signals)
        if signals.get("start", False):
            st["armed"] = True
            st["off"] = 0
            st["sat"] = False
        if st["armed"]:
            k = int(st["off"])  # type: ignore[call-overload]
            in_window = lo <= k <= hi
            hit = in_window and p and not bool(st["sat"])
            if hit:
                nxt_pass = True
                st["sat"] = True
            if k >= hi:
                if not bool(st["sat"]) and not hit:
                    nxt_fail = True
                st["armed"] = False
            st["off"] = k + 1

        st["o_pass"] = nxt_pass
        st["o_fail"] = nxt_fail
        return out

    def _tick_s_always(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """Bounded always ``always [lo:hi] p`` — the universal dual of eventually.

        Independent contract model (derived from IEEE 1800 semantics, NOT from the
        RTL template — RISK-01): armed at the ``start`` cycle t0 (offset 0), the
        operand p must hold at EVERY offset k in [lo,hi].  Registered outputs
        (latency 1): FAIL at t0 + k_viol + 1 where k_viol is the first in-window
        offset where p is false; PASS at t0 + hi + 1 if every in-window offset
        holds.  ``active`` is the registered ``armed`` state.
        """
        lo = int(node.params.get("lo", 0))
        hi = int(node.params.get("hi", 0))
        key = node.module_name
        if not hasattr(self, "_sa_state"):
            self._sa_state: dict[str, dict[str, object]] = {}
        st = self._sa_state.setdefault(
            key, {"armed": False, "off": 0, "viol": False, "o_pass": False, "o_fail": False}
        )

        # Registered outputs: emit what was scheduled at the previous tick.
        out = {
            "pass": bool(st["o_pass"]),
            "fail": bool(st["o_fail"]),
            "active": bool(st["armed"]),
            "overflow": False,
        }
        nxt_pass = False
        nxt_fail = False

        p = self._eval_operand(node, signals)
        if signals.get("start", False):
            st["armed"] = True
            st["off"] = 0
            st["viol"] = False
        if st["armed"]:
            k = int(st["off"])  # type: ignore[call-overload]
            in_window = lo <= k <= hi
            miss = in_window and (not p) and not bool(st["viol"])
            if miss:
                nxt_fail = True
                st["viol"] = True
            if k >= hi:
                if not bool(st["viol"]) and not miss:
                    nxt_pass = True
                st["armed"] = False
            st["off"] = k + 1

        st["o_pass"] = nxt_pass
        st["o_fail"] = nxt_fail
        return out

    def _tick_until_prop(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """Weak ``a until b`` / ``a until_with b`` — safety FSM.

        Independent contract model (derived from IEEE 1800 semantics, NOT from the
        RTL template — RISK-01).  Armed at ``start``; each active cycle samples
        a (left) and b (right):

        * ``until``      : PASS when b; FAIL when ~b & ~a (a dropped before b).
        * ``until_with`` : PASS when a & b; FAIL when ~a (a required at b-cycle).

        Registered outputs (latency 1).  ``active`` is the registered armed state.
        Once decided, the attempt stops; an undecided attempt stays pending (no
        verdict), faithfully modelling the weak (no-liveness) semantics.
        """
        with_ = str(node.params.get("with_", "0")) == "1"
        key = node.module_name
        if not hasattr(self, "_until_state"):
            self._until_state: dict[str, dict[str, object]] = {}
        st = self._until_state.setdefault(key, {"armed": False, "o_pass": False, "o_fail": False})

        out = {
            "pass": bool(st["o_pass"]),
            "fail": bool(st["o_fail"]),
            "active": bool(st["armed"]),
            "overflow": False,
        }
        nxt_pass = False
        nxt_fail = False

        left_sigs = [s for s in str(node.params.get("left_signals", "")).split(",") if s]
        right_sigs = [s for s in str(node.params.get("right_signals", "")).split(",") if s]
        a = all(bool(signals.get(s, False)) for s in left_sigs) if left_sigs else False
        b = all(bool(signals.get(s, False)) for s in right_sigs) if right_sigs else False

        if signals.get("start", False):
            st["armed"] = True
        if st["armed"]:
            if with_:
                if not a:
                    nxt_fail = True
                    st["armed"] = False
                elif b:
                    nxt_pass = True
                    st["armed"] = False
            else:
                if b:
                    nxt_pass = True
                    st["armed"] = False
                elif not a:
                    nxt_fail = True
                    st["armed"] = False

        st["o_pass"] = nxt_pass
        st["o_fail"] = nxt_fail
        return out

    def _tick_nfa_generic(self, node: CheckerNode, signals: dict[str, bool]) -> dict[str, bool]:
        """v1.5.1 rule-based NFA thread simulator (RISK-01 independent).

        Implements the NFA composition oracle for ``nfa_generic``-template
        CheckerNodes (produced by ``_compose_intersect_nfa`` /
        ``_compose_within_nfa`` / ``_compose_throughout_nfa`` and multi-cycle
        implication consequents).  The transition table, accept-set and
        ``nfa_kind`` are read from ``node.params``:

        * ``nfa_transitions``: string ``"s0,g0,t0;s1,g1,t1;..."`` — each triple
          is ``from_state,guard_expr,to_state``. Semicolon-separated.
        * ``nfa_accept``: string ``"i,j,k"`` — comma-separated accept-state
          IDs.
        * ``nfa_kind``: ``"sequence"`` or ``"property"`` — fail-rule selector.

        Latency model (matches ``nfa_generic.sv.j2``):
          state_q registers next_active from previous cycle;
          pass_q = |(state_d & accept), fail_q derived from state_d & kind.
        Output on cycle t reflects state_d at the previous cycle → 1-cycle
        latency from ``start`` to ``pass``.

        Fail semantics (per v1.5-ROADMAP G1.2 correction):
          sequence NFA: dead-end = vacuous no-match (fail = False).
          property NFA: dead-end after attempt_fired without accept = fail.

        Guard evaluation is done by ``_eval_nfa_guard`` (recursive descent,
        independent of any RTL evaluator — this is the whole point of D2).
        """
        transitions = _parse_nfa_transitions(node.params.get("nfa_transitions", ""))
        accept = _parse_nfa_accept(node.params.get("nfa_accept", ""))
        nfa_kind = str(node.params.get("nfa_kind", "sequence"))

        key = node.module_name
        if not hasattr(self, "_nfa_state"):
            self._nfa_state: dict[str, dict[str, object]] = {}
        st = self._nfa_state.setdefault(
            key,
            {
                "active": frozenset(),
                "attempt_fired": False,
                "o_pass": False,
                "o_fail": False,
                "o_active": False,
            },
        )

        # Registered outputs: emit what was scheduled last tick.
        out = {
            "pass": bool(st["o_pass"]),
            "fail": bool(st["o_fail"]),
            "active": bool(st["o_active"]),
            "overflow": False,
        }

        # Compute new active set for this cycle.
        active: set[int] = set(st["active"])  # type: ignore[call-overload]
        if signals.get("start", False):
            active.add(0)
            st["attempt_fired"] = True

        next_active: set[int] = set()
        for from_s, guard, to_s in transitions:
            if from_s in active and _eval_nfa_guard(guard, signals):
                next_active.add(to_s)

        nxt_pass = bool(next_active & accept)
        if nfa_kind == "property":
            # Dead-end after attempt_fired without accept = fail.
            nxt_fail = bool(st["attempt_fired"]) and (not next_active) and (not nxt_pass)
        else:  # "sequence"
            # Dead-end = vacuous no-match, NOT fail.
            nxt_fail = False

        # Schedule next-cycle outputs (1-cycle registered latency).
        st["active"] = frozenset(next_active)
        st["o_pass"] = nxt_pass
        st["o_fail"] = nxt_fail
        st["o_active"] = bool(next_active)
        return out

    def _eval_operand(self, node: CheckerNode, signals: dict[str, bool]) -> bool:
        """Evaluate the (boolean) operand of a liveness node from the stimulus.

        Single-signal operands are exact; multi-signal expressions use the same
        conservative convention as the other condition evaluators (RISK-02), with
        true correctness established by the formal-equivalence proof.
        """
        semantic = _eval_bool_semantic_param(node, signals)
        if semantic is not None:
            return semantic
        sigs = [port for port, _ in node.observed_signals]
        if not sigs:
            return bool(signals.get("sig", False))
        return all(bool(signals.get(s, False)) for s in sigs)

    def _tick_implication(
        self, node: CheckerNode, signals: dict[str, bool], tname: str
    ) -> dict[str, bool]:
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        ant_out = self._tick_node(node.children[0], signals)
        cons_signals = dict(signals)
        if tname == "nonoverlap":
            cons_signals["start"] = ant_out["pass"]
        else:
            cons_signals["start"] = signals.get("start", False)
        cons_out = self._tick_node(node.children[1], cons_signals)
        if tname == "nonoverlap":
            return {
                "pass": cons_out["pass"],
                "fail": cons_out["fail"],
                "active": ant_out["active"] or cons_out["active"],
                "overflow": False,
            }
        return {
            "pass": ant_out["pass"] and cons_out["pass"],
            "fail": ant_out["pass"] and cons_out["fail"],
            "active": ant_out["active"] or cons_out["active"],
            "overflow": False,
        }

    def _tick_implication_nfa(
        self,
        node: CheckerNode,
        signals: dict[str, bool],
    ) -> dict[str, bool]:
        """v1.5.1 P2: implication with NFA consequent.

        Antecedent evaluated combinationally from ``ant_guard`` param
        (no child bool_expr).  child[0] = nfa_generic (consequent, prop).

        For |->: con_start = ant_match (combinational same-cycle)
        For |=>: con_start = delayed ant_match (prev cycle)
        """
        if not node.children:
            return {"pass": False, "fail": False, "active": False, "overflow": False}

        ant_guard = str(node.params.get("ant_guard", "1'b0"))
        start = bool(signals.get("start", False))
        ant_match = start and _eval_nfa_guard(ant_guard, signals)

        overlapping = str(node.params.get("overlapping", "true")).lower() in ("true", "1", "yes")
        module = node.module_name
        if not hasattr(self, "_impl_ant_q"):
            self._impl_ant_q: dict[str, bool] = {}
        if overlapping:
            con_start = ant_match
        else:
            con_start = self._impl_ant_q.get(module, False)
        self._impl_ant_q[module] = ant_match

        con_signals = dict(signals)
        con_signals["start"] = con_start
        con_out = self._tick_node(node.children[0], con_signals)

        return {
            "pass": con_out["pass"],
            "fail": con_out["fail"],
            "active": con_out["active"],
            "overflow": False,
        }


def _extract_oracle_params(node: CheckerNode) -> dict[str, Any]:
    tname = node.template_name
    params: dict[str, Any] = {}
    if tname in ("delay_fixed", "delay_range", "concat_delay"):
        params["delay_min"] = int(node.params.get("delay_min", 1))
        params["delay_max"] = int(node.params.get("delay_max", 1))
    elif tname in ("rep_consecutive", "goto_rep", "nonconsec_rep"):
        params["rep_min"] = int(node.params.get("rep_min", 1))
        params["rep_max"] = int(node.params.get("rep_max", 1))
    elif tname in ("rose", "fell", "stable", "past", "changed"):
        params["depth"] = int(node.params.get("depth", 1))
    elif tname in ("overlap_bitvec", "nonoverlap"):
        params["bv_width"] = int(node.params.get("bv_width", 1))
    return params


def _map_stimulus(tname: str, signals: dict[str, bool], node: CheckerNode) -> dict[str, bool]:
    if tname == "bool_expr":
        return {"start": signals.get("start", False)}
    if tname in ("delay_fixed", "delay_range"):
        return {"start": signals.get("start", False)}
    if tname in (
        "rep_consecutive",
        "goto_rep",
        "nonconsec_rep",
        "rose",
        "fell",
        "stable",
        "past",
        "changed",
    ):
        sig_name = _extract_obs_sig(node, 0)
        return {"start": signals.get("start", False), "sig": signals.get(sig_name, False)}
    if tname in ("overlap_bitvec", "nonoverlap"):
        return {
            "ant_pass": signals.get("ant_pass", signals.get("start", False)),
            "con_pass": signals.get("con_pass", False),
        }
    return signals


def _extract_obs_sig(node: CheckerNode, idx: int) -> str:
    obs = node.observed_signals
    if idx < len(obs):
        return str(obs[idx][0])
    return "sig"


def _eval_cond_expr(cond_node: CheckerNode, signals: Mapping[str, bool | int]) -> bool:
    """Evaluate a boolean-expression checker's condition against signal values.

    The behavioral oracle models ``bool_expr`` as ``delay_fixed(0,0)`` which
    always passes when started — it does not evaluate the actual boolean
    expression.  For throughout we need to know whether the condition signal
    (e.g. ``en``) itself is true, so we look at the signal value in the
    stimulus.
    """
    if cond_node.template_name != "bool_expr":
        return True  # non-boolexpr: assume passes (conservative)
    semantic = _eval_bool_semantic_param(cond_node, signals)
    if semantic is not None:
        return semantic
    obs = cond_node.observed_signals
    if obs:
        # For simple throughot like ``en throughout body``, check if en is high
        for port_name, _ in obs:
            if signals.get(port_name, False):
                return True  # at least one observed signal is true
        return False  # all observed signals are false → condition violated
    return True  # no signals to check: assume passes


def _parse_nfa_transitions(spec: str) -> list[tuple[int, str, int]]:
    """Parse a serialised NFA transition table.

    Format: ``"s0,g0,t0;s1,g1,t1;..."`` — each semicolon-separated triple is
    ``from_state,guard_expr,to_state``. Guards may not contain literal commas
    or semicolons (grammar restricted to ``&``, ``|``, ``~``, parentheses,
    identifiers, ``0``, ``1``). Empty string → no transitions.
    """
    if not spec:
        return []
    result: list[tuple[int, str, int]] = []
    for chunk in spec.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(",")
        if len(parts) != 3:
            raise ValueError(f"malformed NFA transition {chunk!r}")
        from_s, guard, to_s = parts
        result.append((int(from_s), guard.strip(), int(to_s)))
    return result


def _parse_nfa_accept(spec: str) -> frozenset[int]:
    """Parse a serialised NFA accept-state set: ``"i,j,k"``."""
    if not spec:
        return frozenset()
    return frozenset(int(x) for x in spec.split(",") if x.strip())


def _eval_nfa_guard(expr: str, sig: dict[str, bool]) -> bool:
    """Evaluate a boolean guard against a signal snapshot.

    Grammar: ``signal | '1' | '0' | '~' expr | expr '&' expr | expr '|' expr
    | '(' expr ')'``. Precedence ``~`` > ``&`` > ``|``. Recursive-descent
    parser — deliberately independent of any RTL evaluator (RISK-01 D2).

    Direct copy of the parser validated in
    ``tools/audit/probe_nfa_prototype.py`` on 4 hand-derived vectors.
    """
    tokens = _nfa_tokenize(expr)
    pos = [0]

    def parse_or() -> bool:
        v = parse_and()
        while pos[0] < len(tokens) and tokens[pos[0]] == "|":
            pos[0] += 1
            v = v | parse_and()
        return v

    def parse_and() -> bool:
        v = parse_not()
        while pos[0] < len(tokens) and tokens[pos[0]] == "&":
            pos[0] += 1
            v = v & parse_not()
        return v

    def parse_not() -> bool:
        if pos[0] < len(tokens) and tokens[pos[0]] == "~":
            pos[0] += 1
            return not parse_not()
        return parse_atom()

    def parse_atom() -> bool:
        t = tokens[pos[0]]
        pos[0] += 1
        if t == "(":
            v = parse_or()
            if pos[0] >= len(tokens) or tokens[pos[0]] != ")":
                raise ValueError(f"unbalanced parens in guard {expr!r}")
            pos[0] += 1
            return v
        if t == "1":
            return True
        if t == "0":
            return False
        return bool(sig.get(t, False))

    return parse_or()


def _nfa_tokenize(expr: str) -> list[str]:
    """Tokenise an NFA guard expression (see ``_eval_nfa_guard`` for grammar)."""
    out: list[str] = []
    i = 0
    while i < len(expr):
        c = expr[i]
        if c.isspace():
            i += 1
        elif c in "()~&|":
            out.append(c)
            i += 1
        elif c.isalnum() or c == "_":
            j = i
            while j < len(expr) and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            out.append(expr[i:j])
            i = j
        else:
            raise ValueError(f"bad char {c!r} in guard {expr!r}")
    return out


def _eval_bool_leaf(cond_node: CheckerNode, signals: Mapping[str, bool | int]) -> bool:
    """Independent (RISK-01) boolean-leaf value evaluator for RISK-02 fix.

    Used by ``_tick_prop_intersect`` / ``_tick_prop_within`` to close the
    RISK-02 gap where composed sequence operators previously ignored their
    boolean operand values.

    Semantics: for a ``bool_expr`` leaf whose ``observed_signals`` is
    ``[(p1, w1), (p2, w2), ...]``, the leaf holds this cycle iff **all**
    observed signals are true in the stimulus — this is the standard
    single-cycle-sequence semantics from IEEE 1800 (a sequence completes
    on the cycle its boolean expression holds).

    Independence: derived from IEEE semantics of a boolean sequence atom,
    NOT from the RTL template's structure. This is the v1.5 G1 "rule-based
    thread simulator" (D2) applied to the specific single-cycle sequence
    case; the full NFA path in G2 will generalise this to multi-cycle
    sequences.

    Returns True (conservative) for non-``bool_expr`` children so composed
    sequences continue to see them as always-holding for now — G2 replaces
    the whole ``prop_intersect``/``prop_within`` oracle path with the NFA
    engine, at which point this helper becomes vacuously true for its
    remaining callers.
    """
    if cond_node.template_name != "bool_expr":
        return True
    semantic = _eval_bool_semantic_param(cond_node, signals)
    if semantic is not None:
        return semantic
    obs = cond_node.observed_signals
    if not obs:
        return True
    # AND across all observed signals — sequence-atom semantics.
    return all(bool(signals.get(port_name, False)) for port_name, _ in obs)


def _eval_bool_semantic_param(
    node: CheckerNode,
    signals: Mapping[str, bool | int],
) -> bool | None:
    """Evaluate serialized bool_semantic params when a checker carries them."""
    payload = node.params.get("bool_semantic")
    if payload is None:
        return None
    return bool(eval_bool_expr(deserialize_bool_expr(payload), signals))


from sva2rtl.ir import CheckerNode  # noqa: E402
