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
            "changed",
            "goto_rep",
            "nonconsec_rep",
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

        if start and not old_running:
            self._rep_running = True
            self._rep_count = 1 if sig else 0
            self._attempt_fired = True
        elif old_running and sig:
            if old_count < rep_max:
                self._rep_count = old_count + 1

        pass_val = old_running and sig and old_count >= rep_min - 1
        active_val = old_running

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

        if start:
            self._attempt_fired = True
            if sig and old_count < rep_max:
                self._rep_count = old_count + 1

        pass_val = old_count >= rep_min
        active_val = start

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

# ── Hierarchical oracle: composes SVABehavioralSim instances ─────────────
# Appended to behavioral_oracle.py for Phase 4 (ORACLE-01).

from typing import Any
import re as _re_oracle


def simulate_checker_hierarchy(
    tree: "CheckerNode",
    stimulus: list[dict[str, bool]],
) -> list[dict[str, bool]]:
    """Simulate a composed checker tree cycle-by-cycle.

    Walks the CheckerNode hierarchy, instantiates SVABehavioralSim for each
    leaf template, and wires them according to the token-passing architecture
    (seq_concat_top, overlap_bitvec, disable_iff_top).
    """
    hier_sim = _HierarchicalSim(tree)
    return [hier_sim.tick(cycle) for cycle in stimulus]


_LEAF_TEMPLATES: frozenset[str] = frozenset({
    "bool_expr", "concat_delay", "delay_fixed", "delay_range", "rep_consecutive",
    "rose", "fell", "stable", "past", "changed", "goto_rep", "nonconsec_rep",
    "overlap_bitvec", "nonoverlap",
})

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

    def __init__(self, root: "CheckerNode") -> None:
        self._root = root
        self._leaf_oracles: dict[str, "SVABehavioralSim"] = {}
        self._build_oracles(root)

    def _build_oracles(self, node: "CheckerNode") -> None:
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

    def _tick_node(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
        tname = node.template_name
        if tname in _LEAF_TEMPLATES:
            oracle = self._leaf_oracles[node.module_name]
            return oracle.tick(_map_stimulus(tname, signals, node))
        if tname == "seq_concat_top":
            return self._tick_seq_concat(node, signals)
        if tname == "disable_iff_top":
            return self._tick_disable_iff(node, signals)
        if tname == "first_match_top":
            return self._tick_first_match(node, signals)
        if tname in ("overlap_bitvec", "nonoverlap"):
            return self._tick_implication(node, signals, tname)
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
        if node.children:
            return self._tick_node(node.children[0], signals)
        return {"pass": False, "fail": False, "active": False, "overflow": False}

    def _tick_seq_concat(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
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

    def _tick_disable_iff(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
        body = node.children[0] if node.children else None
        if body is None:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        cond_text = node.params.get("cond_expr", "")
        cond_sigs = _re_oracle.findall(r"\b([a-zA-Z_]\w*)\b", cond_text)
        cond_val = all(signals.get(s, False) for s in cond_sigs) if cond_sigs else signals.get("cond", False)
        if cond_val:
            self._tick_node(body, {**signals, "disable": True})
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        return self._tick_node(body, signals)

    def _tick_first_match(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
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
            return {"pass": False, "fail": False, "active": False, "overflow": out.get("overflow", False)}
        # Not yet passed, not locked: pass through body outputs
        return out

    # ── Phase 3: Complex sequence operator oracles (v1.3) ────────────────

    def _tick_prop_or(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
        """prop_or: OR two sub-checkers."""
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        l = self._tick_node(node.children[0], signals)
        r = self._tick_node(node.children[1], signals)
        return {"pass": l["pass"] or r["pass"], "fail": l["fail"] or r["fail"],
                "active": l["active"] or r["active"], "overflow": l.get("overflow", False) or r.get("overflow", False)}

    def _tick_prop_and(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
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
        l = self._tick_node(node.children[0], signals)
        r = self._tick_node(node.children[1], signals)

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
        if signals.get("start", False) and not l["active"] and not r["active"]:
            st["left_m"] = False
            st["right_m"] = False

        if l["pass"]:
            st["left_m"] = True
        if r["pass"]:
            st["right_m"] = True

        pass_val = (l["pass"] and st["right_m"]) or (r["pass"] and st["left_m"]) or (l["pass"] and r["pass"])
        return {"pass": pass_val, "fail": l["fail"] or r["fail"],
                "active": l["active"] or r["active"],
                "overflow": l.get("overflow", False) or r.get("overflow", False)}

    def _tick_prop_intersect(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
        """prop_intersect: both must pass at same cycle (intersection)."""
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
        l = self._tick_node(node.children[0], signals)
        r = self._tick_node(node.children[1], signals)
        return {"pass": l["pass"] and r["pass"], "fail": l["fail"] or r["fail"],
                "active": l["active"] and r["active"], "overflow": l.get("overflow", False) or r.get("overflow", False)}

    def _tick_prop_within(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
        """prop_within: inner pass while outer is still active."""
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        # RISK-03: explicit disable handling (see _tick_prop_intersect).
        if signals.get("disable", False):
            self._tick_node(node.children[0], signals)
            self._tick_node(node.children[1], signals)
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        inner = self._tick_node(node.children[0], signals)
        outer = self._tick_node(node.children[1], signals)
        return {"pass": inner["pass"] and outer["active"],
                "fail": inner["fail"] or outer["fail"],
                "active": inner["active"] or outer["active"],
                "overflow": inner.get("overflow", False) or outer.get("overflow", False)}

    def _tick_prop_throughout(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
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

        return {"pass": body["pass"] and cond_expr_ok,
                "fail": body["fail"] or (body["active"] and not cond_expr_ok),
                "active": body["active"],
                "overflow": cond.get("overflow", False) or body.get("overflow", False)}

    def _tick_prop_not(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
        """prop_not: invert pass/fail of body."""
        body = node.children[0] if node.children else None
        if body is None:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        out = self._tick_node(body, signals)
        return {"pass": out["fail"], "fail": out["pass"],
                "active": out["active"], "overflow": out.get("overflow", False)}

    def _tick_prop_if_else(self, node: "CheckerNode", signals: dict[str, bool]) -> dict[str, bool]:
        """prop_if_else: multiplex between true/false branches."""
        # Evaluate condition from cond_expr in params
        cond_text = node.params.get("cond_expr", "")
        cond_sigs = _re_oracle.findall(r"\b([a-zA-Z_]\w*)\b", cond_text)
        cond_val = all(signals.get(s, False) for s in cond_sigs) if cond_sigs else signals.get("cond", False)
        if cond_val:
            return self._tick_node(node.children[0], signals)
        if len(node.children) > 1:
            return self._tick_node(node.children[1], signals)
        return {"pass": False, "fail": False, "active": False, "overflow": False}

    def _tick_implication(self, node: "CheckerNode", signals: dict[str, bool], tname: str) -> dict[str, bool]:
        if len(node.children) < 2:
            return {"pass": False, "fail": False, "active": False, "overflow": False}
        ant_out = self._tick_node(node.children[0], signals)
        cons_out = self._tick_node(node.children[1], signals)
        return {
            "pass": ant_out["pass"] and cons_out["pass"],
            "fail": ant_out["pass"] and cons_out["fail"],
            "active": ant_out["active"] or cons_out["active"],
            "overflow": False,
        }


def _extract_oracle_params(node: "CheckerNode") -> dict[str, Any]:
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


def _map_stimulus(tname: str, signals: dict[str, bool], node: "CheckerNode") -> dict[str, bool]:
    if tname == "bool_expr":
        return {"start": signals.get("start", False)}
    if tname in ("delay_fixed", "delay_range"):
        return {"start": signals.get("start", False)}
    if tname in ("rep_consecutive", "goto_rep", "nonconsec_rep", "rose", "fell", "stable", "past", "changed"):
        sig_name = _extract_obs_sig(node, 0)
        return {"start": signals.get("start", False), "sig": signals.get(sig_name, False)}
    if tname in ("overlap_bitvec", "nonoverlap"):
        return {
            "ant_pass": signals.get("ant_pass", signals.get("start", False)),
            "con_pass": signals.get("con_pass", False),
        }
    return signals


def _extract_obs_sig(node: "CheckerNode", idx: int) -> str:
    obs = node.observed_signals
    if idx < len(obs):
        return str(obs[idx][0])
    return "sig"


def _eval_cond_expr(cond_node: "CheckerNode", signals: dict[str, bool]) -> bool:
    """Evaluate a boolean-expression checker's condition against signal values.

    The behavioral oracle models ``bool_expr`` as ``delay_fixed(0,0)`` which
    always passes when started — it does not evaluate the actual boolean
    expression.  For throughout we need to know whether the condition signal
    (e.g. ``en``) itself is true, so we look at the signal value in the
    stimulus.
    """
    if cond_node.template_name != "bool_expr":
        return True  # non-boolexpr: assume passes (conservative)
    obs = cond_node.observed_signals
    if obs:
        # For simple throughot like ``en throughout body``, check if en is high
        for port_name, _ in obs:
            if signals.get(port_name, False):
                return True  # at least one observed signal is true
        return False  # all observed signals are false → condition violated
    return True  # no signals to check: assume passes


from sva2rtl.ir import CheckerNode  # noqa: E402
