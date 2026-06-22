#!/usr/bin/env python3
"""Test: change logic to wire for intermediate signals in prop_or"""
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

# Fix: replace 'logic' with 'wire' for inter-module connection signals
sv = mods[checker.module_name]
sv = sv.replace('logic left_active, left_pass, left_fail;', 'wire left_active, left_pass, left_fail;')
sv = sv.replace('logic right_active, right_pass, right_fail;', 'wire right_active, right_pass, right_fail;')
sv = sv.replace('logic left_disabled, right_disabled;', 'wire left_disabled, right_disabled;')
# Also fix _body_* to use wire
sv = sv.replace('logic _body_active =', 'wire _body_active =')
sv = sv.replace('logic _body_pass   =', 'wire _body_pass   =')
sv = sv.replace('logic _body_fail   =', 'wire _body_fail   =')
mods[checker.module_name] = sv

tb = f'''
`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rst_n, dis, start, a, b;
  wire act, p, f, af, dout;
  {checker.module_name} dut(.clk(clk),.rst_n(rst_n),.start(start),.a(a),.b(b),.disable_i(dis),.active(act),.pass(p),.fail(f),.attempt_fired(af),.disabled_o(dout));
  initial begin
    $monitor("%0t act=%b pass=%b", $time, act, p);
    rst_n=0; dis=0; start=0; a=0; b=0;
    #15 rst_n=1;
    #13 start=1; a=1; b=1;
    #10 start=0; a=0; b=0;
    #20 $finish;
  end
endmodule
'''

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    (tmp/'dut.sv').write_text('\n\n'.join(mods.values()))
    (tmp/'tb.sv').write_text(tb)
    r = subprocess.run(['iverilog','-g2012','-o',str(tmp/'s.vvp'),str(tmp/'tb.sv'),str(tmp/'dut.sv')],capture_output=True,text=True)
    if r.returncode: print('COMPILE:',r.stderr[:300]); sys.exit(1)
    r = subprocess.run(['vvp',str(tmp/'s.vvp')],capture_output=True,text=True)
    print(r.stdout)
