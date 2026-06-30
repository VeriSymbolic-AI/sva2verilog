"""Targeted golden regeneration for the BUG-DELAY-01 fix.

Regenerates ONLY the delay-affected goldens, each from the CANONICAL fixture its
consuming test uses, so the ``// Source:`` comment matches exactly. Shared
modules (e.g. sva_delay_1_1) are pinned to one fixture to avoid last-writer-wins
clobbering. Run from the repo root.
"""

from __future__ import annotations

import json
from pathlib import Path

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.normalizer import normalize

FIX = Path("tests/fixtures")
GOLD = Path("tests/golden")


def full_pipeline(fixture: str) -> dict[str, str]:
    ast = json.loads((FIX / f"{fixture}.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    return emit_all(checker) if checker.children else {checker.module_name: emit(checker)}


def write_module(mods: dict[str, str], module: str) -> None:
    src = mods[module].rstrip("\n") + "\n"
    (GOLD / f"{module}.sv").write_text(src, encoding="utf-8")
    print(f"wrote {module}.sv")


def write_concat(mods: dict[str, str], golden_name: str) -> None:
    """Concatenated golden (join of all modules), as test_emit_first_match_golden expects."""
    all_sv = "\n".join(mods.values())
    (GOLD / golden_name).write_text(all_sv.rstrip("\n") + "\n", encoding="utf-8")
    print(f"wrote {golden_name} (concat)")


def main() -> None:
    # Per-module goldens, each pinned to the fixture its golden test consumes.
    dthree = full_pipeline("delay_three_element")
    write_module(dthree, "sva_delay_1_1")
    write_module(dthree, "sva_delay_2_2")

    dfixed = full_pipeline("delay_fixed")
    write_module(dfixed, "sva_delay_3_3")

    drange = full_pipeline("delay_range")
    write_module(drange, "sva_delay_2_5")

    # Concatenated golden for first_match (compose-only pipeline, per its test).
    ast = json.loads((FIX / "first_match.json").read_text(encoding="utf-8"))
    node, clock, text, label = import_assertion(ast)
    fm = emit_all(compose(node, clock, label, text))
    write_concat(fm, "sva_first_match.sv")


if __name__ == "__main__":
    main()
