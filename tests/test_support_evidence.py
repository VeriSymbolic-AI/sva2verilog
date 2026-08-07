"""Machine-readable evidence ledger regressions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


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
