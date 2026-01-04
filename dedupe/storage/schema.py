import sqlite3
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger("dedupe")

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
        checksum TEXT,
        duration REAL,
        bit_depth INTEGER,
        sample_rate INTEGER,
        bitrate INTEGER,
        metadata_json TEXT,
        flac_ok INTEGER,
        acoustid TEXT
    );
    """)
    
    # 2. Additive Migrations: Ensure all required columns exist
    existing_columns = _get_existing_columns(conn, "files")
    required_columns = {
        "library": "TEXT",
        "checksum": "TEXT",
        "duration": "REAL",
        "bit_depth": "INTEGER",
        "sample_rate": "INTEGER",
        "bitrate": "INTEGER",
        "metadata_json": "TEXT",
        "flac_ok": "INTEGER",
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

def _get_existing_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    """Helper to retrieve a list of column names for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row["name"] for row in cursor.fetchall()]
