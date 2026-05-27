"""Tests for Phase 3.2: signal functions $rose/$fell/$stable/$past.

Requirements covered:
- OP-06: $rose operator support
- OP-07: $fell operator support
- OP-08: $stable operator support
- OP-09: $past operator support
- TEST-02: deterministic golden-file codegen
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.behavioral_oracle import SVABehavioralSim
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.ir import ClockSpec, SignalFunc, SourceLoc

# ── Paths ──────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = Path(__file__).parent / "golden"


# ── Helpers ────────────────────────────────────────────────────────────────


def _load_fixture(name: str) -> dict[str, object]:
    result: dict[str, object] = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    return result


def _full_pipeline(fixture_name: str) -> str:
    """Load fixture, import, compose, emit; return rendered SV string."""
    ast = _load_fixture(fixture_name)
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    return list(modules.values())[0]


# ── 3.2.1: IR node tests ───────────────────────────────────────────────────


def test_ir_signal_func_rose_creation() -> None:
    """SignalFunc for rose has correct fields."""
    loc = SourceLoc("test.sv", 1, 1)
    sf = SignalFunc(func_name="rose", signal="req", depth=1, source_loc=loc)
    assert sf.func_name == "rose"
    assert sf.signal == "req"
    assert sf.depth == 1
    assert sf.source_loc == loc


def test_ir_signal_func_past_depth() -> None:
    """SignalFunc for past stores depth correctly."""
    loc = SourceLoc("test.sv", 1, 1)
    sf = SignalFunc(func_name="past", signal="data", depth=3, source_loc=loc)
    assert sf.func_name == "past"
    assert sf.depth == 3


def test_ir_signal_func_frozen() -> None:
    """SignalFunc is immutable (frozen=True)."""
    loc = SourceLoc("test.sv", 1, 1)
    sf = SignalFunc(func_name="fell", signal="ack", depth=1, source_loc=loc)
    with pytest.raises(Exception):  # FrozenInstanceError
        sf.func_name = "rose"  # type: ignore[misc]


def test_ir_signal_func_hashable() -> None:
    """SignalFunc supports hashing and equal nodes produce the same hash."""
    loc = SourceLoc("test.sv", 1, 1)
    sf1 = SignalFunc(func_name="stable", signal="bus", depth=1, source_loc=loc)
    sf2 = SignalFunc(func_name="stable", signal="bus", depth=1, source_loc=loc)
    assert isinstance(hash(sf1), int)
    assert hash(sf1) == hash(sf2)


def test_ir_signal_func_default_depth() -> None:
    """SignalFunc default depth is 1."""
    loc = SourceLoc("test.sv", 1, 1)
    sf = SignalFunc(func_name="rose", signal="sig", source_loc=loc)
    assert sf.depth == 1


# ── 3.2.2: AST importer tests ─────────────────────────────────────────────


def test_import_rose() -> None:
    """rose.json imports as SignalFunc(func_name='rose', signal='sig')."""
    ast = _load_fixture("rose.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SignalFunc)
    assert node.func_name == "rose"
    assert node.signal == "sig"
    assert node.depth == 1


def test_import_fell() -> None:
    """fell.json imports as SignalFunc(func_name='fell', signal='sig')."""
    ast = _load_fixture("fell.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SignalFunc)
    assert node.func_name == "fell"
    assert node.signal == "sig"


def test_import_stable() -> None:
    """stable.json imports as SignalFunc(func_name='stable', signal='sig')."""
    ast = _load_fixture("stable.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SignalFunc)
    assert node.func_name == "stable"
    assert node.signal == "sig"


def test_import_past() -> None:
    """past.json imports as SignalFunc(func_name='past', signal='sig', depth=3)."""
    ast = _load_fixture("past.json")
    node, clock, text, label = import_assertion(ast)
    assert isinstance(node, SignalFunc)
    assert node.func_name == "past"
    assert node.signal == "sig"
    assert node.depth == 3


def test_import_rose_text() -> None:
    """Reconstructed text for $rose(sig) contains '$rose(sig)'."""
    ast = _load_fixture("rose.json")
    _node, _clock, text, _label = import_assertion(ast)
    assert "$rose(sig)" in text


def test_import_past_text_depth() -> None:
    """Reconstructed text for $past(sig, 3) contains '$past(sig, 3)'."""
    ast = _load_fixture("past.json")
    _node, _clock, text, _label = import_assertion(ast)
    assert "$past(sig, 3)" in text


def test_import_unknown_system_func_raises() -> None:
    """Unknown system function (e.g. $countones) raises UnsupportedConstruct."""
    unknown_ast = {
        "design": {
            "members": [
                {
                    "kind": "Instance",
                    "name": "bad",
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
                                        "kind": "CallExpression",
                                        "type": "int",
                                        "subroutineName": "$countones",
                                        "arguments": [
                                            {"kind": "NamedValue", "symbol": "1 x"}
                                        ],
                                    },
                                },
                            }
                        ],
                    },
                }
            ]
        }
    }
    with pytest.raises(UnsupportedConstruct):
        import_assertion(unknown_ast)


def test_import_past_dynamic_depth_raises() -> None:
    """$past with non-literal depth raises UnsupportedConstruct."""
    dynamic_ast = {
        "design": {
            "members": [
                {
                    "kind": "Instance",
                    "name": "dyn",
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
                                        "kind": "CallExpression",
                                        "type": "bit",
                                        "subroutineName": "$past",
                                        "arguments": [
                                            {"kind": "NamedValue", "symbol": "2 sig"},
                                            {"kind": "NamedValue", "symbol": "3 n"},
                                        ],
                                    },
                                },
                            }
                        ],
                    },
                }
            ]
        }
    }
    with pytest.raises(UnsupportedConstruct):
        import_assertion(dynamic_ast)


# ── 3.2.3: Composer tests ─────────────────────────────────────────────────


def test_compose_rose_template_name() -> None:
    """compose() on SignalFunc(rose) returns CheckerNode with template_name='rose'."""
    ast = _load_fixture("rose.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "rose"


def test_compose_past_depth_in_params() -> None:
    """compose() on SignalFunc(past, depth=3) puts depth='3' in params."""
    ast = _load_fixture("past.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "past"
    assert checker.params["depth"] == "3"


def test_compose_observed_signals_single() -> None:
    """compose() on a SignalFunc produces exactly one observed_signal pair."""
    loc = SourceLoc("test.sv", 1, 1)
    clock = ClockSpec(edge="posedge", signal="clk", source_loc=loc)
    sf = SignalFunc(func_name="rose", signal="req", depth=1, source_loc=loc)
    checker = compose(sf, clock, None, "$rose(req)")
    assert len(checker.observed_signals) == 1
    assert checker.observed_signals[0] == ("req", "req")


def test_compose_fell_template_name() -> None:
    """compose() on SignalFunc(fell) returns CheckerNode with template_name='fell'."""
    ast = _load_fixture("fell.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "fell"


def test_compose_stable_template_name() -> None:
    """compose() on SignalFunc(stable) returns CheckerNode with template_name='stable'."""
    ast = _load_fixture("stable.json")
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    assert checker.template_name == "stable"


# ── 3.2.4: Template emit tests ─────────────────────────────────────────────


def test_emit_rose_structure() -> None:
    """Emitted rose module contains rose_detect and sig_prev_q."""
    sv = _full_pipeline("rose.json")
    assert "module " in sv
    assert "endmodule" in sv
    assert "rose_detect" in sv
    assert "sig_prev_q" in sv
    assert "disable_i" in sv
    assert "disabled_o" in sv


def test_emit_rose_detection_logic() -> None:
    """Emitted rose module contains the AND-NOT edge-detect assign."""
    sv = _full_pipeline("rose.json")
    assert "sig & ~sig_prev_q" in sv


def test_emit_fell_detection_logic() -> None:
    """Emitted fell module contains the AND (inverted) edge-detect assign."""
    sv = _full_pipeline("fell.json")
    assert "~sig & sig_prev_q" in sv


def test_emit_stable_detection_logic() -> None:
    """Emitted stable module contains the XNOR-style comparator."""
    sv = _full_pipeline("stable.json")
    assert "sig == sig_prev_q" in sv


def test_emit_past_shift_register() -> None:
    """Emitted past module (depth=3) contains shift_q and parameter DEPTH = 3."""
    sv = _full_pipeline("past.json")
    assert "shift_q" in sv
    assert "parameter DEPTH = 3" in sv
    assert "disable_i" in sv


def test_emit_rose_golden(tmp_path: Path) -> None:
    """Emit rose → write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    sv = _full_pipeline("rose.json")
    golden_path = _GOLDEN / "sva_rose.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")
    assert_golden(sv, golden_path)


def test_emit_fell_golden() -> None:
    """Emit fell → write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    sv = _full_pipeline("fell.json")
    golden_path = _GOLDEN / "sva_fell.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")
    assert_golden(sv, golden_path)


def test_emit_stable_golden() -> None:
    """Emit stable → write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    sv = _full_pipeline("stable.json")
    golden_path = _GOLDEN / "sva_stable.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")
    assert_golden(sv, golden_path)


def test_emit_past_golden() -> None:
    """Emit past → write golden file if missing, then assert match."""
    from tests.conftest import assert_golden

    sv = _full_pipeline("past.json")
    golden_path = _GOLDEN / "sva_past.sv"
    if not golden_path.exists():
        golden_path.write_text(sv, encoding="utf-8")
    assert_golden(sv, golden_path)


# ── 3.2.6: Behavioral oracle tests ────────────────────────────────────────


def test_oracle_rose_edge_detected() -> None:
    """$rose: 0->1 transition fires pass."""
    sim = SVABehavioralSim("rose", {})
    sim.tick({"start": False, "sig": False})  # prev=False (initial)
    out = sim.tick({"start": True, "sig": True})   # 0->1: rose fires
    assert out["pass"],  "0->1 transition: $rose should pass"
    assert not out["fail"], "0->1 transition: not fail"


def test_oracle_rose_no_edge_no_pass() -> None:
    """$rose: 1->1 (stable high) does NOT fire pass."""
    sim = SVABehavioralSim("rose", {})
    sim.tick({"start": False, "sig": True})   # prev=True
    out = sim.tick({"start": True, "sig": True})   # 1->1: no rose
    assert not out["pass"], "1->1: no $rose"
    assert out["fail"],     "1->1: fail (no edge detected)"


def test_oracle_rose_reset_clears_prev() -> None:
    """reset() clears sig_prev so initial cycle sees prev=0."""
    sim = SVABehavioralSim("rose", {})
    sim.tick({"start": False, "sig": True})  # prev set to True
    sim.reset()
    out = sim.tick({"start": True, "sig": True})  # after reset prev=0 → 0->1 = rose
    assert out["pass"], "after reset prev=0, sig=1 → $rose"


def test_oracle_fell_edge_detected() -> None:
    """$fell: 1->0 transition fires pass."""
    sim = SVABehavioralSim("fell", {})
    sim.tick({"start": False, "sig": True})   # prev=True
    out = sim.tick({"start": True, "sig": False})  # 1->0: fell fires
    assert out["pass"],  "1->0 transition: $fell should pass"
    assert not out["fail"], "1->0: not fail"


def test_oracle_fell_no_edge_no_pass() -> None:
    """$fell: 0->0 (stable low) does NOT fire pass."""
    sim = SVABehavioralSim("fell", {})
    sim.tick({"start": False, "sig": False})  # prev=False
    out = sim.tick({"start": True, "sig": False})  # 0->0: no fell
    assert not out["pass"], "0->0: no $fell"
    assert out["fail"],     "0->0: fail (no falling edge)"


def test_oracle_stable_no_change_passes() -> None:
    """$stable: same value in consecutive cycles fires pass."""
    sim = SVABehavioralSim("stable", {})
    sim.tick({"start": False, "sig": True})   # prev=True
    out = sim.tick({"start": True, "sig": True})   # 1->1: stable
    assert out["pass"],  "1->1: $stable passes"
    assert not out["fail"], "1->1: not fail"


def test_oracle_stable_change_fails() -> None:
    """$stable: different values in consecutive cycles fires fail."""
    sim = SVABehavioralSim("stable", {})
    sim.tick({"start": False, "sig": True})   # prev=True
    out = sim.tick({"start": True, "sig": False})  # 1->0: not stable
    assert not out["pass"], "1->0: $stable fails"
    assert out["fail"],     "1->0: fail"


def test_oracle_past_depth_1() -> None:
    """$past(sig, 1): reflects sig value from 1 cycle ago."""
    sim = SVABehavioralSim("past", {"depth": "1"})
    sim.tick({"start": False, "sig": True})   # sig[t-1]=True stored
    out = sim.tick({"start": True,  "sig": False})  # past_value = True (from t-1)
    assert out["pass"],  "past(sig,1) 1 cycle ago was True → pass"
    assert not out["fail"], "not fail"


def test_oracle_past_depth_3() -> None:
    """$past(sig, 3): reflects sig value from 3 cycles ago."""
    sim = SVABehavioralSim("past", {"depth": "3"})
    # Cycle 0: sig=True pushed into shift[0]
    sim.tick({"start": False, "sig": True})
    # Cycle 1: sig=False
    sim.tick({"start": False, "sig": False})
    # Cycle 2: sig=False
    sim.tick({"start": False, "sig": False})
    # Cycle 3: past_value = sig from 3 cycles ago = True
    out = sim.tick({"start": True, "sig": False})
    assert out["pass"], "past(sig,3): sig was True 3 cycles ago → pass"


def test_oracle_past_depth_3_false() -> None:
    """$past(sig, 3): 3 cycles ago was False → fail."""
    sim = SVABehavioralSim("past", {"depth": "3"})
    sim.tick({"start": False, "sig": False})  # t-3=False
    sim.tick({"start": False, "sig": True})
    sim.tick({"start": False, "sig": True})
    out = sim.tick({"start": True, "sig": False})
    assert out["fail"], "past(sig,3): sig was False 3 cycles ago → fail"


def test_oracle_rose_invalid_kind_regression() -> None:
    """Constructor still raises ValueError for unknown kind (regression)."""
    with pytest.raises(ValueError, match="Unknown kind"):
        SVABehavioralSim("bogus_func", {})
