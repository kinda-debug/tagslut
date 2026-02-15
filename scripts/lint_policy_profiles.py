#!/usr/bin/env python3
"""Lint policy profiles under config/policies (or a custom path)."""

from __future__ import annotations

import argparse
from pathlib import Path

from tagslut.policy import lint_policy_profile, list_policy_profiles, load_policy_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint tagslut policy profiles")
    parser.add_argument(
        "--policy-dir",
        type=Path,
        help="Directory containing policy YAML files (default: config/policies)",
    )
    args = parser.parse_args()

    profiles = list_policy_profiles(policy_dir=args.policy_dir)
    if not profiles:
        print("ERROR: no policy profiles found")
        return 1

    errors: list[str] = []
    for name in profiles:
        profile = load_policy_profile(name, policy_dir=args.policy_dir)
        issues = lint_policy_profile(profile)
        if issues:
            errors.extend(issues)

    if errors:
        print("ERRORS:")
        for issue in errors:
            print(f"- {issue}")
        return 1

    print(f"OK: policy lint passed ({len(profiles)} profiles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
