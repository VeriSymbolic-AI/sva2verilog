"""Print structure of candidate fixtures for formal-equivalence proof authoring."""
from __future__ import annotations

import json
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_FIX = Path(__file__).resolve().parents[2] / "tests/fixtures"

CANDIDATES = [
    "delay_range",
    "rep_fixed",
    "rep_range",
    "disable_iff",
    "v13_and_seq",
    "v13_or_seq",
    "v13_prop_not",
    "v13_if_else_prop",
]


def describe(node: CheckerNode, depth: int = 0) -> None:
    pad = "  " * depth
    tn = getattr(node, "template_name", "?")
    mn = getattr(node, "module_name", "?")
    bw = node.params.get("bv_width", "-")
    print(f"{pad}- {tn} [{mn}] bv_width={bw} sigs={node.observed_signals}")
    for c in node.children:
        describe(c, depth + 1)


for name in CANDIDATES:
    p = _FIX / f"{name}.json"
    if not p.exists():
        print(f"\n### {name}: (no json)")
        continue
    ast = json.loads(p.read_text())
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    try:
        checker = optimize(compose(node, clock, label, text))
    except Exception as e:  # noqa: BLE001
        print(f"\n### {name}: COMPOSE RAISED: {type(e).__name__}: {str(e)[:80]}")
        continue
    print(f"\n### {name}: '{text}'  clock={clock.edge} {clock.signal}")
    describe(checker)
