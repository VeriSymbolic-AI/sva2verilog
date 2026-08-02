`ifdef ENABLE_PROJECT_CHECK
project_check: assert property (@(posedge clk) a == EXPECTED_PARAM);
`endif
