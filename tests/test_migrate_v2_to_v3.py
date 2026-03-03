"""Tests for scripts/db/migrate_v2_to_v3.py."""

from __future__ import annotations

import importlib.util as _ilu
import sqlite3
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "db" / "migrate_v2_to_v3.py"
_SPEC = _ilu.spec_from_file_location("migrate_v2_to_v3", _SCRIPT)
_MOD = _ilu.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)

migrate_v2_to_v3 = _MOD.migrate_v2_to_v3


def _create_v2_fixture(path: Path) -> Path:
    db_path = path / "music_v2_fixture.db"
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE files (
                path TEXT PRIMARY KEY,
                sha256 TEXT,
                streaminfo_md5 TEXT,
                checksum TEXT,
                size INTEGER,
                mtime REAL,
                duration REAL,
                duration_measured_ms INTEGER,
                sample_rate INTEGER,
                bit_depth INTEGER,
                bitrate INTEGER,
                library TEXT,
                zone TEXT,
                flac_ok INTEGER,
                integrity_state TEXT,
                integrity_checked_at TEXT,
                sha256_checked_at TEXT,
                streaminfo_checked_at TEXT,
                download_source TEXT,
                download_date TEXT,
                mgmt_status TEXT,
                canonical_isrc TEXT,
                isrc TEXT,
                beatport_id TEXT,
                canonical_artist TEXT,
                canonical_title TEXT,
                canonical_album TEXT,
                canonical_genre TEXT,
                canonical_bpm REAL,
                canonical_key TEXT,
                spotify_id TEXT,
                tidal_id TEXT,
                qobuz_id TEXT,
                itunes_id TEXT,
                deezer_id TEXT,
                traxsource_id TEXT,
                musicbrainz_id TEXT,
                library_track_key TEXT
            )
            """
        )

        conn.executemany(
            """
            INSERT INTO files (
                path, sha256, streaminfo_md5, checksum, size, mtime, duration,
                duration_measured_ms, sample_rate, bit_depth, bitrate, library, zone,
                flac_ok, integrity_state, integrity_checked_at, sha256_checked_at, streaminfo_checked_at,
                download_source, download_date, mgmt_status,
                canonical_isrc, isrc, beatport_id, canonical_artist, canonical_title, canonical_album,
                canonical_genre, canonical_bpm, canonical_key,
                spotify_id, tidal_id, qobuz_id, itunes_id, deezer_id, traxsource_id, musicbrainz_id,
                library_track_key
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "/music/a.flac",
                    "sha_a",
                    "smd5_a",
                    "chk_a",
                    1000,
                    100.0,
                    200.3,
                    None,  # duration_measured_ms should be derived
                    96000,
                    24,
                    0,
                    "default",
                    "accepted",
                    1,
                    "ok",
                    "2026-02-01T00:00:00Z",
                    "2026-02-01T00:00:00Z",
                    "2026-02-01T00:00:00Z",
                    "bpdl",
                    "2026-01-01",
                    "verified",
                    "USAAA1111111",
                    "USAAA1111111",
                    None,
                    "Artist A",
                    "Track A",
                    "Album A",
                    "House",
                    128.0,
                    "8A",
                    "sp_1",
                    "td_1",
                    "qb_1",
                    "it_1",
                    "dz_1",
                    "tx_1",
                    "mb_1",
                    "isrc:USAAA1111111",
                ),
                (
                    "/music/b.flac",
                    "sha_b",
                    "smd5_b",
                    "chk_b",
                    2000,
                    200.0,
                    180.0,
                    180000,
                    44100,
                    16,
                    0,
                    "default",
                    "accepted",
                    1,
                    "ok",
                    "2026-02-02T00:00:00Z",
                    "2026-02-02T00:00:00Z",
                    "2026-02-02T00:00:00Z",
                    "legacy",
                    "2026-01-02",
                    "checked",
                    None,
                    None,
                    "BP-42",
                    "Artist B",
                    "Track B",
                    "Album B",
                    "Techno",
                    130.0,
                    "9A",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "beatport:BP-42",
                ),
                (
                    "/music/c.flac",
                    "sha_c",
                    "smd5_c",
                    "chk_c",
                    3000,
                    300.0,
                    150.2,
                    None,
                    44100,
                    16,
                    0,
                    "default",
                    "accepted",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "dropbox",
                    "2026-01-03",
                    "new",
                    None,
                    None,
                    None,
                    "Artist C",
                    "Track C",
                    None,
                    "Progressive",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "text:artist c|track c|150s",
                ),
                (
                    "/music/d.flac",
                    None,
                    None,
                    "chk_d",
                    4000,
                    400.0,
                    210.0,
                    None,
                    44100,
                    16,
                    0,
                    "default",
                    "quarantine",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ],
        )

        conn.execute(
            """
            CREATE TABLE library_track_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                library_track_key TEXT,
                service TEXT,
                service_track_id TEXT,
                url TEXT,
                metadata_json TEXT,
                isrc TEXT,
                match_confidence TEXT,
                fetched_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO library_track_sources (
                library_track_key, service, service_track_id, url, metadata_json, isrc, match_confidence, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "isrc:USAAA1111111",
                "beatport",
                "BP-42",
                "https://example.test/track",
                '{"raw":"payload"}',
                "USAAA1111111",
                "0.99",
                "2026-02-10T00:00:00Z",
            ),
        )

        # Optional v3-style tables in source DB to validate move/provenance copying.
        conn.execute("CREATE TABLE asset_file (id INTEGER PRIMARY KEY, path TEXT)")
        conn.execute("INSERT INTO asset_file (id, path) VALUES (?, ?)", (101, "/music/a.flac"))

        conn.execute("CREATE TABLE track_identity (id INTEGER PRIMARY KEY, identity_key TEXT)")
        conn.execute("INSERT INTO track_identity (id, identity_key) VALUES (?, ?)", (201, "isrc:USAAA1111111"))

        conn.execute(
            """
            CREATE TABLE move_plan (
                id INTEGER PRIMARY KEY,
                plan_key TEXT,
                plan_type TEXT,
                plan_path TEXT,
                policy_version TEXT,
                context_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO move_plan (id, plan_key, plan_type, plan_path, policy_version, context_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (11, "plan:1", "move", "/tmp/plan.csv", "v1", "{}", "2026-02-11T00:00:00Z"),
        )

        conn.execute(
            """
            CREATE TABLE move_execution (
                id INTEGER PRIMARY KEY,
                plan_id INTEGER,
                asset_id INTEGER,
                source_path TEXT,
                dest_path TEXT,
                action TEXT,
                status TEXT,
                verification TEXT,
                error TEXT,
                details_json TEXT,
                executed_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO move_execution (
                id, plan_id, asset_id, source_path, dest_path, action, status,
                verification, error, details_json, executed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                21,
                11,
                101,
                "/music/a.flac",
                "/music/renamed_a.flac",
                "move",
                "success",
                "ok",
                None,
                '{"receipt":"r1"}',
                "2026-02-11T01:00:00Z",
            ),
        )

        conn.execute(
            """
            CREATE TABLE provenance_event (
                id INTEGER PRIMARY KEY,
                event_type TEXT,
                event_time TEXT,
                asset_id INTEGER,
                identity_id INTEGER,
                move_plan_id INTEGER,
                move_execution_id INTEGER,
                source_path TEXT,
                dest_path TEXT,
                status TEXT,
                details_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO provenance_event (
                id, event_type, event_time, asset_id, identity_id, move_plan_id, move_execution_id,
                source_path, dest_path, status, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                31,
                "moved",
                "2026-02-11T01:01:00Z",
                101,
                201,
                11,
                21,
                "/music/a.flac",
                "/music/renamed_a.flac",
                "success",
                '{"receipt":"r1"}',
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_migrate_v2_to_v3_fixture_preserves_rules(tmp_path: Path) -> None:
    v2 = _create_v2_fixture(tmp_path)
    v3 = tmp_path / "music_v3.db"

    summary = migrate_v2_to_v3(
        v2_path=v2,
        v3_path=v3,
        batch_size=2,
        resume=False,
        dry_run=False,
        strict=True,
    )

    assert summary["assets_migrated"] == 4
    assert summary["identities_created"] == 4
    assert summary["unidentified_count"] == 1
    assert summary["integrity_preserved_count"] == 2
    assert summary["enrichment_preserved_count"] == 3

    conn = sqlite3.connect(str(v3))
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(DISTINCT asset_id) FROM asset_link").fetchone()[0] == 4

        unidentified = conn.execute(
            "SELECT identity_key FROM track_identity WHERE identity_key LIKE 'unidentified:%'"
        ).fetchone()
        assert unidentified is not None

        a = conn.execute(
            """
            SELECT duration_measured_ms, flac_ok, integrity_state, integrity_checked_at,
                   sha256_checked_at, streaminfo_checked_at, download_source, download_date, mgmt_status
            FROM asset_file WHERE path = '/music/a.flac'
            """
        ).fetchone()
        assert a is not None
        assert int(a["duration_measured_ms"]) == 200300
        assert int(a["flac_ok"]) == 1
        assert a["integrity_state"] == "ok"
        assert a["integrity_checked_at"] == "2026-02-01T00:00:00Z"
        assert a["sha256_checked_at"] == "2026-02-01T00:00:00Z"
        assert a["streaminfo_checked_at"] == "2026-02-01T00:00:00Z"
        assert a["download_source"] == "bpdl"
        assert a["download_date"] == "2026-01-01"
        assert a["mgmt_status"] == "verified"

        isrc_identity = conn.execute(
            """
            SELECT canonical_artist, canonical_title, spotify_id, tidal_id, qobuz_id,
                   itunes_id, deezer_id, traxsource_id, musicbrainz_id
            FROM track_identity WHERE identity_key = 'isrc:USAAA1111111'
            """
        ).fetchone()
        assert isrc_identity is not None
        assert isrc_identity["canonical_artist"] == "Artist A"
        assert isrc_identity["canonical_title"] == "Track A"
        assert isrc_identity["spotify_id"] == "sp_1"
        assert isrc_identity["tidal_id"] == "td_1"
        assert isrc_identity["qobuz_id"] == "qb_1"
        assert isrc_identity["itunes_id"] == "it_1"
        assert isrc_identity["deezer_id"] == "dz_1"
        assert isrc_identity["traxsource_id"] == "tx_1"
        assert isrc_identity["musicbrainz_id"] == "mb_1"

        source_row = conn.execute(
            """
            SELECT identity_key, provider, provider_track_id, metadata_json
            FROM library_track_sources
            """
        ).fetchone()
        assert source_row is not None
        assert source_row["identity_key"] == "isrc:USAAA1111111"
        assert source_row["provider"] == "beatport"
        assert source_row["provider_track_id"] == "BP-42"
        assert "v2_library_track_key" in str(source_row["metadata_json"])

        assert conn.execute("SELECT COUNT(*) FROM move_plan").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM move_execution").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM provenance_event").fetchone()[0] == 1

        asset_a_id = int(conn.execute("SELECT id FROM asset_file WHERE path = '/music/a.flac'").fetchone()[0])
        identity_a_id = int(
            conn.execute("SELECT id FROM track_identity WHERE identity_key = 'isrc:USAAA1111111'").fetchone()[0]
        )
        move_exec = conn.execute("SELECT asset_id FROM move_execution WHERE id = 21").fetchone()
        prov = conn.execute("SELECT asset_id, identity_id FROM provenance_event WHERE id = 31").fetchone()
        assert int(move_exec["asset_id"]) == asset_a_id
        assert int(prov["asset_id"]) == asset_a_id
        assert int(prov["identity_id"]) == identity_a_id
    finally:
        conn.close()


def test_migrate_v2_to_v3_resume_is_idempotent(tmp_path: Path) -> None:
    v2 = _create_v2_fixture(tmp_path)
    v3 = tmp_path / "music_v3.db"

    first = migrate_v2_to_v3(
        v2_path=v2,
        v3_path=v3,
        batch_size=1,
        resume=False,
        dry_run=False,
        strict=True,
    )
    second = migrate_v2_to_v3(
        v2_path=v2,
        v3_path=v3,
        batch_size=1,
        resume=True,
        dry_run=False,
        strict=True,
    )

    assert first["assets_migrated"] == 4
    assert second["assets_migrated"] == 4
    assert second["identities_created"] == first["identities_created"]

    conn = sqlite3.connect(str(v3))
    conn.row_factory = sqlite3.Row
    try:
        progress = conn.execute("SELECT is_complete, last_v2_rowid FROM migration_progress WHERE id = 1").fetchone()
        assert progress is not None
        assert int(progress["is_complete"]) == 1
        assert int(progress["last_v2_rowid"]) > 0

        assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM asset_link").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 4
    finally:
        conn.close()
