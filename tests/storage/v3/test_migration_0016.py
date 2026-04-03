from __future__ import annotations

import sqlite3

from tagslut.storage.v3.migration_runner import run_pending_v3
from tagslut.storage.v3.schema import create_schema_v3


def test_migration_0016_adds_tidal_audio_fields() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        create_schema_v3(conn)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (schema_name, version, note) VALUES ('v3', 15, 'fixture')"
        )

        applied = run_pending_v3(conn)
        assert "0016_tidal_audio_fields.sql" in applied

        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(track_identity)").fetchall()}
        for expected in (
            "tidal_bpm",
            "tidal_key",
            "tidal_key_scale",
            "tidal_camelot",
            "replay_gain_track",
            "replay_gain_album",
            "tidal_dj_ready",
            "tidal_stem_ready",
        ):
            assert expected in cols
    finally:
        conn.close()

