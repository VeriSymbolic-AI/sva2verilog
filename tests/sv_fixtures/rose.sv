module test_rose(input clk, a, b);
  rose_check: assert property (@(posedge clk) $rose(a) |-> b);
endmodule
