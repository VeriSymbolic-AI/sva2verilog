#!/usr/bin/env python3
"""Debug RTL sim - print raw output"""
import json, sys, os, tempfile, subprocess
sys.path.insert(0, os.getcwd())
from pathlib import Path
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize
from tests.simulation.tb_generator import extra_inputs_from_checker, generate_testbench

ast = json.loads(open('tests/fixtures/v13_or_seq.json').read())
node, clock, text, label = import_assertion(ast)
node = normalize(node)
checker = compose(node, clock, label, text)
modules = emit_all(checker)
inputs = extra_inputs_from_checker(checker)

stim = []
for i in range(10):
    stim.append({'start': i == 0, 'a': True, 'b': True})

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    tb = generate_testbench(checker.module_name, checker.params['clock_signal'], inputs, stim)
    combined = '\n\n'.join(modules.values()) + '\n\n' + tb
    dut_path = tmp / 'dut.sv'
    dut_path.write_text(combined)
    exe = tmp / 'dut.vvp'
    r = subprocess.run(['iverilog', '-g2012', '-o', str(exe), str(dut_path)], capture_output=True, text=True)
    if r.returncode != 0:
        print('Compile error:')
        print(r.stderr[:500])
        sys.exit(1)
    r = subprocess.run(['vvp', str(exe)], capture_output=True, text=True, cwd=str(tmp))
    print('=== RAW OUTPUT ===')
    print(r.stdout)
    print('=== STDERR ===')
    print(r.stderr[:500])
