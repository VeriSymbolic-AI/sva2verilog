module test_goto_rep(input clk, a, b);
  goto_rep: assert property (@(posedge clk) a |-> b[->3]);
endmodule
