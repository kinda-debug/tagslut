"""Library scanning logic."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from . import fingerprints, metadata, utils

LOGGER = logging.getLogger(__name__)

LIBRARY_TABLE = "library_files"


@dataclass(slots=True)
class ScanRecord:
    """Metadata collected for an audio file."""

    path: str
    size_bytes: int
    mtime: float
    checksum: str
    duration: Optional[float]
    sample_rate: Optional[int]
    bit_rate: Optional[int]
    channels: Optional[int]
    bit_depth: Optional[int]
    tags_json: str
    fingerprint: Optional[str]
    fingerprint_duration: Optional[float]


@dataclass(slots=True)
class ScanConfig:
    """Configuration for :func:`scan_library`."""

    root: Path
    database: Path
    include_fingerprints: bool = False
    batch_size: int = 100


def initialise_database(connection: sqlite3.Connection) -> None:
    """Ensure the SQLite schema exists."""

    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {LIBRARY_TABLE} (
            path TEXT PRIMARY KEY,
            size_bytes INTEGER NOT NULL,
            mtime REAL NOT NULL,
            checksum TEXT NOT NULL,
            duration REAL,
            sample_rate INTEGER,
            bit_rate INTEGER,
            channels INTEGER,
            bit_depth INTEGER,
            tags_json TEXT,
            fingerprint TEXT,
            fingerprint_duration REAL
        )
        """
    )


def _prepare_record(path: Path, include_fingerprints: bool) -> ScanRecord:
    meta = metadata.probe_audio(path)
    checksum = utils.compute_md5(path)
    fingerprint_result = (
        fingerprints.generate_chromaprint(path)
        if include_fingerprints
        else None
    )
    return ScanRecord(
        path=utils.normalise_path(str(path)),
        size_bytes=meta.size_bytes,
        mtime=path.stat().st_mtime,
        checksum=checksum,
        duration=meta.stream.duration,
        sample_rate=meta.stream.sample_rate,
        bit_rate=meta.stream.bit_rate,
        channels=meta.stream.channels,
        bit_depth=meta.stream.bit_depth,
        tags_json=json.dumps(meta.tags, sort_keys=True),
        fingerprint=(
            fingerprint_result.fingerprint if fingerprint_result else None
        ),
        fingerprint_duration=(
            fingerprint_result.duration if fingerprint_result else None
        ),
    )


def _iter_records(
    paths: Iterable[Path],
    include_fingerprints: bool,
) -> Iterator[ScanRecord]:
    for path in paths:
        try:
            yield _prepare_record(path, include_fingerprints)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to scan %s: %s", path, exc)


def _upsert_batch(
    connection: sqlite3.Connection,
    records: Iterable[ScanRecord],
) -> None:
    connection.executemany(
        f"""
        INSERT INTO {LIBRARY_TABLE} (
            path,
            size_bytes,
            mtime,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            channels,
            bit_depth,
            tags_json,
            fingerprint,
            fingerprint_duration
        ) VALUES (
            :path,
            :size_bytes,
            :mtime,
            :checksum,
            :duration,
            :sample_rate,
            :bit_rate,
            :channels,
            :bit_depth,
            :tags_json,
            :fingerprint,
            :fingerprint_duration
        )
        ON CONFLICT(path) DO UPDATE SET
            size_bytes=excluded.size_bytes,
            mtime=excluded.mtime,
            checksum=excluded.checksum,
            duration=excluded.duration,
            sample_rate=excluded.sample_rate,
            bit_rate=excluded.bit_rate,
            channels=excluded.channels,
            bit_depth=excluded.bit_depth,
            tags_json=excluded.tags_json,
            fingerprint=excluded.fingerprint,
            fingerprint_duration=excluded.fingerprint_duration
        """,
        [record.__dict__ for record in records],
    )


def scan_library(config: ScanConfig) -> int:
    """Scan ``config.root`` and populate ``config.database``."""

    utils.ensure_parent_directory(config.database)
    db = utils.DatabaseContext(config.database)
    start = time.time()
    total = 0
    with db.connect() as connection:
        initialise_database(connection)
        for batch in utils.chunks(
            utils.iter_audio_files(config.root),
            config.batch_size,
        ):
            records = list(_iter_records(batch, config.include_fingerprints))
            if not records:
                continue
            _upsert_batch(connection, records)
            connection.commit()
            total += len(records)
            LOGGER.info(
                "Processed %s files (%.1fs elapsed)",
                total,
                time.time() - start,
            )
    LOGGER.info("Completed scan of %s (%s files)", config.root, total)
    return total
