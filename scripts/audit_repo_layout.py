#!/usr/bin/env python3
"""Repo layout sanity checks for dedupe.

Usage:
  python scripts/audit_repo_layout.py
  python scripts/audit_repo_layout.py --strict-warnings
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def find_root_runtime_files(root: Path) -> list[Path]:
    patterns = ("*.log", "*.db", "*.csv", "*.tmp")
    keep = {".gitignore", ".gitattributes", "pyproject.toml", "Thumbs.db", ".DS_Store"}
    matches: list[Path] = []
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if candidate.name in keep:
                continue
            if candidate.is_file():
                matches.append(candidate)
    return sorted(matches)


def duplicate_script_names(*roots: Path) -> dict[str, list[Path]]:
    by_name: dict[str, list[Path]] = defaultdict(list)
    for root in roots:
        if not root.exists():
            continue
        for script in root.rglob("*.py"):
            by_name[script.name].append(script)
    return {name: paths for name, paths in sorted(by_name.items()) if len(paths) > 1}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit repo layout and script surface drift")
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Return non-zero exit code when warnings are present",
    )
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []

    for name in ("db", "logs", "tmp"):
        expected = PROJECT_ROOT / "artifacts" / name
        if not expected.is_dir():
            errors.append(f"Missing artifacts subdirectory: {expected}")

    root_runtime_files = find_root_runtime_files(PROJECT_ROOT)
    if root_runtime_files:
        pretty = ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in root_runtime_files)
        errors.append(f"Runtime artifacts should not live in repo root: {pretty}")

    duplicates = duplicate_script_names(
        PROJECT_ROOT / "tools" / "review",
        PROJECT_ROOT / "legacy" / "tools" / "review",
    )
    if duplicates:
        lines = []
        for name, paths in duplicates.items():
            refs = ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in paths)
            lines.append(f"{name}: {refs}")
        warnings.append(
            "Duplicate script basenames across active/legacy surfaces: "
            + " | ".join(lines)
        )

    mgmt_doc = PROJECT_ROOT / "docs" / "MGMT_MODE.md"
    if mgmt_doc.exists():
        text = mgmt_doc.read_text(encoding="utf-8", errors="replace")
        stale_markers = [
            "--register",
            "--scan",
            "--status",
            "--threshold",
            "--check / --no-check",
        ]
        seen = [marker for marker in stale_markers if marker in text]
        if seen:
            warnings.append(
                "MGMT_MODE.md contains historical flag descriptions "
                "that do not match current CLI group options: "
                + ", ".join(seen)
            )

    if errors:
        print("ERRORS:")
        for item in errors:
            print(f"- {item}")

    if warnings:
        print("WARNINGS:")
        for item in warnings:
            print(f"- {item}")

    if not errors and not warnings:
        print("OK: repo layout audit passed")

    if errors:
        return 1
    if warnings and args.strict_warnings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
