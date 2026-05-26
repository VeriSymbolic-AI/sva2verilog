module test_impl_overlap_delay(input clk, a, b);
  assert property (@(posedge clk) a |-> ##[2:5] b);
endmodule
