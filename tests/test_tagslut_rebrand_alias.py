"""Validate rebrand aliases for tagslut CLI entrypoints."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_python_module_tagslut_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "tagslut", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        "Expected python -m tagslut --help to succeed.\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
    assert "Commands:" in proc.stdout
    for command in ("intake", "index", "decide", "execute", "verify", "report", "auth"):
        assert command in proc.stdout


def test_pyproject_rebrand_scripts_present() -> None:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)

    project_scripts = data.get("project", {}).get("scripts", {})

    for script_name in ("tagslut", "dedupe"):
        assert script_name in project_scripts
