"""Tests for v3 DJ profile management."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from tagslut.storage.v3.dj_profile import ensure_schema, get_profile, upsert_profile
from tagslut.storage.v3.schema import V3_SCHEMA_VERSION_DJ_PROFILE, create_schema_v3

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _create_db(tmp_path: Path) -> Path:
    db = tmp_path / "music_v3.db"
    conn = sqlite3.connect(str(db))
    try:
        create_schema_v3(conn)
        conn.executemany(
            "INSERT INTO track_identity (id, identity_key, merged_into_id, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (1, "id:one", None, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
                (2, "id:two", None, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
                (3, "id:merged", 1, '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
            ],
        )
        conn.execute(
            "INSERT INTO identity_status (identity_id, status, reason_json, version) VALUES (2, 'archived', '{}', 1)"
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_schema_created_and_migration_recorded(tmp_path: Path) -> None:
    db = _create_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        ensure_schema(conn)
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dj_track_profile'"
        ).fetchone()
        assert table_exists is not None
        mig = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE schema_name='v3' AND version=?",
            (V3_SCHEMA_VERSION_DJ_PROFILE,),
        ).fetchone()
        assert mig is not None
    finally:
        conn.close()


def test_set_get_and_tag_mutations(tmp_path: Path) -> None:
    db = _create_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        ensure_schema(conn)
        upsert_profile(
            conn,
            1,
            {
                "rating": 4,
                "energy": 7,
                "set_role": "builder",
                "dj_tags_json": json.dumps(["groovy", "warm"], separators=(",", ":")),
                "notes": "candidate",
            },
        )
        profile = get_profile(conn, 1)
        assert profile is not None
        assert profile["rating"] == 4
        assert profile["energy"] == 7
        assert profile["set_role"] == "builder"
        assert sorted(json.loads(profile["dj_tags_json"])) == ["groovy", "warm"]

        # Update tags deterministically
        upsert_profile(
            conn,
            1,
            {"dj_tags_json": json.dumps(["groovy", "peak"], separators=(",", ":"))},
        )
        updated = get_profile(conn, 1)
        assert updated is not None
        assert sorted(json.loads(updated["dj_tags_json"])) == ["groovy", "peak"]
    finally:
        conn.close()


def test_rejects_nonexistent_and_merged_identity(tmp_path: Path) -> None:
    db = _create_db(tmp_path)
    conn = sqlite3.connect(str(db))
    try:
        ensure_schema(conn)
        try:
            upsert_profile(conn, 999, {"rating": 1})
            assert False, "expected failure for missing identity"
        except RuntimeError:
            pass
        try:
            upsert_profile(conn, 3, {"rating": 1})
            assert False, "expected failure for merged identity"
        except RuntimeError:
            pass
    finally:
        conn.close()


def test_cli_rejects_archived_without_override(tmp_path: Path) -> None:
    db = _create_db(tmp_path)
    cmd = [
        sys.executable,
        "scripts/dj/profile_v3.py",
        "set",
        "--db",
        str(db),
        "--identity",
        "2",
        "--rating",
        "2",
    ]
    proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 2

    cmd_override = cmd + ["--allow-archived"]
    proc_override = subprocess.run(
        cmd_override,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_override.returncode == 0, f"STDOUT:\n{proc_override.stdout}\nSTDERR:\n{proc_override.stderr}"
