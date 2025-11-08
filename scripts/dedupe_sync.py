"""Compatibility wrapper around :mod:`dedupe.sync`."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from dedupe.health import CommandHealthChecker
from dedupe.sync import (
    DEFAULT_DEDUPE_LISTING,
    HealthMode,
    SyncOutcome,
    SyncSummary,
    discover_dedupe_root,
    parse_library_root,
    run_sync,
)

__all__ = [
    "DEFAULT_DEDUPE_LISTING",
    "CommandHealthChecker",
    "HealthMode",
    "SyncOutcome",
    "SyncSummary",
    "discover_dedupe_root",
    "parse_library_root",
    "run_cli",
    "run_sync",
    "main",
]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensure the healthiest copy of each staged track lives in the main library",
    )
    parser.add_argument(
        "--library-root",
        type=Path,
        default=parse_library_root(Path("config.toml")),
        help="Root directory of the main music library",
    )
    parser.add_argument(
        "--dedupe-root",
        type=Path,
        default=None,
        help="Override dedupe directory (defaults to path discovered via DEDUPE_DIR.txt)",
    )
    parser.add_argument(
        "--dedupe-listing",
        type=Path,
        default=DEFAULT_DEDUPE_LISTING,
        help="Path to DEDUPE_DIR.txt listing file used to discover dedupe directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned actions without modifying any files",
    )
    parser.add_argument(
        "--health-check",
        choices=[mode.value for mode in HealthMode],
        default=HealthMode.AUTO.value,
        help="Enable automatic health checks (default) or disable them",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Health check timeout in seconds for external commands",
    )
    parser.add_argument(
        "--verify-library",
        action="store_true",
        help="Decode every track in the library after sync to confirm full playback",
    )
    return parser


def run_cli(args: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    ns = parser.parse_args(args=args)

    if ns.verify_library and ns.health_check == HealthMode.NONE.value:
        parser.error("--verify-library requires active health checks; remove --health-check none")

    summary = run_sync(
        library_root=ns.library_root,
        dedupe_root=ns.dedupe_root,
        dedupe_listing=ns.dedupe_listing,
        health_mode=HealthMode(ns.health_check),
        timeout=ns.timeout,
        dry_run=ns.dry_run,
        verify_library=ns.verify_library,
    )

    for outcome in summary.outcomes:
        print(f"{outcome.action:>12}  {outcome.relative_path}  {outcome.message}")
    summary_line = ", ".join(
        f"{action}: {count}" for action, count in sorted(summary.counts.items())
    )
    print(f"Processed {len(summary.outcomes)} files — {summary_line}")

    if summary.audit_results is not None:
        unhealthy = [
            result
            for result in summary.audit_results
            if not result.exists or result.healthy is False
        ]
        unknown = [
            result
            for result in summary.audit_results
            if result.exists and result.healthy is None
        ]
        for result in unhealthy:
            note = result.note or "playback verification failed"
            print(f"   UNHEALTHY  {result.relative_path}  {note}")
        for result in unknown:
            note = result.note or "health unknown"
            print(f"   UNKNOWN    {result.relative_path}  {note}")
        print(
            "Library audit: "
            f"{len(summary.audit_results)} files checked, "
            f"{len(unhealthy)} unhealthy, "
            f"{len(unknown)} unknown health"
        )

    return 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
