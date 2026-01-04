#!/usr/bin/env python3
"""Reconcile MusicBrainz Picard moves for staged files."""

from __future__ import annotations

import argparse
import logging
import sqlite3
from pathlib import Path

from dedupe.external.picard import reconcile_picard_changes
from dedupe.utils import normalise_path
from dedupe.utils.config import get_config

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
    libraries = config.get("libraries", {})
    staging = libraries.get("recovery_staging")
    if not staging:
        raise SystemExit("recovery_staging missing from config libraries section")
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
    """CLI entry point for Picard reconciliation."""

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
        "Picard reconciliation complete: %s moved, %s unchanged, %s inserted",
        result.moved,
        result.unchanged,
        result.inserted,
    )


if __name__ == "__main__":
    main()
