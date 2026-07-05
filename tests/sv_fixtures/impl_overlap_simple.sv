module test_impl_overlap_simple(input clk, a, b);
  assert property (@(posedge clk) a |-> b);
endmodule
