"""Migration 0008: add DJ analysis table and export metadata views."""

from __future__ import annotations

import sqlite3

VERSION = 8


def up(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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

        CREATE INDEX IF NOT EXISTS idx_asset_analysis_asset ON asset_analysis(asset_id);
        CREATE INDEX IF NOT EXISTS idx_asset_analysis_scope ON asset_analysis(analysis_scope, computed_at);

        DROP VIEW IF EXISTS v_asset_analysis_latest_dj;
        CREATE VIEW v_asset_analysis_latest_dj AS
        SELECT *
        FROM asset_analysis
        WHERE analysis_scope = 'dj';

        DROP VIEW IF EXISTS v_dj_export_metadata_v1;
        CREATE VIEW v_dj_export_metadata_v1 AS
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
    conn.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (schema_name, version, note)
        VALUES ('v3', ?, ?)
        """,
        (VERSION, "asset analysis and dj export metadata views"),
    )
