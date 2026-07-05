module test_delay_range_0_15(input clk, a, b);
  assert property (@(posedge clk) a ##[0:15] b);
endmodule
