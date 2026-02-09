#!/usr/bin/env python3
"""Check consistency between live CLI help and key docs.

Usage:
  python scripts/check_cli_docs_consistency.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"

TOP_CANONICAL_COMMANDS = {"intake", "index", "decide", "execute", "verify", "report", "auth"}
REMOVED_LEGACY_COMMANDS = {"scan", "recommend", "apply", "promote", "quarantine"}
REMOVED_COMPAT_COMMANDS = {"mgmt", "metadata", "recover", "m"}
INTAKE_REQUIRED_COMMANDS = {"run", "prefilter"}
INDEX_REQUIRED_COMMANDS = {
    "register",
    "check",
    "duration-check",
    "duration-audit",
    "set-duration-ref",
    "enrich",
}
DECIDE_REQUIRED_COMMANDS = {"profiles", "plan"}
EXECUTE_REQUIRED_COMMANDS = {"move-plan", "quarantine-plan", "promote-tags"}
VERIFY_REQUIRED_COMMANDS = {"duration", "recovery", "parity", "receipts"}
REPORT_REQUIRED_COMMANDS = {"m3u", "duration", "recovery", "plan-summary"}
AUTH_REQUIRED_COMMANDS = {"status", "init", "refresh", "login"}


def run_help(module_name: str, *args: str) -> str:
    cmd = [sys.executable, "-m", module_name, *args, "--help"]
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Failed to run {' '.join(cmd)} (exit {proc.returncode})\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc.stdout


def parse_help_commands(help_text: str) -> set[str]:
    commands: set[str] = set()
    in_commands = False
    pattern = re.compile(r"^\s{2}([a-zA-Z0-9_-]+)\s{2,}")

    for line in help_text.splitlines():
        if line.strip() == "Commands:":
            in_commands = True
            continue
        if not in_commands:
            continue
        if not line.strip():
            continue
        match = pattern.match(line)
        if match:
            commands.add(match.group(1))
    return commands


def parse_help_options(help_text: str) -> set[str]:
    options: set[str] = set()
    in_options = False
    option_pattern = re.compile(r"^\s{2}(--[a-zA-Z0-9-]+)")

    for line in help_text.splitlines():
        if line.strip() == "Options:":
            in_options = True
            continue
        if line.strip() == "Commands:":
            in_options = False
            continue
        if not in_options:
            continue

        match = option_pattern.match(line)
        if match:
            options.add(match.group(1))

    return options


def ensure_contains(text: str, needle: str, errors: list[str], context: str) -> None:
    if needle not in text:
        errors.append(f"Missing '{needle}' in {context}")


def ensure_not_contains(text: str, needle: str, errors: list[str], context: str) -> None:
    if needle in text:
        errors.append(f"Unexpected stale marker '{needle}' present in {context}")


def ensure_regex(text: str, pattern: str, errors: list[str], context: str) -> None:
    if re.search(pattern, text, flags=re.MULTILINE) is None:
        errors.append(f"Missing pattern /{pattern}/ in {context}")


def main() -> int:
    errors: list[str] = []

    top_help = run_help("tagslut")
    intake_help = run_help("tagslut", "intake")
    index_help = run_help("tagslut", "index")
    decide_help = run_help("tagslut", "decide")
    execute_help = run_help("tagslut", "execute")
    verify_help = run_help("tagslut", "verify")
    report_help = run_help("tagslut", "report")
    auth_help = run_help("tagslut", "auth")
    dedupe_alias_help = run_help("dedupe")

    top_commands = parse_help_commands(top_help)
    intake_commands = parse_help_commands(intake_help)
    index_commands = parse_help_commands(index_help)
    decide_commands = parse_help_commands(decide_help)
    execute_commands = parse_help_commands(execute_help)
    verify_commands = parse_help_commands(verify_help)
    report_commands = parse_help_commands(report_help)
    auth_commands = parse_help_commands(auth_help)

    missing_top = sorted(TOP_CANONICAL_COMMANDS - top_commands)
    if missing_top:
        errors.append("Missing expected top-level commands: " + ", ".join(missing_top))
    stale_top = sorted(top_commands & (REMOVED_LEGACY_COMMANDS | REMOVED_COMPAT_COMMANDS))
    if stale_top:
        errors.append(
            "Removed top-level commands still present: " + ", ".join(stale_top)
        )
    dedupe_alias_commands = parse_help_commands(dedupe_alias_help)
    missing_dedupe_alias = sorted(TOP_CANONICAL_COMMANDS - dedupe_alias_commands)
    if missing_dedupe_alias:
        errors.append(
            "dedupe alias missing expected top-level commands: "
            + ", ".join(missing_dedupe_alias)
        )
    stale_dedupe_alias = sorted(
        dedupe_alias_commands & (REMOVED_LEGACY_COMMANDS | REMOVED_COMPAT_COMMANDS)
    )
    if stale_dedupe_alias:
        errors.append(
            "dedupe alias exposes removed top-level commands: "
            + ", ".join(stale_dedupe_alias)
        )

    missing_intake = sorted(INTAKE_REQUIRED_COMMANDS - intake_commands)
    if missing_intake:
        errors.append("Missing expected intake subcommands: " + ", ".join(missing_intake))

    missing_index = sorted(INDEX_REQUIRED_COMMANDS - index_commands)
    if missing_index:
        errors.append("Missing expected index subcommands: " + ", ".join(missing_index))

    missing_decide = sorted(DECIDE_REQUIRED_COMMANDS - decide_commands)
    if missing_decide:
        errors.append("Missing expected decide subcommands: " + ", ".join(missing_decide))

    missing_execute = sorted(EXECUTE_REQUIRED_COMMANDS - execute_commands)
    if missing_execute:
        errors.append("Missing expected execute subcommands: " + ", ".join(missing_execute))

    missing_verify = sorted(VERIFY_REQUIRED_COMMANDS - verify_commands)
    if missing_verify:
        errors.append("Missing expected verify subcommands: " + ", ".join(missing_verify))

    missing_report = sorted(REPORT_REQUIRED_COMMANDS - report_commands)
    if missing_report:
        errors.append("Missing expected report subcommands: " + ", ".join(missing_report))

    missing_auth = sorted(AUTH_REQUIRED_COMMANDS - auth_commands)
    if missing_auth:
        errors.append("Missing expected auth subcommands: " + ", ".join(missing_auth))

    script_surface = (DOCS_DIR / "SCRIPT_SURFACE.md").read_text(encoding="utf-8", errors="replace")
    surface_policy = (DOCS_DIR / "SURFACE_POLICY.md").read_text(encoding="utf-8", errors="replace")
    phase1_doc = (DOCS_DIR / "PHASE1_V3_DUAL_WRITE.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    phase2_doc = (DOCS_DIR / "PHASE2_POLICY_DECIDE.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    phase3_doc = (DOCS_DIR / "PHASE3_EXECUTOR.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    phase4_doc = (DOCS_DIR / "PHASE4_CLI_CONVERGENCE.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    phase5_doc = (DOCS_DIR / "PHASE5_LEGACY_DECOMMISSION.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    phase5_verify_doc = (DOCS_DIR / "PHASE5_VERIFICATION_2026-02-09.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    workflow_3_doc = (DOCS_DIR / "WORKFLOW_3_COMMANDS.md").read_text(
        encoding="utf-8",
        errors="replace",
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8", errors="replace")

    # SCRIPT_SURFACE requirements
    for canonical in sorted(TOP_CANONICAL_COMMANDS):
        ensure_contains(
            script_surface,
            f"poetry run tagslut {canonical} ...",
            errors,
            "docs/SCRIPT_SURFACE.md",
        )
    ensure_contains(script_surface, "Compatibility aliases:", errors, "docs/SCRIPT_SURFACE.md")
    ensure_contains(script_surface, "`dedupe`", errors, "docs/SCRIPT_SURFACE.md")
    ensure_contains(script_surface, "`taglslut`", errors, "docs/SCRIPT_SURFACE.md")
    ensure_contains(
        script_surface, "docs/PHASE1_V3_DUAL_WRITE.md", errors, "docs/SCRIPT_SURFACE.md"
    )
    ensure_contains(
        script_surface, "docs/PHASE2_POLICY_DECIDE.md", errors, "docs/SCRIPT_SURFACE.md"
    )
    ensure_contains(
        script_surface, "docs/PHASE3_EXECUTOR.md", errors, "docs/SCRIPT_SURFACE.md"
    )
    ensure_contains(
        script_surface, "docs/PHASE4_CLI_CONVERGENCE.md", errors, "docs/SCRIPT_SURFACE.md"
    )
    ensure_contains(
        script_surface, "docs/PHASE5_LEGACY_DECOMMISSION.md", errors, "docs/SCRIPT_SURFACE.md"
    )

    for removed in sorted(REMOVED_LEGACY_COMMANDS | REMOVED_COMPAT_COMMANDS):
        ensure_not_contains(
            script_surface, f"`dedupe {removed}`", errors, "docs/SCRIPT_SURFACE.md"
        )

    # SURFACE_POLICY requirements
    ensure_contains(
        surface_policy,
        "## Canonical Surface (Use For New Work)",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "## Transitional Surface",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "validate_v3_dual_write_parity.py",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "lint_policy_profiles.py",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "docs/PHASE2_POLICY_DECIDE.md",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "docs/PHASE3_EXECUTOR.md",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "docs/PHASE4_CLI_CONVERGENCE.md",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "docs/PHASE5_LEGACY_DECOMMISSION.md",
        errors,
        "docs/SURFACE_POLICY.md",
    )
    ensure_contains(
        surface_policy,
        "Retired in Phase 5",
        errors,
        "docs/SURFACE_POLICY.md",
    )

    # PHASE1 runbook requirements
    ensure_contains(
        phase1_doc,
        "DEDUPE_V3_DUAL_WRITE=1",
        errors,
        "docs/PHASE1_V3_DUAL_WRITE.md",
    )
    ensure_contains(
        phase1_doc,
        "backfill_v3_identity_links.py",
        errors,
        "docs/PHASE1_V3_DUAL_WRITE.md",
    )
    ensure_contains(
        phase1_doc,
        "validate_v3_dual_write_parity.py",
        errors,
        "docs/PHASE1_V3_DUAL_WRITE.md",
    )

    # PHASE2 runbook requirements
    ensure_contains(
        phase2_doc,
        "build_deterministic_plan",
        errors,
        "docs/PHASE2_POLICY_DECIDE.md",
    )
    ensure_contains(
        phase2_doc,
        "dj_strict",
        errors,
        "docs/PHASE2_POLICY_DECIDE.md",
    )
    ensure_contains(
        phase2_doc,
        "lint_policy_profiles.py",
        errors,
        "docs/PHASE2_POLICY_DECIDE.md",
    )

    # PHASE3 runbook requirements
    ensure_contains(
        phase3_doc,
        "execute_move",
        errors,
        "docs/PHASE3_EXECUTOR.md",
    )
    ensure_contains(
        phase3_doc,
        "record_move_receipt",
        errors,
        "docs/PHASE3_EXECUTOR.md",
    )
    ensure_contains(
        phase3_doc,
        "update_legacy_path_with_receipt",
        errors,
        "docs/PHASE3_EXECUTOR.md",
    )

    # PHASE4 runbook requirements
    ensure_contains(
        phase4_doc,
        "intake/index/decide/execute/verify/report/auth",
        errors,
        "docs/PHASE4_CLI_CONVERGENCE.md",
    )
    ensure_contains(
        phase4_doc,
        "dedupe mgmt",
        errors,
        "docs/PHASE4_CLI_CONVERGENCE.md",
    )
    ensure_contains(
        phase4_doc,
        "dedupe metadata",
        errors,
        "docs/PHASE4_CLI_CONVERGENCE.md",
    )

    # PHASE5 runbook requirements
    ensure_contains(
        phase5_doc,
        "P5-LEG-001",
        errors,
        "docs/PHASE5_LEGACY_DECOMMISSION.md",
    )
    ensure_contains(
        phase5_doc,
        "P5-COMP-001",
        errors,
        "docs/PHASE5_LEGACY_DECOMMISSION.md",
    )
    ensure_contains(
        phase5_doc,
        "July 3, 2026",
        errors,
        "docs/PHASE5_LEGACY_DECOMMISSION.md",
    )
    ensure_contains(
        phase5_verify_doc,
        "Phase 5 decommission is complete",
        errors,
        "docs/PHASE5_VERIFICATION_2026-02-09.md",
    )

    # README minimal workflow checks
    required_readme_phrases = [
        "docs/WORKFLOW_3_COMMANDS.md",
        "tools/get <beatport-url>",
        "tools/get-sync <beatport-url>",
        "tools/get-report <beatport-url>",
        "tagslut",
        "dedupe",
    ]
    for phrase in required_readme_phrases:
        ensure_contains(readme, phrase, errors, "README.md")

    # 3-command workflow doc checks
    required_workflow_phrases = [
        "tools/get <beatport-url>",
        "tools/get-sync <beatport-url>",
        "tools/get-report <beatport-url>",
    ]
    for phrase in required_workflow_phrases:
        ensure_contains(workflow_3_doc, phrase, errors, "docs/WORKFLOW_3_COMMANDS.md")

    if errors:
        print("ERRORS:")
        for issue in errors:
            print(f"- {issue}")
        return 1

    print("OK: CLI/docs consistency checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
