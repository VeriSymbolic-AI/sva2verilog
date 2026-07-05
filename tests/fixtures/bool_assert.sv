module test_bool(input logic clk, rst_n, a, b);
  my_check: assert property (@(posedge clk) a && b);
endmodule
