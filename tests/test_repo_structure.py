"""Ensure the repository root follows the canonical layout and stays clean."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import tomllib
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_required_directories_exist() -> None:
    """Verify required directories and placeholders are present."""

    expected_dirs = ["tagslut", "tools", "artifacts", "tests"]
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
    # Allow common system files that may appear on some OSes
    allowed_system_files = {".DS_Store", "Thumbs.db"}
    for name in forbidden_names:
        assert name not in root_files, f"Forbidden root file remains: {name}"

    patterns = ["*.bak", "*.old", "*.tmp", "*.log", "*.db", "*.csv"]
    allowed_root_files = {".gitignore", ".gitattributes", "pyproject.toml"} | allowed_system_files
    for pattern in patterns:
        matches = [m for m in PROJECT_ROOT.glob(pattern) if m.name not in allowed_root_files]
        # Exclude allowed system files from matches
        matches = [m for m in matches if m.name not in allowed_system_files]
        # Only fail if matches remain after filtering
        filtered = [str(m) for m in matches if m.name not in allowed_system_files]
        assert not matches, f"Found forbidden pattern {pattern}: {filtered}"

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
        "tagslut",
        "tagslut.core",
        "tagslut.core.matching",
        "tagslut.core.metadata",
        "tagslut.exec",
        "tagslut.core.scanner",
        "tagslut.policy",
        "tagslut.decide",
        "tagslut.decide.planner",
        "tagslut.storage",
        "tagslut.storage.schema",
        "tagslut.utils",
        "tagslut",
    ],
)
def test_modules_import_cleanly(module_path: str) -> None:
    """Import each core module to validate dependency availability and package wiring."""

    importlib.import_module(module_path)


def test_integrity_scanner_orphan_absent() -> None:
    """Ensure the old top-level orphan tagslut/integrity_scanner.py no longer exists.

    Logic must live under tagslut.core.scanner (issue #109).
    """
    orphan = PROJECT_ROOT / "tagslut" / "integrity_scanner.py"
    assert not orphan.exists(), (
        "tagslut/integrity_scanner.py must not exist; "
        "scanner logic belongs in tagslut.core.scanner"
    )


def test_scan_library_accessible_from_core_scanner() -> None:
    """Verify that scan_library is importable from tagslut.core.scanner."""
    from tagslut.core.scanner import scan_library  # noqa: F401


def test_docs_readme_exists() -> None:
    """Ensure docs index referenced by root README exists."""
    assert (PROJECT_ROOT / "docs" / "README.md").exists()


def test_docs_readme_links_resolve_to_repo_files() -> None:
    """Ensure all local markdown links in docs/README.md point to existing files."""
    docs_readme = PROJECT_ROOT / "docs" / "README.md"
    text = docs_readme.read_text(encoding="utf-8")
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)

    assert links, "docs/README.md should contain markdown links"
    for link in links:
        if link.startswith(("http://", "https://", "mailto:", "#")):
            continue
        target = (docs_readme.parent / link).resolve()
        assert target.exists(), f"Broken docs link in docs/README.md: {link}"


def test_archived_classifier_changelog_exists() -> None:
    """Ensure classifier-specific changelog was archived out of project root."""
    archived = PROJECT_ROOT / "docs" / "archive" / "CLASSIFY_V2_CHANGELOG.md"
    assert archived.exists(), "Expected archived classifier changelog at docs/archive/CLASSIFY_V2_CHANGELOG.md"


def test_classify_changelog_archived() -> None:
    assert (PROJECT_ROOT / "docs" / "archive" / "CLASSIFY_V2_CHANGELOG.md").exists()


def test_recovery_package_absent_or_stubbed() -> None:
    """Ensure `tagslut.recovery` implementation is archived from live package."""
    recovery_dir = PROJECT_ROOT / "tagslut" / "recovery"
    if not recovery_dir.exists():
        return

    init_file = recovery_dir / "__init__.py"
    assert init_file.exists(), "tagslut/recovery must be absent or contain a stub __init__.py"
    live_modules = sorted(path.name for path in recovery_dir.glob("*.py") if path.name != "__init__.py")
    assert not live_modules, f"Unexpected live recovery modules remain: {live_modules}"
    init_text = init_file.read_text(encoding="utf-8")
    assert "ImportError" in init_text


def test_scan_package_absent_or_stubbed() -> None:
    """Ensure `tagslut.scan` implementation is archived from live package."""
    scan_dir = PROJECT_ROOT / "tagslut" / "scan"
    if not scan_dir.exists():
        return

    init_file = scan_dir / "__init__.py"
    assert init_file.exists(), "tagslut/scan must be absent or contain a stub __init__.py"
    live_modules = sorted(path.name for path in scan_dir.glob("*.py") if path.name != "__init__.py")
    assert not live_modules, f"Unexpected live scan modules remain: {live_modules}"
    init_text = init_file.read_text(encoding="utf-8")
    assert "ImportError" in init_text


def test_recovery_is_decommissioned() -> None:
    with pytest.raises(ImportError):
        import tagslut.recovery  # noqa: F401


def test_scan_is_archived() -> None:
    with pytest.raises(ImportError, match="archived"):
        import tagslut.scan  # noqa: F401
