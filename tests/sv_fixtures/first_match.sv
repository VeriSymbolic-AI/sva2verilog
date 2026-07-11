module test_first_match(input clk, a, b, c);
  first_match_check: assert property (@(posedge clk) first_match(a ##1 b ##1 c));
endmodule
