module multiclock_spec(input logic clk, clk2, rst_n, a, b);
    p_multiclock: assert property (
        @(posedge clk) a |=> @(posedge clk2) b
    );
endmodule
