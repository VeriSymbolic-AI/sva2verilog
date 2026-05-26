module test_delay_range_0_1(input clk, a, b);
  assert property (@(posedge clk) a ##[0:1] b);
endmodule
