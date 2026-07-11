"""Regenerate ALL golden SV files using the current pipeline (after importer fix)."""
import json
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.normalizer import normalize as norm

FIXTURES = Path("tests/fixtures")
GOLDEN = Path("tests/golden")

ALL_CASES = [
    # Single-module JSON fixtures
    ("delay_fixed.json", [("sva_delay_3_3", "sva_delay_3_3.sv")]),
    ("delay_range.json", [("sva_delay_2_5", "sva_delay_2_5.sv")]),
    ("delay_three_element.json", [
        ("sva_delay_1_1", "sva_delay_1_1.sv"),
        ("sva_delay_2_2", "sva_delay_2_2.sv"),
    ]),
    # Multi-module fixtures
    ("delay_zero.json", []),
    ("implication_overlap.json", [
        ("sva_impl_check_ant", "sva_impl_check_ant.sv"),
        ("sva_impl_check_con", "sva_impl_check_con.sv"),
        ("sva_impl_check", "sva_impl_check.sv"),
    ]),
    ("implication_nonoverlap.json", [
        ("sva_nonoverlap_check_ant", "sva_nonoverlap_check_ant.sv"),
        ("sva_nonoverlap_check_con", "sva_nonoverlap_check_con.sv"),
        ("sva_nonoverlap_check", "sva_nonoverlap_check.sv"),
    ]),
]

for fixture_name, expected in ALL_CASES:
    ast = json.loads((FIXTURES / fixture_name).read_text())
    node, clock, text, label = import_assertion(ast)
    node = norm(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        result = emit_all(checker)
    else:
        result = {checker.module_name: emit(checker)}
    for name, sv in result.items():
        path = GOLDEN / f"{name}.sv"
        path.write_text(sv)
        print(f"  {path}")
print("Done.")
