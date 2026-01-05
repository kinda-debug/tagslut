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
    # Enable Write-Ahead Logging for better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    
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
            f"CREATE INDEX IF NOT EXISTS idx_{STEP0_INTEGRITY_TABLE}_hash ON {STEP0_INTEGRITY_TABLE}(content_hash)"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{STEP0_SCAN_TABLE}_timestamp ON {STEP0_SCAN_TABLE}(timestamp)"
        )

def _get_existing_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """Helper to retrieve a list of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row["name"] for row in cursor.fetchall()]
