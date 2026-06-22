// sva2rtl v1.3 fixture: sequence INTERSECT
module m(input clk, a, b);
    assert property (@(posedge clk) a intersect b);
endmodule
