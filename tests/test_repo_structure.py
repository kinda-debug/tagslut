"""Ensure the repository root follows the canonical layout and stays clean."""

from __future__ import annotations

import importlib
from pathlib import Path

import tomllib
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_required_directories_exist() -> None:
    """Verify required directories and placeholders are present."""

    expected_dirs = ["dedupe", "tools", "artifacts", "tests"]
    for name in expected_dirs:
        candidate = PROJECT_ROOT / name
        assert candidate.is_dir(), f"Missing required directory: {name}"

    for name in ["db", "logs", "tmp"]:
        candidate = PROJECT_ROOT / "artifacts" / name
        assert candidate.is_dir(), f"Missing artifacts subdirectory: {name}"


def test_forbidden_root_files_absent() -> None:
    """Guard against obsolete files and scratch artifacts in the repository root."""

    root_files = {path.name for path in PROJECT_ROOT.iterdir() if path.is_file()}
    forbidden_names = {"rstudio_parser.py"}
    for name in forbidden_names:
        assert name not in root_files, f"Forbidden root file remains: {name}"

    patterns = ["*.bak", "*.old", "*.tmp", "*.log", "*.db", "*.csv"]
    for pattern in patterns:
        matches = list(PROJECT_ROOT.glob(pattern))
        assert not matches, f"Found forbidden pattern {pattern}: {matches}"

    checkpoints = PROJECT_ROOT / ".ipynb_checkpoints"
    assert not checkpoints.exists(), "Jupyter checkpoints directory should not be present in root"


def test_pyproject_toml_parses() -> None:
    """Ensure the packaging metadata file is syntactically valid TOML."""

    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        data = tomllib.load(handle)
    assert "project" in data, "pyproject.toml must define a [project] table"


@pytest.mark.parametrize(
    "module_path",
    [
        "dedupe",
        "dedupe.cli",
        "dedupe.deduper",
        "dedupe.fingerprints",
        "dedupe.global_recovery",
        "dedupe.health_score",
        "dedupe.manifest",
        "dedupe.matcher",
        "dedupe.metadata",
        "dedupe.scanner",
        "dedupe.utils",
    ],
)
def test_modules_import_cleanly(module_path: str) -> None:
    """Import each core module to validate dependency availability and package wiring."""

    importlib.import_module(module_path)
