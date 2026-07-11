module test_nonconsec_rep(input clk, a, b);
  nonconsec_rep: assert property (@(posedge clk) a |-> b[=3]);
endmodule
