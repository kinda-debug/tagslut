"""Library scanning utilities.

This module backs the main `dedupe` CLI and is covered by unit tests.
It scans audio files into the legacy `library_files` table.
"""

from __future__ import annotations

import json
import logging
import platform
import sqlite3
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import metadata, utils
from dedupe.storage.schema import LIBRARY_TABLE, initialise_library_schema
from dedupe.storage.queries import (
    finalize_scan_session,
    insert_file_scan_run,
    insert_scan_session,
)
from dedupe.utils.config import get_config
from dedupe.utils.library import load_zone_paths, ensure_dedupe_zone, identify_zone

logger = logging.getLogger(__name__)

# Controls whether checksum hashing runs during record preparation.
# Set by ScanConfig in scan_library; defaults to True.
COMPUTE_CHECKSUM: bool = True


def initialise_database(connection: sqlite3.Connection) -> None:
    """Backward-compatible shim for initialising the library schema."""

    initialise_library_schema(connection)


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
    compute_checksum: bool = True
    zone: Optional[str] = None
    create_db: bool = False
    allow_repo_db: bool = False


def prepare_record(path: Path, include_fingerprints: bool, zone: Optional[str]) -> ScanRecord:
    """Probe metadata for *path* and return a ScanRecord."""

    stat = path.stat()
    info = metadata.probe_audio(path)
    tags_json = json.dumps(info.tags, sort_keys=True, separators=(",", ":"))
    return ScanRecord(
        path=utils.normalise_path(str(path)),
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
        checksum=utils.compute_md5(path) if COMPUTE_CHECKSUM else None,
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

    ctx = utils.DatabaseContext(
        database,
        purpose="write",
        allow_create=config.create_db,
        allow_repo_db=config.allow_repo_db,
    )
    processed = 0
    failed = 0
    aborted = False

    zone_name: Optional[str] = config.zone
    app_config = get_config()
    zone_paths = load_zone_paths(app_config)
    if zone_paths is not None:
        if zone_name is None:
            # Only infer/enforce a zone when the scan root is inside a
            # configured COMMUNE zone. This allows scanning non-COMMUNE roots
            # (e.g., FINAL_LIBRARY) even when COMMUNE zones exist in config.
            inferred = identify_zone(root, zone_paths)
            if inferred is not None:
                zone_name = ensure_dedupe_zone(root, zone_paths)
        elif zone_name not in ("staging", "accepted"):
            raise ValueError(f"Zone '{zone_name}' is out of scope for dedupe.")

    library_name = app_config.get("library.name")
    status = "completed"

    with ctx.connect() as connection:
        initialise_library_schema(connection)
        existing = _existing_index(connection) if (config.resume or config.resume_safe) else {}

        files = sorted(
            (p for p in utils.iter_audio_files(root) if p.suffix.lower() == ".flac"),
            key=lambda p: utils.normalise_path(str(p)),
        )
        total_discovered = len(files)

        session_id = insert_scan_session(
            connection,
            db_path=database,
            library=library_name,
            zone=zone_name,
            root_path=root,
            paths_source=None,
            scan_integrity=False,
            scan_hash=config.compute_checksum,
            recheck=False,
            incremental=bool(config.resume or config.resume_safe),
            force_all=False,
            discovered=total_discovered,
            considered=total_discovered,
            skipped=0,
            scan_limit=None,
            host=platform.node(),
        )
        connection.commit()

        # Control checksum computation globally during scanning
        global COMPUTE_CHECKSUM
        prev_compute = COMPUTE_CHECKSUM
        COMPUTE_CHECKSUM = bool(config.compute_checksum)
        try:
            for batch in utils.chunks(files, max(1, int(config.batch_size))):
                if config.resume_safe and not config.resume:
                    for path in batch:
                        npath = utils.normalise_path(str(path))
                        if npath in existing:
                            aborted = True
                            status = "aborted"
                            break
                    if aborted:
                        break

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

                    try:
                        record = prepare_record(path, config.include_fingerprints, zone_name)
                    except Exception as exc:
                        failed += 1
                        insert_file_scan_run(
                            connection,
                            session_id=session_id,
                            path=path,
                            outcome="failed",
                            checked_metadata=False,
                            checked_hash=False,
                            checked_integrity=False,
                            checked_streaminfo=False,
                            error_class=type(exc).__name__,
                            error_message=str(exc),
                        )
                        continue
                    records.append(record)

                if records:
                    _upsert_batch(connection, records)
                    processed += len(records)
                    for record in records:
                        insert_file_scan_run(
                            connection,
                            session_id=session_id,
                            path=Path(record.path),
                            outcome="succeeded",
                            checked_metadata=True,
                            checked_hash=config.compute_checksum,
                            checked_integrity=False,
                            checked_streaminfo=False,
                            mtime=record.mtime,
                            size=record.size_bytes,
                        )
        except KeyboardInterrupt:
            aborted = True
            status = "aborted"
        except Exception:
            status = "failed"
            raise
        finally:
            COMPUTE_CHECKSUM = prev_compute
            skipped = max(0, total_discovered - processed - failed)
            ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            finalize_scan_session(
                connection,
                session_id=session_id,
                status=status,
                succeeded=processed,
                failed=failed,
                ended_at=ended_at,
                updated=processed,
            )
            connection.execute(
                "UPDATE scan_sessions SET skipped=?, discovered=?, considered=? WHERE id=?",
                (skipped, total_discovered, total_discovered, session_id),
            )
            connection.commit()

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
    compute_checksum: bool = True,
    zone: Optional[str] = None,
    create_db: bool = False,
    allow_repo_db: bool = False,
) -> int:
    config = ScanConfig(
        root=root,
        database=database,
        include_fingerprints=include_fingerprints,
        batch_size=batch_size,
        resume=resume,
        resume_safe=resume_safe,
        show_progress=show_progress,
        compute_checksum=compute_checksum,
        zone=zone,
        create_db=create_db,
        allow_repo_db=allow_repo_db,
    )
    return scan_library(config)


def rescan_missing(
    *,
    root: Path,
    database: Path,
    include_fingerprints: bool,
    zone: Optional[str] = None,
    create_db: bool = False,
    allow_repo_db: bool = False,
) -> dict[str, Any]:
    root = Path(utils.normalise_path(str(root)))
    database = Path(utils.normalise_path(str(database)))
    ctx = utils.DatabaseContext(
        database,
        purpose="write",
        allow_create=create_db,
        allow_repo_db=allow_repo_db,
    )
    ingested: list[str] = []
    processed = 0
    failed = 0
    zone_name: Optional[str] = zone
    app_config = get_config()
    zone_paths = load_zone_paths(app_config)
    if zone_paths is not None:
        if zone_name is None:
            inferred = identify_zone(root, zone_paths)
            if inferred is not None:
                zone_name = ensure_dedupe_zone(root, zone_paths)
        elif zone_name not in ("staging", "accepted"):
            raise ValueError(f"Zone '{zone_name}' is out of scope for dedupe.")

    files = sorted(
        (p for p in utils.iter_audio_files(root) if p.suffix.lower() == ".flac"),
        key=lambda p: utils.normalise_path(str(p)),
    )
    total_discovered = len(files)
    library_name = app_config.get("library.name")

    with ctx.connect() as connection:
        initialise_library_schema(connection)
        existing_paths = {
            utils.normalise_path(row["path"])
            for row in connection.execute(f"SELECT path FROM {LIBRARY_TABLE}").fetchall()
        }
        session_id = insert_scan_session(
            connection,
            db_path=database,
            library=library_name,
            zone=zone_name,
            root_path=root,
            paths_source=None,
            scan_integrity=False,
            scan_hash=True,
            recheck=False,
            incremental=True,
            force_all=False,
            discovered=total_discovered,
            considered=total_discovered,
            skipped=0,
            scan_limit=None,
            host=platform.node(),
        )
        connection.commit()

        for path in files:
            npath = utils.normalise_path(str(path))
            if npath in existing_paths:
                continue
            try:
                record = prepare_record(path, include_fingerprints, zone_name)
            except Exception as exc:
                failed += 1
                insert_file_scan_run(
                    connection,
                    session_id=session_id,
                    path=path,
                    outcome="failed",
                    checked_metadata=False,
                    checked_hash=False,
                    checked_integrity=False,
                    checked_streaminfo=False,
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                )
                continue

            _upsert_batch(connection, [record])
            ingested.append(npath)
            existing_paths.add(npath)
            processed += 1
            insert_file_scan_run(
                connection,
                session_id=session_id,
                path=Path(record.path),
                outcome="succeeded",
                checked_metadata=True,
                checked_hash=True,
                checked_integrity=False,
                checked_streaminfo=False,
                mtime=record.mtime,
                size=record.size_bytes,
            )

        skipped = max(0, total_discovered - processed - failed)
        ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        finalize_scan_session(
            connection,
            session_id=session_id,
            status="completed",
            succeeded=processed,
            failed=failed,
            ended_at=ended_at,
            updated=processed,
        )
        connection.execute(
            "UPDATE scan_sessions SET skipped=?, discovered=?, considered=? WHERE id=?",
            (skipped, total_discovered, total_discovered, session_id),
        )
        connection.commit()

    return {
        "missing": [],
        "ingested": ingested,
        "unreadable": [],
        "corrupt": [],
    }



def hash_missing(
    *,
    database: Path,
    batch_size: int = 500,
    allow_repo_db: bool = False,
) -> int:
    """Compute checksums for library rows missing them and update the database.

    Returns the number of rows updated.
    """

    database = Path(utils.normalise_path(str(database)))

    ctx = utils.DatabaseContext(
        database,
        purpose="write",
        allow_create=False,
        allow_repo_db=allow_repo_db,
    )
    updated = 0
    failed = 0

    with ctx.connect() as connection:
        initialise_library_schema(connection)
        cursor = connection.execute(
            f"SELECT path FROM {LIBRARY_TABLE} WHERE checksum IS NULL"
        )
        paths = [Path(row[0]) for row in cursor.fetchall()]

        session_id = insert_scan_session(
            connection,
            db_path=database,
            library=get_config().get("library.name"),
            zone=None,
            root_path=None,
            paths_source=None,
            scan_integrity=False,
            scan_hash=True,
            recheck=False,
            incremental=True,
            force_all=False,
            discovered=len(paths),
            considered=len(paths),
            skipped=0,
            scan_limit=None,
            host=platform.node(),
        )
        connection.commit()

        for batch in utils.chunks(paths, max(1, int(batch_size))):
            payload: list[tuple[str, str]] = []
            updated_paths: list[Path] = []
            for path in batch:
                try:
                    if not path.exists():
                        raise FileNotFoundError(str(path))
                    checksum = utils.compute_md5(path)
                except Exception as exc:
                    failed += 1
                    insert_file_scan_run(
                        connection,
                        session_id=session_id,
                        path=path,
                        outcome="failed",
                        checked_metadata=False,
                        checked_hash=True,
                        checked_integrity=False,
                        checked_streaminfo=False,
                        error_class=type(exc).__name__,
                        error_message=str(exc),
                    )
                    continue
                payload.append((checksum, utils.normalise_path(str(path))))
                updated_paths.append(path)

            if payload:
                with connection:
                    connection.executemany(
                        f"UPDATE {LIBRARY_TABLE} SET checksum=? WHERE path=?",
                        payload,
                    )
                updated += len(payload)
                for path in updated_paths:
                    insert_file_scan_run(
                        connection,
                        session_id=session_id,
                        path=path,
                        outcome="succeeded",
                        checked_metadata=False,
                        checked_hash=True,
                        checked_integrity=False,
                        checked_streaminfo=False,
                    )

        skipped = max(0, len(paths) - updated - failed)
        ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        finalize_scan_session(
            connection,
            session_id=session_id,
            status="completed",
            succeeded=updated,
            failed=failed,
            ended_at=ended_at,
            updated=updated,
        )
        connection.execute(
            "UPDATE scan_sessions SET skipped=?, discovered=?, considered=? WHERE id=?",
            (skipped, len(paths), len(paths), session_id),
        )
        connection.commit()

    return updated
