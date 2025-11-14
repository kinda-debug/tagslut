"""CLI entry point for the global multi-volume recovery workflow."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from dedupe import global_recovery


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Global multi-volume audio recovery workflow",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level (default: INFO)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan one or more roots into the global database",
    )
    scan_parser.add_argument(
        "--root",
        action="append",
        required=True,
        help="Root directory to scan (may be supplied multiple times)",
    )
    scan_parser.add_argument(
        "--db",
        required=True,
        help="Path to the global recovery SQLite database",
    )
    scan_parser.add_argument(
        "--include-fp",
        action="store_true",
        help="Compute audio fingerprints where supported",
    )
    scan_parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of files processed per database transaction batch",
    )
    scan_parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip files that appear unchanged since the last scan",
    )
    scan_parser.add_argument(
        "--show-progress",
        action="store_true",
        help="Display a progress bar while scanning",
    )

    parse_parser = subparsers.add_parser(
        "parse-recognized",
        help="Load an R-Studio 'Recognized Files' export into the database",
    )
    parse_parser.add_argument(
        "export",
        help="Path to the Recognized*.txt export",
    )
    parse_parser.add_argument(
        "--db",
        required=True,
        help="Path to the global recovery SQLite database",
    )

    resolve_parser = subparsers.add_parser(
        "resolve",
        help="Analyse candidates and produce recovery reports",
    )
    resolve_parser.add_argument(
        "--db",
        required=True,
        help="Path to the global recovery SQLite database",
    )
    resolve_parser.add_argument(
        "--out-prefix",
        required=True,
        help="Prefix for generated CSV reports",
    )
    resolve_parser.add_argument(
        "--min-name-similarity",
        type=float,
        default=0.65,
        help="Minimum similarity required to attach fragments to a group",
    )
    resolve_parser.add_argument(
        "--duration-tolerance",
        type=float,
        default=1.0,
        help="Tolerance in seconds before duration mismatches are penalised",
    )
    resolve_parser.add_argument(
        "--size-tolerance",
        type=float,
        default=0.02,
        help="Allowed proportional size difference before penalising",
    )
    resolve_parser.add_argument(
        "--threshold",
        type=float,
        default=0.55,
        help="Minimum score required to automatically accept a keeper",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by ``python scripts/global_recovery.py``."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO)
    )

    if args.command == "scan":
        roots = [Path(root) for root in args.root]
        count = global_recovery.scan_roots(
            roots,
            Path(args.db),
            include_fingerprints=args.include_fp,
            batch_size=args.batch_size,
            resume=args.resume,
            show_progress=args.show_progress,
        )
        LOGGER = logging.getLogger(__name__)
        LOGGER.info("Indexed %s files", count)
        return 0

    if args.command == "parse-recognized":
        total = global_recovery.parse_recognized_export(
            Path(args.export),
            Path(args.db),
        )
        LOGGER = logging.getLogger(__name__)
        LOGGER.info("Database now tracks %s fragments", total)
        return 0

    if args.command == "resolve":
        config = global_recovery.ResolverConfig(
            database=Path(args.db),
            out_prefix=Path(args.out_prefix),
            min_name_similarity=args.min_name_similarity,
            duration_tolerance=args.duration_tolerance,
            size_tolerance=args.size_tolerance,
            threshold=args.threshold,
        )
        global_recovery.resolve_database(config)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
