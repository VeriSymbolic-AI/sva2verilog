module user_live_dut (
    input  logic clk,
    input  logic rst_n,
    output logic req,
    output logic ack
);
    assign req = 1'b1;
    assign ack = 1'b0;
endmodule
