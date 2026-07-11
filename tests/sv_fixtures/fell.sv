module test_fell(input clk, a, b);
  fell_check: assert property (@(posedge clk) $fell(a) |-> b);
endmodule
