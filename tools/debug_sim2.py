#!/usr/bin/env python3
"""Debug RTL sim output"""
import json, sys, os, tempfile
sys.path.insert(0, os.getcwd())
from pathlib import Path
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize
from tests.simulation.tb_generator import extra_inputs_from_checker, generate_testbench, run_simulation

ast = json.loads(open('tests/fixtures/v13_or_seq.json').read())
node, clock, text, label = import_assertion(ast)
node = normalize(node)
checker = compose(node, clock, label, text)
modules = emit_all(checker)
inputs = extra_inputs_from_checker(checker)

# 15-cycle stimulus: start at cycle 0
stim = []
for i in range(15):
    stim.append({'start': i == 0, 'a': i == 0, 'b': i == 0})

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    tb = generate_testbench(checker.module_name, checker.params['clock_signal'], inputs, stim)
    res = run_simulation(checker.module_name, list(modules.values()), tb,
                         work_dir=tmp, simulator='iverilog', stimulus=stim, extra_inputs=inputs)
    print(f'Total cycles: {len(res)}')
    for i, r in enumerate(res):
        print(f'c{i:2d}: active={int(r["active"])} pass={int(r["pass"])} fail={int(r["fail"])}')
