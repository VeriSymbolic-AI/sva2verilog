module test_stable(input clk, a, b);
  stable_check: assert property (@(posedge clk) $stable(a) |-> b);
endmodule
