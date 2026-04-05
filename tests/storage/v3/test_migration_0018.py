from __future__ import annotations

import sqlite3

from tagslut.storage.v3 import create_schema_v3
from tagslut.storage.v3.migration_runner import run_pending_v3


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def test_migration_0018_adds_blocked_cohort_state() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)

        applied = run_pending_v3(conn)

        assert "0018_blocked_cohort_state.sql" in applied
        asset_file_columns = _column_names(conn, "asset_file")
        assert "status" in asset_file_columns
        assert "blocked_reason" in asset_file_columns

        cohort_columns = _column_names(conn, "cohort")
        assert {"source_url", "source_kind", "status", "blocked_reason", "flags"} <= cohort_columns

        cohort_file_columns = _column_names(conn, "cohort_file")
        assert {
            "cohort_id",
            "asset_file_id",
            "source_path",
            "status",
            "blocked_reason",
            "blocked_stage",
        } <= cohort_file_columns

        row = conn.execute(
            """
            SELECT 1
            FROM schema_migrations
            WHERE schema_name = 'v3' AND version = 18 AND note = '0018_blocked_cohort_state.sql'
            """
        ).fetchone()
        assert row is not None
    finally:
        conn.close()
