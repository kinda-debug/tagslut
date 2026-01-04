import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from dedupe.storage.models import AudioFile

logger = logging.getLogger("dedupe")

def upsert_file(conn: sqlite3.Connection, file: AudioFile) -> None:
    """
    Inserts or Updates a file record in the database.
    Uses 'path' as the unique key.
    """
    query = """
    INSERT INTO files (
        path, library, checksum, duration, bit_depth, sample_rate, bitrate, 
        metadata_json, flac_ok, acoustid
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(path) DO UPDATE SET
        library=excluded.library,
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

    return AudioFile(
        path=Path(row["path"]),
        library=library,
        checksum=row["checksum"],
        duration=row["duration"],
        bit_depth=row["bit_depth"],
        sample_rate=row["sample_rate"],
        bitrate=row["bitrate"],
        metadata=metadata,
        flac_ok=bool(row["flac_ok"]),
        acoustid=row["acoustid"]
    )
