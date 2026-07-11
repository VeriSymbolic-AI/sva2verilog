module test_past(input clk, a, b);
  past_check: assert property (@(posedge clk) a |-> ($past(b, 2)));
endmodule
