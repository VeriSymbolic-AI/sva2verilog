"""Regenerate custom-named golden files for test_sequential, test_emitter, etc."""
import json
from pathlib import Path
from sva2rtl.ast_importer import import_assertion, import_all_assertions
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all

GOLDEN = Path('tests/golden')
FIXTURES = Path('tests/fixtures')

def write_sv(mod_name, mod_src):
    p = GOLDEN / f'{mod_name}.sv'
    p.write_text(mod_src.rstrip('\n') + '\n', encoding='utf-8')
    print(f'Wrote {p}')

# These fixtures generate SV modules directly
single_map = {
    'bool_simple.json': None,
    'bool_labeled.json': None,
    'bool_complex.json': None,
    'rose.json': None,
    'fell.json': None,
    'stable.json': None,
    'past1.json': None,
    'past3.json': None,
}

for fname in single_map:
    ast = json.loads((FIXTURES / fname).read_text(encoding='utf-8'))
    node, clock, text, label = import_assertion(ast)
    checker = compose(node, clock, label, text)
    modules = emit_all(checker)
    for mn, ms in modules.items():
        write_sv(mn, ms)

# Multi-assertion fixtures
multi_map = {
    'delay_fixed.json': None,
    'delay_range.json': None,
    'delay_three_element.json': None,
    'delay_zero.json': None,
    'overlap.json': None,
    'nonoverlap.json': None,
}

for fname in multi_map:
    ast = json.loads((FIXTURES / fname).read_text(encoding='utf-8'))
    assertions = import_all_assertions(ast)
    for node, clock, text, label in assertions:
        checker = compose(node, clock, label, text)
        modules = emit_all(checker)
        for mn, ms in modules.items():
            write_sv(mn, ms)

print('Done')
