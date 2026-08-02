module library_checker (
    input logic clk,
    input logic a
);
    library_check: assert property (@(posedge clk) a);
endmodule
