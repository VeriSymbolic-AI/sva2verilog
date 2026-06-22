#!/usr/bin/env python3
"""Debug prop_if_else true_branch RTL timing"""
import json, subprocess, tempfile, os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize

ast = json.loads(open('tests/fixtures/v13_if_else_prop.json').read())
node, clock, text, label = import_assertion(ast)
node = normalize(node)
checker = compose(node, clock, label, text)
mods = emit_all(checker)

# Add monitor to parent module
sv = mods[checker.module_name]
sv = sv.replace('endmodule', '''
assign _ta=true_active; assign _tp=true_pass; assign _fa=false_active; assign _fp=false_pass;
assign _body_debug = _body_pass;
initial $monitor("%0t IFELSE: sel=%b start=%b ta=%b tp=%b fa=%b fp=%b body_pass=%b act=%b pass=%b",
  $time, sel, start, _ta, _tp, _fa, _fp, _body_debug, active, pass);
endmodule''')
mods[checker.module_name] = sv

tb = f'''
`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rst_n, dis, start, sel, a, b;
  wire act, p, f, af, dout;
  {checker.module_name} dut(.clk(clk),.rst_n(rst_n),.start(start),.sel(sel),.a(a),.b(b),.disable_i(dis),.active(act),.pass(p),.fail(f),.attempt_fired(af),.disabled_o(dout));
  initial begin
    rst_n=0; dis=0; start=0; sel=0; a=0; b=0;
    #15 rst_n=1;
    #13 start=1; sel=1; a=1; b=0;
    #10 start=0; sel=0; a=0; b=0;
    #10; #10; #10; #10;
    #10 $finish;
  end
endmodule
'''

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    (tmp/'dut.sv').write_text('\n\n'.join(mods.values()))
    (tmp/'tb.sv').write_text(tb)
    r = subprocess.run(['iverilog','-g2012','-o',str(tmp/'s.vvp'),str(tmp/'tb.sv'),str(tmp/'dut.sv')],capture_output=True,text=True)
    if r.returncode: print('COMPILE:',r.stderr[:500]); sys.exit(1)
    r = subprocess.run(['vvp',str(tmp/'s.vvp')],capture_output=True,text=True)
    print(r.stdout)
