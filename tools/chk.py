#!/usr/bin/env python3
import json, tempfile, os, sys
sys.path.insert(0, os.getcwd())
from pathlib import Path
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize
from tests.simulation.tb_generator import *

ast = json.loads(open('tests/fixtures/v13_or_seq.json').read())
node, clock, text, label = import_assertion(ast)
node = normalize(node)
checker = compose(node, clock, label, text)
mods = emit_all(checker)
ins = extra_inputs_from_checker(checker)

stim = [{'start': True, 'a': True, 'b': True}]
stim += [{'start': False, 'a': False, 'b': False}] * 12

with tempfile.TemporaryDirectory() as td:
    tmp = Path(td)
    tb = generate_testbench(checker.module_name, checker.params['clock_signal'], ins, stim)
    res = run_simulation(checker.module_name, list(mods.values()), tb, work_dir=tmp, simulator='iverilog', stimulus=stim, extra_inputs=ins)
    print(f'total cycles: {len(res)}')
    for i, r in enumerate(res):
        print(f'c{i}: a={int(r["active"])} p={int(r["pass"])} f={int(r["fail"])}')
