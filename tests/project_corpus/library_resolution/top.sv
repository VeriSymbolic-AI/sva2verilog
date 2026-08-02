module library_top (
    input logic clk,
    input logic a
);
    library_checker u_checker (
        .clk(clk),
        .a(a)
    );
endmodule
