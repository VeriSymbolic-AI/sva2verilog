// SPDX-License-Identifier: Apache-2.0

module prim_flop_2sync_spec(
  input logic clk_i,
  input logic rst_ni,
  input logic [15:0] d_i,
  input logic [15:0] q_o
);
  p_two_cycle: assert property (
    @(posedge clk_i) disable iff (!rst_ni)
    d_i[0] |-> ##2 q_o[0]
  );
endmodule
