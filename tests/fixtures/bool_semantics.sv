module bool_semantics_fixture(
  input logic clk,
  input logic a,
  input logic b,
  input logic c,
  input logic [3:0] data
);
  bool_or:       assert property (@(posedge clk) a || b);
  bool_not:      assert property (@(posedge clk) !a);
  bool_const:    assert property (@(posedge clk) 1'b1);
  bool_nested:   assert property (@(posedge clk) (a && b) || !c);
  bool_eq:       assert property (@(posedge clk) data == 4'd3);
  bool_ne:       assert property (@(posedge clk) data != 4'd0);
  bool_bit:      assert property (@(posedge clk) data[0]);
endmodule
