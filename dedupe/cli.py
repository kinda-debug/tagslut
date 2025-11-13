"""Command-line interface for the dedupe toolkit."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Iterable, Optional

from . import manifest, matcher, rstudio_parser, scanner

LOGGER = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _path(value: str) -> Path:
    return Path(value).expanduser()


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
        help="Capture Chromaprint fingerprints during scanning",
    )

    parse_parser = subparsers.add_parser(
        "parse-rstudio",
        help="Parse an R-Studio Recognized Files export into SQLite",
    )
    parse_parser.add_argument(
        "--input",
        type=_path,
        required=True,
        help="R-Studio export path",
    )
    parse_parser.add_argument(
        "--out",
        type=_path,
        required=True,
        help="SQLite database to store recovery candidates",
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
    )
    total = scanner.scan_library(config)
    LOGGER.info("Indexed %s files", total)
    return 0


def _command_parse_rstudio(args: argparse.Namespace) -> int:
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


COMMAND_HANDLERS = {
    "scan-library": _command_scan,
    "parse-rstudio": _command_parse_rstudio,
    "match": _command_match,
    "generate-manifest": _command_manifest,
}


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    _configure_logging(args.verbose)
    handler = COMMAND_HANDLERS[args.command]
    return handler(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
