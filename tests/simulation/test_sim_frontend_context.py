"""Dual-simulator regression for structured real-project frontend context."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sva2rtl.ast_importer import import_all_assertions
from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all, observed_signal_widths
from sva2rtl.frontend import SlangCompilationContext, invoke_slang
from sva2rtl.optimizer import optimize
from tests.conftest import requires_slang
from tests.simulation.tb_generator import (
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

pytestmark = [pytest.mark.simulation, requires_slang]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_parameter_specialized_project_matches_oracle_on_selected_simulator(
    tmp_path: Path,
    simulator: str,
) -> None:
    """Filelist/include/define/top/-G output agrees with the independent oracle."""
    include_dir = tmp_path / "include"
    _write(
        include_dir / "project_check.svh",
        "`ifdef ENABLE_PROJECT_CHECK\n"
        "project_check: assert property (@(posedge clk) a == EXPECTED_PARAM);\n"
        "`endif\n",
    )
    _write(
        tmp_path / "blocks" / "assertion_block.sv",
        "module assertion_block #(parameter bit EXPECTED_PARAM = 0) "
        "(input logic clk, input logic a);\n"
        "  `include \"project_check.svh\"\n"
        "endmodule\n",
    )
    primary = _write(
        tmp_path / "top.sv",
        "module project_top #(parameter bit EXPECTED_PARAM = 0) "
        "(input logic clk, input logic a);\n"
        "  assertion_block #(.EXPECTED_PARAM(EXPECTED_PARAM)) "
        "u_checker(.clk(clk), .a(a));\n"
        "endmodule\n",
    )
    filelist = _write(tmp_path / "files.f", "blocks/assertion_block.sv\n")
    context = SlangCompilationContext(
        filelists=(filelist,),
        include_dirs=(include_dir,),
        defines=("ENABLE_PROJECT_CHECK=1",),
        top_modules=("project_top",),
        parameter_overrides=("EXPECTED_PARAM=1",),
        single_unit=True,
    )

    ast = invoke_slang(primary, context=context)
    assertions = import_all_assertions(ast)
    assert len(assertions) == 1
    node, clock, text, label = assertions[0]
    checker = optimize(compose(node, clock, label, text))
    assert checker.observed_signals == (("a", "a"),)

    stimulus: list[dict[str, Any]] = [
        {"start": True, "a": False},
        {"start": True, "a": True},
        {"start": False, "a": True},
        {"start": True, "a": False},
    ]
    modules = emit_all(checker)
    extra_inputs = extra_inputs_from_checker(checker)
    testbench = generate_testbench(
        module_name=checker.module_name,
        clock_signal="clk",
        extra_inputs=extra_inputs,
        input_widths=observed_signal_widths(checker),
        stimulus=stimulus,
        capture_contract=True,
    )
    simulation_dir = tmp_path / "simulation"
    simulation_dir.mkdir()
    rtl = run_simulation(
        simulator=simulator,
        module_name=checker.module_name,
        sv_sources=list(modules.values()),
        tb_code=testbench,
        work_dir=simulation_dir,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
        capture_contract=True,
    )
    oracle = simulate_checker_hierarchy(checker, stimulus)

    for output in ("active", "pass", "fail"):
        assert [row[output] for row in rtl] == [row[output] for row in oracle]
    assert any(row["attempt_fired"] for row in rtl)
    assert not any(row["disabled_o"] for row in rtl)
