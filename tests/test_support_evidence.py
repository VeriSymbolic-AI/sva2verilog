"""Machine-readable evidence ledger regressions."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ci.check_support_evidence import validate_payload

ROOT = Path(__file__).parent.parent
LEDGER = ROOT / "support_evidence.json"


def test_support_evidence_paths_and_promotion_gate_are_valid() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "ci" / "check_support_evidence.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "3 capabilities" in completed.stdout


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("executable_sha", "5ad7e2f", "40 lowercase hex digits"),
        ("ci_run", "not-a-run", "positive decimal run ID"),
        ("differential_run", "0", "positive decimal run ID"),
        ("full_formal_run", 31167747619, "positive decimal run ID"),
    ],
)
def test_support_evidence_rejects_invalid_qualification_identity(
    field: str, value: object, message: str
) -> None:
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    mutated = copy.deepcopy(payload)
    mutated["qualified_baseline"][field] = value

    with pytest.raises(RuntimeError, match=message):
        validate_payload(mutated, root=ROOT)


def test_support_evidence_rejects_unknown_qualification_state() -> None:
    payload = json.loads(LEDGER.read_text(encoding="utf-8"))
    payload["current_worktree_qualification"] = "probably-green"

    with pytest.raises(RuntimeError, match="qualification state"):
        validate_payload(payload, root=ROOT)
