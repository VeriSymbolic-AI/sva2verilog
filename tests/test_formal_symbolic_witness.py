"""Phase 21 symbolic-witness bounded formal backend contracts."""

from __future__ import annotations

import itertools
import shutil
import subprocess
from pathlib import Path

import pytest

from sva2rtl.errors import UnsupportedConstruct
from sva2rtl.formal_flow import (
    AttemptMode,
    FormalMode,
    FormalRunConfig,
    FormalStatus,
    build_formal_bundle,
    run_formal_bundle,
)
from sva2rtl.formal_lowering import (
    ObligationKind,
    evaluate_all_attempts,
    evaluate_symbolic_witness,
    lower_bounded_implication,
)
from sva2rtl.ir import (
    BoolConst,
    BoolExpr,
    BoolIdent,
    PropImplication,
    SeqConcat,
    SeqRepetition,
    SourceLoc,
)

_LOC = SourceLoc("witness.sv", 1, 1)


def _bool(name: str) -> BoolExpr:
    return BoolExpr(
        text=name,
        expr=BoolIdent(name=name, source_loc=_LOC),
        source_loc=_LOC,
    )


def _true() -> BoolExpr:
    return BoolExpr(
        text="1'b1",
        expr=BoolConst(value=1, width=1, raw="1'b1", source_loc=_LOC),
        source_loc=_LOC,
    )


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


def test_lower_exact_and_ranged_delay_without_monitor_budget() -> None:
    exact = PropImplication(
        antecedent=_bool("req"),
        consequent=SeqConcat(
            elements=(_true(), _bool("ack")),
            delays=((64, 64),),
            source_loc=_LOC,
        ),
        overlapping=True,
        source_loc=_LOC,
    )
    ranged = PropImplication(
        antecedent=_bool("req"),
        consequent=SeqConcat(
            elements=(_true(), _bool("ack")),
            delays=((2, 5),),
            source_loc=_LOC,
        ),
        overlapping=False,
        source_loc=_LOC,
    )

    exact_lowering = lower_bounded_implication(exact, label="exact", original_text="p")
    ranged_lowering = lower_bounded_implication(ranged, label="ranged", original_text="p")
    assert exact_lowering is not None
    assert exact_lowering.params["obligation_kind"] == ObligationKind.EVENTUALLY.value
    assert exact_lowering.params["min_cycles"] == "64"
    assert exact_lowering.params["max_cycles"] == "64"
    assert ranged_lowering is not None
    assert ranged_lowering.params["min_cycles"] == "3"
    assert ranged_lowering.params["max_cycles"] == "6"


def test_lower_bounded_consecutive_repetition() -> None:
    node = PropImplication(
        antecedent=_bool("req"),
        consequent=SeqRepetition(
            expr=_bool("ack"), rep_min=3, rep_max=5, source_loc=_LOC
        ),
        overlapping=True,
        source_loc=_LOC,
    )
    lowering = lower_bounded_implication(node, label="rep", original_text="p")
    assert lowering is not None
    assert lowering.params["obligation_kind"] == ObligationKind.CONSECUTIVE.value
    assert lowering.params["min_cycles"] == "3"
    assert lowering.params["max_cycles"] == "5"


@pytest.mark.parametrize(
    ("kind", "lo", "hi"),
    [
        (ObligationKind.EVENTUALLY, 0, 0),
        (ObligationKind.EVENTUALLY, 1, 1),
        (ObligationKind.EVENTUALLY, 1, 3),
        (ObligationKind.CONSECUTIVE, 2, 3),
    ],
)
def test_symbolic_witness_matches_exhaustive_attempts_on_all_small_traces(
    kind: ObligationKind, lo: int, hi: int
) -> None:
    length = 6
    for ant_bits in itertools.product((False, True), repeat=length):
        for cond_bits in itertools.product((False, True), repeat=length):
            exhaustive = evaluate_all_attempts(ant_bits, cond_bits, kind, lo, hi)
            selected = tuple(
                evaluate_symbolic_witness(ant_bits, cond_bits, kind, lo, hi, index)
                for index in range(length)
                if ant_bits[index]
                and index
                + (hi if kind is ObligationKind.EVENTUALLY else max(0, lo - 1))
                < length
            )
            assert exhaustive == all(selected)


def _config(tmp_path: Path, *, good: bool, delay: int) -> FormalRunConfig:
    dut = tmp_path / ("witness-good.sv" if good else "witness-bad.sv")
    prop = tmp_path / "witness-property.sv"
    dut.write_text(
        "module witness_dut(input logic clk, input logic rst_n, input logic req, "
        "output logic ack);\n"
        f"  assign ack = 1'b{1 if good else 0};\n"
        "endmodule\n",
        encoding="utf-8",
    )
    prop.write_text(
        "module witness_property(input logic clk, rst_n, req, ack);\n"
        f"  p: assert property (@(posedge clk) disable iff (!rst_n) "
        f"req |-> nexttime[{delay}] ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    return FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="witness_dut",
        output_dir=tmp_path / ("witness-good" if good else "witness-bad"),
        mode=FormalMode.PROVE,
        attempt_mode=AttemptMode.SYMBOLIC_WITNESS,
        depth=delay + 8,
        timeout_seconds=90,
    )


@pytest.mark.formal
@requires_formal_stack
@pytest.mark.parametrize("good", [True, False])
def test_delay_above_monitor_budget_distinguishes_real_duts(
    tmp_path: Path, good: bool
) -> None:
    evidence = build_formal_bundle(_config(tmp_path, good=good, delay=64))
    assert evidence.manifest["backend"] == "symbolic-witness-safety"
    assert evidence.manifest["generated_sources"] == []
    bind = (evidence.bundle_dir / "formal_bind.sv").read_text(encoding="utf-8")
    assert "witness_select" in bind
    assert "MAX_CYCLES = 64" in bind
    assert "u_monitor" not in bind

    result = run_formal_bundle(evidence)
    expected = FormalStatus.PROVEN if good else FormalStatus.FAILED
    assert result.status is expected, (evidence.bundle_dir / "sby.log").read_text()


def test_symbolic_witness_mode_rejects_unrecognized_property_shape(tmp_path: Path) -> None:
    dut = tmp_path / "dut.sv"
    prop = tmp_path / "property.sv"
    dut.write_text("module dut(input logic clk, rst_n, ack); endmodule\n", encoding="utf-8")
    prop.write_text(
        "module spec(input logic clk, rst_n, ack);\n"
        "  p: assert property (@(posedge clk) always ack);\n"
        "endmodule\n",
        encoding="utf-8",
    )
    config = FormalRunConfig(
        dut_sources=(dut,),
        property_file=prop,
        property_name="p",
        top="dut",
        output_dir=tmp_path / "evidence",
        attempt_mode=AttemptMode.SYMBOLIC_WITNESS,
    )
    with pytest.raises(UnsupportedConstruct, match="symbolic-witness"):
        build_formal_bundle(config)
