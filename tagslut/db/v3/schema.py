"""Create the standalone v3 schema.

This schema is intentionally separate from the legacy/v2 mega-table model and
must not include the `files` table.
"""

from __future__ import annotations

import sqlite3

V3_SCHEMA_NAME = "v3"
V3_SCHEMA_VERSION = 1


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
            sample_rate INTEGER,
            bit_depth INTEGER,
            bitrate INTEGER,
            library TEXT,
            zone TEXT,
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
            artist_norm TEXT,
            title_norm TEXT,
            album_norm TEXT,
            duration_ref_ms INTEGER,
            ref_source TEXT,
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

        CREATE INDEX IF NOT EXISTS idx_asset_link_identity ON asset_link(identity_id);
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
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES (?, ?, ?)
        """,
        (V3_SCHEMA_NAME, V3_SCHEMA_VERSION, "initial v3 schema"),
    )
    conn.commit()
