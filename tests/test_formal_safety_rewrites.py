"""Phase 20 direct-safety and nexttime rewrite contracts."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sva2rtl.ast_importer import _dispatch_expr_to_ir, import_assertion
from sva2rtl.composer import compose
from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.formal_flow import (
    FormalMode,
    FormalRunConfig,
    FormalStatus,
    PropertyClass,
    build_formal_bundle,
    classify_property,
    run_formal_bundle,
)
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import (
    BoolConst,
    BoolExpr,
    ClockSpec,
    DisableIff,
    PropAlways,
    PropImplication,
    PropNexttime,
    SeqConcat,
)
from sva2rtl.normalizer import normalize


def _bool_operand(signal: str = "ack") -> dict[str, object]:
    return {
        "kind": "Simple",
        "expr": {"kind": "NamedValue", "type": "logic", "symbol": f"1 {signal}"},
    }


def _unary(op: str, *, cycles: int | None = None) -> dict[str, object]:
    node: dict[str, object] = {"kind": "Unary", "op": op, "expr": _bool_operand()}
    if cycles is not None:
        node.update({"min": cycles, "max": cycles})
    return node


def _has_formal_stack() -> bool:
    if any(shutil.which(tool) is None for tool in ("slang", "yosys", "sby", "yices-smt2")):
        return False
    completed = subprocess.run(
        ["yosys", "-m", "slang", "-Q", "-p", "help read_slang"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    return completed.returncode == 0 and "read_slang" in completed.stdout


requires_formal_stack = pytest.mark.skipif(
    not _has_formal_stack(),
    reason="requires slang, Yosys read_slang plugin, SBY, and yices-smt2",
)


def test_unbounded_always_imports_as_formal_only_safety_ir() -> None:
    node = _dispatch_expr_to_ir(_unary("Always"))
    assert isinstance(node, PropAlways)
    assert isinstance(node.body, BoolExpr)
    assert node.strong is False
    assert classify_property(node) is PropertyClass.SAFETY

    clock = ClockSpec(edge="posedge", signal="clk", source_loc=node.source_loc)
    with pytest.raises(UnsupportedConstruct, match="PropAlways"):
        compose(node, clock, "p", "always ack")


def test_s_always_import_preserves_strength() -> None:
    node = _dispatch_expr_to_ir(_unary("SAlways"))
    assert isinstance(node, PropAlways)
    assert node.strong is True


@pytest.mark.parametrize(
    ("op", "cycles", "expected_strong"),
    [("NextTime", None, False), ("NextTime", 3, False), ("SNextTime", 3, True)],
)
def test_nexttime_import_and_exact_delay_normalization(
    op: str, cycles: int | None, expected_strong: bool
) -> None:
    node = _dispatch_expr_to_ir(_unary(op, cycles=cycles))
    assert isinstance(node, PropNexttime)
    assert node.cycles == (cycles or 1)
    assert node.strong is expected_strong

    normalized = normalize(node)
    assert isinstance(normalized, PropImplication)
    assert isinstance(normalized.consequent, SeqConcat)
    assert normalized.consequent.delays == ((cycles or 1, cycles or 1),)
    assert len(normalized.consequent.elements) == 2
    first, second = normalized.consequent.elements
    assert isinstance(first, BoolExpr)
    assert isinstance(first.expr, BoolConst)
    assert first.expr.value == 1
    assert second == node.body
    assert normalize(normalized) == normalized


def test_nexttime_rejects_nonfixed_or_negative_bounds() -> None:
    ranged = _unary("NextTime", cycles=2)
    ranged["max"] = 3
    with pytest.raises(UnsupportedConstruct, match="fixed delay"):
        _dispatch_expr_to_ir(ranged)

    with pytest.raises(UnsupportedConstruct, match="nonnegative"):
        _dispatch_expr_to_ir(_unary("NextTime", cycles=-1))


def test_live_slang_shapes_import_for_always_and_nexttime(tmp_path: Path) -> None:
    source = tmp_path / "property.sv"
    source.write_text(
        "module spec(input logic clk, rst_n, ack);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) always ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    node, _clock, text, label = import_assertion(invoke_slang(source))
    assert isinstance(node, DisableIff)
    assert isinstance(node.body, PropAlways)
    assert text == "disable iff ((!rst_n)) always (ack)"
    assert label == "p"

    source.write_text(
        "module spec(input logic clk, rst_n, ack);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) s_nexttime[3] ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    node, _clock, _text, _label = import_assertion(invoke_slang(source))
    assert isinstance(node, DisableIff)
    assert isinstance(node.body, PropNexttime)


def _formal_config(tmp_path: Path, *, good: bool, property_text: str) -> FormalRunConfig:
    dut = tmp_path / ("good.sv" if good else "bad.sv")
    prop = tmp_path / "property.sv"
    dut.write_text(
        "module safety_dut(input logic clk, input logic rst_n, input logic req, "
        "output logic ack);\n"
        + ("  always_comb ack = req;\n" if good else "  always_comb ack = 1'b0;\n")
        + "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module safety_spec(input logic clk, rst_n, req, ack);\n"
        f"  p: assert property (@(posedge clk) disable iff (!rst_n) {property_text});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="safety_dut",
        output_dir=tmp_path / ("evidence-good" if good else "evidence-bad"),
        mode=FormalMode.PROVE,
        depth=12,
        timeout_seconds=60,
    )


def _nexttime_config(tmp_path: Path, *, good: bool) -> FormalRunConfig:
    dut = tmp_path / ("next-good.sv" if good else "next-bad.sv")
    prop = tmp_path / "next-property.sv"
    dut.write_text(
        "module nexttime_dut(input logic clk, input logic rst_n, output logic ack);\n"
        f"  always_comb ack = 1'b{1 if good else 0};\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module nexttime_spec(input logic clk, rst_n, ack);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) nexttime ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="nexttime_dut",
        output_dir=tmp_path / ("next-evidence-good" if good else "next-evidence-bad"),
        mode=FormalMode.PROVE,
        depth=12,
        timeout_seconds=60,
    )


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize("good", [True, False])
def test_unbounded_always_uses_direct_invariant_and_distinguishes_duts(
    tmp_path: Path, good: bool
) -> None:
    evidence = build_formal_bundle(
        _formal_config(tmp_path, good=good, property_text="always ((!req) || ack)")
    )
    assert evidence.property_class is PropertyClass.SAFETY
    assert evidence.manifest["backend"] == "direct-invariant-safety"
    assert evidence.manifest["generated_sources"] == []
    bind = (evidence.bundle_dir / "formal_bind.sv").read_text(encoding="utf-8")
    assert "assert (" in bind
    assert "req" in bind and "ack" in bind
    assert "u_monitor" not in bind

    result = run_formal_bundle(evidence)
    expected = FormalStatus.PROVEN if good else FormalStatus.FAILED
    assert result.status is expected, (evidence.bundle_dir / "sby.log").read_text()


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize("good", [True, False])
def test_nexttime_normalization_distinguishes_real_duts(tmp_path: Path, good: bool) -> None:
    evidence = build_formal_bundle(_nexttime_config(tmp_path, good=good))
    assert evidence.property_class is PropertyClass.FINITE_VERDICT
    assert evidence.manifest["backend"] == "generated-monitor-safety"
    assert evidence.manifest["generated_sources"]

    result = run_formal_bundle(evidence)
    expected = FormalStatus.PROVEN if good else FormalStatus.FAILED
    assert result.status is expected, (evidence.bundle_dir / "sby.log").read_text()
