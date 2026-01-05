#!/usr/bin/env python3
"""Reconcile tagger moves (Yate-first) for staged files."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

from dedupe.external.picard import reconcile_picard_changes
from dedupe.utils import normalise_path
from dedupe.utils.config import get_config
from dedupe.utils.library import load_zone_paths

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _resolve_root(config_path: Path | None, root: Path | None) -> Path:
    """Resolve the staging root using config or CLI input."""

    if root is not None:
        return Path(normalise_path(str(root)))

    config = get_config(config_path)
    zone_paths = load_zone_paths(config)
    if zone_paths is None:
        raise SystemExit("COMMUNE library zones are not configured.")
    staging = zone_paths.zones.get("staging")
    if staging is None:
        raise SystemExit("staging zone missing from config.")
    return Path(normalise_path(str(staging)))


def build_parser() -> argparse.ArgumentParser:
    """Build the reconcile CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="SQLite database path to update.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Staging root directory (defaults to config).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional config.toml path override.",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Allow missing staging files without failing.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main() -> None:
    """CLI entry point for tagger reconciliation."""

    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)

    root = _resolve_root(args.config, args.root)
    with sqlite3.connect(args.db) as connection:
        connection.row_factory = sqlite3.Row
        result = reconcile_picard_changes(
            connection,
            root,
            strict=not args.allow_missing,
        )
        connection.commit()
    logger.info(
        "Tagger reconciliation complete: %s moved, %s unchanged, %s inserted",
        result.moved,
        result.unchanged,
        result.inserted,
    )


if __name__ == "__main__":
    main()
