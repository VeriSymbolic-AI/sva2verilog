module test_rep_fixed(input clk, a, b);
  rep_fixed: assert property (@(posedge clk) a |-> b[*3]);
endmodule
