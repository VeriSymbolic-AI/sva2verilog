module test_delay_3(input clk, a, b);
  assert property (@(posedge clk) a ##3 b);
endmodule
