#!/usr/bin/env python3
"""Promote staged files into the final library."""

from __future__ import annotations

import argparse
import logging
import shutil
import sqlite3
from pathlib import Path

from dedupe.core.metadata import tags_are_valid
from dedupe.storage import LIBRARY_TABLE, initialise_library_schema
from dedupe.storage.queries import extract_tags
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


def _resolve_root(config_path: Path | None, root: Path | None, key: str) -> Path:
    """Resolve a library root using config or CLI input."""

    if root is not None:
        return Path(normalise_path(str(root)))

    config = get_config(config_path)
    libraries = config.get("libraries", {})
    library_path = libraries.get(key)
    if not library_path:
        raise SystemExit(f"{key} missing from config libraries section")
    return Path(normalise_path(str(library_path)))


def _has_duplicate_final(connection: sqlite3.Connection, checksum: str | None) -> bool:
    """Return ``True`` when a checksum already exists in FINAL canonical files."""

    if not checksum:
        return False
    cursor = connection.execute(
        f"""
        SELECT 1 FROM {LIBRARY_TABLE}
        WHERE checksum = ?
          AND library_state = 'FINAL'
          AND is_canonical = 1
        LIMIT 1
        """,
        (checksum,),
    )
    return cursor.fetchone() is not None


def _eligible_metadata(tags_json: str | None) -> bool:
    """Return ``True`` when tags are present and normalized."""

    tags = extract_tags(tags_json)
    return bool(tags) and tags_are_valid(tags)


def promote_staged(
    connection: sqlite3.Connection,
    staging_root: Path,
    final_root: Path,
) -> int:
    """Promote eligible staged files into the final library."""

    initialise_library_schema(connection)
    cursor = connection.execute(
        f"SELECT * FROM {LIBRARY_TABLE} WHERE library_state = 'STAGING'"
    )
    rows = cursor.fetchall()
    promoted = 0

    for row in rows:
        if row["flac_ok"] != 1:
            logger.info("Skipping %s: flac_ok is false", row["path"])
            continue
        if not _eligible_metadata(row["tags_json"]):
            logger.info("Skipping %s: metadata incomplete", row["path"])
            continue
        if _has_duplicate_final(connection, row["checksum"]):
            logger.info("Skipping %s: duplicate of FINAL canonical file", row["path"])
            continue

        source = Path(row["path"])
        if not source.exists():
            raise FileNotFoundError(f"Staged file missing: {source}")
        try:
            relative = source.relative_to(staging_root)
        except ValueError as exc:
            raise ValueError(
                f"Staged file not under staging root: {source}"
            ) from exc

        destination = final_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Promoting %s -> %s", source, destination)
        shutil.move(str(source), str(destination))

        try:
            with connection:
                updated = connection.execute(
                    f"""
                    UPDATE {LIBRARY_TABLE}
                    SET path = ?, library_state = 'FINAL'
                    WHERE path = ? AND library_state = 'STAGING'
                    """,
                    (normalise_path(str(destination)), normalise_path(str(source))),
                )
                if updated.rowcount != 1:
                    raise RuntimeError(f"Failed to update database for {source}")
        except Exception as exc:
            logger.error("Database update failed for %s: %s", source, exc)
            shutil.move(str(destination), str(source))
            raise

        promoted += 1

    return promoted


def build_parser() -> argparse.ArgumentParser:
    """Build the promote CLI parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        required=True,
        type=Path,
        help="SQLite database path to update.",
    )
    parser.add_argument(
        "--staging-root",
        type=Path,
        help="Staging root directory (defaults to config).",
    )
    parser.add_argument(
        "--final-root",
        type=Path,
        help="Final library root directory (defaults to config).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional config.toml path override.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main() -> None:
    """CLI entry point for promoting staged files."""

    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)

    staging_root = _resolve_root(args.config, args.staging_root, "dotad_staging")
    final_root = _resolve_root(args.config, args.final_root, "dotad_final")

    with sqlite3.connect(args.db) as connection:
        connection.row_factory = sqlite3.Row
        promoted = promote_staged(connection, staging_root, final_root)

    logger.info("Promoted %s staged files into %s", promoted, final_root)


if __name__ == "__main__":
    main()
