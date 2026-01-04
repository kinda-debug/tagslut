import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Iterable

from dedupe.storage.models import AudioFile
from dedupe.storage.schema import LIBRARY_TABLE, PICARD_MOVES_TABLE

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
    ]

    placeholders = ",".join(["?"] * len(columns))
    assignments = ",".join([f"{col}=excluded.{col}" for col in columns if col != "path"])
    query = (
        f"INSERT INTO {LIBRARY_TABLE} ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(path) DO UPDATE SET {assignments}"
    )

    values = [tuple(row.get(col) for col in columns) for row in payload]
    conn.executemany(query, values)


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
        path, library, mtime, size, checksum, duration, bit_depth, sample_rate, bitrate, 
        metadata_json, flac_ok, acoustid
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        library=excluded.library,
        mtime=excluded.mtime,
        size=excluded.size,
        checksum=excluded.checksum,
        duration=excluded.duration,
        bit_depth=excluded.bit_depth,
        sample_rate=excluded.sample_rate,
        bitrate=excluded.bitrate,
        metadata_json=excluded.metadata_json,
        flac_ok=excluded.flac_ok,
        acoustid=excluded.acoustid;
    """
    
    # Serialize metadata to JSON for storage
    meta_json = json.dumps(file.metadata)
    
    try:
        conn.execute(query, (
            str(file.path),
            file.library,
            file.mtime,
            file.size,
            file.checksum,
            file.duration,
            file.bit_depth,
            file.sample_rate,
            file.bitrate,
            meta_json,
            1 if file.flac_ok else 0,
            file.acoustid
        ))
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
    try:
        if "library" in row.keys():
            library = row["library"]
    except Exception:
        library = None

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

    return AudioFile(
        path=Path(row["path"]),
        library=library,
        mtime=mtime,
        size=size,
        checksum=row["checksum"],
        duration=row["duration"],
        bit_depth=row["bit_depth"],
        sample_rate=row["sample_rate"],
        bitrate=row["bitrate"],
        metadata=metadata,
        flac_ok=bool(row["flac_ok"]),
        acoustid=row["acoustid"]
    )
