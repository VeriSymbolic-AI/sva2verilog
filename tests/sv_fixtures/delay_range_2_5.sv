module test_delay_range_2_5(input clk, a, b);
  assert property (@(posedge clk) a ##[2:5] b);
endmodule
