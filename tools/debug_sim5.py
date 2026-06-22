#!/usr/bin/env python3
"""Minimal debug: drive all signals to 0, check outputs"""
import json, sys, os, subprocess, tempfile
sys.path.insert(0, os.getcwd())
from pathlib import Path
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize

ast = json.loads(open('tests/fixtures/v13_or_seq.json').read())
node, clock, text, label = import_assertion(ast)
node = normalize(node)
checker = compose(node, clock, label, text)
modules = emit_all(checker)

# Minimal TB - just check if outputs are ever x
tb = """
`timescale 1ns/1ps
module tb;
    reg clk; initial clk = 0; always #5 clk = ~clk;
    reg rst_n, disable_i, start, a, b;
    wire active, pass_out, fail_out, attempt_fired, disabled_o;

    sva_prop_07e57e0a dut (
        .clk(clk), .rst_n(rst_n), .start(start),
        .a(a), .b(b), .disable_i(disable_i),
        .active(active), .pass(pass_out), .fail(fail_out),
        .attempt_fired(attempt_fired), .disabled_o(disabled_o)
    );

    initial begin
        rst_n = 0; disable_i = 0; start = 0; a = 0; b = 0;
        repeat(3) @(posedge clk);
        @(negedge clk); rst_n = 1;
        repeat(3) @(posedge clk);
        $display("idle: active=%b pass=%b fail=%b", active, pass_out, fail_out);
        $finish;
    end
endmodule
"""

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    combined = '\n\n'.join(modules.values()) + '\n\n' + tb
    dut_path = tmp / 'dut.sv'
    dut_path.write_text(combined)
    exe = tmp / 'dut.vvp'
    r = subprocess.run(['iverilog', '-g2012', '-o', str(exe), str(dut_path)], capture_output=True, text=True)
    if r.returncode != 0:
        print(f'COMPILE ERROR:\n{r.stderr[:500]}')
        sys.exit(1)
    r = subprocess.run(['vvp', str(exe)], capture_output=True, text=True, cwd=str(tmp))
    print(f'Output: [{r.stdout.strip()}]')
    if r.stderr:
        print(f'Stderr: {r.stderr[:200]}')
