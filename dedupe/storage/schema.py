import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Iterable

from dedupe.utils.db import DbReadOnlyError, DbResolutionError, open_db, resolve_db_path

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
SCAN_SESSIONS_TABLE = "scan_sessions"
FILE_SCAN_RUNS_TABLE = "file_scan_runs"
FILE_QUARANTINE_TABLE = "file_quarantine"
SCHEMA_MIGRATIONS_TABLE = "schema_migrations"
INTEGRITY_SCHEMA_VERSION = 1
LIBRARY_SCHEMA_VERSION = 1

def get_connection(
    db_path: Path | str,
    *,
    purpose: str = "write",
    allow_create: bool = False,
    allow_repo_db: bool = False,
    repo_root: Optional[Path] = None,
    source_label: str = "explicit",
) -> sqlite3.Connection:
    """Establish a SQLite connection using the canonical resolver."""
    try:
        resolution = resolve_db_path(
            db_path,
            allow_repo_db=allow_repo_db,
            repo_root=repo_root,
            purpose=purpose,
            allow_create=allow_create,
            source_label=source_label,
        )
        return open_db(resolution)
    except (DbResolutionError, DbReadOnlyError, sqlite3.Error) as e:
        logger.error("Failed to connect to database at %s: %s", db_path, e)
        raise

def init_db(
    conn: sqlite3.Connection | Path | str,
    *,
    allow_create: bool = False,
    allow_repo_db: bool = False,
    repo_root: Optional[Path] = None,
    source_label: str = "explicit",
) -> None:
    """
    Initializes the database schema.
    Performs additive migrations: creates the table if missing,
    and adds missing columns if the table exists but is outdated.
    """
    close_after = False
    connection: sqlite3.Connection
    if isinstance(conn, (str, Path)):
        resolution = resolve_db_path(
            conn,
            allow_repo_db=allow_repo_db,
            repo_root=repo_root,
            purpose="write",
            allow_create=allow_create,
            source_label=source_label,
        )
        connection = open_db(resolution)
        close_after = True
    else:
        connection = conn

    original_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        # Performance tuning (mandatory for multi-library scans)
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        connection.execute("PRAGMA temp_store=MEMORY;")
        connection.execute("PRAGMA cache_size=-200000;")  # -200000 = 200MB cache

        # 1. Create table if it doesn't exist
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                library TEXT,
                zone TEXT,
                mtime REAL,
                size INTEGER,
                checksum TEXT,
                streaminfo_md5 TEXT,
                sha256 TEXT,
                duration REAL,
                bit_depth INTEGER,
                sample_rate INTEGER,
                bitrate INTEGER,
                metadata_json TEXT,
                flac_ok INTEGER,
                integrity_state TEXT,
                integrity_checked_at TEXT,
                streaminfo_checked_at TEXT,
                sha256_checked_at TEXT,
                acoustid TEXT
            );
            """
        )

        # 2. Additive Migrations: Ensure all required columns exist
        existing_columns = _get_existing_columns(connection, "files")
        required_columns = {
            "library": "TEXT",
            "zone": "TEXT",
            "mtime": "REAL",
            "size": "INTEGER",
            "checksum": "TEXT",
            "streaminfo_md5": "TEXT",
            "sha256": "TEXT",
            "duration": "REAL",
            "bit_depth": "INTEGER",
            "sample_rate": "INTEGER",
            "bitrate": "INTEGER",
            "metadata_json": "TEXT",
            "flac_ok": "INTEGER",
            "integrity_state": "TEXT",
            "integrity_checked_at": "TEXT",
            "streaminfo_checked_at": "TEXT",
            "sha256_checked_at": "TEXT",
            "acoustid": "TEXT",
            # Recovery columns
            "recovery_status": "TEXT",
            "recovery_method": "TEXT",
            "backup_path": "TEXT",
            "recovered_at": "TEXT",
            "new_duration": "REAL",
            "duration_delta": "REAL",
            "pcm_md5": "TEXT",
            "silence_events": "INTEGER",
            "verified_at": "TEXT",
            # Enrichment columns - core
            "canonical_title": "TEXT",
            "canonical_artist": "TEXT",
            "canonical_album": "TEXT",
            "canonical_isrc": "TEXT",
            "canonical_duration": "REAL",
            "canonical_duration_source": "TEXT",
            "canonical_year": "INTEGER",
            "canonical_release_date": "TEXT",
            # Enrichment columns - DJ metadata
            "canonical_bpm": "REAL",
            "canonical_key": "TEXT",
            "canonical_genre": "TEXT",
            "canonical_sub_genre": "TEXT",
            # Enrichment columns - release info
            "canonical_label": "TEXT",
            "canonical_catalog_number": "TEXT",
            "canonical_mix_name": "TEXT",
            "canonical_explicit": "INTEGER",
            # Enrichment columns - Spotify audio features
            "canonical_energy": "REAL",
            "canonical_danceability": "REAL",
            "canonical_valence": "REAL",
            "canonical_acousticness": "REAL",
            "canonical_instrumentalness": "REAL",
            "canonical_loudness": "REAL",
            # Enrichment columns - artwork
            "canonical_album_art_url": "TEXT",
            # Enrichment columns - provider IDs
            "spotify_id": "TEXT",
            "beatport_id": "TEXT",
            "tidal_id": "TEXT",
            "qobuz_id": "TEXT",
            "itunes_id": "TEXT",
            # Enrichment columns - status
            "enriched_at": "TEXT",
            "enrichment_providers": "TEXT",
            "enrichment_confidence": "TEXT",
            "metadata_health": "TEXT",
            "metadata_health_reason": "TEXT",
            # Track-hub link (library_tracks/library_track_sources)
            "library_track_key": "TEXT",
        }

        for col_name, col_type in required_columns.items():
            if col_name not in existing_columns:
                logger.info(
                    "Migrating DB: Adding column '%s' to 'files' table.",
                    col_name,
                )
                connection.execute(f"ALTER TABLE files ADD COLUMN {col_name} {col_type}")

        # 3. Indices for performance
        connection.execute("CREATE INDEX IF NOT EXISTS idx_checksum ON files(checksum);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_acoustid ON files(acoustid);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_streaminfo_md5 ON files(streaminfo_md5);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sha256 ON files(sha256);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_recovery_status ON files(recovery_status);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_integrity_state ON files(integrity_state);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_enriched_at ON files(enriched_at);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_canonical_isrc ON files(canonical_isrc);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_library_track_key ON files(library_track_key);")

        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {FILE_QUARANTINE_TABLE} (
                id INTEGER PRIMARY KEY,
                original_path TEXT NOT NULL,
                quarantine_path TEXT NOT NULL,
                sha256 TEXT,
                keeper_path TEXT,
                source_zone TEXT,
                reason TEXT,
                tier TEXT,
                plan_id TEXT,
                quarantined_at TEXT NOT NULL,
                deleted_at TEXT,
                delete_reason TEXT
            );
            """
        )
        quarantine_columns = {
            "original_path": "TEXT",
            "quarantine_path": "TEXT",
            "sha256": "TEXT",
            "keeper_path": "TEXT",
            "source_zone": "TEXT",
            "reason": "TEXT",
            "tier": "TEXT",
            "plan_id": "TEXT",
            "quarantined_at": "TEXT",
            "deleted_at": "TEXT",
            "delete_reason": "TEXT",
        }
        _add_missing_columns(connection, FILE_QUARANTINE_TABLE, quarantine_columns)
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{FILE_QUARANTINE_TABLE}_quarantined_at "
            f"ON {FILE_QUARANTINE_TABLE}(quarantined_at);"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{FILE_QUARANTINE_TABLE}_deleted_at "
            f"ON {FILE_QUARANTINE_TABLE}(deleted_at);"
        )
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{FILE_QUARANTINE_TABLE}_sha256 "
            f"ON {FILE_QUARANTINE_TABLE}(sha256);"
        )

        # Promotions tracking table
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path TEXT NOT NULL UNIQUE,
                dest_path TEXT NOT NULL,
                mode TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_promotions_source "
            "ON promotions(source_path);"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_promotions_timestamp "
            "ON promotions(timestamp);"
        )

        # Library tracks table (canonical track identity for enrichment)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS library_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_track_key TEXT UNIQUE,
                title TEXT,
                artist TEXT,
                album TEXT,
                duration_ms INTEGER,
                isrc TEXT,
                release_date TEXT,
                explicit INTEGER,
                best_cover_url TEXT,
                lyrics_excerpt TEXT,
                genre TEXT,
                bpm REAL,
                musical_key TEXT,
                label TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_tracks_isrc ON library_tracks(isrc);"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_tracks_key ON library_tracks(library_track_key);"
        )

        # Library track sources table (per-provider metadata snapshots)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS library_track_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_track_key TEXT,
                service TEXT,
                service_track_id TEXT,
                url TEXT,
                metadata_json TEXT,
                duration_ms INTEGER,
                isrc TEXT,
                album_art_url TEXT,
                pdf_companions TEXT,
                lyrics_excerpt TEXT,
                genre TEXT,
                bpm REAL,
                musical_key TEXT,
                album_title TEXT,
                artist_name TEXT,
                track_number INTEGER,
                disc_number INTEGER,
                match_confidence TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(library_track_key) REFERENCES library_tracks(library_track_key)
            );
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_track_sources_key "
            "ON library_track_sources(library_track_key);"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_track_sources_service "
            "ON library_track_sources(service);"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_track_sources_isrc "
            "ON library_track_sources(isrc);"
        )

        # Helpful for deduping repeated upserts without requiring a unique constraint.
        # (We delete-then-insert in code to avoid index creation failures on existing DBs.)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_library_track_sources_triplet "
            "ON library_track_sources(library_track_key, service, service_track_id);"
        )

        _ensure_scan_tracking_tables(connection)
        _record_schema_version(connection, schema_name="integrity", version=INTEGRITY_SCHEMA_VERSION)

        # Migrate the 'files' table as well
        try:
            existing_files_columns = _get_existing_columns(connection, "files")
            files_columns = {
                "checksum_type": "TEXT",
            }
            for col_name, col_type in files_columns.items():
                if col_name not in existing_files_columns:
                    connection.execute(f"ALTER TABLE files ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            # Table 'files' might not exist in some test scenarios
            pass

        # Handle legacy 'library_files' table if it exists
        try:
            existing_library_columns = _get_existing_columns(connection, LIBRARY_TABLE)
            if existing_library_columns:
                library_columns = {
                    "score_integrity": "REAL",
                    "score_audio": "REAL",
                    "score_tags": "REAL",
                    "score_total": "REAL",
                }
                for col_name, col_type in library_columns.items():
                    if col_name not in existing_library_columns:
                        connection.execute(f"ALTER TABLE {LIBRARY_TABLE} ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            # Table LIBRARY_TABLE might not exist yet
            pass

        connection.commit()
    except sqlite3.OperationalError as e:
        if "readonly" in str(e).lower():
            raise DbReadOnlyError(
                "Database is read-only. Fix permissions or open a writable copy "
                "before running migrations."
            ) from e
        raise
    finally:
        connection.row_factory = original_factory
        if close_after:
            connection.close()


def initialise_library_schema(connection: sqlite3.Connection) -> None:
    """Create/upgrade the legacy unified library schema.

    This is intentionally additive and safe to call repeatedly.
    """

    with connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")

        # Ensure base columns exist
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
                score_integrity REAL,
                score_audio REAL,
                score_tags REAL,
                score_total REAL
            )
            """
        )

        existing_columns = _get_existing_columns(connection, LIBRARY_TABLE)
        library_columns = {
            "library_state": "TEXT",
            "flac_ok": "INTEGER",
            "integrity_state": "TEXT",
            "zone": "TEXT",
            "checksum_type": "TEXT",
            "streaminfo_md5": "TEXT",
            "sha256": "TEXT",
            "bitrate": "INTEGER",
            "metadata_json": "TEXT",
        }
        for col_name, col_type in library_columns.items():
            if col_name not in existing_columns:
                logger.info(
                    "Migrating DB: Adding column '%s' to '%s' table.",
                    col_name,
                    LIBRARY_TABLE,
                )
                connection.execute(f"ALTER TABLE {LIBRARY_TABLE} ADD COLUMN {col_name} {col_type}")

        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{LIBRARY_TABLE}_checksum ON {LIBRARY_TABLE}(checksum)"
        )
        # Surgical indexing for matching queries
        connection.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{LIBRARY_TABLE}_checksum_size ON {LIBRARY_TABLE}(checksum, size_bytes)"
        )
        try:
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{LIBRARY_TABLE}_streaminfo ON {LIBRARY_TABLE}(streaminfo_md5)"
            )
        except sqlite3.OperationalError:
            # Table or column might not exist yet if this is called early
            pass

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
        _ensure_scan_tracking_tables(connection)
        _record_schema_version(connection, schema_name="library", version=LIBRARY_SCHEMA_VERSION)


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
    columns: list[str] = []
    for row in cursor.fetchall():
        if isinstance(row, sqlite3.Row):
            columns.append(row["name"])
        else:
            columns.append(row[1])
    return columns


def _add_missing_columns(
    conn: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing = set(_get_existing_columns(conn, table_name))
    for name, definition in columns.items():
        if name in existing:
            continue
        logger.info("Migrating DB: Adding column '%s' to '%s' table.", name, table_name)
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {definition}")


def _ensure_scan_tracking_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCAN_SESSIONS_TABLE} (
            id INTEGER PRIMARY KEY,
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            ended_at TEXT,
            finished_at TEXT,
            db_path TEXT,
            library TEXT,
            zone TEXT,
            root_path TEXT,
            paths_source TEXT,
            paths_from_file TEXT,
            scan_integrity INTEGER,
            scan_hash INTEGER,
            recheck INTEGER,
            incremental INTEGER,
            force_all INTEGER,
            discovered INTEGER,
            considered INTEGER,
            skipped INTEGER,
            updated INTEGER,
            succeeded INTEGER,
            failed INTEGER,
            scan_limit INTEGER,
            status TEXT,
            host TEXT
        );
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{SCAN_SESSIONS_TABLE}_started_at ON {SCAN_SESSIONS_TABLE}(started_at);"
    )

    scan_session_columns = {
        "finished_at": "TEXT",
        "paths_from_file": "TEXT",
        "updated": "INTEGER",
        "scan_limit": "INTEGER",
    }
    _add_missing_columns(conn, SCAN_SESSIONS_TABLE, scan_session_columns)

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {FILE_SCAN_RUNS_TABLE} (
            id INTEGER PRIMARY KEY,
            session_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            mtime REAL,
            size INTEGER,
            streaminfo_md5 TEXT,
            streaminfo_checked_at TEXT,
            sha256 TEXT,
            sha256_checked_at TEXT,
            flac_ok INTEGER,
            integrity_state TEXT,
            integrity_checked_at TEXT,
            outcome TEXT,
            checked_metadata INTEGER,
            checked_integrity INTEGER,
            checked_hash INTEGER,
            checked_streaminfo INTEGER,
            error_class TEXT,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES {SCAN_SESSIONS_TABLE}(id)
        );
        """
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{FILE_SCAN_RUNS_TABLE}_session ON {FILE_SCAN_RUNS_TABLE}(session_id);"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{FILE_SCAN_RUNS_TABLE}_path ON {FILE_SCAN_RUNS_TABLE}(path);"
    )

    file_scan_columns = {
        "outcome": "TEXT",
        "checked_metadata": "INTEGER",
        "checked_integrity": "INTEGER",
        "checked_hash": "INTEGER",
        "checked_streaminfo": "INTEGER",
    }
    _add_missing_columns(conn, FILE_SCAN_RUNS_TABLE, file_scan_columns)


def _record_schema_version(
    conn: sqlite3.Connection,
    *,
    schema_name: str,
    version: int,
) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATIONS_TABLE} (
            id INTEGER PRIMARY KEY,
            schema_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            UNIQUE(schema_name, version)
        )
        """
    )
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current < version:
        conn.execute(f"PRAGMA user_version = {version}")
    conn.execute(
        f"""
        INSERT OR IGNORE INTO {SCHEMA_MIGRATIONS_TABLE} (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (schema_name, version, f"init_{schema_name}_schema"),
    )
