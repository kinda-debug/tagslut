"""Create the standalone v3 schema.

This schema is intentionally separate from the legacy/v2 mega-table model and
must not include the `files` table.
"""

from __future__ import annotations

import sqlite3

V3_SCHEMA_NAME = "v3"
V3_SCHEMA_VERSION = 12
V3_SCHEMA_VERSION_INITIAL = 1
V3_SCHEMA_VERSION_IDENTITY_MERGE = 2
V3_SCHEMA_VERSION_PREFERRED_ASSET = 3
V3_SCHEMA_VERSION_IDENTITY_STATUS = 4
V3_SCHEMA_VERSION_DJ_PROFILE = 5
V3_SCHEMA_VERSION_TRACK_IDENTITY_PHASE1 = 6
V3_SCHEMA_VERSION_TRACK_IDENTITY_PHASE1_RENAME = 7
V3_SCHEMA_VERSION_ASSET_ANALYSIS = 8
V3_SCHEMA_VERSION_CHROMAPRINT = 9
V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS = 10
V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING = 11
V3_SCHEMA_VERSION_INGESTION_PROVENANCE = 12


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except sqlite3.OperationalError:
        return False
    return any(str(row[1]) == column for row in rows)


def create_schema_v3(conn: sqlite3.Connection) -> None:
    """Create all v3 tables and indexes on an open SQLite connection."""
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS asset_file (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            content_sha256 TEXT,
            streaminfo_md5 TEXT,
            checksum TEXT,
            size_bytes INTEGER,
            mtime REAL,
            duration_s REAL,
            duration_measured_ms INTEGER,
            sample_rate INTEGER,
            bit_depth INTEGER,
            bitrate INTEGER,
            library TEXT,
            zone TEXT,
            download_source TEXT,
            download_date TEXT,
            mgmt_status TEXT,
            flac_ok INTEGER,
            integrity_state TEXT,
            integrity_checked_at TEXT,
            sha256_checked_at TEXT,
            streaminfo_checked_at TEXT,
            chromaprint_fingerprint TEXT,
            chromaprint_duration_s REAL,
            first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS track_identity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL UNIQUE,
            isrc TEXT,
            beatport_id TEXT,
            tidal_id TEXT,
            qobuz_id TEXT,
            spotify_id TEXT,
            apple_music_id TEXT,
            deezer_id TEXT,
            traxsource_id TEXT,
            itunes_id TEXT,
            musicbrainz_id TEXT,
            artist_norm TEXT,
            title_norm TEXT,
            album_norm TEXT,
            canonical_title TEXT,
            canonical_artist TEXT,
            canonical_album TEXT,
            canonical_genre TEXT,
            canonical_sub_genre TEXT,
            canonical_label TEXT,
            canonical_catalog_number TEXT,
            canonical_mix_name TEXT,
            canonical_duration REAL,
            canonical_year INTEGER,
            canonical_release_date TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_payload_json TEXT,
            enriched_at TEXT,
            duration_ref_ms INTEGER,
            ref_source TEXT,
            ingested_at TEXT NOT NULL,
            ingestion_method TEXT NOT NULL CHECK (
                ingestion_method IN (
                    'provider_api',
                    'isrc_lookup',
                    'fingerprint_match',
                    'fuzzy_text_match',
                    'picard_tag',
                    'manual',
                    'migration',
                    'multi_provider_reconcile'
                )
            ),
            ingestion_source TEXT NOT NULL,
            ingestion_confidence TEXT NOT NULL CHECK (
                ingestion_confidence IN ('verified','corroborated','high','uncertain','legacy')
            ),
            merged_into_id INTEGER REFERENCES track_identity(id),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS asset_link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL,
            identity_id INTEGER NOT NULL,
            confidence REAL,
            link_source TEXT,
            active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(asset_id),
            FOREIGN KEY(asset_id) REFERENCES asset_file(id) ON DELETE CASCADE,
            FOREIGN KEY(identity_id) REFERENCES track_identity(id)
        );

        CREATE TABLE IF NOT EXISTS library_track_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identity_key TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_track_id TEXT NOT NULL,
            source_url TEXT,
            match_confidence TEXT,
            raw_payload_json TEXT,
            metadata_json TEXT,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(identity_key, provider, provider_track_id),
            FOREIGN KEY(identity_key) REFERENCES track_identity(identity_key) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS move_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_key TEXT NOT NULL UNIQUE,
            plan_type TEXT,
            plan_path TEXT,
            policy_version TEXT,
            context_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS move_execution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER,
            asset_id INTEGER,
            source_path TEXT,
            dest_path TEXT,
            action TEXT,
            status TEXT NOT NULL,
            verification TEXT,
            error TEXT,
            details_json TEXT,
            executed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES move_plan(id),
            FOREIGN KEY(asset_id) REFERENCES asset_file(id)
        );

        CREATE TABLE IF NOT EXISTS provenance_event (
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
            FOREIGN KEY(asset_id) REFERENCES asset_file(id),
            FOREIGN KEY(identity_id) REFERENCES track_identity(id),
            FOREIGN KEY(move_plan_id) REFERENCES move_plan(id),
            FOREIGN KEY(move_execution_id) REFERENCES move_execution(id)
        );

        CREATE TABLE IF NOT EXISTS identity_merge_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            merged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            merge_type TEXT NOT NULL,
            key_value TEXT NOT NULL,
            winner_identity_id INTEGER NOT NULL,
            loser_identity_ids TEXT NOT NULL,
            assets_moved INTEGER NOT NULL,
            fields_copied_json TEXT,
            rationale_json TEXT,
            dry_run INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(winner_identity_id) REFERENCES track_identity(id)
        );

        CREATE TABLE IF NOT EXISTS preferred_asset (
            identity_id INTEGER PRIMARY KEY REFERENCES track_identity(id),
            asset_id INTEGER NOT NULL REFERENCES asset_file(id),
            score REAL NOT NULL,
            reason_json TEXT NOT NULL,
            version INTEGER NOT NULL,
            computed_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS identity_status (
            identity_id INTEGER PRIMARY KEY REFERENCES track_identity(id),
            status TEXT NOT NULL CHECK(status IN ('active', 'orphan', 'archived')),
            reason_json TEXT NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL,
            computed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS dj_track_profile (
            identity_id INTEGER PRIMARY KEY REFERENCES track_identity(id),
            rating INTEGER NULL CHECK(rating BETWEEN 0 AND 5),
            energy INTEGER NULL CHECK(energy BETWEEN 0 AND 10),
            set_role TEXT NULL CHECK(
                set_role IN ('warmup','builder','peak','tool','closer','ambient','break','unknown')
            ),
            dj_tags_json TEXT NOT NULL DEFAULT '[]',
            notes TEXT NULL,
            last_played_at TEXT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS asset_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER NOT NULL REFERENCES asset_file(id) ON DELETE CASCADE,
            analyzer TEXT NOT NULL,
            analyzer_version TEXT NOT NULL,
            analysis_scope TEXT NOT NULL,
            bpm REAL,
            musical_key TEXT,
            analysis_energy_1_10 INTEGER CHECK(analysis_energy_1_10 BETWEEN 1 AND 10),
            confidence REAL,
            raw_payload_json TEXT,
            computed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(asset_id, analysis_scope) ON CONFLICT REPLACE
        );

        CREATE TABLE IF NOT EXISTS scan_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL DEFAULT 'queue' CHECK (mode = 'queue'),
            library_root TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            completed_at TEXT,
            tool_versions_json TEXT,
            metadata_json TEXT
        );

        CREATE TABLE IF NOT EXISTS scan_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER,
            mtime_ns INTEGER,
            stage TEXT NOT NULL DEFAULT 'discover',
            state TEXT NOT NULL DEFAULT 'PENDING',
            last_error TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(run_id, path),
            FOREIGN KEY(run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scan_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            queue_id INTEGER,
            path TEXT,
            issue_code TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'INFO',
            evidence_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(run_id) REFERENCES scan_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(queue_id) REFERENCES scan_queue(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY,
            schema_name TEXT NOT NULL,
            version INTEGER NOT NULL,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
            note TEXT,
            UNIQUE(schema_name, version)
        );

        CREATE INDEX IF NOT EXISTS idx_asset_file_sha256 ON asset_file(content_sha256);
        CREATE INDEX IF NOT EXISTS idx_asset_file_streaminfo_md5 ON asset_file(streaminfo_md5);
        CREATE INDEX IF NOT EXISTS idx_asset_file_checksum ON asset_file(checksum);
        CREATE INDEX IF NOT EXISTS idx_asset_file_integrity_state ON asset_file(integrity_state);
        CREATE INDEX IF NOT EXISTS idx_asset_file_chromaprint ON asset_file(chromaprint_fingerprint);
        CREATE INDEX IF NOT EXISTS idx_asset_file_chromaprint_duration ON asset_file(chromaprint_duration_s);

        CREATE INDEX IF NOT EXISTS idx_track_identity_key ON track_identity(identity_key);
        CREATE INDEX IF NOT EXISTS idx_track_identity_isrc ON track_identity(isrc);
        CREATE INDEX IF NOT EXISTS idx_track_identity_beatport ON track_identity(beatport_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_tidal ON track_identity(tidal_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_qobuz ON track_identity(qobuz_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_spotify ON track_identity(spotify_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_apple_music ON track_identity(apple_music_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_deezer ON track_identity(deezer_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_traxsource ON track_identity(traxsource_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_itunes ON track_identity(itunes_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_musicbrainz ON track_identity(musicbrainz_id);
        CREATE INDEX IF NOT EXISTS idx_track_identity_ingested_at ON track_identity(ingested_at);
        CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_method ON track_identity(ingestion_method);
        CREATE INDEX IF NOT EXISTS idx_track_identity_ingestion_confidence ON track_identity(ingestion_confidence);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_beatport_id
            ON track_identity(beatport_id)
            WHERE beatport_id IS NOT NULL
              AND TRIM(beatport_id) != ''
              AND merged_into_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_tidal_id
            ON track_identity(tidal_id)
            WHERE tidal_id IS NOT NULL
              AND TRIM(tidal_id) != ''
              AND merged_into_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_qobuz_id
            ON track_identity(qobuz_id)
            WHERE qobuz_id IS NOT NULL
              AND TRIM(qobuz_id) != ''
              AND merged_into_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_spotify_id
            ON track_identity(spotify_id)
            WHERE spotify_id IS NOT NULL
              AND TRIM(spotify_id) != ''
              AND merged_into_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_apple_music_id
            ON track_identity(apple_music_id)
            WHERE apple_music_id IS NOT NULL
              AND TRIM(apple_music_id, ' \t\n\r') != ''
              AND merged_into_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_deezer_id
            ON track_identity(deezer_id)
            WHERE deezer_id IS NOT NULL
              AND TRIM(deezer_id, ' \t\n\r') != ''
              AND merged_into_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_track_identity_active_traxsource_id
            ON track_identity(traxsource_id)
            WHERE traxsource_id IS NOT NULL
              AND TRIM(traxsource_id, ' \t\n\r') != ''
              AND merged_into_id IS NULL;

        CREATE INDEX IF NOT EXISTS idx_asset_link_identity ON asset_link(identity_id);
        CREATE INDEX IF NOT EXISTS idx_identity_merge_log_key_value ON identity_merge_log(key_value);
        CREATE INDEX IF NOT EXISTS idx_preferred_asset_asset_id ON preferred_asset(asset_id);
        CREATE INDEX IF NOT EXISTS idx_preferred_asset_identity ON preferred_asset(identity_id);
        CREATE INDEX IF NOT EXISTS idx_preferred_asset_version ON preferred_asset(version);
        CREATE INDEX IF NOT EXISTS idx_identity_status_status ON identity_status(status);
        CREATE INDEX IF NOT EXISTS idx_identity_status_identity ON identity_status(identity_id);
        CREATE INDEX IF NOT EXISTS idx_identity_status_version ON identity_status(version);
        CREATE INDEX IF NOT EXISTS idx_dj_track_profile_set_role ON dj_track_profile(set_role);
        CREATE INDEX IF NOT EXISTS idx_dj_track_profile_energy ON dj_track_profile(energy);
        CREATE INDEX IF NOT EXISTS idx_dj_track_profile_last_played_at ON dj_track_profile(last_played_at);
        CREATE INDEX IF NOT EXISTS idx_dj_profile_identity ON dj_track_profile(identity_id);
        CREATE INDEX IF NOT EXISTS idx_asset_analysis_asset ON asset_analysis(asset_id);
        CREATE INDEX IF NOT EXISTS idx_asset_analysis_scope
            ON asset_analysis(analysis_scope, computed_at);
        CREATE INDEX IF NOT EXISTS idx_library_track_sources_identity_key
            ON library_track_sources(identity_key);
        CREATE INDEX IF NOT EXISTS idx_library_track_sources_provider_id
            ON library_track_sources(provider, provider_track_id);

        CREATE INDEX IF NOT EXISTS idx_move_execution_plan ON move_execution(plan_id);
        CREATE INDEX IF NOT EXISTS idx_move_execution_asset ON move_execution(asset_id);
        CREATE INDEX IF NOT EXISTS idx_move_execution_status ON move_execution(status);

        CREATE INDEX IF NOT EXISTS idx_provenance_event_type ON provenance_event(event_type);
        CREATE INDEX IF NOT EXISTS idx_provenance_event_asset ON provenance_event(asset_id);
        CREATE INDEX IF NOT EXISTS idx_provenance_event_move_exec ON provenance_event(move_execution_id);

        CREATE INDEX IF NOT EXISTS idx_scan_queue_run_state ON scan_queue(run_id, state);
        CREATE INDEX IF NOT EXISTS idx_scan_queue_stage ON scan_queue(stage);
        CREATE INDEX IF NOT EXISTS idx_scan_issues_code ON scan_issues(issue_code);

        CREATE VIEW IF NOT EXISTS v_active_identity AS
        SELECT ti.*
        FROM track_identity ti
        JOIN identity_status ist ON ist.identity_id = ti.id
        WHERE ti.merged_into_id IS NULL
          AND ist.status = 'active';

        CREATE VIEW IF NOT EXISTS v_dj_ready_candidates AS
        SELECT
            ti.id AS identity_id,
            ti.identity_key AS identity_key,
            ti.canonical_artist AS artist,
            ti.canonical_title AS title,
            ti.canonical_bpm AS bpm,
            ti.canonical_key AS key,
            ti.canonical_genre AS genre,
            ti.canonical_duration AS duration_s,
            pa.asset_id AS preferred_asset_id,
            af.path AS preferred_path,
            COALESCE(ist.status, 'unknown') AS status,
            dj.rating AS rating,
            dj.energy AS energy,
            dj.set_role AS set_role,
            dj.dj_tags_json AS dj_tags_json,
            dj.notes AS notes,
            dj.last_played_at AS last_played_at
        FROM track_identity ti
        LEFT JOIN identity_status ist ON ist.identity_id = ti.id
        LEFT JOIN preferred_asset pa ON pa.identity_id = ti.id
        LEFT JOIN asset_file af ON af.id = pa.asset_id
        LEFT JOIN dj_track_profile dj ON dj.identity_id = ti.id
        WHERE ti.merged_into_id IS NULL;

        CREATE VIEW IF NOT EXISTS v_dj_pool_candidates_v3 AS
        SELECT
            ti.id AS identity_id,
            ti.identity_key AS identity_key,
            ti.isrc AS isrc,
            ti.beatport_id AS beatport_id,
            ti.tidal_id AS tidal_id,
            ti.deezer_id AS deezer_id,
            ti.spotify_id AS spotify_id,
            ti.traxsource_id AS traxsource_id,
            ti.musicbrainz_id AS musicbrainz_id,
            ti.canonical_artist AS artist,
            ti.canonical_title AS title,
            ti.canonical_album AS album,
            ti.canonical_mix_name AS mix_name,
            ti.canonical_genre AS genre,
            ti.canonical_sub_genre AS sub_genre,
            ti.canonical_bpm AS bpm,
            ti.canonical_key AS musical_key,
            COALESCE(ti.canonical_duration, af.duration_s) AS duration_s,
            ist.status AS identity_status,
            pa.asset_id AS preferred_asset_id,
            af.path AS asset_path,
            af.mtime AS asset_mtime,
            af.content_sha256 AS sha256,
            af.sample_rate AS sample_rate,
            af.bit_depth AS bit_depth,
            af.bitrate AS bitrate,
            af.integrity_state AS integrity_state,
            af.integrity_checked_at AS integrity_checked_at,
            af.first_seen_at AS first_seen_at,
            af.last_seen_at AS last_seen_at,
            dj.rating AS dj_rating,
            dj.energy AS dj_energy,
            dj.set_role AS dj_set_role,
            dj.dj_tags_json AS dj_tags_json,
            dj.last_played_at AS dj_last_played_at,
            dj.notes AS dj_notes,
            dj.updated_at AS dj_updated_at,
            ti.enriched_at AS identity_enriched_at,
            ti.created_at AS identity_created_at,
            ti.updated_at AS identity_updated_at,
            ti.merged_into_id AS merged_into_id
        FROM track_identity ti
        LEFT JOIN identity_status ist ON ist.identity_id = ti.id
        LEFT JOIN preferred_asset pa ON pa.identity_id = ti.id
        LEFT JOIN asset_file af ON af.id = pa.asset_id
        LEFT JOIN dj_track_profile dj ON dj.identity_id = ti.id
        WHERE ti.merged_into_id IS NULL;

        CREATE VIEW IF NOT EXISTS v_dj_pool_candidates_active_v3 AS
        SELECT *
        FROM v_dj_pool_candidates_v3
        WHERE
            preferred_asset_id IS NOT NULL
            AND identity_status = 'active';

        CREATE VIEW IF NOT EXISTS v_dj_pool_candidates_active_orphan_v3 AS
        SELECT *
        FROM v_dj_pool_candidates_v3
        WHERE
            preferred_asset_id IS NOT NULL
            AND identity_status IN ('active', 'orphan');

        CREATE VIEW IF NOT EXISTS v_asset_analysis_latest_dj AS
        SELECT *
        FROM asset_analysis
        WHERE analysis_scope = 'dj';

        CREATE VIEW IF NOT EXISTS v_dj_export_metadata_v1 AS
        SELECT
            ti.id AS identity_id,
            ti.identity_key AS identity_key,
            ti.isrc AS isrc,
            ti.canonical_artist AS artist,
            ti.canonical_title AS title,
            ti.canonical_album AS album,
            ti.canonical_genre AS genre,
            ti.canonical_label AS label,
            ti.canonical_year AS year,
            pa.asset_id AS preferred_asset_id,
            af.path AS preferred_path,
            COALESCE(ti.canonical_bpm, aa.bpm) AS export_bpm,
            CASE
                WHEN ti.canonical_bpm IS NOT NULL THEN 'identity'
                WHEN aa.bpm IS NOT NULL THEN 'analysis'
                ELSE NULL
            END AS bpm_source,
            COALESCE(ti.canonical_key, aa.musical_key) AS export_key,
            CASE
                WHEN ti.canonical_key IS NOT NULL THEN 'identity'
                WHEN aa.musical_key IS NOT NULL THEN 'analysis'
                ELSE NULL
            END AS key_source,
            COALESCE(dj.energy, aa.analysis_energy_1_10) AS export_energy,
            CASE
                WHEN dj.energy IS NOT NULL THEN 'dj_profile'
                WHEN aa.analysis_energy_1_10 IS NOT NULL THEN 'analysis'
                ELSE NULL
            END AS energy_source,
            aa.analyzer AS analysis_analyzer,
            aa.computed_at AS analysis_computed_at
        FROM track_identity ti
        LEFT JOIN preferred_asset pa ON pa.identity_id = ti.id
        LEFT JOIN asset_file af ON af.id = pa.asset_id
        LEFT JOIN dj_track_profile dj ON dj.identity_id = ti.id
        LEFT JOIN v_asset_analysis_latest_dj aa ON aa.asset_id = pa.asset_id
        WHERE ti.merged_into_id IS NULL;
        """
    )
    if not _column_exists(conn, "track_identity", "merged_into_id"):
        conn.execute(
            "ALTER TABLE track_identity ADD COLUMN merged_into_id INTEGER REFERENCES track_identity(id)"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_identity_merged_into ON track_identity(merged_into_id)"
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_INITIAL, "initial v3 schema"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_IDENTITY_MERGE, "identity merge support"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_PREFERRED_ASSET, "preferred asset support"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_IDENTITY_STATUS, "identity lifecycle status support"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_DJ_PROFILE, "dj profile support"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_TRACK_IDENTITY_PHASE1, "phase 1 canonical identity extension"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (
            V3_SCHEMA_NAME,
            V3_SCHEMA_VERSION_TRACK_IDENTITY_PHASE1_RENAME,
            "rename phase 1 track identity columns to canonical names",
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_ASSET_ANALYSIS, "asset analysis and dj export metadata views"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION_CHROMAPRINT, "add chromaprint columns and indexes to asset_file"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (
            V3_SCHEMA_NAME,
            V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS,
            "0010_track_identity_provider_uniqueness.py",
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (
            V3_SCHEMA_NAME,
            V3_SCHEMA_VERSION_PROVIDER_UNIQUENESS_HARDENING,
            "0011_track_identity_provider_uniqueness_hardening.py",
        ),
    )
    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_track_identity_provenance_required
        BEFORE INSERT ON track_identity
        BEGIN
            SELECT CASE
                WHEN NEW.ingested_at IS NULL OR TRIM(NEW.ingested_at) = '' THEN
                    RAISE(ABORT, 'track_identity.ingested_at is required')
                WHEN NEW.ingestion_method IS NULL OR TRIM(NEW.ingestion_method) = '' THEN
                    RAISE(ABORT, 'track_identity.ingestion_method is required')
                WHEN NEW.ingestion_source IS NULL THEN
                    RAISE(ABORT, 'track_identity.ingestion_source is required')
                WHEN NEW.ingestion_confidence IS NULL OR TRIM(NEW.ingestion_confidence) = '' THEN
                    RAISE(ABORT, 'track_identity.ingestion_confidence is required')
            END;
        END
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (
            V3_SCHEMA_NAME,
            V3_SCHEMA_VERSION_INGESTION_PROVENANCE,
            "0012_ingestion_provenance.py",
        ),
    )
    conn.commit()
