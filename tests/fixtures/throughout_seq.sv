// sva2rtl v1.3 fixture: sequence THROUGHOUT
module m(input clk, en, a);
    assert property (@(posedge clk) en throughout (a ##1 a));
endmodule
