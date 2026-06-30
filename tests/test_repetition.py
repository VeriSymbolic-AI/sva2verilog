"""Tests for Phase 3.1: consecutive repetition [*N] / [*M:N].

Requirements covered:
- OP-05: consecutive repetition operator support
- TEST-02: deterministic golden-file codegen
- TEST-06: boundary cycle behavior
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.behavioral_oracle import SVABehavioralSim
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.errors import SvaCompileError
from sva2rtl.ir import BoolExpr, ClockSpec, SeqRepetition, SourceLoc

# ── Paths ──────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = Path(__file__).parent / "golden"


# ── Helpers ────────────────────────────────────────────────────────────────


def _load_fixture(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


# ── 3.1.1: IR node tests ───────────────────────────────────────────────────


def test_ir_node_creation() -> None:
    """SeqRepetition is a frozen dataclass with the correct fields."""
    loc = SourceLoc("test.sv", 1, 1)
    inner = BoolExpr(text="a", source_loc=loc)
    rep = SeqRepetition(expr=inner, rep_min=2, rep_max=5, source_loc=loc)
    assert rep.expr is inner
    assert rep.rep_min == 2
    assert rep.rep_max == 5
    assert rep.source_loc == loc


def test_ir_node_frozen() -> None:
    """SeqRepetition is immutable (frozen=True)."""
    loc = SourceLoc("test.sv", 1, 1)
    rep = SeqRepetition(
        expr=BoolExpr(text="a", source_loc=loc),
        rep_min=3,
        rep_max=3,
        source_loc=loc,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        rep.rep_min = 99  # type: ignore[misc]


def test_ir_node_hashable() -> None:
    """SeqRepetition supports hashing (required for CSE)."""
    loc = SourceLoc("test.sv", 1, 1)
    rep = SeqRepetition(
        expr=BoolExpr(text="a", source_loc=loc),
        rep_min=2,
        rep_max=5,
        source_loc=loc,
    )
    assert isinstance(hash(rep), int)
    # Two identical nodes hash the same
    rep2 = SeqRepetition(
        expr=BoolExpr(text="a", source_loc=loc),
        rep_min=2,
        rep_max=5,
        source_loc=loc,
    )
    assert hash(rep) == hash(rep2)


# ── 3.1.2: AST importer tests ─────────────────────────────────────────────


def test_import_rep_fixed() -> None:
    """Fixture with [*3] imports as SeqRepetition(rep_min=3, rep_max=3)."""
    ast = _load_fixture("rep_fixed.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SeqRepetition)
    assert node.rep_min == 3
    assert node.rep_max == 3
    assert isinstance(node.expr, BoolExpr)
    assert node.expr.text == "a"


def test_import_rep_range() -> None:
    """Fixture with [*2:5] imports as SeqRepetition(rep_min=2, rep_max=5)."""
    ast = _load_fixture("rep_range.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SeqRepetition)
    assert node.rep_min == 2
    assert node.rep_max == 5


def test_import_unbounded_rejects() -> None:
    """Unbounded repetition [*0:$] raises SvaCompileError with SVA-E002."""
    # Build a minimal AST dict with max="$" inline
    unbounded_ast = {
        "design": {
            "members": [
                {
                    "kind": "Instance",
                    "name": "unbounded",
                    "body": {
                        "kind": "InstanceBody",
                        "members": [
                            {
                                "kind": "ConcurrentAssertion",
                                "body": {
                                    "kind": "PropertySpec",
                                    "clocking": {
                                        "kind": "TimingControl",
                                        "event": {
                                            "kind": "SignalEvent",
                                            "edge": "posedge",
                                            "expr": {"kind": "NamedValue", "symbol": "0 clk"},
                                        },
                                    },
                                    "expr": {
                                        "kind": "SimpleAssertionExpr",
                                        "expr": {
                                            "kind": "NamedValue",
                                            "symbol": "1 a",
                                        },
                                        "repetition": {
                                            "kind": "Consecutive",
                                            "min": 0,
                                            "max": "$",
                                        },
                                    },
                                },
                            }
                        ],
                    },
                }
            ]
        }
    }
    with pytest.raises(SvaCompileError, match="SVA-E002"):
        import_assertion(unbounded_ast)


def test_import_rep_text_fixed() -> None:
    """Reconstructed text for [*3] is 'a [*3]'."""
    ast = _load_fixture("rep_fixed.json")
    _node, _clock, text, _label = import_assertion(ast)
    assert "[*3]" in text


def test_import_rep_text_range() -> None:
    """Reconstructed text for [*2:5] is 'a [*2:5]'."""
    ast = _load_fixture("rep_range.json")
    _node, _clock, text, _label = import_assertion(ast)
    assert "[*2:5]" in text


# ── 3.1.3: Composer tests ─────────────────────────────────────────────────


def test_compose_rep_fixed() -> None:
    """compose() on SeqRepetition[*3] returns CheckerNode with rep_consecutive template."""
    ast = _load_fixture("rep_fixed.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "rep_consecutive"
    assert checker.params["rep_min"] == "3"
    assert checker.params["rep_max"] == "3"


def test_compose_cnt_width_rep3() -> None:
    """cnt_width for rep_max=3 is ceil(log2(4)) = 2."""
    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    rep = SeqRepetition(
        expr=BoolExpr(text="a", source_loc=loc),
        rep_min=3,
        rep_max=3,
        source_loc=loc,
    )
    checker = compose(rep, clock, None, "a [*3]")
    assert checker.params["cnt_width"] == "2"


def test_compose_cnt_width_rep5() -> None:
    """cnt_width for rep_max=5 is ceil(log2(6)) = 3."""
    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    rep = SeqRepetition(
        expr=BoolExpr(text="a", source_loc=loc),
        rep_min=2,
        rep_max=5,
        source_loc=loc,
    )
    checker = compose(rep, clock, None, "a [*2:5]")
    assert checker.params["cnt_width"] == "3"


# ── 3.1.4: Template emit tests ─────────────────────────────────────────────


def test_emit_rep_fixed() -> None:
    """Full pipeline: rep_fixed.json → emit_all → valid SV with module/endmodule."""
    ast = _load_fixture("rep_fixed.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    assert len(modules) >= 1
    sv = list(modules.values())[0]
    assert "module " in sv
    assert "endmodule" in sv
    assert "parameter CNT_WIDTH" in sv
    assert "disable_i" in sv
    assert "disabled_o" in sv
    assert "count_q" in sv
    assert "running_q" in sv


def test_emit_rep_range() -> None:
    """Full pipeline: rep_range.json → emit_all → SV with correct rep bounds."""
    ast = _load_fixture("rep_range.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    sv = list(modules.values())[0]
    assert "2" in sv  # rep_min=2
    assert "5" in sv  # rep_max=5


def test_emit_rep_fixed_golden(tmp_path: Path) -> None:
    """Emit rep_fixed, write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    ast = _load_fixture("rep_fixed.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    sv = list(modules.values())[0]

    golden_path = _GOLDEN / "sva_rep_fixed.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")

    assert_golden(sv, golden_path)


def test_emit_rep_range_golden() -> None:
    """Emit rep_range, write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    ast = _load_fixture("rep_range.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    sv = list(modules.values())[0]

    golden_path = _GOLDEN / "sva_rep_range.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")

    assert_golden(sv, golden_path)


def test_emit_cnt_width_in_golden() -> None:
    """Golden sva_rep_fixed.sv has parameter CNT_WIDTH = 2 (ceil(log2(3+1))=2)."""
    import re

    ast = _load_fixture("rep_fixed.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    sv = list(modules.values())[0]
    m = re.search(r"parameter CNT_WIDTH\s*=\s*(\d+)", sv)
    assert m is not None, "CNT_WIDTH not found in emitted SV"
    assert int(m.group(1)) == 2, f"Expected CNT_WIDTH=2, got {m.group(1)}"


# ── 3.1.5: Behavioral oracle tests ────────────────────────────────────────


def test_oracle_rep_exact_3() -> None:
    """rep_consecutive [*3]: pass fires at exactly the 4th tick (old_count=3).

    Outputs are derived from OLD registered state:
    tick 0 (start+sig): old_running=False → active=F, pass=F; update: running=T, count=1
    tick 1 (sig):       old_count=1 < 3  → active=T, pass=F; update: count=2
    tick 2 (sig):       old_count=2 < 3  → active=T, pass=F; update: count=3
    tick 3 (sig):       old_count=3 == 3 → active=T, pass=T (capped at rep_max)
    """
    sim = SVABehavioralSim("rep_consecutive", {"rep_min": 3, "rep_max": 3})
    out0 = sim.tick({"start": True,  "sig": True})   # old_count=N/A (not running)
    out1 = sim.tick({"start": False, "sig": True})   # old_count=1
    out2 = sim.tick({"start": False, "sig": True})   # old_count=2
    out3 = sim.tick({"start": False, "sig": True})   # old_count=3 → pass

    assert not out0["pass"], "old_running=False: no pass on start cycle"
    assert not out1["pass"], "old_count=1 < rep_min=3: no pass"
    assert not out2["pass"], "old_count=2 < rep_min=3: no pass"
    assert out3["pass"],     "old_count=3 == rep_min=3: pass"
    assert out3["active"],   "running at old_count=3: active"


def test_oracle_rep_fail_early() -> None:
    """rep_consecutive [*3]: fail fires when sig drops before reaching rep_min."""
    sim = SVABehavioralSim("rep_consecutive", {"rep_min": 3, "rep_max": 3})
    sim.tick({"start": True,  "sig": True})   # count=1
    out1 = sim.tick({"start": False, "sig": False})  # broken at count=1 < 3 → fail

    assert out1["fail"],      "sig dropped before rep_min=3: fail"
    assert not out1["pass"],  "not pass when sig drops"


def test_oracle_rep_no_start_no_eval() -> None:
    """rep_consecutive: no start → no evaluation, no pass, no fail."""
    sim = SVABehavioralSim("rep_consecutive", {"rep_min": 2, "rep_max": 2})
    for i in range(5):
        out = sim.tick({"start": False, "sig": True})
        assert not out["pass"],   f"tick {i}: no start → no pass"
        assert not out["fail"],   f"tick {i}: no start → no fail"
        assert not out["active"], f"tick {i}: no start → not active"


def test_oracle_rep_range_2_5_pass_counts() -> None:
    """rep_consecutive [*2:5]: pass fires when old_count in [2,5].

    With OLD-state outputs, the first pass fires at tick 2 (old_count=2),
    not tick 1 (old_count=1 < rep_min=2).
    """
    sim = SVABehavioralSim("rep_consecutive", {"rep_min": 2, "rep_max": 5})
    sim.tick({"start": True,  "sig": True})   # tick 0: old_running=F → no pass; update count=1
    out1 = sim.tick({"start": False, "sig": True})   # tick 1: old_count=1 < 2 → no pass
    out2 = sim.tick({"start": False, "sig": True})   # tick 2: old_count=2 → pass
    out3 = sim.tick({"start": False, "sig": True})   # tick 3: old_count=3 → pass
    out4 = sim.tick({"start": False, "sig": True})   # tick 4: old_count=4 → pass
    out5 = sim.tick({"start": False, "sig": True})   # tick 5: old_count=5 == rep_max → pass

    assert not out1["pass"], "old_count=1 < rep_min=2: no pass"
    assert out2["pass"], "old_count=2: pass"
    assert out3["pass"], "old_count=3: pass"
    assert out4["pass"], "old_count=4: pass"
    assert out5["pass"], "old_count=5 == rep_max=5: pass"


def test_oracle_rep_range_fail_before_min() -> None:
    """rep_consecutive [*2:5]: fail when sig drops before count reaches 2."""
    sim = SVABehavioralSim("rep_consecutive", {"rep_min": 2, "rep_max": 5})
    sim.tick({"start": True, "sig": True})   # count=1
    out = sim.tick({"start": False, "sig": False})  # broken at count=1 < 2 → fail

    assert out["fail"],     "dropped at count=1 < rep_min=2: fail"
    assert not out["pass"], "not pass on fail"


def test_oracle_rep_reset_clears_state() -> None:
    """reset() clears rep_count and rep_running."""
    sim = SVABehavioralSim("rep_consecutive", {"rep_min": 3, "rep_max": 3})
    sim.tick({"start": True,  "sig": True})  # count=1, running=True
    sim.tick({"start": False, "sig": True})  # count=2

    sim.reset()

    # After reset, no active, no pass, no fail
    out = sim.tick({"start": False, "sig": True})
    assert not out["active"], "after reset: not active"
    assert not out["pass"],   "after reset: not pass"
    assert not out["fail"],   "after reset: not fail"


def test_oracle_invalid_kind_still_raises() -> None:
    """Constructor still raises ValueError for unknown kind (regression)."""
    with pytest.raises(ValueError, match="Unknown kind"):
        SVABehavioralSim("bogus_op", {})


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Tier 2 — goto repetition [->N]
# ══════════════════════════════════════════════════════════════════════════════

from sva2rtl.ir import SeqGotoRep  # noqa: E402


def test_import_goto_rep() -> None:
    """Fixture with [->3] imports as SeqGotoRep(rep_min=3, rep_max=3)."""
    ast = _load_fixture("goto_rep.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SeqGotoRep)
    assert node.rep_min == 3
    assert node.rep_max == 3
    assert isinstance(node.expr, BoolExpr)
    assert node.expr.text == "a"


def test_import_goto_rep_text() -> None:
    """Reconstructed text for [->3] contains '[->3]'."""
    ast = _load_fixture("goto_rep.json")
    _node, _clock, text, _label = import_assertion(ast)
    assert "[->3]" in text


def test_compose_goto_rep() -> None:
    """compose() on SeqGotoRep returns CheckerNode with goto_rep template."""
    ast = _load_fixture("goto_rep.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "goto_rep"
    assert checker.params["rep_min"] == "3"
    assert checker.params["rep_max"] == "3"
    assert checker.params["cnt_width"] == "2"


def test_compose_goto_rep_cnt_width() -> None:
    """cnt_width for rep_max=7 is ceil(log2(8)) = 3."""
    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    rep = SeqGotoRep(expr=BoolExpr(text="a", source_loc=loc), rep_min=7, rep_max=7, source_loc=loc)
    checker = compose(rep, clock, None, "a [->7]")
    assert checker.params["cnt_width"] == "3"


def test_emit_goto_rep() -> None:
    """Full pipeline: goto_rep.json → emit_all → valid SV with module/endmodule."""
    ast = _load_fixture("goto_rep.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    assert len(modules) >= 1
    sv = list(modules.values())[0]
    assert "module " in sv
    assert "endmodule" in sv
    assert "count_q" in sv
    assert "passed_q" in sv


def test_emit_goto_rep_golden() -> None:
    """Emit goto_rep, write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    ast = _load_fixture("goto_rep.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    sv = list(modules.values())[0]

    golden_path = _GOLDEN / "sva_goto_rep.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")

    assert_golden(sv, golden_path)


def test_oracle_goto_rep_exact_3() -> None:
    """goto_rep [->3]: pass fires at exactly the 3rd occurrence (non-consecutive)."""
    sim = SVABehavioralSim("goto_rep", {"rep_min": 3, "rep_max": 3})
    out0 = sim.tick({"start": True, "sig": True})   # count → 1
    assert not out0["pass"], "count just became 1, no pass yet"
    sim.tick({"start": False, "sig": False})  # gap OK for [->N]
    sim.tick({"start": False, "sig": False})  # gap OK
    out3 = sim.tick({"start": False, "sig": True})   # count → 2
    out4 = sim.tick({"start": False, "sig": True})   # count → 3: pass
    assert not out3["pass"]
    assert out4["pass"], "3rd occurrence: pass"


def test_oracle_goto_rep_never_fails() -> None:
    """goto_rep [->N]: never asserts fail, only waits."""
    sim = SVABehavioralSim("goto_rep", {"rep_min": 2, "rep_max": 2})
    sim.tick({"start": True, "sig": True})
    for i in range(10):
        out = sim.tick({"start": False, "sig": False})
        assert not out["fail"], f"tick {i}: [->N] should never fail"


def test_oracle_goto_rep_lock_after_pass() -> None:
    """goto_rep [->2]: once passed, stays in pass state."""
    sim = SVABehavioralSim("goto_rep", {"rep_min": 2, "rep_max": 2})
    sim.tick({"start": True, "sig": True})   # count=1
    assert not sim.tick({"start": False, "sig": False})["pass"]
    out = sim.tick({"start": False, "sig": True})   # count=2 → pass
    assert out["pass"]
    for i in range(5):
        assert sim.tick({"start": False, "sig": True})["pass"], f"tick {i}: locked pass"


def test_oracle_goto_rep_reset_clears() -> None:
    """reset() clears count and running state for goto_rep."""
    sim = SVABehavioralSim("goto_rep", {"rep_min": 3, "rep_max": 3})
    sim.tick({"start": True, "sig": True})
    sim.tick({"start": False, "sig": True})
    sim.reset()
    out = sim.tick({"start": True, "sig": True})
    assert not out["pass"], "after reset: should not be in pass state"


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Tier 2 — non-consecutive repetition [=N]
# ══════════════════════════════════════════════════════════════════════════════

from sva2rtl.ir import SeqNonconsecRep  # noqa: E402


def test_import_nonconsec_rep() -> None:
    """Fixture with [=5] imports as SeqNonconsecRep(rep_min=5, rep_max=5)."""
    ast = _load_fixture("nonconsec_rep.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SeqNonconsecRep)
    assert node.rep_min == 5
    assert node.rep_max == 5
    assert isinstance(node.expr, BoolExpr)
    assert node.expr.text == "a"


def test_import_nonconsec_rep_text() -> None:
    """Reconstructed text for [=5] contains '[=5]'."""
    ast = _load_fixture("nonconsec_rep.json")
    _node, _clock, text, _label = import_assertion(ast)
    assert "[=5]" in text


def test_compose_nonconsec_rep() -> None:
    """compose() on SeqNonconsecRep returns CheckerNode with nonconsec_rep template."""
    ast = _load_fixture("nonconsec_rep.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "nonconsec_rep"
    assert checker.params["rep_min"] == "5"
    assert checker.params["rep_max"] == "5"
    assert checker.params["cnt_width"] == "3"


def test_emit_nonconsec_rep() -> None:
    """Full pipeline: nonconsec_rep.json → emit_all → valid SV output."""
    ast = _load_fixture("nonconsec_rep.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    sv = list(modules.values())[0]
    assert "module " in sv
    assert "endmodule" in sv
    assert "count_q" in sv
    assert "passed_q" not in sv


def test_emit_nonconsec_rep_golden() -> None:
    """Emit nonconsec_rep, write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    ast = _load_fixture("nonconsec_rep.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    sv = list(modules.values())[0]

    golden_path = _GOLDEN / "sva_nonconsec_rep.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")

    assert_golden(sv, golden_path)


def test_oracle_nonconsec_rep_pass_at_5() -> None:
    """nonconsec_rep [=5]: passes when old_count >= 5.

    OLD-state semantics, start-driven counting.
    """
    sim = SVABehavioralSim("nonconsec_rep", {"rep_min": 5, "rep_max": 5})
    # Oracle increments count on (start=True, sig=True).
    # After 5 such cycles: old_count=5 → pass_val=True
    sim.tick({"start": True, "sig": True})   # old_count=0 → no pass; count→1
    sim.tick({"start": True, "sig": True})   # old_count=1 → no pass; count→2
    sim.tick({"start": True, "sig": True})   # old_count=2 → no pass; count→3
    sim.tick({"start": True, "sig": True})   # old_count=3 → no pass; count→4
    out4 = sim.tick({"start": True, "sig": True})  # old_count=4 → no pass; count→5
    out5 = sim.tick({"start": True, "sig": True})  # old_count=5 → pass
    assert not out4["pass"], "old_count=4 < 5: no pass"
    assert out5["pass"], "old_count=5 >= rep_min=5: pass"


def test_oracle_nonconsec_rep_never_fails() -> None:
    """nonconsec_rep [=N]: never asserts fail, only waits."""
    sim = SVABehavioralSim("nonconsec_rep", {"rep_min": 3, "rep_max": 3})
    for i in range(20):
        out = sim.tick({"start": False, "sig": False})
        assert not out["fail"], f"tick {i}: [=N] should never fail"


def test_oracle_nonconsec_rep_no_start_no_pass() -> None:
    """[=N]: without start, no counting occurs and no pass."""
    sim = SVABehavioralSim("nonconsec_rep", {"rep_min": 2, "rep_max": 2})
    for i in range(10):
        out = sim.tick({"start": False, "sig": True})
        assert not out["pass"], f"tick {i}: no start → no pass"
        assert not out["active"], f"tick {i}: no start → not active"


def test_oracle_nonconsec_reset_clears() -> None:
    """reset() clears count for nonconsec_rep."""
    sim = SVABehavioralSim("nonconsec_rep", {"rep_min": 3, "rep_max": 3})
    sim.tick({"start": True, "sig": True})
    sim.tick({"start": True, "sig": True})
    sim.reset()
    out = sim.tick({"start": True, "sig": True})
    assert not out["pass"], "after reset: count restarts"


# ══════════════════════════════════════════════════════════════════════════════
# v1.3 Tier 2 — first_match
# ══════════════════════════════════════════════════════════════════════════════

from sva2rtl.ir import SeqConcat, SeqFirstMatch  # noqa: E402


def test_import_first_match() -> None:
    """Fixture with first_match(a ##1 b) imports as SeqFirstMatch wrapping SeqConcat."""
    ast = _load_fixture("first_match.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SeqFirstMatch)
    assert isinstance(node.body, SeqConcat)


def test_import_first_match_text() -> None:
    """Reconstructed text contains 'first_match' wrapper."""
    ast = _load_fixture("first_match.json")
    _node, _clock, text, _label = import_assertion(ast)
    assert "first_match" in text


def test_compose_first_match() -> None:
    """compose() on SeqFirstMatch returns first_match_top template with child."""
    ast = _load_fixture("first_match.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "first_match_top"
    assert len(checker.children) == 1
    body = checker.children[0]
    # Two-element sequence concat → seq_concat_top wrapper (3 children: e0, delay, e1)
    assert body.template_name == "seq_concat_top"
    assert checker.params.get("body_tmpl") == "seq_concat_top"
    assert len(body.children) == 3


def test_emit_first_match() -> None:
    """Full pipeline: first_match.json → emit_all → valid SV with body instantiation."""
    ast = _load_fixture("first_match.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    assert len(modules) >= 2
    all_sv = "\n".join(modules.values())
    assert "module " in all_sv
    assert "locked_q" in all_sv
    assert "endmodule" in all_sv


def test_emit_first_match_golden() -> None:
    """Emit first_match, write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    ast = _load_fixture("first_match.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)

    golden_path = _GOLDEN / "sva_first_match.sv"
    all_sv = "\n".join(modules.values())
    if not golden_path.exists():
        golden_path.write_text(all_sv, encoding="utf-8")

    assert_golden(all_sv, golden_path)
