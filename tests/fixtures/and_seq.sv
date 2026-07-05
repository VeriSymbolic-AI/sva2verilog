// sva2rtl v1.3 fixture: sequence AND
module m(input clk, a, b);
    assert property (@(posedge clk) a and b);
endmodule
