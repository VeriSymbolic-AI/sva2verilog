module xz_spec(input logic clk, rst_n, a);
    p_xz: assert property (@(posedge clk) a == 1'bx);
endmodule
