"""Command-line interface for the dedupe toolkit."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, Optional

from . import (
    deduper,
    healthcheck,
    healthscore,
    hrm_relocation,
    manifest,
    matcher,
    scanner,
    utils,
)
from tools.db_upgrade import upgrade_db

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    """Configure basic logging output based on the ``--verbose`` flag."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _path(value: str) -> Path:
    """Return a NFC-normalised absolute path from a CLI argument."""

    return Path(utils.normalise_path(value))


def _existing_dir(value: str) -> Path:
    """Validate that ``value`` is an existing directory path."""

    path = _path(value)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"Directory not found: {path}")
    return path


def _existing_file(value: str) -> Path:
    """Validate that ``value`` is an existing file path."""

    path = _path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"File not found: {path}")
    return path


def _output_path(value: str) -> Path:
    """Validate that ``value`` points to a writable file location.

    Parent directories may be created later by the caller, but an existing
    parent must be a directory.
    """

    path = _path(value)
    if path.is_dir():
        raise argparse.ArgumentTypeError(
            f"Expected a file path but received a directory: {path}"
        )
    parent = path.parent if path.parent != Path("") else Path(".")
    if parent.exists() and not parent.is_dir():
        raise argparse.ArgumentTypeError(
            f"Parent path for output is not a directory: {parent}"
        )
    return path


def _non_negative_float(value: str) -> float:
    """Return a float value that must be zero or greater."""

    try:
        parsed = float(value)
    except ValueError as exc:  # pragma: no cover - argparse guards
        raise argparse.ArgumentTypeError(str(exc)) from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("Value must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser for the dedupe CLI."""
    parser = argparse.ArgumentParser(
        prog="dedupe",
        description="Audio recovery and reconciliation toolkit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging for troubleshooting.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan-library",
        help="Scan a library directory and write audio metadata to SQLite.",
    )
    scan_parser.add_argument(
        "--root",
        type=_existing_dir,
        required=True,
        help="Library root directory to scan (must exist).",
    )
    scan_parser.add_argument(
        "--out",
        type=_output_path,
        required=True,
        help="SQLite database to populate with scan results.",
    )
    scan_parser.add_argument(
        "--fingerprints",
        action="store_true",
        help=(
            "Capture Chromaprint fingerprints when fpcalc is available; skipped "
            "automatically otherwise."
        ),
    )
    scan_parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Skip files already recorded in the database when size and mtime "
            "match."
        ),
    )
    scan_parser.add_argument(
        "--resume-safe",
        action="store_true",
        help=(
            "Skip entire batches if any file matches existing records by size "
            "and mtime."
        ),
    )
    scan_parser.add_argument(
        "--progress",
        action="store_true",
        help="Display a progress bar during scanning.",
    )

    match_parser = subparsers.add_parser(
        "match",
        help="Match a scanned library database with recovered files.",
    )
    match_parser.add_argument(
        "--library",
        type=_existing_file,
        required=True,
        help="Existing library SQLite database path.",
    )
    match_parser.add_argument(
        "--recovered",
        type=_existing_file,
        required=True,
        help="Existing recovered files SQLite database path.",
    )
    match_parser.add_argument(
        "--out",
        type=_output_path,
        required=True,
        help="CSV file to write match results (parent directory must exist).",
    )

    manifest_parser = subparsers.add_parser(
        "generate-manifest",
        help="Create a recovery manifest CSV from match results.",
    )
    manifest_parser.add_argument(
        "--matches",
        type=_existing_file,
        required=True,
        help="CSV file produced by the match command.",
    )
    manifest_parser.add_argument(
        "--out",
        type=_output_path,
        required=True,
        help="Destination CSV path for the generated manifest.",
    )

    rescan_parser = subparsers.add_parser(
        "rescan-missing",
        help="Ingest only FLAC files missing from an existing database.",
    )
    rescan_parser.add_argument(
        "--root",
        type=_existing_dir,
        required=True,
        help="Root directory to scan for missing FLAC files.",
    )
    rescan_parser.add_argument(
        "--out",
        type=_output_path,
        required=True,
        help="Target library database; created if it does not exist.",
    )
    rescan_parser.add_argument(
        "--fingerprints",
        action="store_true",
        help="Compute fingerprints for missing files when fpcalc is available.",
    )

    health_parser = subparsers.add_parser(
        "health",
        help="Score a single FLAC file and print the report.",
    )
    health_parser.add_argument(
        "path",
        type=_existing_file,
        help="Path to a FLAC file to evaluate.",
    )

    health_batch_parser = subparsers.add_parser(
        "health-batch",
        help="Score each FLAC path listed in a UTF-8 text file.",
    )
    health_batch_parser.add_argument(
        "list_path",
        type=_existing_file,
        help="Text file containing one FLAC path per line.",
    )

    healthscore_parser = subparsers.add_parser(
        "healthscore",
        help="Compute read-only health scores for one or more FLAC files.",
    )
    healthscore_parser.add_argument(
        "paths",
        nargs="+",
        type=_existing_file,
        help="One or more FLAC files to score.",
    )
    healthscore_parser.set_defaults(func=run_healthscore)

    dedupe_parser = subparsers.add_parser(
        "dedupe-db",
        help="Mark canonical files and report duplicate groups in a database.",
    )
    dedupe_parser.add_argument(
        "database",
        type=_existing_file,
        help="Library database to deduplicate.",
    )
    dedupe_parser.add_argument(
        "--report",
        type=_output_path,
        help="Optional JSON file to write a duplicate report.",
    )

    hrm_parser = subparsers.add_parser(
        "hrm-move",
        help="Move canonical, healthy files into the HRM structure.",
    )
    hrm_parser.add_argument(
        "database",
        type=_existing_file,
        help="Library database containing canonical selections.",
    )
    hrm_parser.add_argument(
        "--root",
        type=_existing_dir,
        required=True,
        help="Destination HRM root directory (must exist).",
    )

    hrm_relocate_parser = subparsers.add_parser(
        "relocate-hrm",
        help="Relocate healthy files into the HRM hierarchy.",
    )
    hrm_relocate_parser.add_argument(
        "--db",
        type=_existing_file,
        required=True,
        help="Source library database with health data.",
    )
    hrm_relocate_parser.add_argument(
        "--root",
        type=_existing_dir,
        required=True,
        help="Root directory containing the source audio files.",
    )
    hrm_relocate_parser.add_argument(
        "--hrm-root",
        type=_existing_dir,
        required=True,
        help="HRM root directory where files will be relocated.",
    )
    hrm_relocate_parser.add_argument(
        "--min-score",
        type=_non_negative_float,
        default=10,
        help="Minimum total health score required for relocation (default: 10).",
    )

    upgrade_parser = subparsers.add_parser(
        "upgrade-db",
        help="Upgrade a legacy per-volume database to the unified schema.",
    )
    upgrade_parser.add_argument(
        "legacy_db",
        type=_existing_file,
        help="Path to the legacy per-volume SQLite database.",
    )
    upgrade_parser.add_argument(
        "out_db",
        type=_output_path,
        help="Destination path for the upgraded database.",
    )
    upgrade_parser.set_defaults(func=run_upgrade_db)

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
    logger.info("Indexed %s files", total)
    return 0


def _command_match(args: argparse.Namespace) -> int:
    matcher.match_databases(args.library, args.recovered, args.out)
    return 0


def _command_manifest(args: argparse.Namespace) -> int:
    manifest.generate_manifest(args.matches, args.out)
    return 0


def _command_rescan_missing(args: argparse.Namespace) -> int:
    """Ingest only FLAC files missing from the target database."""

    result = scanner.rescan_missing(
        root=args.root,
        database=args.out,
        include_fingerprints=args.fingerprints,
    )
    logger.info(
        "Missing: %s | Ingested: %s | Unreadable: %s | Corrupt: %s",
        len(result["missing"]),
        len(result["ingested"]),
        len(result["unreadable"]),
        len(result["corrupt"]),
    )
    return 0


def _command_health(args: argparse.Namespace) -> int:
    """Score a single FLAC file and print the result."""

    report = healthcheck.score_file(args.path)
    print(report)
    return 0


def _command_health_batch(args: argparse.Namespace) -> int:
    """Score every path listed in a text file."""

    with open(args.list_path, "r", encoding="utf8") as handle:
        paths: list[Path] = [Path(line.strip()) for line in handle if line.strip()]
    for path in paths:
        report = healthcheck.score_file(path)
        print(report)
    return 0


def run_healthscore(args: argparse.Namespace) -> int:
    """Compute read-only health scores for one or more FLAC files."""

    for path in args.paths:
        score, _ = healthscore.score_file(path)
        print(f"{score}\t{path}")
    return 0


def _command_dedupe(args: argparse.Namespace) -> int:
    """Mark canonical files and report duplicate sets."""

    result = deduper.deduplicate_database(args.database, args.report)
    logger.info("Deduplicated %s groups", result["groups"])
    return 0


def _command_hrm_move(args: argparse.Namespace) -> int:
    """Move canonical, healthy files into the HRM hierarchy."""

    from tools.move_to_hrm import move_canonical_to_hrm

    moved = move_canonical_to_hrm(args.database, args.root)
    logger.info("Moved %s files to HRM", moved)
    return 0


def _command_relocate_hrm(args: argparse.Namespace) -> int:
    """Relocate healthy files into the HRM folder structure."""

    try:
        result = hrm_relocation.relocate_hrm(
            db_path=args.db,
            root=args.root,
            hrm_root=args.hrm_root,
            min_score=args.min_score,
        )
    except hrm_relocation.MissingScoreColumnsError as exc:
        logger.error(str(exc))
        return 1
    logger.info(
        "Relocation results: moved=%s skipped=%s conflicts=%s missing=%s manifest=%s",
        result.moved,
        result.skipped,
        result.conflicts,
        result.missing,
        result.manifest_path,
    )
    return 0


def run_upgrade_db(args: argparse.Namespace) -> int:
    """Upgrade a legacy per-volume database into the unified schema."""

    upgrade_db(str(args.legacy_db), str(args.out_db))
    logger.info("Upgraded legacy database %s -> %s", args.legacy_db, args.out_db)
    return 0


COMMAND_HANDLERS = {
    "scan-library": _command_scan,
    "match": _command_match,
    "generate-manifest": _command_manifest,
    "rescan-missing": _command_rescan_missing,
    "health": _command_health,
    "health-batch": _command_health_batch,
    "healthscore": run_healthscore,
    "dedupe-db": _command_dedupe,
    "hrm-move": _command_hrm_move,
    "relocate-hrm": _command_relocate_hrm,
    "upgrade-db": run_upgrade_db,
}


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()

    # Allow callers to place global options (like --verbose) either before
    # or after the subcommand. argparse supports `parse_intermixed_args`
    # (Python 3.8+) which accepts intermixed options; fall back to the
    # regular `parse_args` when it's not available.
    import sys

    arglist: list[str] = list(argv) if argv is not None else list(sys.argv[1:])

    # Normalize placement of a small set of known global options so users can
    # place them after the subcommand. This is a pragmatic, minimal shim that
    # moves `--verbose` before the subparser if necessary.
    if arglist:
        # index of first positional (likely the subcommand)
        first_pos = None
        for i, arg in enumerate(arglist):
            if not arg.startswith("-"):
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
