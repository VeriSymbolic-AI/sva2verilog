module test_impl_nonoverlap_simple(input clk, a, b);
  assert property (@(posedge clk) a |=> b);
endmodule
