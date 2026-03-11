import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterable, cast

from tagslut.storage.models import AudioFile
from tagslut.zones import coerce_zone
from tagslut.storage.schema import (
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

logger = logging.getLogger(__name__)


def _normalize_metadata_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple, set)):
        return [_normalize_metadata_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _normalize_metadata_value(v) for k, v in value.items()}
    return str(value)


def _normalize_text_field(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return str(getattr(value, "value"))
        except Exception as e:
            logger.warning("Failed to coerce %s via .value from %r: %s", field_name, value, e)
            pass
    if isinstance(value, str):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, int):
        # streaminfo_md5 can be an int from mutagen
        return f"{value:032x}" if field_name == "streaminfo_md5" else str(value)
    if isinstance(value, (list, tuple)):
        candidates: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, str):
                candidates.append(item)
            elif isinstance(item, (bytes, bytearray)):
                candidates.append(item.decode("utf-8", errors="replace"))
            else:
                candidates.append(str(item))
        if not candidates:
            logger.warning("Dropping %s: empty sequence %r", field_name, value)
            return None
        if len(candidates) == 1:
            return candidates[0]
        joined = ";".join(candidates)
        logger.warning("Coalescing %s from sequence to %r", field_name, joined)
        return joined
    if isinstance(value, dict):
        logger.warning("Dropping %s: dict not supported for scalar field", field_name)
        return None
    logger.warning(
        "Dropping %s: unsupported value type %s",
        field_name,
        type(value).__name__,
    )
    return None


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


def insert_scan_session(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    library: str | None,
    zone: str | None,
    root_path: Path | None,
    paths_source: str | None,
    paths_from_file: str | None = None,
    scan_integrity: bool,
    scan_hash: bool,
    recheck: bool,
    incremental: bool,
    force_all: bool,
    discovered: int,
    considered: int,
    skipped: int,
    scan_limit: int | None = None,
    host: str | None,
) -> int:
    query = """
    INSERT INTO scan_sessions (
        db_path, library, zone, root_path, paths_source, paths_from_file,
        scan_integrity, scan_hash, recheck, incremental, force_all,
        discovered, considered, skipped, scan_limit, status, host
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cursor = conn.execute(
        query,
        (
            str(db_path),
            library,
            zone,
            str(root_path) if root_path else None,
            paths_source,
            paths_from_file,
            int(scan_integrity),
            int(scan_hash),
            int(recheck),
            int(incremental),
            int(force_all),
            discovered,
            considered,
            skipped,
            scan_limit,
            "running",
            host,
        ),
    )
    rowid = cursor.lastrowid
    if rowid is None:
        raise RuntimeError("Failed to insert scan session; no rowid returned.")
    return rowid


def finalize_scan_session(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    status: str,
    succeeded: int,
    failed: int,
    ended_at: str,
    updated: int | None = None,
) -> None:
    updated_count = succeeded if updated is None else updated
    conn.execute(
        """
        UPDATE scan_sessions
        SET ended_at=?, finished_at=?, status=?, succeeded=?, failed=?, updated=?
        WHERE id=?
        """,
        (ended_at, ended_at, status, succeeded, failed, updated_count, session_id),
    )


def insert_file_scan_run(
    conn: sqlite3.Connection,
    *,
    session_id: int,
    path: Path,
    file: AudioFile | None = None,
    outcome: str | None = None,
    checked_metadata: bool | None = None,
    checked_integrity: bool | None = None,
    checked_hash: bool | None = None,
    checked_streaminfo: bool | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    mtime: float | None = None,
    size: int | None = None,
    streaminfo_md5: str | None = None,
    streaminfo_checked_at: str | None = None,
    sha256: str | None = None,
    sha256_checked_at: str | None = None,
    flac_ok: bool | None = None,
    integrity_state: str | None = None,
    integrity_checked_at: str | None = None,
) -> None:
    def _short(value: str | None, limit: int = 300) -> str | None:
        if not value:
            return None
        return value if len(value) <= limit else value[:limit]

    if file:
        mtime = file.mtime
        size = file.size
        streaminfo_md5 = _normalize_text_field(file.streaminfo_md5, "streaminfo_md5")
        streaminfo_checked_at = _normalize_text_field(
            file.streaminfo_checked_at, "streaminfo_checked_at"
        )
        sha256 = _normalize_text_field(file.sha256, "sha256")
        sha256_checked_at = _normalize_text_field(file.sha256_checked_at, "sha256_checked_at")
        flac_ok = None if file.flac_ok is None else bool(file.flac_ok)
        integrity_state = _normalize_text_field(file.integrity_state, "integrity_state")
        integrity_checked_at = _normalize_text_field(
            file.integrity_checked_at, "integrity_checked_at"
        )

    outcome_value = outcome
    if outcome_value is None:
        outcome_value = "failed" if error_class else "succeeded"

    conn.execute(
        """
        INSERT INTO file_scan_runs (
            session_id, path, mtime, size, streaminfo_md5, streaminfo_checked_at,
            sha256, sha256_checked_at, flac_ok, integrity_state, integrity_checked_at,
            outcome, checked_metadata, checked_integrity, checked_hash, checked_streaminfo,
            error_class, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            str(path),
            mtime,
            size,
            _normalize_text_field(streaminfo_md5, "streaminfo_md5"),
            _normalize_text_field(streaminfo_checked_at, "streaminfo_checked_at"),
            _normalize_text_field(sha256, "sha256"),
            _normalize_text_field(sha256_checked_at, "sha256_checked_at"),
            None if flac_ok is None else int(bool(flac_ok)),
            _normalize_text_field(integrity_state, "integrity_state"),
            _normalize_text_field(integrity_checked_at, "integrity_checked_at"),
            outcome_value,
            None if checked_metadata is None else int(bool(checked_metadata)),
            None if checked_integrity is None else int(bool(checked_integrity)),
            None if checked_hash is None else int(bool(checked_hash)),
            None if checked_streaminfo is None else int(bool(checked_streaminfo)),
            _normalize_text_field(error_class, "error_class"),
            _short(_normalize_text_field(error_message, "error_message")),
        ),
    )


def upsert_file(conn: sqlite3.Connection, file: AudioFile) -> None:
    """
    Inserts or Updates a file record in the database.
    Uses 'path' as the unique key.
    """
    query = """
    INSERT INTO files (
        path, library, zone, mtime, size, checksum, streaminfo_md5, sha256, duration,
        bit_depth, sample_rate, bitrate, metadata_json, flac_ok, integrity_state,
        integrity_checked_at, streaminfo_checked_at, sha256_checked_at, acoustid, original_path,
        checksum_type, dj_set_role, dj_subrole
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        library=excluded.library,
        zone=excluded.zone,
        mtime=excluded.mtime,
        size=excluded.size,
        checksum=excluded.checksum,
        streaminfo_md5=excluded.streaminfo_md5,
        sha256=excluded.sha256,
        duration=excluded.duration,
        bit_depth=excluded.bit_depth,
        sample_rate=excluded.sample_rate,
        bitrate=excluded.bitrate,
        metadata_json=excluded.metadata_json,
        flac_ok=excluded.flac_ok,
        integrity_state=excluded.integrity_state,
        integrity_checked_at=excluded.integrity_checked_at,
        streaminfo_checked_at=excluded.streaminfo_checked_at,
        sha256_checked_at=excluded.sha256_checked_at,
        acoustid=excluded.acoustid,
        original_path=excluded.original_path,
        checksum_type=excluded.checksum_type,
        dj_set_role=excluded.dj_set_role,
        dj_subrole=excluded.dj_subrole;
    """

    normalized_metadata = {
        k: _normalize_metadata_value(v) for k, v in (file.metadata or {}).items()
    }
    meta_json = json.dumps(normalized_metadata, sort_keys=True, separators=(",", ":"))

    flac_ok_value = None if file.flac_ok is None else int(bool(file.flac_ok))
    integrity_state = _normalize_text_field(file.integrity_state, "integrity_state")
    acoustid = _normalize_text_field(file.acoustid, "acoustid")

    params = (
        str(file.path),
        _normalize_text_field(file.library, "library"),
        _normalize_text_field(file.zone, "zone"),
        file.mtime,
        file.size,
        _normalize_text_field(file.checksum, "checksum"),
        _normalize_text_field(file.streaminfo_md5, "streaminfo_md5"),
        _normalize_text_field(file.sha256, "sha256"),
        file.duration,
        file.bit_depth,
        file.sample_rate,
        file.bitrate,
        meta_json,
        flac_ok_value,
        integrity_state,
        _normalize_text_field(file.integrity_checked_at, "integrity_checked_at"),
        _normalize_text_field(file.streaminfo_checked_at, "streaminfo_checked_at"),
        _normalize_text_field(file.sha256_checked_at, "sha256_checked_at"),
        acoustid,
        _normalize_text_field(file.original_path, "original_path"),
        _normalize_text_field(file.checksum_type, "checksum_type"),
        _normalize_text_field(file.dj_set_role, "dj_set_role"),
        _normalize_text_field(file.dj_subrole, "dj_subrole"),
    )

    try:
        conn.execute(query, params)
    except sqlite3.Error as e:
        logger.error(f"DB Error upserting {file.path}: {e}")
        for idx, param in enumerate(params):
            logger.debug(f"  Param {idx}: {type(param).__name__} = {repr(param)[:100]}")
        raise


def get_file(conn: sqlite3.Connection, path: Path) -> Optional[AudioFile]:
    """Retrieve a single file by path."""
    cursor = conn.execute("SELECT * FROM files WHERE path = ?", (str(path),))
    row = cursor.fetchone()
    if not row:
        return None

    return _row_to_audiofile(row)


def get_file_by_isrc(conn: sqlite3.Connection, isrc: str | None) -> Optional[sqlite3.Row]:
    """Primary identity lookup — use this before any other lookup."""
    if isrc is None:
        return None
    normalized = str(isrc).strip()
    if not normalized:
        return None
    row = conn.execute(
        "SELECT path, quality_rank, isrc FROM files WHERE isrc = ? LIMIT 1",
        (normalized,),
    ).fetchone()
    return cast(Optional[sqlite3.Row], row)


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
    row_keys = set(row.keys())

    def _get(key: str, default: Any = None) -> Any:
        return row[key] if key in row_keys else default

    # Handle JSON deserialization safely
    meta_json = _get("metadata_json")
    metadata: Dict[str, Any] = {}
    if meta_json:
        try:
            metadata = json.loads(meta_json)
        except json.JSONDecodeError:
            logger.warning(f"Corrupt metadata JSON for {row['path']}")
            metadata = {}

    library = _get("library")
    zone = coerce_zone(_get("zone"))
    integrity_state = _get("integrity_state")
    mtime = _get("mtime")
    size = _get("size")

    flac_ok = _get("flac_ok")
    if flac_ok is not None:
        flac_ok = bool(flac_ok)
    if not integrity_state and flac_ok is not None:
        integrity_state = "valid" if flac_ok else "recoverable"

    return AudioFile(
        path=Path(row["path"]),
        library=library,
        zone=zone,
        mtime=mtime,
        size=size,
        checksum=_get("checksum", ""),
        streaminfo_md5=_get("streaminfo_md5"),
        sha256=_get("sha256"),
        duration=_get("duration"),
        bit_depth=_get("bit_depth"),
        sample_rate=_get("sample_rate"),
        bitrate=_get("bitrate"),
        metadata=metadata,
        flac_ok=flac_ok,
        acoustid=_get("acoustid"),
        original_path=_get("original_path"),
        integrity_state=integrity_state,
        integrity_checked_at=_get("integrity_checked_at"),
        streaminfo_checked_at=_get("streaminfo_checked_at"),
        sha256_checked_at=_get("sha256_checked_at"),
        checksum_type=_get("checksum_type"),
        dj_set_role=_get("dj_set_role"),
        dj_subrole=_get("dj_subrole"),
    )
