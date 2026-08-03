module progress_spec (
    input logic clk,
    input logic rst_n,
    input logic req,
    input logic ack
);
    req_has_delayed_ack: assert property (
        @(posedge clk) disable iff (!rst_n)
        req |-> nexttime[2] ack
    );
endmodule
