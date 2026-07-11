module test_changed(input clk, a, b);
  changed_check: assert property (@(posedge clk) $changed(a) |-> b);
endmodule
