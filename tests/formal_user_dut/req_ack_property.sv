module req_ack_spec (
    input logic clk,
    input logic rst_n,
    input logic req,
    input logic ack
);
    req_has_ack: assert property (@(posedge clk) (!req) || ack);
endmodule
