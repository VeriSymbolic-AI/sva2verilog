module test_imp_overlap_delay_range(input logic clk, req, ack);
  range_lower_bound: assert property (@(posedge clk) req |-> ##[1:3] ack);
endmodule
