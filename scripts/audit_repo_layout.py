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
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MOVE_EXECUTOR_SCRIPTS = (
    PROJECT_ROOT / "tools" / "review" / "move_from_plan.py",
    PROJECT_ROOT / "tools" / "review" / "quarantine_from_plan.py",
)
PROMOTE_SCRIPT = PROJECT_ROOT / "tools" / "review" / "promote_by_tags.py"
FILE_OPS_MODULE = PROJECT_ROOT / "dedupe" / "utils" / "file_operations.py"
COMPAT_MODULE = PROJECT_ROOT / "dedupe" / "exec" / "compat.py"


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


def find_legacy_wrapper_imports(cli_path: Path) -> set[str]:
    if not cli_path.exists():
        return set()
    text = cli_path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"from\\s+(legacy\\.tools\\.[a-zA-Z0-9_\\.]+)\\s+import", text)
    return set(matches)


def check_move_executor_adapter_usage(script_path: Path) -> list[str]:
    issues: list[str] = []
    if not script_path.exists():
        issues.append(f"Missing move executor script: {script_path}")
        return issues

    text = script_path.read_text(encoding="utf-8", errors="replace")
    rel = script_path.relative_to(PROJECT_ROOT)

    has_central_import = (
        "from dedupe.exec import execute_move" in text
        or "from dedupe.exec.engine import execute_move" in text
    )
    if not has_central_import:
        issues.append(f"{rel} must import execute_move from dedupe.exec")

    if "execute_move(" not in text:
        issues.append(f"{rel} must route move calls through dedupe.exec.execute_move")

    for disallowed in (r"\bshutil\.move\(", r"\bos\.replace\("):
        if re.search(disallowed, text):
            issues.append(f"{rel} contains direct move call matching /{disallowed}/")

    return issues


def check_promote_move_audit(promote_path: Path, file_ops_path: Path) -> list[str]:
    issues: list[str] = []

    if not promote_path.exists():
        issues.append(f"Missing promote script: {promote_path}")
        return issues
    if not file_ops_path.exists():
        issues.append(f"Missing file operations module: {file_ops_path}")
        return issues

    promote_text = promote_path.read_text(encoding="utf-8", errors="replace")
    file_ops_text = file_ops_path.read_text(encoding="utf-8", errors="replace")

    promote_rel = promote_path.relative_to(PROJECT_ROOT)
    file_ops_rel = file_ops_path.relative_to(PROJECT_ROOT)

    if "--move-log" not in promote_text:
        issues.append(f"{promote_rel} must expose --move-log for move audit control")
    if "audit_log_path=" not in promote_text:
        issues.append(f"{promote_rel} must pass audit_log_path into FileOperations")
    if ".safe_move(" not in promote_text:
        issues.append(f"{promote_rel} must execute moves through FileOperations.safe_move")

    if "append_jsonl(" not in file_ops_text:
        issues.append(f"{file_ops_rel} must write move audit events via append_jsonl")
    if '"event": "file_move"' not in file_ops_text:
        issues.append(f"{file_ops_rel} must stamp move audit events with event=file_move")
    if "verification" not in file_ops_text:
        issues.append(f"{file_ops_rel} must include move verification metadata in audit events")

    return issues


def check_compat_adapter_mapping(compat_path: Path) -> list[str]:
    issues: list[str] = []
    if not compat_path.exists():
        issues.append(f"Missing compatibility adapter module: {compat_path}")
        return issues
    text = compat_path.read_text(encoding="utf-8", errors="replace")
    rel = compat_path.relative_to(PROJECT_ROOT)
    if "from dedupe.exec.engine import execute_move" not in text:
        issues.append(f"{rel} must map to central executor execute_move")
    if "def execute_move_action" not in text:
        issues.append(f"{rel} must expose execute_move_action compatibility API")
    return issues


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

    for doc_name in ("SCRIPT_SURFACE.md", "SURFACE_POLICY.md", "MOVE_EXECUTOR_COMPAT.md"):
        doc_path = PROJECT_ROOT / "docs" / doc_name
        if not doc_path.is_file():
            errors.append(f"Missing required surface policy doc: {doc_path}")

    phase1_doc = PROJECT_ROOT / "docs" / "PHASE1_V3_DUAL_WRITE.md"
    if not phase1_doc.is_file():
        errors.append(f"Missing Phase 1 runbook doc: {phase1_doc}")
    phase2_doc = PROJECT_ROOT / "docs" / "PHASE2_POLICY_DECIDE.md"
    if not phase2_doc.is_file():
        errors.append(f"Missing Phase 2 runbook doc: {phase2_doc}")
    phase3_doc = PROJECT_ROOT / "docs" / "PHASE3_EXECUTOR.md"
    if not phase3_doc.is_file():
        errors.append(f"Missing Phase 3 runbook doc: {phase3_doc}")
    phase4_doc = PROJECT_ROOT / "docs" / "PHASE4_CLI_CONVERGENCE.md"
    if not phase4_doc.is_file():
        errors.append(f"Missing Phase 4 runbook doc: {phase4_doc}")
    phase5_doc = PROJECT_ROOT / "docs" / "PHASE5_LEGACY_DECOMMISSION.md"
    if not phase5_doc.is_file():
        errors.append(f"Missing Phase 5 runbook doc: {phase5_doc}")
    for profile in ("dj_strict.yaml", "library_balanced.yaml", "bulk_recovery.yaml"):
        profile_path = PROJECT_ROOT / "config" / "policies" / profile
        if not profile_path.is_file():
            errors.append(f"Missing policy profile: {profile_path}")

    root_runtime_files = find_root_runtime_files(PROJECT_ROOT)
    if root_runtime_files:
        pretty = ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in root_runtime_files)
        errors.append(f"Runtime artifacts should not live in repo root: {pretty}")

    duplicates = duplicate_script_names(
        PROJECT_ROOT / "tools" / "review",
        PROJECT_ROOT / "legacy" / "tools" / "review",
    )
    allowed_duplicate_basenames = {"promote_by_tags.py"}
    duplicates = {
        name: paths
        for name, paths in duplicates.items()
        if name not in allowed_duplicate_basenames
    }
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
            "--check / --no-check   Enable/disable similarity check (default: --check)",
            "--threshold FLOAT      Similarity threshold 0.0-1.0 (default: 0.85)",
            "--register             Register files to inventory without moving",
            "--scan                 Scan and update inventory from paths",
            "--status               Show inventory statistics",
        ]
        seen = [marker for marker in stale_markers if marker in text]
        if seen:
            warnings.append(
                "MGMT_MODE.md contains historical flag descriptions "
                "that do not match current CLI group options: "
                + ", ".join(seen)
            )

    # Guardrail: prevent adding new legacy CLI wrappers without explicit review.
    cli_legacy_imports = find_legacy_wrapper_imports(
        PROJECT_ROOT / "dedupe" / "cli" / "main.py"
    )
    if cli_legacy_imports:
        errors.append(
            "Legacy CLI wrapper imports should be fully decommissioned, found: "
            + ", ".join(sorted(cli_legacy_imports))
        )

    for script_path in MOVE_EXECUTOR_SCRIPTS:
        errors.extend(check_move_executor_adapter_usage(script_path))

    errors.extend(check_promote_move_audit(PROMOTE_SCRIPT, FILE_OPS_MODULE))
    errors.extend(check_compat_adapter_mapping(COMPAT_MODULE))

    for script_name in (
        "backfill_v3_identity_links.py",
        "backfill_v3_provenance_from_logs.py",
        "validate_v3_dual_write_parity.py",
        "lint_policy_profiles.py",
    ):
        candidate = PROJECT_ROOT / "scripts" / script_name
        if not candidate.is_file():
            errors.append(f"Missing migration script: {candidate}")

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
