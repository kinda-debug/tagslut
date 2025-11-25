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
    rstudio_parser,
    scanner,
    utils,
)
from tools.db_upgrade import upgrade_db

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

    rstudio_parser_cli = subparsers.add_parser(
        "parse-rstudio",
        help=(
            "Parse an R-Studio export (deprecated). "
            "WARNING: this command is deprecated and will be removed in a future release."
        ),
    )
    rstudio_parser_cli.add_argument(
        "--input",
        type=_path,
        required=True,
        help="Recognized Files export to parse",
    )
    rstudio_parser_cli.add_argument(
        "--out",
        type=_path,
        required=True,
        help="SQLite database path to populate",
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

    rescan_parser = subparsers.add_parser(
        "rescan-missing",
        help="Ingest only missing FLAC files under a root path",
    )
    rescan_parser.add_argument("--root", type=_path, required=True)
    rescan_parser.add_argument("--out", type=_path, required=True)
    rescan_parser.add_argument(
        "--fingerprints",
        action="store_true",
        help="Compute fingerprints for missing files when possible",
    )

    health_parser = subparsers.add_parser(
        "health",
        help="Score a single FLAC file",
    )
    health_parser.add_argument("path", type=_path)

    health_batch_parser = subparsers.add_parser(
        "health-batch",
        help="Score a list of FLAC files from a text list",
    )
    health_batch_parser.add_argument("list_path", type=_path)

    healthscore_parser = subparsers.add_parser(
        "healthscore",
        help="Compute read-only health scores for one or more FLAC files",
    )
    healthscore_parser.add_argument("paths", nargs="+", type=str)
    healthscore_parser.set_defaults(func=run_healthscore)

    dedupe_parser = subparsers.add_parser(
        "dedupe-db",
        help="Deduplicate entries in a library database",
    )
    dedupe_parser.add_argument("database", type=_path)
    dedupe_parser.add_argument(
        "--report",
        type=_path,
        help="Optional path to write a JSON duplicate report",
    )

    hrm_parser = subparsers.add_parser(
        "hrm-move",
        help="Move canonical, healthy files into the HRM structure",
    )
    hrm_parser.add_argument("database", type=_path)
    hrm_parser.add_argument("--root", type=_path, required=True)

    hrm_relocate_parser = subparsers.add_parser(
        "relocate-hrm",
        help="Relocate healthy files into the HRM hierarchy",
    )
    hrm_relocate_parser.add_argument("--db", type=_path, required=True)
    hrm_relocate_parser.add_argument("--root", type=_path, required=True)
    hrm_relocate_parser.add_argument("--hrm-root", type=_path, required=True)
    hrm_relocate_parser.add_argument(
        "--min-score",
        type=float,
        default=10,
        help="Minimum total health score required for relocation",
    )

    upgrade_parser = subparsers.add_parser(
        "upgrade-db",
        help="Upgrade a legacy per-volume database to the unified schema",
    )
    upgrade_parser.add_argument(
        "legacy_db",
        type=_path,
        help="Path to the legacy per-volume SQLite database",
    )
    upgrade_parser.add_argument(
        "out_db",
        type=_path,
        help="Destination path for the upgraded database",
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
    LOGGER.info("Indexed %s files", total)
    return 0


def _command_parse_rstudio(args: argparse.Namespace) -> int:
    """Ingest an R-Studio export into the recovered files database."""

    logging.warning(
        "dedupe parse-rstudio is deprecated and will be removed in a future release."
    )
    records = list(rstudio_parser.parse_export(args.input))
    count = rstudio_parser.load_into_database(records, args.out)
    LOGGER.info("Captured %s recovery candidates", count)
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
    LOGGER.info(
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
        paths = [Path(line.strip()) for line in handle if line.strip()]
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
    LOGGER.info("Deduplicated %s groups", result["groups"])
    return 0


def _command_hrm_move(args: argparse.Namespace) -> int:
    """Move canonical, healthy files into the HRM hierarchy."""

    from tools.move_to_hrm import move_canonical_to_hrm

    moved = move_canonical_to_hrm(args.database, args.root)
    LOGGER.info("Moved %s files to HRM", moved)
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
        LOGGER.error(str(exc))
        return 1
    LOGGER.info(
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
    LOGGER.info("Upgraded legacy database %s -> %s", args.legacy_db, args.out_db)
    return 0


COMMAND_HANDLERS = {
    "scan-library": _command_scan,
    "parse-rstudio": _command_parse_rstudio,
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
