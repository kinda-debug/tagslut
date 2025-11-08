"""Unified command-line interface for the dedupe toolkit."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional

from . import health, quarantine, sync


def _add_common_directory_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("directory", type=Path, help="Directory of quarantine files")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of files to process",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional CSV output path",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dedupe", description="Unified FLAC dedupe toolkit")
    # Global debug flag to assist with diagnosing invocation/runtime issues
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output to assist troubleshooting",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    health.build_health_parser(subparsers)

    sync_parser = subparsers.add_parser(
        "sync", help="Synchronise staged duplicates back into the library"
    )
    sync_parser.add_argument(
        "--library-root",
        type=Path,
        default=sync.parse_library_root(Path("config.toml")),
        help="Path to the main music library",
    )
    sync_parser.add_argument(
        "--dedupe-root",
        type=Path,
        default=None,
        help="Override the dedupe directory (defaults to discovery via DEDUPE_DIR.txt)",
    )
    sync_parser.add_argument(
        "--dedupe-listing",
        type=Path,
        default=sync.DEFAULT_DEDUPE_LISTING,
        help="Path to DEDUPE_DIR.txt for dedupe directory discovery",
    )
    sync_parser.add_argument(
        "--health-check",
        choices=[mode.value for mode in sync.HealthMode],
        default=sync.HealthMode.AUTO.value,
        help="Health check mode (auto or none)",
    )
    sync_parser.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="Health check timeout in seconds",
    )
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show actions without modifying the filesystem",
    )
    sync_parser.add_argument(
        "--verify-library",
        action="store_true",
        help="Verify playback health across the entire library after sync",
    )

    quarantine_parser = subparsers.add_parser(
        "quarantine",
        help="Analyse quarantine directories",
    )
    quarantine_sub = quarantine_parser.add_subparsers(dest="quarantine_command", required=True)

    analyse_parser = quarantine_sub.add_parser(
        "inspect",
        help="Capture detailed ffprobe/fingerprint metadata",
        aliases=["analyse"],
    )
    _add_common_directory_argument(analyse_parser)
    analyse_parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of worker threads for analysis",
    )

    scan_parser = quarantine_sub.add_parser(
        "inventory",
        help="Record basic size/duration metadata",
        aliases=["scan"],
    )
    _add_common_directory_argument(scan_parser)

    length_parser = quarantine_sub.add_parser(
        "duration",
        help="Detect playback duration mismatches",
        aliases=["length"],
    )
    _add_common_directory_argument(length_parser)

    return parser


def _write_rows(rows: Iterable[dict], output: Optional[Path], fieldnames: Iterable[str]) -> None:
    if output is None:
        for row in rows:
            print(row)
        return
    quarantine.write_rows_csv(list(fieldnames), rows, output)
    print(f"Wrote {output}")


def run_cli(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()

    # Allow `--debug` to appear anywhere (before or after the sub-command).
    # argparse normally treats options after a subparser as belonging to the
    # subparser so a user placing --debug at the end would cause an
    # "unrecognized arguments" error. Detect and strip it here so it's
    # recognised regardless of position.
    raw_argv = list(argv) if argv is not None else None
    search_space = raw_argv if raw_argv is not None else __import__("sys").argv[1:]
    debug = "--debug" in search_space
    if raw_argv is not None and "--debug" in raw_argv:
        # remove all occurrences so argparse won't complain
        raw_argv = [a for a in raw_argv if a != "--debug"]
        args = parser.parse_args(raw_argv)
    else:
        args = parser.parse_args(raw_argv)

    if args.command == "health":
        if args.health_command == "scan":
            health_summary = health.scan_directory(
                args.root,
                log_path=args.log,
                workers=args.workers,
            )
        else:
            health_summary = health.check_spreadsheet(
                args.spreadsheet,
                log_path=args.log,
                workers=args.workers,
            )
        print(health_summary.formatted_counts())
        print(f"Log written to {health_summary.log_path}")
        return 0

    if args.command == "sync":
        mode = sync.HealthMode(args.health_check)
        sync_summary = sync.run_sync(
            library_root=args.library_root,
            dedupe_root=args.dedupe_root,
            dedupe_listing=args.dedupe_listing,
            health_mode=mode,
            timeout=args.timeout,
            dry_run=args.dry_run,
            verify_library=args.verify_library,
        )
        for outcome in sync_summary.outcomes:
            print(f"{outcome.action:>12}  {outcome.relative_path}  {outcome.message}")
        summary_line = ", ".join(
            f"{action}: {count}" for action, count in sorted(sync_summary.counts.items())
        )
        if not summary_line:
            summary_line = "no actions performed"
        print(f"Processed {len(sync_summary.outcomes)} files — {summary_line}")
        if sync_summary.audit_results is not None:
            unhealthy = [
                r for r in sync_summary.audit_results if not r.exists or r.healthy is False
            ]
            unknown = [
                r for r in sync_summary.audit_results if r.exists and r.healthy is None
            ]
            for result in unhealthy:
                note = result.note or "playback verification failed"
                print(f"   UNHEALTHY  {result.relative_path}  {note}")
            for result in unknown:
                note = result.note or "health unknown"
                print(f"   UNKNOWN    {result.relative_path}  {note}")
            print(
                "Library audit: "
                f"{len(sync_summary.audit_results)} files checked, "
                f"{len(unhealthy)} unhealthy, "
                f"{len(unknown)} unknown health"
            )
        return 0

    if args.command == "quarantine":
        directory: Path = args.directory
        if not directory.is_dir():
            parser.error(f"{directory} is not a directory")
        if debug:
            try:
                file_count = sum(1 for _ in directory.rglob("*.flac"))
            except Exception:
                file_count = 0
            print(f"DEBUG: cwd={Path.cwd()}")
            print(f"DEBUG: found {file_count} .flac files in {directory}")
            if args.output:
                try:
                    print(f"DEBUG: output path resolved to {args.output.resolve()}")
                except Exception:
                    print(f"DEBUG: output path (raw) = {args.output}")
        limit = args.limit

        if args.quarantine_command == "inspect":
            rows = quarantine.analyse_quarantine(directory, limit=limit, workers=args.workers)
            if args.output:
                quarantine.write_analysis_csv(rows, args.output)
                print(f"Wrote {args.output}")
            else:
                for row in rows:
                    print(row)
            return 0

        if args.quarantine_command == "inventory":
            rows = quarantine.simple_scan(directory, limit=limit)
            fieldnames = ["path", "size", "duration"]
            _write_rows(rows, args.output, fieldnames)
            return 0

        if args.quarantine_command == "duration":
            rows = quarantine.detect_playback_issues(directory, limit=limit)
            fieldnames = ["path", "reported", "decoded", "ratio"]
            _write_rows(rows, args.output, fieldnames)
            return 0

    raise AssertionError("Unhandled command")


def main() -> int:
    return run_cli()


__all__ = ["build_parser", "main", "run_cli"]
