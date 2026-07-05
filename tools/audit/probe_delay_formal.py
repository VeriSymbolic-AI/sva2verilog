"""FPV-grade (SymbiYosys) confirmation of the ##N spacing defect.

Builds a SEMANTICALLY-CORRECT reference monitor for `a ##3 b` whose a->b gap is
hard-fixed to 3 (shift-register depth 3) — the gap is the operator's value, NOT
tuned to the generated monitor. Only a single uniform report latency (one cycle,
matching the b-leaf registration) is applied. Then miters monitor.pass against
ref.pass via BMC.

If the generated monitor were correct, BMC would PASS (no disagreement). The
existing test_delay_fixed_3_equiv passes only because its reference was tuned to
cnt==5 (gap+latency conflated) — circular. With the gap pinned to the operator
value, a real +2 defect must surface as a counterexample.
"""

from __future__ import annotations

import json
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.formal_equiv import run_sva_miter_check
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

# Semantically-correct, SINGLE-ATTEMPT reference for `a ##3 b`, aligned to the
# miter harness's single `start` pulse protocol. The attempt is armed at
# (start & a); b is then sampled EXACTLY 3 cycles later (one-hot delay line of
# depth 3 — the gap is hard-fixed to the operator value 3, NOT tuned). pass is
# registered one cycle after the b-sample (uniform report latency).
_REF_A3B_CORRECT = """\
module ref_a3b_correct (
    input  logic clk,
    input  logic rst_n,
    input  logic start,
    input  logic a,
    input  logic b,
    output logic pass
);
    logic [2:0] arm_sr;   // one-hot delay line of the armed attempt
    always_ff @(posedge clk) begin
        if (!rst_n) arm_sr <= 3'b0;
        else        arm_sr <= {arm_sr[1:0], (start & a)};
    end
    // arm_sr[2] high exactly 3 cycles after (start&a) -> sample b at gap 3.
    wire b_sample = arm_sr[2];
    logic pass_q;
    always_ff @(posedge clk) begin
        if (!rst_n) pass_q <= 1'b0;
        else        pass_q <= b_sample & b;
    end
    assign pass = pass_q;
endmodule
"""


def main() -> None:
    ast = json.loads(Path("tests/fixtures/delay_fixed.json").read_text())
    node, clock, label, text = import_assertion(ast)
    node = normalize(node)
    ck = optimize(compose(node, clock, label, text))

    passed, output = run_sva_miter_check(
        ck, _REF_A3B_CORRECT, "ref_a3b_correct", compare="pass", depth=20
    )
    print("=== a ##3 b  vs  semantically-correct reference (gap fixed = 3) ===")
    print("miter passed (monitor == correct ref):", passed)
    if not passed:
        print("\n--- BMC found a disagreement (confirms spacing defect) ---")
        # Surface the assertion-failure / counterexample portion.
        tail = output[-1800:]
        print(tail)


if __name__ == "__main__":
    main()
