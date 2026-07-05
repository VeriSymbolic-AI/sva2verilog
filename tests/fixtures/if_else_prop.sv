// sva2rtl v1.3 fixture: property IF-ELSE
module m(input clk, sel, a, b);
    assert property (@(posedge clk) if (sel) a else b);
endmodule
