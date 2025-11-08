"""Compatibility command-line entry points for legacy scripts.

The original repository exposed a collection of ad-hoc scripts (e.g.
``analyze_quarantine_subdir.py``) that users wired into cron jobs and shell
aliases.  The modern packaging layout only installs the :mod:`dedupe`
package, which meant the historical entry points defined in
``pyproject.toml`` no longer resolved to importable modules.  This module
implements thin, typed wrappers that replicate the legacy behaviour while
delegating to :mod:`dedupe.quarantine`.

Each function here mirrors a legacy ``main`` function so that we can reuse the
same logic from both the compatibility scripts under ``scripts/`` and the
packaged console entry points.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import quarantine


def _build_directory_parser(
    description: str,
    *,
    include_workers: bool = False,
) -> argparse.ArgumentParser:
    """Create an :class:`argparse.ArgumentParser` for quarantine style CLIs."""

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--dir", required=True, type=Path, help="Directory to scan")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional CSV output path",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of files processed",
    )
    if include_workers:
        parser.add_argument(
            "--workers",
            type=int,
            default=4,
            help="Number of worker threads to use",
        )
    return parser


def _emit_rows(
    rows: Iterable[dict],
    *,
    output: Optional[Path],
    fieldnames: Optional[Sequence[str]] = None,
) -> None:
    """Write *rows* either to ``output`` or to standard output."""

    if output is None:
        for row in rows:
            print(row)
        return

    if fieldnames is None:
        raise ValueError("fieldnames must be provided when writing to a file")

    quarantine.write_rows_csv(list(fieldnames), rows, output)
    print(f"Wrote {output}")


def analyse_quarantine_subdir_main(argv: Optional[list[str]] = None) -> int:
    """Entry point replicating ``analyze_quarantine_subdir.py`` behaviour."""

    parser = _build_directory_parser(
        "Analyse quarantine directory with ffprobe/fpcalc",
        include_workers=True,
    )
    args = parser.parse_args(argv)

    directory: Path = args.dir
    if not directory.is_dir():
        parser.error(f"Not a directory: {directory}")

    rows = quarantine.analyse_quarantine(
        directory,
        limit=args.limit,
        workers=args.workers,
    )

    if args.out is None:
        for row in rows:
            print(row)
    else:
        quarantine.write_analysis_csv(rows, args.out)
        print(f"Wrote {args.out}")
    return 0


def simple_quarantine_scan_main(argv: Optional[list[str]] = None) -> int:
    """Entry point replicating ``simple_quarantine_scan.py`` behaviour."""

    parser = _build_directory_parser("Simple quarantine metadata scan")
    args = parser.parse_args(argv)

    directory: Path = args.dir
    if not directory.is_dir():
        parser.error(f"Not a directory: {directory}")

    rows = quarantine.simple_scan(directory, limit=args.limit)
    _emit_rows(
        rows,
        output=args.out,
        fieldnames=["path", "size", "duration"],
    )
    return 0


def detect_playback_length_issues_main(argv: Optional[list[str]] = None) -> int:
    """Entry point replicating ``detect_playback_length_issues.py`` behaviour."""

    parser = _build_directory_parser("Detect playback duration mismatches")
    args = parser.parse_args(argv)

    directory: Path = args.dir
    if not directory.is_dir():
        parser.error(f"Not a directory: {directory}")

    rows = quarantine.detect_playback_issues(directory, limit=args.limit)
    _emit_rows(
        rows,
        output=args.out,
        fieldnames=["path", "reported", "decoded", "ratio"],
    )
    return 0


__all__ = [
    "analyse_quarantine_subdir_main",
    "detect_playback_length_issues_main",
    "simple_quarantine_scan_main",
]

