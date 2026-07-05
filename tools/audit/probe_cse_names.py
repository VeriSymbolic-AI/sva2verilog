"""Check module-name consistency before/after CSE for the bitvec implication."""
from __future__ import annotations

import json
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_FIX = Path(__file__).resolve().parents[2] / "tests/fixtures/implication_bitvec.json"


def _report(tag: str, mods: dict[str, str]) -> None:
    defined: set[str] = set()
    instated: set[str] = set()
    for v in mods.values():
        for line in v.splitlines():
            s = line.strip()
            if s.startswith("module "):
                defined.add(s.split()[1].split("#")[0].rstrip("(").strip())
            if " u_" in line:
                tok = s.split()[0]
                if tok.startswith("sva"):
                    instated.add(tok)
    print(f"\n=== {tag} ===")
    print("defined modules :", sorted(defined))
    print("instantiated    :", sorted(instated))
    print("MISSING (inst but not defined):", sorted(instated - defined))


ast = json.loads(_FIX.read_text())
node, clock, label, text = import_assertion(ast)
node = normalize(node)
comp = compose(node, clock, label, text)
_report("UNOPTIMIZED", emit_all(comp))
_report("OPTIMIZED (CSE)", emit_all(optimize(comp)))
