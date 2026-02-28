import sqlite3
import logging
from pathlib import Path
from typing import List, Optional, Iterable

from tagslut.utils.db import DbReadOnlyError, DbResolutionError, open_db, resolve_db_path

logger = logging.getLogger("tagslut")

# Legacy unified library schema (used by `tagslut` CLI + tests)
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
V3_ASSET_FILE_TABLE = "asset_file"
V3_TRACK_IDENTITY_TABLE = "track_identity"
V3_ASSET_LINK_TABLE = "asset_link"
V3_PROVENANCE_EVENT_TABLE = "provenance_event"
V3_MOVE_PLAN_TABLE = "move_plan"
V3_MOVE_EXECUTION_TABLE = "move_execution"
INTEGRITY_SCHEMA_VERSION = 1
LIBRARY_SCHEMA_VERSION = 1
V3_SCHEMA_VERSION = 1

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
            # Management & Inventory fields (tagslut mgmt)
            "download_source": "TEXT",  # bpdl, qobuz, tidal, legacy
            "download_date": "TEXT",  # ISO timestamp
            "original_path": "TEXT",  # Source location before canonical move
            "mgmt_status": "TEXT",  # new → checked → verified → moved
            "fingerprint": "TEXT",  # chromaprint for fuzzy matching
            "m3u_exported": "TEXT",  # Last M3U export timestamp
            "m3u_path": "TEXT",  # Path to latest M3U containing this file
            # Duration safety fields (DJ-safe promotion)
            "is_dj_material": "INTEGER DEFAULT 0",
            "duration_ref_ms": "INTEGER",
            "duration_ref_source": "TEXT",
            "duration_ref_track_id": "TEXT",
            "duration_ref_updated_at": "TEXT",
            "duration_measured_ms": "INTEGER",
            "duration_measured_at": "TEXT",
            "duration_delta_ms": "INTEGER",
            "duration_status": "TEXT",
            "duration_check_version": "TEXT",
            # DJ pool output tracking
            "dj_pool_path": "TEXT",
            "quality_rank": "INTEGER",
            "rekordbox_id": "INTEGER",
            "last_exported_usb": "TEXT",
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
        connection.execute("CREATE INDEX IF NOT EXISTS idx_download_source ON files(download_source);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_mgmt_status ON files(mgmt_status);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_fingerprint ON files(fingerprint);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_original_path ON files(original_path);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_files_mtime ON files(mtime);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_files_path_mtime ON files(path, mtime);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_is_dj_material ON files(is_dj_material);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_duration_status ON files(duration_status);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_duration_ref_track_id ON files(duration_ref_track_id);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_quality_rank ON files(quality_rank);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_dj_pool_path ON files(dj_pool_path);")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_last_exported_usb ON files(last_exported_usb);")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_duration_mtime ON files(duration_status, mtime);"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_files_duration_source_mtime "
            "ON files(duration_status, download_source, mtime);"
        )

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
            """
            CREATE TABLE IF NOT EXISTS track_duration_refs (
                ref_id TEXT PRIMARY KEY,
                ref_type TEXT NOT NULL,
                duration_ref_ms INTEGER NOT NULL,
                ref_source TEXT NOT NULL,
                ref_updated_at TEXT
            );
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_track_duration_refs_type "
            "ON track_duration_refs(ref_type);"
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
        _ensure_v3_schema(connection)
        _ensure_gig_tables(connection)
        _ensure_scan_tables(connection)
        _record_schema_version(connection, schema_name="integrity", version=INTEGRITY_SCHEMA_VERSION)
        _record_schema_version(connection, schema_name="v3", version=V3_SCHEMA_VERSION)

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


def _ensure_scan_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_root TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'initial',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            tool_versions_json TEXT
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            stage INTEGER DEFAULT 0,
            state TEXT DEFAULT 'PENDING',
            last_error TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES scan_runs(id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            checksum TEXT,
            issue_code TEXT NOT NULL,
            severity TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES scan_runs(id)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_metadata_archive (
            checksum TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            first_seen_path TEXT NOT NULL,
            raw_tags_json TEXT NOT NULL,
            technical_json TEXT NOT NULL,
            durations_json TEXT NOT NULL,
            isrc_candidates_json TEXT NOT NULL,
            fingerprint_json TEXT,
            identity_confidence INTEGER NOT NULL,
            quality_rank INTEGER
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_path_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            checksum TEXT NOT NULL,
            path TEXT NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_queue_run_state ON scan_queue(run_id, state);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_queue_stage ON scan_queue(stage);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scan_issues_code ON scan_issues(issue_code);")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_archive_confidence ON file_metadata_archive(identity_confidence);"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_path_history_checksum ON file_path_history(checksum);")

    _add_missing_columns(
        conn,
        "files",
        {
            "scan_status": "TEXT",
            "scan_flags_json": "TEXT",
            "actual_duration": "REAL",
            "duration_delta": "REAL",
            "identity_confidence": "INTEGER",
            "isrc_candidates_json": "TEXT",
            "duplicate_of_checksum": "TEXT",
            "last_scanned_at": "TEXT",
            "scan_stage_reached": "INTEGER",
        },
    )


def _ensure_gig_tables(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gig_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filter_expr TEXT,
            usb_path TEXT,
            manifest_path TEXT,
            track_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            exported_at TEXT
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_sets_name ON gig_sets(name);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_sets_exported_at ON gig_sets(exported_at);")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gig_set_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gig_set_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            mp3_path TEXT,
            usb_dest_path TEXT,
            transcoded_at TEXT,
            exported_at TEXT,
            rekordbox_id INTEGER,
            FOREIGN KEY(gig_set_id) REFERENCES gig_sets(id)
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_set_tracks_set ON gig_set_tracks(gig_set_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gig_set_tracks_file ON gig_set_tracks(file_path);")
    _add_missing_columns(
        conn,
        "gig_sets",
        {
            "filter_expr": "TEXT",
            "usb_path": "TEXT",
            "manifest_path": "TEXT",
            "track_count": "INTEGER DEFAULT 0",
            "exported_at": "TEXT",
        },
    )
    _add_missing_columns(
        conn,
        "gig_set_tracks",
        {
            "mp3_path": "TEXT",
            "usb_dest_path": "TEXT",
            "transcoded_at": "TEXT",
            "exported_at": "TEXT",
            "rekordbox_id": "INTEGER",
        },
    )


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


def _ensure_v3_schema(conn: sqlite3.Connection) -> None:
    """Create/upgrade v3 migration tables used for dual-write."""

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {V3_ASSET_FILE_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            content_sha256 TEXT,
            streaminfo_md5 TEXT,
            checksum TEXT,
            size_bytes INTEGER,
            mtime REAL,
            duration_s REAL,
            sample_rate INTEGER,
            bit_depth INTEGER,
            bitrate INTEGER,
            library TEXT,
            zone TEXT,
            download_source TEXT,
            download_date TEXT,
            mgmt_status TEXT,
            first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _add_missing_columns(
        conn,
        V3_ASSET_FILE_TABLE,
        {
            "content_sha256": "TEXT",
            "streaminfo_md5": "TEXT",
            "checksum": "TEXT",
            "size_bytes": "INTEGER",
            "mtime": "REAL",
            "duration_s": "REAL",
            "sample_rate": "INTEGER",
            "bit_depth": "INTEGER",
            "bitrate": "INTEGER",
            "library": "TEXT",
            "zone": "TEXT",
            "download_source": "TEXT",
            "download_date": "TEXT",
            "mgmt_status": "TEXT",
            "first_seen_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "last_seen_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_ASSET_FILE_TABLE}_sha256 "
        f"ON {V3_ASSET_FILE_TABLE}(content_sha256)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_ASSET_FILE_TABLE}_streaminfo "
        f"ON {V3_ASSET_FILE_TABLE}(streaminfo_md5)"
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {V3_TRACK_IDENTITY_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL UNIQUE,
            isrc TEXT,
            beatport_id TEXT,
            artist_norm TEXT,
            title_norm TEXT,
            duration_ref_ms INTEGER,
            ref_source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _add_missing_columns(
        conn,
        V3_TRACK_IDENTITY_TABLE,
        {
            "isrc": "TEXT",
            "beatport_id": "TEXT",
            "artist_norm": "TEXT",
            "title_norm": "TEXT",
            "duration_ref_ms": "INTEGER",
            "ref_source": "TEXT",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_TRACK_IDENTITY_TABLE}_isrc "
        f"ON {V3_TRACK_IDENTITY_TABLE}(isrc)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_TRACK_IDENTITY_TABLE}_beatport "
        f"ON {V3_TRACK_IDENTITY_TABLE}(beatport_id)"
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {V3_ASSET_LINK_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            identity_id INTEGER NOT NULL,
            confidence REAL,
            link_source TEXT,
            active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(asset_id, identity_id),
            FOREIGN KEY(asset_id) REFERENCES {V3_ASSET_FILE_TABLE}(id),
            FOREIGN KEY(identity_id) REFERENCES {V3_TRACK_IDENTITY_TABLE}(id)
        )
        """
    )
    _add_missing_columns(
        conn,
        V3_ASSET_LINK_TABLE,
        {
            "confidence": "REAL",
            "link_source": "TEXT",
            "active": "INTEGER DEFAULT 1",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_ASSET_LINK_TABLE}_asset "
        f"ON {V3_ASSET_LINK_TABLE}(asset_id)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_ASSET_LINK_TABLE}_identity "
        f"ON {V3_ASSET_LINK_TABLE}(identity_id)"
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {V3_MOVE_PLAN_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_key TEXT NOT NULL UNIQUE,
            plan_type TEXT,
            plan_path TEXT,
            policy_version TEXT,
            context_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    _add_missing_columns(
        conn,
        V3_MOVE_PLAN_TABLE,
        {
            "plan_type": "TEXT",
            "plan_path": "TEXT",
            "policy_version": "TEXT",
            "context_json": "TEXT",
            "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {V3_MOVE_EXECUTION_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER,
            asset_id INTEGER,
            source_path TEXT,
            dest_path TEXT,
            action TEXT,
            status TEXT,
            verification TEXT,
            error TEXT,
            details_json TEXT,
            executed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES {V3_MOVE_PLAN_TABLE}(id),
            FOREIGN KEY(asset_id) REFERENCES {V3_ASSET_FILE_TABLE}(id)
        )
        """
    )
    _add_missing_columns(
        conn,
        V3_MOVE_EXECUTION_TABLE,
        {
            "plan_id": "INTEGER",
            "asset_id": "INTEGER",
            "source_path": "TEXT",
            "dest_path": "TEXT",
            "action": "TEXT",
            "status": "TEXT",
            "verification": "TEXT",
            "error": "TEXT",
            "details_json": "TEXT",
            "executed_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_MOVE_EXECUTION_TABLE}_plan "
        f"ON {V3_MOVE_EXECUTION_TABLE}(plan_id)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_MOVE_EXECUTION_TABLE}_status "
        f"ON {V3_MOVE_EXECUTION_TABLE}(status)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_MOVE_EXECUTION_TABLE}_dest "
        f"ON {V3_MOVE_EXECUTION_TABLE}(dest_path)"
    )

    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {V3_PROVENANCE_EVENT_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            event_time TEXT DEFAULT CURRENT_TIMESTAMP,
            asset_id INTEGER,
            identity_id INTEGER,
            move_plan_id INTEGER,
            move_execution_id INTEGER,
            source_path TEXT,
            dest_path TEXT,
            status TEXT,
            details_json TEXT,
            FOREIGN KEY(asset_id) REFERENCES {V3_ASSET_FILE_TABLE}(id),
            FOREIGN KEY(identity_id) REFERENCES {V3_TRACK_IDENTITY_TABLE}(id),
            FOREIGN KEY(move_plan_id) REFERENCES {V3_MOVE_PLAN_TABLE}(id),
            FOREIGN KEY(move_execution_id) REFERENCES {V3_MOVE_EXECUTION_TABLE}(id)
        )
        """
    )
    _add_missing_columns(
        conn,
        V3_PROVENANCE_EVENT_TABLE,
        {
            "event_type": "TEXT",
            "event_time": "TEXT DEFAULT CURRENT_TIMESTAMP",
            "asset_id": "INTEGER",
            "identity_id": "INTEGER",
            "move_plan_id": "INTEGER",
            "move_execution_id": "INTEGER",
            "source_path": "TEXT",
            "dest_path": "TEXT",
            "status": "TEXT",
            "details_json": "TEXT",
        },
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_PROVENANCE_EVENT_TABLE}_event "
        f"ON {V3_PROVENANCE_EVENT_TABLE}(event_type)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_PROVENANCE_EVENT_TABLE}_asset "
        f"ON {V3_PROVENANCE_EVENT_TABLE}(asset_id)"
    )
    conn.execute(
        f"CREATE INDEX IF NOT EXISTS idx_{V3_PROVENANCE_EVENT_TABLE}_move_exec "
        f"ON {V3_PROVENANCE_EVENT_TABLE}(move_execution_id)"
    )


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
