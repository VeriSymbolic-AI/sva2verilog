module project_top #(parameter bit EXPECTED_PARAM = 0) (
    input logic clk,
    input logic a
);
    assertion_block #(.EXPECTED_PARAM(EXPECTED_PARAM)) u_checker (
        .clk(clk),
        .a(a)
    );
endmodule
