"""Dual-simulator regression for structured real-project frontend context."""

from __future__ import annotations

import json
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

_CORPUS = Path(__file__).parents[1] / "project_corpus" / "parameter_specialization"


def test_parameter_specialized_project_matches_oracle_on_selected_simulator(
    tmp_path: Path,
    simulator: str,
) -> None:
    """A versioned project has source-derived truth beyond oracle agreement."""
    manifest = json.loads((_CORPUS / "expected.json").read_text(encoding="utf-8"))
    context = SlangCompilationContext(
        filelists=(_CORPUS / "files.f",),
        include_dirs=(_CORPUS / "include",),
        defines=tuple(manifest["defines"]),
        top_modules=(manifest["top"],),
        parameter_overrides=tuple(manifest["parameters"]),
        single_unit=True,
    )

    ast = invoke_slang(_CORPUS / "top.sv", context=context)
    assertions = import_all_assertions(ast)
    assert len(assertions) == 1
    node, clock, text, label = assertions[0]
    assert label == manifest["assertion_label"]
    assert text == manifest["assertion_text"]
    checker = optimize(compose(node, clock, label, text))
    assert [port for port, _source in checker.observed_signals] == manifest["observed_signals"]

    stimulus: list[dict[str, Any]] = manifest["stimulus"]
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

    # Primary verdict: a hand-authored, versioned trace derived from the source
    # property and the documented registered-output sampling contract.
    assert rtl == manifest["expected_trace"]
    # Secondary verdict: preserve differential agreement with the independent
    # Python temporal model without making it the sole source of truth.
    for output in ("active", "pass", "fail"):
        assert [row[output] for row in rtl] == [row[output] for row in oracle]
