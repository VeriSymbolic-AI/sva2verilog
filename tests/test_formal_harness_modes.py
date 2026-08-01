"""Text-level tests for formal harness mode contracts.

These tests intentionally avoid SymbiYosys. They prove the generated harness
text exposes the start, disable, reset, output-contract, and cover controls that
formal BMC/prove tests opt into.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sva2rtl.formal_equiv as formal_equiv
from sva2rtl.formal_equiv import (
    FormalHarnessConfig,
    FormalOutputContract,
    build_harness,
    build_miter_harness,
)

_OBSERVED = (("a", "a"), ("b", "b"))
_REF_MODULE = """\
module ref_mon (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    output logic pass,
    output logic fail,
    output logic active,
    output logic attempt_fired,
    output logic disabled_o,
    output logic overflow_flag
);
    assign pass = start & a;
    assign fail = start & ~b;
    assign active = start;
    assign attempt_fired = start;
    assign disabled_o = 1'b0;
    assign overflow_flag = 1'b0;
endmodule
"""


def test_config_defaults_are_named_compatibility_modes() -> None:
    equiv = FormalHarnessConfig.equivalence_default()
    miter = FormalHarnessConfig.miter_default(compare="pass")

    assert equiv.start_mode == "continuous"
    assert equiv.disable_mode == "held_low"
    assert equiv.reset_mode == "first_cycle"
    assert equiv.output_contract.outputs == ("fail",)

    assert miter.start_mode == "single_shot"
    assert miter.disable_mode == "held_low"
    assert miter.reset_mode == "first_cycle"
    assert miter.output_contract.outputs == ("pass",)


def test_build_harness_preserves_continuous_start_default() -> None:
    harness = build_harness("dut_mon", _OBSERVED, "!(a && b)", has_overflow_flag=False)

    assert ".start(1'b1)" in harness
    assert ".disable_i(1'b0)" in harness
    assert "wire _in_reset = (_t == 0);" in harness
    assert "start_mode=continuous" in harness
    assert "disable_mode=held_low" in harness


def test_miter_harness_preserves_single_shot_default() -> None:
    harness = build_miter_harness(
        "dut_mon",
        _OBSERVED,
        _REF_MODULE,
        "ref_mon",
        has_overflow_flag=False,
        compare="pass",
    )

    assert "wire start_pulse = (_t == 1);" in harness
    assert ".start(start_pulse)" in harness
    assert "start_mode=single_shot" in harness
    assert "equiv_pass: assert (m_pass == r_pass);" in harness


def test_arbitrary_start_disable_and_reset_recovery_are_visible() -> None:
    config = FormalHarnessConfig(
        start_mode="arbitrary_start",
        disable_mode="arbitrary_disable",
        reset_mode="reset_recovery",
        assumptions=("no start while reset is asserted",),
        overlap="bounded",
    )
    harness = build_harness("dut_mon", _OBSERVED, "!(a && b)", config=config)

    assert "input logic formal_start" in harness
    assert "input logic formal_disable" in harness
    assert "input logic formal_reset" in harness
    assert ".start(formal_start)" in harness
    assert ".disable_i(formal_disable)" in harness
    assert "wire _in_reset = (_t == 0) || formal_reset;" in harness
    assert "start_mode=arbitrary_start" in harness
    assert "disable_mode=arbitrary_disable" in harness
    assert "reset_mode=reset_recovery" in harness
    assert "Formal overlap policy: bounded" in harness
    assert "assume (!formal_start);" in harness
    assert "assume (!formal_disable);" in harness


def test_miter_can_pass_disable_to_reference_when_requested() -> None:
    config = FormalHarnessConfig(
        disable_mode="arbitrary_disable",
        output_contract=FormalOutputContract.full_monitor(include_overflow=False),
        reference_disable_port=True,
    )
    harness = build_miter_harness(
        "dut_mon",
        _OBSERVED,
        _REF_MODULE,
        "ref_mon",
        has_overflow_flag=False,
        config=config,
    )

    assert "input logic formal_disable" in harness
    assert ".disable_i(formal_disable)" in harness
    assert "equiv_attempt_fired: assert (m_afired == r_afired);" in harness


def test_full_contract_miter_emits_all_requested_assertions() -> None:
    config = FormalHarnessConfig(
        start_mode="single_shot",
        output_contract=FormalOutputContract.full_monitor(include_overflow=True),
    )
    harness = build_miter_harness(
        "dut_mon",
        _OBSERVED,
        _REF_MODULE,
        "ref_mon",
        has_overflow_flag=True,
        config=config,
    )

    for signal in (
        "pass",
        "fail",
        "active",
        "attempt_fired",
        "disabled_o",
        "overflow_flag",
    ):
        assert f"equiv_{signal}: assert" in harness


def test_overflow_contract_is_explicitly_excluded_when_absent() -> None:
    config = FormalHarnessConfig(
        output_contract=FormalOutputContract.full_monitor(include_overflow=True),
    )
    harness = build_miter_harness(
        "dut_mon",
        _OBSERVED,
        _REF_MODULE,
        "ref_mon",
        has_overflow_flag=False,
        config=config,
    )

    assert "Excluded contract signals: overflow_flag" in harness
    assert "equiv_overflow_flag" not in harness


def test_cover_probe_requests_emit_reachability_checks() -> None:
    config = FormalHarnessConfig(
        start_mode="arbitrary_start",
        disable_mode="arbitrary_disable",
        output_contract=FormalOutputContract.full_monitor(include_overflow=True),
        covers=("pass", "fail", "disable", "overflow", "overlap"),
    )
    harness = build_miter_harness(
        "dut_mon",
        _OBSERVED,
        _REF_MODULE,
        "ref_mon",
        has_overflow_flag=True,
        config=config,
    )

    assert "Cover probes check setup reachability" in harness
    assert "cover_probe_pass: cover (m_pass);" in harness
    assert "cover_probe_fail: cover (m_fail);" in harness
    assert "cover_probe_disable: cover (m_disabled);" in harness
    assert "cover_probe_overflow: cover (m_ovf);" in harness
    assert "cover_probe_overlap: cover (formal_start && m_active);" in harness


def test_formal_harness_preserves_observed_vector_widths() -> None:
    """Formal free inputs use the same packed width as the generated monitor."""
    harness = build_harness(
        "dut_mon",
        (("data", "data"),),
        "data != 4'b0011",
        has_overflow_flag=False,
        signal_widths={"data": 4},
    )

    assert "input logic [3:0] data," in harness


def test_required_cover_failure_downgrades_proof_to_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proof PASS cannot mask an unreachable required cover probe."""
    outcomes = iter(
        [
            (0, "PASS 0 0\n", False),
            (1, "FAIL 2 0\n", False),
        ]
    )
    monkeypatch.setattr(formal_equiv, "_run_sby_with_timeout", lambda *_a, **_k: next(outcomes))

    passed, output = formal_equiv._run_sby_plan(
        tmp_path,
        stem="miter",
        primary_mode="prove",
        depth=12,
        timeout=30,
        script_reads="read -sv harness.sv",
        files_block="harness.sv",
        required_covers=("pass",),
    )

    assert not passed
    assert output.startswith("UNKNOWN: required cover reachability failed")
    assert "mode cover" in (tmp_path / "miter_cover.sby").read_text(encoding="utf-8")


def test_status_parser_rejects_pass_as_substring() -> None:
    """Status parsing cannot accept words such as BYPASS as formal PASS."""
    assert formal_equiv._sby_reported_pass("PASS 0 0")
    assert not formal_equiv._sby_reported_pass("BYPASS 0 0")
