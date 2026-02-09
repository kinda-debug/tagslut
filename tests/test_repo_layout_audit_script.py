"""Ensure repo layout/surface audit passes in current repo state."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_repo_layout_audit_script_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/audit_repo_layout.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Repo layout audit failed.\n"
        f"STDOUT:\n{proc.stdout}\n"
        f"STDERR:\n{proc.stderr}"
    )
