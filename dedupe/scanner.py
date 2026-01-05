"""Library scanning utilities.

This module backs the main `dedupe` CLI and is covered by unit tests.
It scans audio files into the legacy `library_files` table.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import metadata, utils
from dedupe.utils.config import get_config
from dedupe.utils.library import load_zone_paths, ensure_dedupe_zone

logger = logging.getLogger(__name__)

LIBRARY_TABLE = "library_files"


@dataclass(slots=True)
class ScanRecord:
    path: str
    size_bytes: int
    mtime: float
    checksum: Optional[str]
    duration: Optional[float]
    sample_rate: Optional[int]
    bit_rate: Optional[int]
    channels: Optional[int]
    bit_depth: Optional[int]
    tags_json: str
    fingerprint: Optional[str]
    fingerprint_duration: Optional[float]
    dup_group: Optional[str]
    duplicate_rank: Optional[int]
    is_canonical: Optional[int]
    extra_json: Optional[str]
    integrity_state: Optional[str]
    zone: Optional[str]


@dataclass(slots=True)
class ScanConfig:
    root: Path
    database: Path
    include_fingerprints: bool
    batch_size: int = 500
    resume: bool = False
    resume_safe: bool = False
    show_progress: bool = False
    zone: Optional[str] = None


def initialise_database(connection: sqlite3.Connection) -> None:
    """Ensure the legacy library schema exists."""

    with connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {LIBRARY_TABLE} (
                path TEXT PRIMARY KEY,
                size_bytes INTEGER,
                mtime REAL,
                checksum TEXT,
                duration REAL,
                sample_rate INTEGER,
                bit_rate INTEGER,
                channels INTEGER,
                bit_depth INTEGER,
                tags_json TEXT,
                fingerprint TEXT,
                fingerprint_duration REAL,
                dup_group TEXT,
                duplicate_rank INTEGER,
                is_canonical INTEGER,
                extra_json TEXT,
                library_state TEXT,
                flac_ok INTEGER,
                integrity_state TEXT,
                zone TEXT
            )
            """
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{LIBRARY_TABLE}_checksum ON {LIBRARY_TABLE}(checksum)"
        )
        columns = {
            "library_state": "TEXT",
            "flac_ok": "INTEGER",
            "integrity_state": "TEXT",
            "zone": "TEXT",
        }
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({LIBRARY_TABLE})")}
        for name, col_type in columns.items():
            if name not in existing:
                connection.execute(
                    f"ALTER TABLE {LIBRARY_TABLE} ADD COLUMN {name} {col_type}"
                )


def prepare_record(path: Path, include_fingerprints: bool, zone: Optional[str]) -> ScanRecord:
    """Probe metadata for *path* and return a ScanRecord."""

    stat = path.stat()
    info = metadata.probe_audio(path)
    tags_json = json.dumps(info.tags, sort_keys=True, separators=(",", ":"))
    return ScanRecord(
        path=utils.normalise_path(str(path)),
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
        checksum=utils.compute_md5(path),
        duration=info.stream.duration,
        sample_rate=info.stream.sample_rate,
        bit_rate=info.stream.bit_rate,
        channels=info.stream.channels,
        bit_depth=info.stream.bit_depth,
        tags_json=tags_json,
        fingerprint=None,
        fingerprint_duration=None,
        dup_group=None,
        duplicate_rank=None,
        is_canonical=None,
        extra_json=None,
        integrity_state=None,
        zone=zone,
    )


def _existing_index(connection: sqlite3.Connection) -> dict[str, tuple[int | None, float | None]]:
    cursor = connection.execute(f"SELECT path, size_bytes, mtime FROM {LIBRARY_TABLE}")
    return {utils.normalise_path(row["path"]): (row["size_bytes"], row["mtime"]) for row in cursor.fetchall()}


def _upsert_batch(connection: sqlite3.Connection, records: list[ScanRecord]) -> None:
    if not records:
        return

    query = (
        f"INSERT INTO {LIBRARY_TABLE} ("
        "path,size_bytes,mtime,checksum,duration,sample_rate,bit_rate,channels,bit_depth,"
        "tags_json,fingerprint,fingerprint_duration,dup_group,duplicate_rank,is_canonical,extra_json,"
        "integrity_state,zone"
        ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "size_bytes=excluded.size_bytes,mtime=excluded.mtime,checksum=excluded.checksum,"
        "duration=excluded.duration,sample_rate=excluded.sample_rate,bit_rate=excluded.bit_rate,"
        "channels=excluded.channels,bit_depth=excluded.bit_depth,tags_json=excluded.tags_json,"
        "fingerprint=excluded.fingerprint,fingerprint_duration=excluded.fingerprint_duration,"
        "dup_group=excluded.dup_group,duplicate_rank=excluded.duplicate_rank,"
        "is_canonical=excluded.is_canonical,extra_json=excluded.extra_json,"
        "integrity_state=excluded.integrity_state,zone=excluded.zone"
    )

    payload = [
        (
            utils.normalise_path(r.path),
            r.size_bytes,
            r.mtime,
            r.checksum,
            r.duration,
            r.sample_rate,
            r.bit_rate,
            r.channels,
            r.bit_depth,
            r.tags_json,
            r.fingerprint,
            r.fingerprint_duration,
            r.dup_group,
            r.duplicate_rank,
            r.is_canonical,
            r.extra_json,
            r.integrity_state,
            r.zone,
        )
        for r in records
    ]

    with connection:
        connection.executemany(query, payload)


def scan_library(config: ScanConfig) -> int:
    root = Path(utils.normalise_path(str(config.root)))
    database = Path(utils.normalise_path(str(config.database)))
    utils.ensure_parent_directory(database)

    ctx = utils.DatabaseContext(database)
    processed = 0

    zone_name: Optional[str] = config.zone
    zone_paths = load_zone_paths(get_config())
    if zone_paths is not None:
        if zone_name is None:
            zone_name = ensure_dedupe_zone(root, zone_paths)
        if zone_name not in ("staging", "accepted"):
            raise ValueError(f"Zone '{zone_name}' is out of scope for dedupe.")

    with ctx.connect() as connection:
        initialise_database(connection)
        existing = _existing_index(connection) if (config.resume or config.resume_safe) else {}

        files = sorted(
            (p for p in utils.iter_audio_files(root) if p.suffix.lower() == ".flac"),
            key=lambda p: utils.normalise_path(str(p)),
        )

        for batch in utils.chunks(files, max(1, int(config.batch_size))):
            if config.resume_safe and not config.resume:
                for path in batch:
                    npath = utils.normalise_path(str(path))
                    if npath in existing:
                        return 0

            records: list[ScanRecord] = []
            for path in batch:
                npath = utils.normalise_path(str(path))
                if config.resume:
                    db_size, db_mtime = existing.get(npath, (None, None))
                    try:
                        stat = path.stat()
                    except Exception:
                        stat = None
                    if stat is not None and db_size == stat.st_size and db_mtime == stat.st_mtime:
                        continue

                record = prepare_record(path, config.include_fingerprints, zone_name)
                records.append(record)

            _upsert_batch(connection, records)
            processed += len(records)

    return processed


def scan(
    *,
    root: Path,
    database: Path,
    include_fingerprints: bool,
    batch_size: int = 500,
    resume: bool = False,
    resume_safe: bool = False,
    show_progress: bool = False,
    zone: Optional[str] = None,
) -> int:
    config = ScanConfig(
        root=root,
        database=database,
        include_fingerprints=include_fingerprints,
        batch_size=batch_size,
        resume=resume,
        resume_safe=resume_safe,
        show_progress=show_progress,
        zone=zone,
    )
    return scan_library(config)


def rescan_missing(
    *,
    root: Path,
    database: Path,
    include_fingerprints: bool,
    zone: Optional[str] = None,
) -> dict[str, Any]:
    root = Path(utils.normalise_path(str(root)))
    database = Path(utils.normalise_path(str(database)))
    utils.ensure_parent_directory(database)

    ctx = utils.DatabaseContext(database)
    ingested: list[str] = []
    zone_name: Optional[str] = zone
    zone_paths = load_zone_paths(get_config())
    if zone_paths is not None:
        if zone_name is None:
            zone_name = ensure_dedupe_zone(root, zone_paths)
        if zone_name not in ("staging", "accepted"):
            raise ValueError(f"Zone '{zone_name}' is out of scope for dedupe.")

    with ctx.connect() as connection:
        initialise_database(connection)
        existing_paths = {
            utils.normalise_path(row["path"])
            for row in connection.execute(f"SELECT path FROM {LIBRARY_TABLE}").fetchall()
        }

        for path in sorted(utils.iter_audio_files(root), key=lambda p: utils.normalise_path(str(p))):
            if path.suffix.lower() != ".flac":
                continue
            npath = utils.normalise_path(str(path))
            if npath in existing_paths:
                continue
            record = prepare_record(path, include_fingerprints, zone_name)
            _upsert_batch(connection, [record])
            ingested.append(npath)
            existing_paths.add(npath)

    return {
        "missing": [],
        "ingested": ingested,
        "unreadable": [],
        "corrupt": [],
    }
