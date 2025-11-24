"""Command-line interface for the dedupe toolkit."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, Optional

from . import manifest, matcher, scanner, utils

LOGGER = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _path(value: str) -> Path:
    """Return a NFC-normalised absolute path from a CLI argument."""

    return Path(utils.normalise_path(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dedupe",
        description="Audio recovery toolkit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging output",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan-library",
        help="Scan an audio library and write metadata to SQLite",
    )
    scan_parser.add_argument(
        "--root",
        type=_path,
        required=True,
        help="Root directory to scan",
    )
    scan_parser.add_argument(
        "--out",
        type=_path,
        required=True,
        help="SQLite database path to populate",
    )
    scan_parser.add_argument(
        "--fingerprints",
        action="store_true",
        help=(
            "Capture optional Chromaprint fingerprints (requires fpcalc; "
            "skipped automatically when unavailable)"
        ),
    )
    scan_parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume a previous scan by skipping unchanged files present in "
            "the database (size + mtime check)"
        ),
    )
    scan_parser.add_argument(
        "--resume-safe",
        action="store_true",
        help=(
            "Resume a previous scan but skip entire batches when any file "
            "matches the database by size + mtime"
        ),
    )
    scan_parser.add_argument(
        "--progress",
        action="store_true",
        help="Show a progress bar during scanning",
    )

    match_parser = subparsers.add_parser(
        "match",
        help="Match scanned library metadata with recovery candidates",
    )
    match_parser.add_argument(
        "--library",
        type=_path,
        required=True,
        help="Library SQLite database",
    )
    match_parser.add_argument(
        "--recovered",
        type=_path,
        required=True,
        help="Recovered files SQLite database",
    )
    match_parser.add_argument(
        "--out",
        type=_path,
        required=True,
        help="CSV file to write match results",
    )

    manifest_parser = subparsers.add_parser(
        "generate-manifest",
        help="Create a recovery manifest from match results",
    )
    manifest_parser.add_argument(
        "--matches",
        type=_path,
        required=True,
        help="CSV file produced by the match command",
    )
    manifest_parser.add_argument(
        "--out",
        type=_path,
        required=True,
        help="Destination CSV for the recovery manifest",
    )

    return parser


def _command_scan(args: argparse.Namespace) -> int:
    config = scanner.ScanConfig(
        root=args.root,
        database=args.out,
        include_fingerprints=args.fingerprints,
        resume=getattr(args, "resume", False),
        resume_safe=getattr(args, "resume_safe", False),
        show_progress=getattr(args, "progress", False),
    )
    total = scanner.scan_library(config)
    LOGGER.info("Indexed %s files", total)
    return 0


def _command_match(args: argparse.Namespace) -> int:
    matcher.match_databases(args.library, args.recovered, args.out)
    return 0


def _command_manifest(args: argparse.Namespace) -> int:
    manifest.generate_manifest(args.matches, args.out)
    return 0


COMMAND_HANDLERS = {
    "scan-library": _command_scan,
    "match": _command_match,
    "generate-manifest": _command_manifest,
}


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()

    # Allow callers to place global options (like --verbose) either before
    # or after the subcommand. argparse supports `parse_intermixed_args`
    # (Python 3.8+) which accepts intermixed options; fall back to the
    # regular `parse_args` when it's not available.
    import sys

    arglist = list(argv) if argv is not None else list(sys.argv[1:])

    # Normalize placement of a small set of known global options so users can
    # place them after the subcommand. This is a pragmatic, minimal shim that
    # moves `--verbose` before the subparser if necessary.
    if arglist:
        # index of first positional (likely the subcommand)
        first_pos = None
        for i, a in enumerate(arglist):
            if not a.startswith("-"):
                first_pos = i
                break
        if first_pos is not None:
            globals_to_move = ["--verbose"]
            for opt in globals_to_move:
                # if the option appears after the subcommand, move it to front
                if opt in arglist[first_pos + 1:]:
                    while opt in arglist:
                        arglist.remove(opt)
                    arglist.insert(0, opt)
    if hasattr(parser, "parse_intermixed_args"):
        try:
            args = parser.parse_intermixed_args(arglist)
        except (TypeError, ValueError):
            # Some argparse versions or complex subparser setups can raise
            # TypeError/ValueError when attempting intermixed parsing. Fall
            # back to the traditional parse_args behaviour.
            args = parser.parse_args(arglist)
    else:
        args = parser.parse_args(arglist)

    _configure_logging(args.verbose)
    handler = COMMAND_HANDLERS[args.command]
    return handler(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
