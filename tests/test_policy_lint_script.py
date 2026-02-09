"""Ensure policy lint script passes for built-in profiles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_policy_lint_script_passes() -> None:
    proc = subprocess.run(
        [sys.executable, "scripts/lint_policy_profiles.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Policy lint script failed.\n"
        f"STDOUT:\n{proc.stdout}\n"
        f"STDERR:\n{proc.stderr}"
    )
