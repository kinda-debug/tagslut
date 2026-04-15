from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.migration_runner import run_pending
from tagslut.storage.schema import init_db
from tagslut.storage.v3.schema import create_schema_v3


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_NAME = "0007_isrc_primary_key.py"


def _migration_source() -> Path:
    return (
        PROJECT_ROOT
        / "tagslut"
        / "storage"
        / "migrations"
        / MIGRATION_NAME
    )


def _seed_fixture_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        create_schema_v3(conn)
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO track_identity (
                id, identity_key, isrc, beatport_id, spotify_id, canonical_artist, canonical_title,
                ingested_at, ingestion_method, ingestion_source, ingestion_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "beatport:BP-1", None, "BP-1", None, "Artist One", "Track One", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
                (2, "text:artist two|track two", None, None, "SP-2", "Artist Two", "Track Two", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
                (3, "text:artist three|track three", None, None, None, "Artist Three", "Track Three", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
                (4, "isrc:usrc17607839", None, None, None, "Artist Four", "Track Four", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
            ],
        )
        conn.executemany(
            """
            INSERT INTO files (path, checksum, beatport_id, spotify_id, isrc, canonical_isrc, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("/music/one.flac", "a", "BP-1", None, "USRC11111111", None, "{}"),
                ("/music/two.flac", "b", None, "SP-2", None, "GBAYE0400123", "{}"),
            ],
        )
        conn.execute(
            """
            INSERT INTO library_track_sources (
                identity_key, provider, provider_track_id, metadata_json, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                "text:artist three|track three",
                "traxsource",
                "TS-3",
                "{}",
                '{"isrc":"QZABC2200001"}',
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _read_identity_isrcs(db_path: Path) -> dict[int, str | None]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT id, isrc FROM track_identity ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    return {
        int(identity_id): (str(isrc) if isrc is not None else None)
        for identity_id, isrc in rows
    }


def test_isrc_migration_cli_dry_run_is_safe(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.sqlite"
    _seed_fixture_db(db_path)

    before = _read_identity_isrcs(db_path)
    proc = subprocess.run(
        [sys.executable, str(_migration_source()), "--db", str(db_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "mode: dry-run" in proc.stdout
    assert "planned_backfills: 4" in proc.stdout
    assert "remaining_null_rows: 0" in proc.stdout
    assert _read_identity_isrcs(db_path) == before


def test_isrc_migration_runner_is_idempotent_on_fixture_db(tmp_path: Path) -> None:
    db_path = tmp_path / "music_v3.sqlite"
    _seed_fixture_db(db_path)

    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()
    shutil.copy2(_migration_source(), migrations_dir / MIGRATION_NAME)

    first = run_pending(db_path, migrations_dir=migrations_dir)
    second = run_pending(db_path, migrations_dir=migrations_dir)

    assert first == [MIGRATION_NAME]
    assert second == []
    assert _read_identity_isrcs(db_path) == {
        1: "USRC11111111",
        2: "GBAYE0400123",
        3: "QZABC2200001",
        4: "USRC17607839",
    }

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        index_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_track_identity_isrc_unique_norm'"
        ).fetchone()
        trigger_rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='trigger' AND name IN (
                'trg_track_identity_isrc_required_insert',
                'trg_track_identity_isrc_required_update'
            )
            ORDER BY name
            """
        ).fetchall()
    finally:
        conn.close()

    assert index_row is not None
    assert "create unique index" in str(index_row["sql"]).lower()
    assert [str(row["name"]) for row in trigger_rows] == [
        "trg_track_identity_isrc_required_insert",
        "trg_track_identity_isrc_required_update",
    ]
