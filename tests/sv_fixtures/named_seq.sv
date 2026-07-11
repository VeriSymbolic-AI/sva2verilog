module test_named_seq(input clk, a, b, c);
  sequence seq_ab (a, b);
    a ##1 b;
  endsequence
  named_seq: assert property (@(posedge clk) seq_ab(a, b) |-> c);
endmodule
