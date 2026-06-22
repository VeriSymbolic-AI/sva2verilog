#!/usr/bin/env python3
"""Debug: standalone sim of prop_or with minimal TB"""
import json, subprocess, tempfile, os, sys
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
mods = emit_all(checker)

# Add $monitor to top module
sv = mods[checker.module_name]
sv = sv.replace('endmodule', '''
initial $monitor("%0t TOP: start=%b act=%b pass=%b left_act=%b left_pass=%b right_act=%b right_pass=%b l_dis=%b r_dis=%b",
  $time, start, active, pass, left_active, left_pass, right_active, right_pass, left_disabled, right_disabled);
endmodule''')
mods[checker.module_name] = sv

# Minimal TB
tb = f'''
`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rst_n, dis, start, a, b;
  wire act, p, f, af, dout;
  {checker.module_name} dut(.clk(clk),.rst_n(rst_n),.start(start),.a(a),.b(b),.disable_i(dis),.active(act),.pass(p),.fail(f),.attempt_fired(af),.disabled_o(dout));
  initial begin
    $dumpfile("dump.vcd"); $dumpvars(0,tb);
    rst_n=0; dis=0; start=0; a=0; b=0;
    #15 rst_n=1;
    #13 start=1; a=1; b=1;
    #10 start=0; a=0; b=0;
    #10 start=0; a=0; b=0;
    #10 start=0; a=0; b=0;
    #10 $finish;
  end
endmodule
'''

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    dut_path = tmp / 'dut.sv'
    dut_path.write_text('\n\n'.join(mods.values()))
    tb_path = tmp / 'tb.sv'
    tb_path.write_text(tb)

    r = subprocess.run(['iverilog', '-g2012', '-o', str(tmp/'s.vvp'), str(tb_path), str(dut_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print('COMPILE ERROR:', r.stderr[:500])
        sys.exit(1)

    r = subprocess.run(['vvp', str(tmp/'s.vvp')], capture_output=True, text=True, cwd=str(tmp))
    print(r.stdout)
