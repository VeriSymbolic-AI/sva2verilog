module live_spec (
    input logic clk,
    input logic rst_n,
    input logic req,
    input logic ack
);
    req_eventually_ack: assert property (
        @(posedge clk) disable iff (!rst_n)
        req |-> s_eventually ack
    );
endmodule
