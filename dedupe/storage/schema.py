import sqlite3
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger("dedupe")

# Legacy unified library schema (used by `dedupe` CLI + tests)
LIBRARY_TABLE = "library_files"
PICARD_MOVES_TABLE = "picard_moves"
STEP0_AUDIO_CONTENT_TABLE = "audio_content"
STEP0_INTEGRITY_TABLE = "integrity_results"
STEP0_IDENTITY_TABLE = "identity_hints"
STEP0_CANONICAL_TABLE = "canonical_map"
STEP0_REACQUIRE_TABLE = "reacquire_manifest"
STEP0_SCAN_TABLE = "scan_events"
STEP0_FILES_TABLE = "step0_files"
STEP0_HASHES_TABLE = "step0_hashes"
STEP0_DECISIONS_TABLE = "step0_decisions"
STEP0_ARTIFACTS_TABLE = "step0_artifacts"

def get_connection(db_path: Path) -> sqlite3.Connection:
    """
    Establishes a connection to the SQLite database.
    Sets row_factory to sqlite3.Row for name-based access.
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.error(f"Failed to connect to database at {db_path}: {e}")
        raise

def init_db(conn: sqlite3.Connection) -> None:
    """
    Initializes the database schema.
    Performs additive migrations: creates the table if missing,
    and adds missing columns if the table exists but is outdated.
    """
    # Performance tuning (mandatory for multi-library scans)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-200000;")  # -200000 = 200MB cache
    
    # 1. Create table if it doesn't exist
    conn.execute("""
    CREATE TABLE IF NOT EXISTS files (
        path TEXT PRIMARY KEY,
        library TEXT,
        zone TEXT,
        mtime REAL,
        size INTEGER,
        checksum TEXT,
        duration REAL,
        bit_depth INTEGER,
        sample_rate INTEGER,
        bitrate INTEGER,
        metadata_json TEXT,
        flac_ok INTEGER,
        integrity_state TEXT,
        acoustid TEXT
    );
    """)
    
    # 2. Additive Migrations: Ensure all required columns exist
    existing_columns = _get_existing_columns(conn, "files")
    required_columns = {
        "library": "TEXT",
        "zone": "TEXT",
        "mtime": "REAL",
        "size": "INTEGER",
        "checksum": "TEXT",
        "duration": "REAL",
        "bit_depth": "INTEGER",
        "sample_rate": "INTEGER",
        "bitrate": "INTEGER",
        "metadata_json": "TEXT",
        "flac_ok": "INTEGER",
        "integrity_state": "TEXT",
        "acoustid": "TEXT"
    }

    for col_name, col_type in required_columns.items():
        if col_name not in existing_columns:
            logger.info(f"Migrating DB: Adding column '{col_name}' to 'files' table.")
            try:
                conn.execute(f"ALTER TABLE files ADD COLUMN {col_name} {col_type}")
            except sqlite3.OperationalError as e:
                logger.error(f"Migration failed for column {col_name}: {e}")
                raise

    # 3. Indices for performance
    conn.execute("CREATE INDEX IF NOT EXISTS idx_checksum ON files(checksum);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_acoustid ON files(acoustid);")
    
    conn.commit()


def initialise_library_schema(connection: sqlite3.Connection) -> None:
    """Create/upgrade the legacy unified library schema.

    This is intentionally additive and safe to call repeatedly.
    """

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

        existing_columns = _get_existing_columns(connection, LIBRARY_TABLE)
        library_columns = {
            "library_state": "TEXT",
            "flac_ok": "INTEGER",
            "integrity_state": "TEXT",
            "zone": "TEXT",
        }
        for col_name, col_type in library_columns.items():
            if col_name not in existing_columns:
                logger.info(
                    "Migrating DB: Adding column '%s' to '%s' table.",
                    col_name,
                    LIBRARY_TABLE,
                )
                connection.execute(
                    f"ALTER TABLE {LIBRARY_TABLE} ADD COLUMN {col_name} {col_type}"
                )

        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {PICARD_MOVES_TABLE} (
                id INTEGER PRIMARY KEY,
                old_path TEXT NOT NULL,
                new_path TEXT NOT NULL,
                checksum TEXT,
                moved_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{PICARD_MOVES_TABLE}_checksum ON {PICARD_MOVES_TABLE}(checksum)"
        )


def initialise_step0_schema(connection: sqlite3.Connection) -> None:
    """Create/upgrade Step-0 ingestion tables.

    This is intentionally additive and safe to call repeatedly.
    """

    with connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_AUDIO_CONTENT_TABLE} (
                content_hash TEXT PRIMARY KEY,
                streaminfo_md5 TEXT,
                duration REAL,
                sample_rate INTEGER,
                bit_depth INTEGER,
                channels INTEGER,
                hash_type TEXT,
                coverage TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_INTEGRITY_TABLE} (
                id INTEGER PRIMARY KEY,
                content_hash TEXT,
                path TEXT,
                checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT,
                stderr_excerpt TEXT,
                return_code INTEGER
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_IDENTITY_TABLE} (
                content_hash TEXT PRIMARY KEY,
                isrc TEXT,
                musicbrainz_track_id TEXT,
                musicbrainz_release_id TEXT,
                artist TEXT,
                title TEXT,
                album TEXT,
                track_number TEXT,
                disc_number TEXT,
                date TEXT,
                tags_json TEXT
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_CANONICAL_TABLE} (
                content_hash TEXT PRIMARY KEY,
                canonical_path TEXT,
                reason TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_REACQUIRE_TABLE} (
                content_hash TEXT PRIMARY KEY,
                reason TEXT,
                confidence REAL,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_SCAN_TABLE} (
                id INTEGER PRIMARY KEY,
                inputs_json TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                version TEXT,
                library_tag TEXT
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_FILES_TABLE} (
                absolute_path TEXT PRIMARY KEY,
                content_hash TEXT,
                volume TEXT,
                zone TEXT,
                library TEXT,
                size_bytes INTEGER,
                mtime REAL,
                scan_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                audio_integrity TEXT,
                flac_test_passed INTEGER,
                flac_error TEXT,
                duration_seconds REAL,
                sample_rate INTEGER,
                bit_depth INTEGER,
                channels INTEGER,
                hash_strategy TEXT,
                provenance_notes TEXT,
                orphaned_db INTEGER DEFAULT 0,
                legacy_marker INTEGER DEFAULT 0
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_HASHES_TABLE} (
                id INTEGER PRIMARY KEY,
                absolute_path TEXT NOT NULL,
                hash_type TEXT NOT NULL,
                hash_value TEXT NOT NULL,
                coverage TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(absolute_path, hash_type)
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_DECISIONS_TABLE} (
                absolute_path TEXT PRIMARY KEY,
                content_hash TEXT,
                decision TEXT,
                reason TEXT,
                winner_path TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {STEP0_ARTIFACTS_TABLE} (
                path TEXT PRIMARY KEY,
                volume TEXT,
                artifact_type TEXT,
                related_path TEXT,
                orphaned_db INTEGER DEFAULT 0,
                legacy_marker INTEGER DEFAULT 0,
                provenance_notes TEXT,
                scanned_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{STEP0_INTEGRITY_TABLE}_hash ON {STEP0_INTEGRITY_TABLE}(content_hash)"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{STEP0_SCAN_TABLE}_timestamp ON {STEP0_SCAN_TABLE}(timestamp)"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{STEP0_FILES_TABLE}_hash ON {STEP0_FILES_TABLE}(content_hash)"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{STEP0_HASHES_TABLE}_hash ON {STEP0_HASHES_TABLE}(hash_value)"
        )

        existing_audio_content = _get_existing_columns(connection, STEP0_AUDIO_CONTENT_TABLE)
        audio_content_columns = {
            "hash_type": "TEXT",
            "coverage": "TEXT",
        }
        for col_name, col_type in audio_content_columns.items():
            if col_name not in existing_audio_content:
                logger.info(
                    "Migrating DB: Adding column '%s' to '%s' table.",
                    col_name,
                    STEP0_AUDIO_CONTENT_TABLE,
                )
                connection.execute(
                    f"ALTER TABLE {STEP0_AUDIO_CONTENT_TABLE} ADD COLUMN {col_name} {col_type}"
                )

def _get_existing_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """Helper to retrieve a list of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row["name"] for row in cursor.fetchall()]
