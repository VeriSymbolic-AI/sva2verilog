module test_delay_1(input clk, a, b);
  assert property (@(posedge clk) a ##1 b);
endmodule
