#!/usr/bin/env python3
"""Debug: add $monitor to internal wires to trace x source"""
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

# Replace output gating in bool_expr children to remove disable_i
for k, sv in list(mods.items()):
    if k == checker.module_name:
        continue
    sv = sv.replace("assign active        = disable_i ? 1'b0 : active_q;", "assign active        = active_q;")
    sv = sv.replace("assign pass          = disable_i ? 1'b0 : pass_q;",   "assign pass          = pass_q;")
    sv = sv.replace("assign fail          = disable_i ? 1'b0 : fail_q;",   "assign fail          = fail_q;")
    mods[k] = sv

# Add monitor to parent
sv = mods[checker.module_name]
sv = sv.replace('endmodule', '''
wire _dbg = _body_active;
assign _la = left_active; assign _ra = right_active; assign _lp = left_pass; assign _rp = right_pass;
initial $monitor("%0t PAR: act=%b left_act=%b right_act=%b body=%b left_pass=%b right_pass=%b body_pass=%b", $time, active, _la, _ra, _dbg, _lp, _rp, _body_pass);
endmodule''')
mods[checker.module_name] = sv

tb = f'''
`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rst_n, dis, start, a, b;
  wire act, p, f, af, dout;
  {checker.module_name} dut(.clk(clk),.rst_n(rst_n),.start(start),.a(a),.b(b),.disable_i(dis),.active(act),.pass(p),.fail(f),.attempt_fired(af),.disabled_o(dout));
  initial begin
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
