#!/usr/bin/env python3
import json, sys, os
sys.path.insert(0, os.getcwd())
from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.normalizer import normalize
from sva2rtl.behavioral_oracle import simulate_checker_hierarchy

ast = json.loads(open('tests/fixtures/v13_throughout_seq.json').read())
node, clock, text, label = import_assertion(ast)
node = normalize(node)
checker = compose(node, clock, label, text)
stim = [
    {'start': True,  'en': True,  'a': True},
    {'start': False, 'en': False, 'a': True},
    {'start': False, 'en': False, 'a': False},
    {'start': False, 'en': False, 'a': False},
    {'start': False, 'en': False, 'a': False},
    {'start': False, 'en': False, 'a': False},
]
res = simulate_checker_hierarchy(checker, stim)
for i, r in enumerate(res):
    print(f'c{i}: a={r["active"]} p={r["pass"]} f={r["fail"]}')
