module test_delay_8(input clk, a, b);
  assert property (@(posedge clk) a ##8 b);
endmodule
