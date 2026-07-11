module test_rep_range(input clk, a, b);
  rep_range: assert property (@(posedge clk) a |-> b[*2:5]);
endmodule
