"""Ensure CLI/docs consistency check script passes in current repo state."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_checker_module():
    script_path = PROJECT_ROOT / "scripts" / "check_cli_docs_consistency.py"
    spec = importlib.util.spec_from_file_location("check_cli_docs_consistency", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_dedupe_alignment_fails_when_dedupe_exists_but_docs_not_marked_deprecated() -> None:
    checker = _load_checker_module()
    errors: list[str] = []
    checker.check_dedupe_docs_alignment(
        surface_policy_text="`tagslut` is the preferred CLI brand.",
        project_scripts={"tagslut", "dedupe"},
        errors=errors,
    )
    assert errors
    combined = "\n".join(errors)
    assert "deprecated alias for `tagslut`" in combined
    assert "2026-06-01" in combined


def test_dedupe_alignment_fails_when_docs_claim_dedupe_but_script_missing() -> None:
    checker = _load_checker_module()
    errors: list[str] = []
    checker.check_dedupe_docs_alignment(
        surface_policy_text=(
            "`dedupe` is a deprecated alias for `tagslut` and is still shipped. "
            "`dedupe` remains supported as a compatibility alias until 2026-06-01."
        ),
        project_scripts={"tagslut"},
        errors=errors,
    )
    assert errors
    assert "no `dedupe` console script" in "\n".join(errors)


def test_dedupe_alignment_passes_when_alias_is_removed_and_docs_match() -> None:
    checker = _load_checker_module()
    errors: list[str] = []
    checker.check_dedupe_docs_alignment(
        surface_policy_text="`tagslut` is the preferred CLI brand.",
        project_scripts={"tagslut"},
        errors=errors,
    )
    assert errors == []
