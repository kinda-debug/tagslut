"""Ensure CLI/docs consistency check script passes in current repo state."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cli_docs_consistency_script_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/check_cli_docs_consistency.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Consistency script failed.\n"
        f"STDOUT:\n{proc.stdout}\n"
        f"STDERR:\n{proc.stderr}"
    )
