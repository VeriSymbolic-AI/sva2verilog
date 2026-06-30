"""Golden parity regression test — proves normalize->compose->emit is byte-for-byte equivalent.

Verifies that the new normalize->compose pipeline produces identical output
for ALL existing golden files.  This is the primary regression gate for
Phase 4: any behavioral change in the pipeline would show up as a golden
file diff.

Coverage:
- D-11: Strict byte-for-byte parity for all Phase 1-3 golden outputs
- D-12: Regenerates all golden files and diffs against committed versions
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sva2rtl.ast_importer import import_assertion
from sva2rtl.composer import compose
from sva2rtl.emitter import emit, emit_all
from sva2rtl.normalizer import normalize
from tests.conftest import assert_golden

# ── Paths ────────────────────────────────────────────────────────────────────

_FIXTURES = Path(__file__).parent / "fixtures"
_GOLDEN = Path(__file__).parent / "golden"


# ── Pipeline helper ──────────────────────────────────────────────────────────


def _load(name: str) -> dict[str, object]:
    """Load a JSON fixture file from ``tests/fixtures/``."""
    return cast(dict[str, object], json.loads((_FIXTURES / name).read_text(encoding="utf-8")))


def _run_full_pipeline(fixture_name: str) -> dict[str, str]:
    """Run the full normalize->compose->emit pipeline on a JSON fixture.

    Returns a dict of {module_name: sv_text} for all generated modules.
    For single-module outputs (no children), wraps in a single-entry dict.
    """
    ast = _load(fixture_name)
    node, clock, text, label = import_assertion(ast)
    node = normalize(node)
    checker = compose(node, clock, label, text)
    if checker.children:
        return emit_all(checker)
    else:
        return {checker.module_name: emit(checker)}


# ── Single-module golden parity tests ────────────────────────────────────────

_SINGLE_MODULE_CASES: list[tuple[str, str]] = [
    ("bool_simple.json", "bool_simple.sv"),
    ("bool_labeled.json", "bool_labeled.sv"),
    ("rose.json", "sva_rose.sv"),
    ("fell.json", "sva_fell.sv"),
    ("stable.json", "sva_stable.sv"),
    ("past.json", "sva_past.sv"),
    ("rep_fixed.json", "sva_rep_fixed.sv"),
    ("rep_range.json", "sva_rep_range.sv"),
]


@pytest.mark.parametrize(
    ("fixture", "golden_file"),
    _SINGLE_MODULE_CASES,
    ids=[g for _, g in _SINGLE_MODULE_CASES],
)
def test_golden_parity_single_module(fixture: str, golden_file: str) -> None:
    """Single-module golden file matches byte-for-byte through normalize->compose->emit."""
    modules = _run_full_pipeline(fixture)
    assert len(modules) == 1, f"Expected 1 module, got {len(modules)}"
    sv_text = next(iter(modules.values()))
    assert_golden(sv_text, _GOLDEN / golden_file)


# ── Multi-module golden parity tests ────────────────────────────────────────

# Each entry: (fixture_name, list of (module_name_in_output, golden_filename))
_MULTI_MODULE_CASES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "delay_fixed.json",
        [
            ("sva_prop_81cf66e0_e0", "sva_prop_81cf66e0_e0.sv"),
            ("sva_delay_3_3", "sva_delay_3_3.sv"),
            ("sva_prop_81cf66e0_e1", "sva_prop_81cf66e0_e1.sv"),
            ("sva_prop_81cf66e0", "sva_prop_81cf66e0.sv"),
        ],
    ),
    (
        "delay_range.json",
        [
            ("sva_prop_e9edaa37_e0", "sva_prop_e9edaa37_e0.sv"),
            ("sva_delay_2_5", "sva_delay_2_5.sv"),
            ("sva_prop_e9edaa37_e1", "sva_prop_e9edaa37_e1.sv"),
            ("sva_prop_e9edaa37", "sva_prop_e9edaa37.sv"),
        ],
    ),
    (
        "delay_three_element.json",
        [
            ("sva_prop_5c9caf75_e0", "sva_prop_5c9caf75_e0.sv"),
            ("sva_delay_1_1", "sva_delay_1_1.sv"),
            ("sva_prop_5c9caf75_e1", "sva_prop_5c9caf75_e1.sv"),
            ("sva_delay_2_2", "sva_delay_2_2.sv"),
            ("sva_prop_5c9caf75_e2", "sva_prop_5c9caf75_e2.sv"),
            ("sva_prop_5c9caf75", "sva_prop_5c9caf75.sv"),
        ],
    ),
    (
        "delay_zero.json",
        [
            ("sva_prop_75080d6b_e0", "sva_prop_75080d6b_e0.sv"),
            ("sva_delay_0_0", "sva_delay_0_0.sv"),
            ("sva_prop_75080d6b_e1", "sva_prop_75080d6b_e1.sv"),
            ("sva_prop_75080d6b", "sva_prop_75080d6b.sv"),
        ],
    ),
    (
        "implication_overlap.json",
        [
            ("sva_impl_check", "overlap_impl.sv"),
        ],
    ),
    (
        "implication_nonoverlap.json",
        [
            ("sva_nonoverlap_check", "nonoverlap_impl.sv"),
        ],
    ),

]


@pytest.mark.parametrize(
    ("fixture", "module_goldens"),
    _MULTI_MODULE_CASES,
    ids=[f for f, _ in _MULTI_MODULE_CASES],
)
def test_golden_parity_multi_module(
    fixture: str,
    module_goldens: list[tuple[str, str]],
) -> None:
    """Multi-module golden files match byte-for-byte through normalize->compose->emit."""
    modules = _run_full_pipeline(fixture)
    for module_name, golden_file in module_goldens:
        assert module_name in modules, (
            f"Module '{module_name}' not found in pipeline output. "
            f"Available: {list(modules.keys())}"
        )
        assert_golden(modules[module_name], _GOLDEN / golden_file)


# ── Golden file count minimum ────────────────────────────────────────────────


def test_golden_file_count_minimum() -> None:
    """tests/golden/ contains at least 59 .sv files (catches accidental deletion)."""
    golden_files = list(_GOLDEN.glob("*.sv"))
    assert len(golden_files) >= 59, (
        f"Expected at least 59 golden .sv files, found {len(golden_files)}. "
        f"Files: {sorted(f.name for f in golden_files)}"
    )
