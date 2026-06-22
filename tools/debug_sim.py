#!/usr/bin/env python3
"""Debug simulation output timing."""
import json, sys
from pathlib import Path
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize
from tests.simulation.tb_generator import *
import tempfile

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
    res = run_simulation('iverilog', checker.module_name, list(modules.values()), tb, tmp, False, stim, inputs)
    for i, r in enumerate(res):
        print(f'c{i}: a={r["active"]} p={r["pass"]} f={r["fail"]}')
