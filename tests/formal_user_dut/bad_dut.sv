module user_formal_dut (
    input  logic clk,
    input  logic rst_n,
    input  logic req,
    output logic ack
);
    always_comb ack = 1'b0;
endmodule
