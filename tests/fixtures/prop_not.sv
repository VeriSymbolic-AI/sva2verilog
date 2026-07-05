// sva2rtl v1.3 fixture: property NOT
module m(input clk, a);
    assert property (@(posedge clk) not (a));
endmodule
