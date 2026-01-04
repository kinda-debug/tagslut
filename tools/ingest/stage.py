#!/usr/bin/env python3
"""Register newly tagged files into the staging database."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
from pathlib import Path
from typing import Iterable

from dedupe import healthcheck, metadata
from dedupe.storage import initialise_library_schema
from dedupe.storage.queries import upsert_library_rows
from dedupe.utils import compute_md5, iter_audio_files, normalise_path
from dedupe.utils.config import get_config

logger = logging.getLogger(__name__)


def _configure_logging(verbose: bool) -> None:
    """Configure logging based on verbosity."""

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _iter_paths(root: Path, paths: Iterable[Path]) -> Iterable[Path]:
    """Return the explicit *paths* or discover audio files under *root*."""

    if paths:
        return paths
    return iter_audio_files(root)


def _build_payload(path: Path) -> dict[str, object]:
    """Collect metadata, health, and library state for *path*."""

    meta = metadata.probe_audio(path)
    health = healthcheck.evaluate_flac(path)
    return {
        "path": normalise_path(str(path)),
        "size_bytes": meta.size_bytes,
        "mtime": path.stat().st_mtime,
        "checksum": compute_md5(path),
        "duration": meta.stream.duration,
        "sample_rate": meta.stream.sample_rate,
        "bit_rate": meta.stream.bit_rate,
        "channels": meta.stream.channels,
        "bit_depth": meta.stream.bit_depth,
        "tags_json": json.dumps(meta.tags, sort_keys=True, separators=(",", ":")),
        "fingerprint": None,
        "fingerprint_duration": None,
        "dup_group": None,
        "duplicate_rank": None,
        "is_canonical": None,
        "extra_json": json.dumps(
            {
                "health_score": health.score,
                "health_reasons": health.reasons,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        "library_state": "STAGING",
        "flac_ok": 1 if health.audio_ok else 0,
    }


def stage_paths(
    database: Path,
    root: Path,
    paths: Iterable[Path],
) -> int:
    """Insert or update staged paths in the database."""

    staged = 0
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        initialise_library_schema(connection)
        payload = []
        for path in _iter_paths(root, list(paths)):
            if not path.is_file():
                logger.warning("Skipping non-file path: %s", path)
                continue
            payload.append(_build_payload(path))
            staged += 1
        if payload:
            upsert_library_rows(connection, payload)
            connection.commit()
    return staged


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
    """Build the staging CLI parser."""

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
        help="Root directory to scan for staged files (defaults to config).",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional config.toml path override.",
    )
    parser.add_argument(
        "--paths",
        nargs="*",
        type=Path,
        default=[],
        help="Specific file paths to register instead of scanning the root.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main() -> None:
    """CLI entry point for staging ingestion."""

    parser = build_parser()
    args = parser.parse_args()
    _configure_logging(args.verbose)

    root = _resolve_root(args.config, args.root)
    staged = stage_paths(args.db, root, args.paths)
    logger.info("Staged %s files into %s", staged, args.db)


if __name__ == "__main__":
    main()
