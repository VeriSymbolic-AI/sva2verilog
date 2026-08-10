"""Independent full-contract proof for the compact bounded-delay backend."""

from __future__ import annotations

import pytest

from sva2rtl.composer import compose
from sva2rtl.formal_equiv import (
    FormalHarnessConfig,
    FormalOutputContract,
    run_sva_miter_check,
    sby_is_available,
)
from sva2rtl.ir import (
    BoolConst,
    BoolExpr,
    BoolIdent,
    CheckerNode,
    ClockSpec,
    PropImplication,
    SeqConcat,
    SourceLoc,
)

pytestmark = [
    pytest.mark.formal,
    pytest.mark.skipif(
        not sby_is_available(),
        reason="sby not found - bounded-delay formal miter disabled",
    ),
]

_LOC = SourceLoc("implication_delay_window_formal.sv", 1, 1)
_CLK = ClockSpec(edge="posedge", signal="clk", source_loc=_LOC)


def _b(name: str) -> BoolExpr:
    return BoolExpr(
        text=name,
        expr=BoolIdent(name=name, source_loc=_LOC),
        source_loc=_LOC,
    )


def _checker(delay_min: int) -> CheckerNode:
    true_expr = BoolExpr(
        text="1'b1",
        expr=BoolConst(value=1, width=1, signed=False, source_loc=_LOC),
        source_loc=_LOC,
    )
    return compose(
        PropImplication(
            antecedent=_b("req"),
            consequent=SeqConcat(
                elements=(true_expr, _b("ack")),
                delays=((delay_min, 3),),
                source_loc=_LOC,
            ),
            overlapping=True,
            source_loc=_LOC,
        ),
        _CLK,
        "delay_window_formal",
        "req |-> ##[1:3] ack",
    )


def _reference(name: str, delay_min: int) -> str:
    """Direct obligation-history reference, authored independently of the template."""
    shift_age_one = "req_d1 & ~ack" if delay_min <= 1 else "req_d1"
    shift_age_two = "req_d2 & ~ack" if delay_min <= 2 else "req_d2"
    eligible_terms = " | ".join(f"req_d{age}" for age in range(delay_min, 4))
    return f"""
module {name} (
    input  logic clk, rst_n, start, req, ack,
    output logic pass, fail, active, attempt_fired, disabled_o, overflow_flag
);
    logic req_d1, req_d2, req_d3;
    logic pass_q, fail_q, attempt_fired_q;
    always_ff @(posedge clk) begin
        if (!rst_n) begin
            req_d1 <= 1'b0;
            req_d2 <= 1'b0;
            req_d3 <= 1'b0;
            pass_q <= 1'b0;
            fail_q <= 1'b0;
        end else begin
            req_d1 <= start & req;
            req_d2 <= {shift_age_one};
            req_d3 <= {shift_age_two};
            pass_q <= ack & ({eligible_terms});
            fail_q <= req_d3 & ~ack;
        end
    end
    always_ff @(posedge clk) begin
        if (!rst_n) attempt_fired_q <= 1'b0;
        else if (start) attempt_fired_q <= 1'b1;
    end
    assign active        = req_d1 | req_d2 | req_d3;
    assign pass          = pass_q;
    assign fail          = fail_q;
    assign attempt_fired = attempt_fired_q;
    assign disabled_o    = 1'b0;
    assign overflow_flag = 1'b0;
endmodule
"""


@pytest.mark.parametrize("delay_min", [1, 2])
def test_delay_window_full_contract_complete_proof(delay_min: int) -> None:
    """Prove all public outputs for arbitrary overlapping starts and inputs."""
    checker = _checker(delay_min)
    assert checker.template_name == "implication_delay_window"
    ref_name = f"ref_delay_window_contract_{delay_min}"
    config = FormalHarnessConfig(
        start_mode="arbitrary_start",
        output_contract=FormalOutputContract.full_monitor(include_overflow=True),
        covers=("pass", "fail", "overlap"),
        assumption_notes=("start is low while reset is asserted",),
        overlap="unconstrained",
    )
    passed, output = run_sva_miter_check(
        checker,
        _reference(ref_name, delay_min),
        ref_name,
        depth=20,
        mode="prove",
        config=config,
    )
    assert passed, f"bounded-delay full-contract proof FAILED:\n{output[-3000:]}"
