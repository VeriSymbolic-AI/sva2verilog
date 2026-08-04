"""Phase 20 typed-expression and advanced temporal formal qualification."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.bool_semantics import collect_bool_signal_types
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
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
from sva2rtl.ir import BoolExpr, DisableIff, SeqGotoRep, SeqNonconsecRep
from sva2rtl.normalizer import normalize


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


def test_live_source_preserves_reduction_vector_comparison_and_signed_ports(
    tmp_path: Path,
) -> None:
    source = tmp_path / "typed.sv"
    source.write_text(
        "module typed_spec(input logic clk, input logic [7:0] data, "
        "input logic signed [7:0] lhs, rhs);\n"
        "  p: assert property (@(posedge clk) (&data) || (lhs < rhs));\n"
        "endmodule\n",
        encoding="utf-8",
    )
    node, clock, text, label = import_assertion(invoke_slang(source))
    assert isinstance(node, BoolExpr)
    assert node.expr is not None
    assert collect_bool_signal_types(node.expr) == (
        ("data", 8, False),
        ("lhs", 8, True),
        ("rhs", 8, True),
    )
    checker = compose(normalize(node), clock, label, text)
    generated = emit_all(checker)[checker.module_name]
    assert "input  logic [7:0] data" in generated
    assert "input  logic signed [7:0] lhs" in generated
    assert "input  logic signed [7:0] rhs" in generated
    assert "(&data)" in generated
    assert "(lhs < rhs)" in generated


@pytest.mark.parametrize(
    "expression",
    ["data == 8'hx1", "$past(data) == 8'h01"],
)
def test_four_state_and_vector_sampled_value_boundaries_reject(
    tmp_path: Path, expression: str
) -> None:
    source = tmp_path / "unsupported.sv"
    source.write_text(
        "module unsupported_spec(input logic clk, input logic [7:0] data);\n"
        f"  p: assert property (@(posedge clk) {expression});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    with pytest.raises(UnsupportedConstruct):
        import_assertion(invoke_slang(source))


@pytest.mark.parametrize(
    ("syntax", "node_type"),
    [("ack[->2]", SeqGotoRep), ("ack[=2]", SeqNonconsecRep)],
)
def test_unbounded_occurrence_forms_reuse_monitor_kernel_but_route_as_liveness(
    tmp_path: Path, syntax: str, node_type: type[object]
) -> None:
    source = tmp_path / "occurrence.sv"
    source.write_text(
        "module occurrence_spec(input logic clk, ack);\n"
        f"  p: assert property (@(posedge clk) {syntax});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    node, clock, text, label = import_assertion(invoke_slang(source))
    assert isinstance(node, node_type)
    assert classify_property(node) is PropertyClass.LIVENESS
    checker = compose(normalize(node), clock, label, text)
    expected_template = "goto_rep" if node_type is SeqGotoRep else "nonconsec_rep"
    assert checker.template_name == expected_template


def _formal_config(
    tmp_path: Path,
    *,
    syntax: str,
    good: bool,
    name: str,
) -> FormalRunConfig:
    dut = tmp_path / f"{name}-{'good' if good else 'bad'}.sv"
    prop = tmp_path / f"{name}-property.sv"
    dut.write_text(
        "module advanced_dut(input logic clk, input logic rst_n, output logic ack);\n"
        f"  always_comb ack = 1'b{1 if good else 0};\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module advanced_spec(input logic clk, rst_n, ack);\n"
        f"  p: assert property (@(posedge clk) disable iff (!rst_n) {syntax});\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="advanced_dut",
        output_dir=tmp_path / f"{name}-{'good' if good else 'bad'}-evidence",
        mode=FormalMode.PROVE,
        depth=16,
        timeout_seconds=60,
    )


def _typed_formal_config(tmp_path: Path, *, good: bool) -> FormalRunConfig:
    dut = tmp_path / ("typed-good.sv" if good else "typed-bad.sv")
    prop = tmp_path / "typed-property.sv"
    dut.write_text(
        "module typed_dut(input logic clk, input logic rst_n, "
        "output logic [7:0] data, output logic signed [7:0] lhs, rhs);\n"
        f"  assign data = 8'h{'ff' if good else '00'};\n"
        "  assign lhs = -8'sd1;\n"
        "  assign rhs = 8'sd1;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module typed_property(input logic clk, rst_n, input logic [7:0] data, "
        "input logic signed [7:0] lhs, rhs);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) "
        "always ((&data) && (lhs < rhs)));\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="typed_dut",
        output_dir=tmp_path / ("typed-good-evidence" if good else "typed-bad-evidence"),
        mode=FormalMode.PROVE,
        depth=12,
        timeout_seconds=60,
    )


@pytest.mark.formal
@requires_formal_stack
def test_multidimensional_packed_signal_rejects_before_false_proven(
    tmp_path: Path,
) -> None:
    dut = tmp_path / "multidim-dut.sv"
    prop = tmp_path / "multidim-property.sv"
    dut.write_text(
        "module multidim_dut(input logic clk, input logic rst_n, "
        "output logic [1:0][3:0] data);\n"
        "  assign data = 8'h04;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module multidim_property(input logic clk, input logic rst_n, "
        "input logic [1:0][3:0] data);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) "
        "always (data == 8'h00));\n"
        "endmodule\n",
        encoding="utf-8",
    )
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="multidim_dut",
        output_dir=tmp_path / "multidim-evidence",
    )

    with pytest.raises(UnsupportedConstruct, match="boolean identifier type"):
        build_formal_bundle(config)
    assert not config.output_dir.exists()


@pytest.mark.formal
@requires_formal_stack
def test_unobserved_complex_dut_signal_does_not_block_scalar_contract(
    tmp_path: Path,
) -> None:
    dut = tmp_path / "scalar-with-debug-bus-dut.sv"
    prop = tmp_path / "scalar-property.sv"
    dut.write_text(
        "module scalar_dut(input logic clk, input logic rst_n, "
        "output logic ack, output logic [1:0][3:0] debug_bus);\n"
        "  assign ack = 1'b1;\n"
        "  assign debug_bus = 8'h00;\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module scalar_property(input logic clk, input logic rst_n, input logic ack);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) always ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="scalar_dut",
        output_dir=tmp_path / "scalar-evidence",
    )

    evidence = build_formal_bundle(config)

    contract_path = evidence.bundle_dir / evidence.manifest["interface_contract"]["path"]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    assert {signal["dut_signal"] for signal in contract["signals"]} == {
        "clk",
        "rst_n",
        "ack",
    }


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize("syntax", ["ack[->2]", "ack[=2]"])
def test_user_formal_rejects_unbounded_occurrence_liveness_without_live_backend(
    tmp_path: Path, syntax: str
) -> None:
    config = _formal_config(
        tmp_path,
        syntax=f"1'b1 |-> {syntax}",
        good=True,
        name="occurrence",
    )
    with pytest.raises(UnsupportedConstruct, match="open live backend"):
        build_formal_bundle(config)


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize(
    ("syntax", "name"),
    [
        ("1'b1 |-> (1'b1 ##[1:3] ack)", "ranged-delay"),
        ("1'b1 |-> ack[*2:3]", "ranged-repeat"),
    ],
)
@pytest.mark.parametrize("good", [True, False])
def test_bounded_ranged_forms_distinguish_real_duts(
    tmp_path: Path, syntax: str, name: str, good: bool
) -> None:
    evidence = build_formal_bundle(
        _formal_config(tmp_path, syntax=syntax, good=good, name=name)
    )
    assert evidence.property_class is PropertyClass.FINITE_VERDICT
    result = run_formal_bundle(evidence)
    expected = FormalStatus.PROVEN if good else FormalStatus.FAILED
    assert result.status is expected, (evidence.bundle_dir / "sby.log").read_text()


@pytest.mark.formal
@requires_formal_stack
def test_bare_ranged_sequence_rejects_instead_of_false_proven(tmp_path: Path) -> None:
    config = _formal_config(
        tmp_path,
        syntax="ack[*2:3]",
        good=False,
        name="bare-ranged-repeat",
    )
    with pytest.raises(UnsupportedConstruct, match="bare sequence"):
        build_formal_bundle(config)


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize("good", [True, False])
def test_typed_reduction_and_signed_comparison_distinguish_real_duts(
    tmp_path: Path, good: bool
) -> None:
    evidence = build_formal_bundle(_typed_formal_config(tmp_path, good=good))
    assert evidence.manifest["backend"] == "direct-invariant-safety"
    bind = (evidence.bundle_dir / "formal_bind.sv").read_text(encoding="utf-8")
    assert "input logic signed [7:0] lhs" in bind
    assert "input logic signed [7:0] rhs" in bind

    result = run_formal_bundle(evidence)
    expected = FormalStatus.PROVEN if good else FormalStatus.FAILED
    assert result.status is expected, (evidence.bundle_dir / "sby.log").read_text()


def test_disable_wrapper_retains_typed_body_classification(tmp_path: Path) -> None:
    source = tmp_path / "disabled.sv"
    source.write_text(
        "module disabled_spec(input logic clk, rst_n, ack);\n"
        "  p: assert property (@(posedge clk) disable iff (!rst_n) ack[*2:3]);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    node, _clock, _text, _label = import_assertion(invoke_slang(source))
    assert isinstance(node, DisableIff)
    assert classify_property(node) is PropertyClass.FINITE_VERDICT
