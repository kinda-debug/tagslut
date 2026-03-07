#!/usr/bin/env python3
"""Check consistency between live CLI help and key docs.

Usage:
  python scripts/check_cli_docs_consistency.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"

TOP_CANONICAL_COMMANDS = {"intake", "index", "decide", "execute", "verify", "report", "auth"}
REMOVED_LEGACY_COMMANDS = {"scan", "recommend", "apply", "promote", "quarantine"}
REMOVED_COMPAT_COMMANDS = {"mgmt", "metadata", "recover", "m"}
INTAKE_REQUIRED_COMMANDS = {"run", "prefilter", "process-root"}
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


def load_project_scripts(pyproject_path: Path) -> set[str]:
    if not pyproject_path.is_file():
        return set()
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    if not isinstance(scripts, dict):
        return set()
    return {str(name) for name in scripts.keys()}


def has_dedupe_deprecation_marker(surface_policy_text: str) -> bool:
    return re.search(
        r"(?is)`dedupe`.*deprecated alias for `tagslut`.*still shipped",
        surface_policy_text,
    ) is not None


def check_dedupe_docs_alignment(
    *,
    surface_policy_text: str,
    project_scripts: set[str],
    errors: list[str],
) -> None:
    dedupe_exists = "dedupe" in project_scripts
    docs_mark_deprecated = has_dedupe_deprecation_marker(surface_policy_text)
    docs_has_horizon = "2026-06-01" in surface_policy_text

    if dedupe_exists:
        if not docs_mark_deprecated:
            errors.append(
                "`dedupe` console script exists, but docs/SURFACE_POLICY.md does not mark it as "
                "a deprecated alias for `tagslut` that is still shipped."
            )
        if not docs_has_horizon:
            errors.append(
                "`dedupe` console script exists, but docs/SURFACE_POLICY.md does not mention "
                "the deprecation horizon date (2026-06-01)."
            )
        return

    if docs_mark_deprecated or docs_has_horizon:
        errors.append(
            "docs/SURFACE_POLICY.md describes shipped/deprecated `dedupe`, "
            "but pyproject.toml has no `dedupe` console script."
        )


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

    operations_doc = (DOCS_DIR / "OPERATIONS.md").read_text(encoding="utf-8", errors="replace")
    surface_policy_doc = (DOCS_DIR / "SURFACE_POLICY.md").read_text(encoding="utf-8", errors="replace")
    project_scripts = load_project_scripts(PROJECT_ROOT / "pyproject.toml")
    # Phase runbook docs have been archived — read if present, skip checks otherwise
    def _read_optional(name: str) -> str:
        p = DOCS_DIR / name
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""

    phase1_doc = _read_optional("PHASE1_V3_DUAL_WRITE.md")
    phase2_doc = _read_optional("PHASE2_POLICY_DECIDE.md")
    phase3_doc = _read_optional("PHASE3_EXECUTOR.md")
    phase4_doc = _read_optional("PHASE4_CLI_CONVERGENCE.md")
    phase5_doc = _read_optional("PHASE5_LEGACY_DECOMMISSION.md")
    phase5_verify_doc = _read_optional("PHASE5_VERIFICATION_2026-02-09.md")
    workflow_3_doc = _read_optional("WORKFLOW_3_COMMANDS.md")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8", errors="replace")
    workflows_doc = (DOCS_DIR / "WORKFLOWS.md").read_text(encoding="utf-8", errors="replace")

    # SCRIPT_SURFACE requirements (now consolidated into docs/OPERATIONS.md)
    for canonical in sorted(TOP_CANONICAL_COMMANDS):
        ensure_contains(
            operations_doc,
            f"poetry run tagslut {canonical} ...",
            errors,
            "docs/OPERATIONS.md",
        )
    ensure_contains(operations_doc, "Compatibility aliases:", errors, "docs/OPERATIONS.md")
    # Phase runbook doc references removed — docs archived during decommission

    for removed in sorted(REMOVED_LEGACY_COMMANDS | REMOVED_COMPAT_COMMANDS):
        ensure_not_contains(
            operations_doc, f"`dedupe {removed}`", errors, "docs/OPERATIONS.md"
        )

    # SURFACE_POLICY requirements (now consolidated into docs/OPERATIONS.md)
    ensure_contains(
        operations_doc,
        "## Canonical Surface (Use For New Work)",
        errors,
        "docs/OPERATIONS.md",
    )
    ensure_contains(
        operations_doc,
        "## Transitional Surface",
        errors,
        "docs/OPERATIONS.md",
    )
    ensure_contains(
        operations_doc,
        "validate_v3_dual_write_parity.py",
        errors,
        "docs/OPERATIONS.md",
    )
    ensure_contains(
        operations_doc,
        "lint_policy_profiles.py",
        errors,
        "docs/OPERATIONS.md",
    )
    check_dedupe_docs_alignment(
        surface_policy_text=surface_policy_doc,
        project_scripts=project_scripts,
        errors=errors,
    )
    # Phase runbook doc cross-references removed — docs archived during decommission

    # README minimal workflow checks
    required_readme_phrases = [
        "tagslut",
        "tools/get <provider-url>",
    ]
    for phrase in required_readme_phrases:
        ensure_contains(readme, phrase, errors, "README.md")

    # Active downloader workflow docs
    required_active_workflow_phrases = [
        "tools/get \"https://www.beatport.com/release/.../...\"",
        "tools/get \"https://tidal.com/browse/album/...\"",
        "tools/get-intake",
        "deprecated Beatport compatibility alias",
    ]
    for phrase in required_active_workflow_phrases:
        ensure_contains(workflows_doc, phrase, errors, "docs/WORKFLOWS.md")

    # Historical 3-command workflow doc checks
    required_workflow_phrases = [
        "tools/get <beatport-url>",
        "tools/get-sync <beatport-url>",
        "tools/get-report <beatport-url>",
    ]
    if workflow_3_doc:
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
