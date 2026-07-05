"""Regenerate all golden files after template changes."""
import json
from pathlib import Path

from sva2rtl.ast_importer import import_all_assertions, import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all

fixtures_dir = Path('tests/fixtures')
golden_dir = Path('tests/golden')

for fpath in sorted(fixtures_dir.glob('*.json')):
    ast = json.loads(fpath.read_text(encoding='utf-8'))
    try:
        assertions = import_all_assertions(ast)
    except Exception:
        try:
            node, clock, text, label = import_assertion(ast)
            assertions = [(node, clock, text, label)]
        except Exception as e:
            print(f'Skip {fpath.name}: {e}')
            continue
    for node, clock, text, label in assertions:
        checker = compose(node, clock, label, text)
        modules = emit_all(checker)
        for mod_name, mod_src in modules.items():
            out_path = golden_dir / f'{mod_name}.sv'
            text = mod_src.rstrip('\n') + '\n'
            out_path.write_text(text, encoding='utf-8')
            print(f'R: {out_path.name}')
print('All golden files regenerated')
