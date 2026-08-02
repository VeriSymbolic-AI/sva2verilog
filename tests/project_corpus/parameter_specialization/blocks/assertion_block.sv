module assertion_block #(parameter bit EXPECTED_PARAM = 0) (
    input logic clk,
    input logic a
);
    `include "project_check.svh"
endmodule
