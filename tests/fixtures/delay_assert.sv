module test_delay(input logic clk, rst_n, a, b);
  assert property (@(posedge clk) a ##1 b);
endmodule
