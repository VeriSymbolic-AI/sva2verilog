module test_disable_iff(input clk, rst_n, a, b);
  disable_check: assert property (@(posedge clk) disable iff (!rst_n) (a |-> b));
endmodule
