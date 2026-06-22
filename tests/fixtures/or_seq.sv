// sva2rtl v1.3 fixture: sequence OR
module m(input clk, a, b);
    assert property (@(posedge clk) a or b);
endmodule
