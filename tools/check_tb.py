#!/usr/bin/env python3
"""Quick test: generate TB and check for multiple driver issues."""
import json, tempfile, os, sys
sys.path.insert(0, '.')
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
extra_inputs = extra_inputs_from_checker(checker)
stimulus = [{'start': True, 'a': True, 'b': True}]
tb = generate_testbench(checker.module_name, checker.params['clock_signal'], extra_inputs, stimulus, False)
sv_sources = list(modules.values())

combined = '\n\n'.join(sv_sources) + '\n\n' + tb
print(f"=== TB (last {min(30, len(tb.split(chr(10))))} lines) ===")
for line in tb.split('\n')[-30:]:
    print(line)
print(f"\n=== Searching for 'active' in TB ===")
for i, line in enumerate(tb.split('\n'), 1):
    if 'active' in line:
        print(f'TB line {i}: {line}')
