"""Regenerate all golden SV files from JSON fixtures."""
import json
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.normalizer import normalize

FIXTURES = Path("tests/fixtures")
GOLDEN = Path("tests/golden")

CASES = [
    ("bool_simple.json", "bool_simple.sv"),
    ("bool_labeled.json", "bool_labeled.sv"),
    ("rose.json", "sva_rose.sv"),
    ("fell.json", "sva_fell.sv"),
    ("stable.json", "sva_stable.sv"),
    ("past.json", "sva_past.sv"),
    ("rep_fixed.json", "sva_rep_fixed.sv"),
    ("rep_range.json", "sva_rep_range.sv"),
    ("s_eventually_1_3.json", "sva_se_1_3.sv"),
    ("always_1_3.json", "sva_sa_1_3.sv"),
    ("until_ab.json", "sva_until_ab.sv"),
]

for fixture_name, golden_file in CASES:
    ast = json.loads((FIXTURES / fixture_name).read_text())
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        result = emit_all(checker)
        for name, sv in result.items():
            path = GOLDEN / f"{name}.sv"
            path.write_text(sv)
            print(f"  {path}")
    else:
        sv = emit(checker)
        path = GOLDEN / golden_file
        path.write_text(sv)
        print(f"  {path}")

print(f"Done: regenerated {len(CASES)} golden files.")
