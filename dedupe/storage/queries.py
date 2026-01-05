import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterable

from dedupe.storage.models import AudioFile
from dedupe.storage.schema import (
    LIBRARY_TABLE,
    PICARD_MOVES_TABLE,
    STEP0_AUDIO_CONTENT_TABLE,
    STEP0_ARTIFACTS_TABLE,
    STEP0_CANONICAL_TABLE,
    STEP0_DECISIONS_TABLE,
    STEP0_FILES_TABLE,
    STEP0_HASHES_TABLE,
    STEP0_IDENTITY_TABLE,
    STEP0_INTEGRITY_TABLE,
    STEP0_REACQUIRE_TABLE,
    STEP0_SCAN_TABLE,
)

logger = logging.getLogger("dedupe")


def upsert_library_rows(conn: sqlite3.Connection, rows: Iterable[dict[str, object]]) -> None:
    """Upsert dict payloads into the legacy `library_files` table."""

    payload = list(rows)
    if not payload:
        return

    columns = [
        "path",
        "size_bytes",
        "mtime",
        "checksum",
        "duration",
        "sample_rate",
        "bit_rate",
        "channels",
        "bit_depth",
        "tags_json",
        "fingerprint",
        "fingerprint_duration",
        "dup_group",
        "duplicate_rank",
        "is_canonical",
        "extra_json",
        "library_state",
        "flac_ok",
        "integrity_state",
        "zone",
    ]

    placeholders = ",".join(["?"] * len(columns))
    assignments = ",".join([f"{col}=excluded.{col}" for col in columns if col != "path"])
    query = (
        f"INSERT INTO {LIBRARY_TABLE} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(path) DO UPDATE SET {assignments}"
    )

    values = [tuple(row.get(col) for col in columns) for row in payload]
    conn.executemany(query, values)


def upsert_audio_content(
    conn: sqlite3.Connection,
    *,
    content_hash: str,
    streaminfo_md5: str | None,
    duration: float | None,
    sample_rate: int | None,
    bit_depth: int | None,
    channels: int | None,
    hash_type: str | None,
    coverage: str | None,
) -> None:
    """Upsert a Step-0 audio content record."""

    query = f"""
    INSERT INTO {STEP0_AUDIO_CONTENT_TABLE} (
        content_hash, streaminfo_md5, duration, sample_rate, bit_depth, channels, hash_type, coverage
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(content_hash) DO UPDATE SET
        streaminfo_md5=excluded.streaminfo_md5,
        duration=excluded.duration,
        sample_rate=excluded.sample_rate,
        bit_depth=excluded.bit_depth,
        channels=excluded.channels,
        hash_type=excluded.hash_type,
        coverage=excluded.coverage
    """
    conn.execute(
        query,
        (
            content_hash,
            streaminfo_md5,
            duration,
            sample_rate,
            bit_depth,
            channels,
            hash_type,
            coverage,
        ),
    )


def insert_integrity_result(
    conn: sqlite3.Connection,
    *,
    content_hash: str,
    path: Path,
    status: str,
    stderr_excerpt: str,
    return_code: int | None,
) -> None:
    """Insert a Step-0 integrity test result."""

    query = f"""
    INSERT INTO {STEP0_INTEGRITY_TABLE} (
        content_hash, path, status, stderr_excerpt, return_code
    ) VALUES (?, ?, ?, ?, ?)
    """
    conn.execute(
        query,
        (content_hash, str(path), status, stderr_excerpt, return_code),
    )


def upsert_identity_hints(
    conn: sqlite3.Connection,
    *,
    content_hash: str,
    hints: dict[str, Optional[str]],
    tags: dict[str, Any],
) -> None:
    """Upsert identity hints for a content hash."""

    query = f"""
    INSERT INTO {STEP0_IDENTITY_TABLE} (
        content_hash,
        isrc,
        musicbrainz_track_id,
        musicbrainz_release_id,
        artist,
        title,
        album,
        track_number,
        disc_number,
        date,
        tags_json
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(content_hash) DO UPDATE SET
        isrc=excluded.isrc,
        musicbrainz_track_id=excluded.musicbrainz_track_id,
        musicbrainz_release_id=excluded.musicbrainz_release_id,
        artist=excluded.artist,
        title=excluded.title,
        album=excluded.album,
        track_number=excluded.track_number,
        disc_number=excluded.disc_number,
        date=excluded.date,
        tags_json=excluded.tags_json
    """
    conn.execute(
        query,
        (
            content_hash,
            hints.get("isrc"),
            hints.get("musicbrainz_track_id"),
            hints.get("musicbrainz_release_id"),
            hints.get("artist"),
            hints.get("title"),
            hints.get("album"),
            hints.get("track_number"),
            hints.get("disc_number"),
            hints.get("date"),
            json.dumps(tags, sort_keys=True, separators=(",", ":")),
        ),
    )


def upsert_canonical_map(
    conn: sqlite3.Connection,
    *,
    content_hash: str,
    canonical_path: str,
    reason: str,
) -> None:
    """Upsert canonical path mapping for a content hash."""

    query = f"""
    INSERT INTO {STEP0_CANONICAL_TABLE} (
        content_hash, canonical_path, reason
    ) VALUES (?, ?, ?)
    ON CONFLICT(content_hash) DO UPDATE SET
        canonical_path=excluded.canonical_path,
        reason=excluded.reason,
        updated_at=CURRENT_TIMESTAMP
    """
    conn.execute(query, (content_hash, canonical_path, reason))


def upsert_reacquire_manifest(
    conn: sqlite3.Connection,
    *,
    content_hash: str,
    reason: str,
    confidence: float,
) -> None:
    """Upsert a Step-0 reacquire manifest entry."""

    query = f"""
    INSERT INTO {STEP0_REACQUIRE_TABLE} (
        content_hash, reason, confidence
    ) VALUES (?, ?, ?)
    ON CONFLICT(content_hash) DO UPDATE SET
        reason=excluded.reason,
        confidence=excluded.confidence,
        recorded_at=CURRENT_TIMESTAMP
    """
    conn.execute(query, (content_hash, reason, confidence))


def insert_scan_event(
    conn: sqlite3.Connection,
    *,
    inputs: list[str],
    version: str,
    library_tag: str,
) -> None:
    """Insert a Step-0 scan event record."""

    query = f"""
    INSERT INTO {STEP0_SCAN_TABLE} (
        inputs_json, version, library_tag
    ) VALUES (?, ?, ?)
    """
    conn.execute(query, (json.dumps(inputs), version, library_tag))


def upsert_step0_file(
    conn: sqlite3.Connection,
    *,
    absolute_path: str,
    content_hash: str | None,
    volume: str | None,
    zone: str | None,
    library: str | None,
    size_bytes: int | None,
    mtime: float | None,
    scan_timestamp: str | None,
    audio_integrity: str | None,
    flac_test_passed: bool | None,
    flac_error: str | None,
    duration_seconds: float | None,
    sample_rate: int | None,
    bit_depth: int | None,
    channels: int | None,
    hash_strategy: str | None,
    provenance_notes: str | None,
    orphaned_db: bool | None,
    legacy_marker: bool | None,
) -> None:
    """Upsert a Step-0 file record with provenance information."""

    query = f"""
    INSERT INTO {STEP0_FILES_TABLE} (
        absolute_path,
        content_hash,
        volume,
        zone,
        library,
        size_bytes,
        mtime,
        scan_timestamp,
        audio_integrity,
        flac_test_passed,
        flac_error,
        duration_seconds,
        sample_rate,
        bit_depth,
        channels,
        hash_strategy,
        provenance_notes,
        orphaned_db,
        legacy_marker
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(absolute_path) DO UPDATE SET
        content_hash=excluded.content_hash,
        volume=excluded.volume,
        zone=excluded.zone,
        library=excluded.library,
        size_bytes=excluded.size_bytes,
        mtime=excluded.mtime,
        scan_timestamp=excluded.scan_timestamp,
        audio_integrity=excluded.audio_integrity,
        flac_test_passed=excluded.flac_test_passed,
        flac_error=excluded.flac_error,
        duration_seconds=excluded.duration_seconds,
        sample_rate=excluded.sample_rate,
        bit_depth=excluded.bit_depth,
        channels=excluded.channels,
        hash_strategy=excluded.hash_strategy,
        provenance_notes=excluded.provenance_notes,
        orphaned_db=excluded.orphaned_db,
        legacy_marker=excluded.legacy_marker
    """
    conn.execute(
        query,
        (
            absolute_path,
            content_hash,
            volume,
            zone,
            library,
            size_bytes,
            mtime,
            scan_timestamp,
            audio_integrity,
            int(flac_test_passed) if flac_test_passed is not None else None,
            flac_error,
            duration_seconds,
            sample_rate,
            bit_depth,
            channels,
            hash_strategy,
            provenance_notes,
            int(orphaned_db) if orphaned_db is not None else None,
            int(legacy_marker) if legacy_marker is not None else None,
        ),
    )


def upsert_step0_hash(
    conn: sqlite3.Connection,
    *,
    absolute_path: str,
    hash_type: str,
    hash_value: str,
    coverage: str | None,
) -> None:
    """Upsert a Step-0 hash record for a file."""

    query = f"""
    INSERT INTO {STEP0_HASHES_TABLE} (
        absolute_path, hash_type, hash_value, coverage
    ) VALUES (?, ?, ?, ?)
    ON CONFLICT(absolute_path, hash_type) DO UPDATE SET
        hash_value=excluded.hash_value,
        coverage=excluded.coverage,
        created_at=CURRENT_TIMESTAMP
    """
    conn.execute(query, (absolute_path, hash_type, hash_value, coverage))


def upsert_step0_decision(
    conn: sqlite3.Connection,
    *,
    absolute_path: str,
    content_hash: str | None,
    decision: str,
    reason: str,
    winner_path: str | None,
) -> None:
    """Upsert a Step-0 decision record for a file."""

    query = f"""
    INSERT INTO {STEP0_DECISIONS_TABLE} (
        absolute_path, content_hash, decision, reason, winner_path
    ) VALUES (?, ?, ?, ?, ?)
    ON CONFLICT(absolute_path) DO UPDATE SET
        content_hash=excluded.content_hash,
        decision=excluded.decision,
        reason=excluded.reason,
        winner_path=excluded.winner_path,
        updated_at=CURRENT_TIMESTAMP
    """
    conn.execute(query, (absolute_path, content_hash, decision, reason, winner_path))


def upsert_step0_artifact(
    conn: sqlite3.Connection,
    *,
    path: str,
    volume: str | None,
    artifact_type: str,
    related_path: str | None,
    orphaned_db: bool | None,
    legacy_marker: bool | None,
    provenance_notes: str | None,
) -> None:
    """Upsert a Step-0 artifact record."""

    query = f"""
    INSERT INTO {STEP0_ARTIFACTS_TABLE} (
        path, volume, artifact_type, related_path, orphaned_db, legacy_marker, provenance_notes
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        volume=excluded.volume,
        artifact_type=excluded.artifact_type,
        related_path=excluded.related_path,
        orphaned_db=excluded.orphaned_db,
        legacy_marker=excluded.legacy_marker,
        provenance_notes=excluded.provenance_notes,
        scanned_at=CURRENT_TIMESTAMP
    """
    conn.execute(
        query,
        (
            path,
            volume,
            artifact_type,
            related_path,
            int(orphaned_db) if orphaned_db is not None else None,
            int(legacy_marker) if legacy_marker is not None else None,
            provenance_notes,
        ),
    )


def fetch_records_by_state(conn: sqlite3.Connection, library_state: str) -> list[sqlite3.Row]:
    cursor = conn.execute(
        f"SELECT * FROM {LIBRARY_TABLE} WHERE library_state = ?",
        (library_state,),
    )
    return cursor.fetchall()


def update_library_path(
    conn: sqlite3.Connection,
    old_path: Path,
    new_path: Path,
    *,
    library_state: str | None = None,
) -> None:
    if library_state is None:
        conn.execute(
            f"UPDATE {LIBRARY_TABLE} SET path=? WHERE path=?",
            (str(new_path), str(old_path)),
        )
    else:
        conn.execute(
            f"UPDATE {LIBRARY_TABLE} SET path=?, library_state=? WHERE path=?",
            (str(new_path), library_state, str(old_path)),
        )


def record_picard_move(conn: sqlite3.Connection, old_path: Path, new_path: Path, checksum: str | None) -> None:
    conn.execute(
        f"INSERT INTO {PICARD_MOVES_TABLE} (old_path, new_path, checksum) VALUES (?, ?, ?)",
        (str(old_path), str(new_path), checksum),
    )

def upsert_file(conn: sqlite3.Connection, file: AudioFile) -> None:
    """
    Inserts or Updates a file record in the database.
    Uses 'path' as the unique key.
    """
    query = """
    INSERT INTO files (
        path, library, zone, mtime, size, checksum, duration, bit_depth, sample_rate, bitrate, 
        metadata_json, flac_ok, integrity_state, acoustid
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        library=excluded.library,
        zone=excluded.zone,
        mtime=excluded.mtime,
        size=excluded.size,
        checksum=excluded.checksum,
        duration=excluded.duration,
        bit_depth=excluded.bit_depth,
        sample_rate=excluded.sample_rate,
        bitrate=excluded.bitrate,
        metadata_json=excluded.metadata_json,
        flac_ok=excluded.flac_ok,
        integrity_state=excluded.integrity_state,
        acoustid=excluded.acoustid;
    """
    
    # Serialize metadata to JSON for storage
    # Normalize parameters: convert any tuple/list/dict to JSON string
    def normalize(value):
        if value is None:
            return None
        if isinstance(value, (list, tuple, dict)):
            return json.dumps(value, ensure_ascii=False)
        return value
    
    # Normalize all metadata values before JSON serialization
    normalized_metadata = {k: (v if not isinstance(v, (list, tuple)) else list(v)) for k, v in file.metadata.items()}
    meta_json = json.dumps(normalized_metadata)
    
    # Build params with normalization on all potentially problematic fields
    params = (
        str(file.path),
        normalize(file.library),
        normalize(file.zone),
        file.mtime,
        file.size,
        normalize(file.checksum),
        file.duration,
        file.bit_depth,
        file.sample_rate,
        file.bitrate,
        meta_json,
        1 if file.flac_ok else 0,
        normalize(file.integrity_state),
        normalize(file.acoustid)
    )
    
    try:
        conn.execute(query, params)
        conn.commit()
    except sqlite3.Error as e:
        logger.error(f"DB Error upserting {file.path}: {e}")
        raise

def get_file(conn: sqlite3.Connection, path: Path) -> Optional[AudioFile]:
    """Retrieve a single file by path."""
    cursor = conn.execute("SELECT * FROM files WHERE path = ?", (str(path),))
    row = cursor.fetchone()
    if not row:
        return None
    
    return _row_to_audiofile(row)

def get_files_by_checksum(conn: sqlite3.Connection, checksum: str) -> List[AudioFile]:
    """Retrieve all files matching a specific checksum."""
    cursor = conn.execute("SELECT * FROM files WHERE checksum = ?", (checksum,))
    return [_row_to_audiofile(row) for row in cursor.fetchall()]

def get_all_checksums(conn: sqlite3.Connection) -> List[str]:
    """Retrieve all unique checksums present in the DB."""
    cursor = conn.execute("SELECT DISTINCT checksum FROM files WHERE checksum IS NOT NULL")
    return [row["checksum"] for row in cursor.fetchall()]

def _row_to_audiofile(row: sqlite3.Row) -> AudioFile:
    """Helper to convert a DB row back to an AudioFile object."""
    # Handle JSON deserialization safely
    meta_json = row["metadata_json"]
    metadata: Dict[str, Any] = {}
    if meta_json:
        try:
            metadata = json.loads(meta_json)
        except json.JSONDecodeError:
            logger.warning(f"Corrupt metadata JSON for {row['path']}")
            metadata = {}

    library = None
    zone = None
    integrity_state = None
    try:
        if "library" in row.keys():
            library = row["library"]
        if "zone" in row.keys():
            zone = row["zone"]
        if "integrity_state" in row.keys():
            integrity_state = row["integrity_state"]
    except Exception:
        library = None
        zone = None
        integrity_state = None

    mtime = None
    size = None
    try:
        if "mtime" in row.keys():
            mtime = row["mtime"]
        if "size" in row.keys():
            size = row["size"]
    except Exception:
        mtime = None
        size = None

    flac_ok = bool(row["flac_ok"])
    if not integrity_state:
        integrity_state = "valid" if flac_ok else "recoverable"

    return AudioFile(
        path=Path(row["path"]),
        library=library,
        zone=zone,
        mtime=mtime,
        size=size,
        checksum=row["checksum"],
        duration=row["duration"],
        bit_depth=row["bit_depth"],
        sample_rate=row["sample_rate"],
        bitrate=row["bitrate"],
        metadata=metadata,
        flac_ok=flac_ok,
        acoustid=row["acoustid"],
        integrity_state=integrity_state
    )
