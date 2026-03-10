from __future__ import annotations

import importlib.util as _ilu
import json
import sqlite3
import sys
from pathlib import Path
from types import ModuleType

from tagslut.storage.schema import init_db

_SCRIPT = (
    Path(__file__).resolve().parents[3] / "scripts" / "backfill_v3_identity_links.py"
)
_SPEC = _ilu.spec_from_file_location("backfill_v3_identity_links", _SCRIPT)
assert _SPEC is not None
_MOD: ModuleType = _ilu.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_MOD)

main = _MOD.main


def _db_fixture(tmp_path: Path) -> Path:
    db_path = tmp_path / "music.db"
    conn = sqlite3.connect(str(db_path))
    try:
        init_db(conn)
        conn.executemany(
            """
            INSERT INTO files (
                path, checksum, sha256, duration, library, zone,
                canonical_isrc, canonical_artist, canonical_title, library_track_key,
                metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "/music/a.flac",
                    "chk-a",
                    "sha-a",
                    301.0,
                    "master",
                    "accepted",
                    "USAAA1111111",
                    "Artist A",
                    "Track A",
                    "isrc:USAAA1111111",
                    json.dumps({"album": "Album A"}),
                ),
                (
                    "/music/a.mp3",
                    "chk-b",
                    "sha-b",
                    301.0,
                    "dj",
                    "accepted",
                    "USAAA1111111",
                    "Artist A",
                    "Track A",
                    "isrc:USAAA1111111",
                    json.dumps({"album": "Album A"}),
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO library_tracks (
                library_track_key, title, artist, album, duration_ms, isrc, genre, bpm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "isrc:USAAA1111111",
                "Track A",
                "Artist A",
                "Album A",
                301000,
                "USAAA1111111",
                "House",
                124.0,
            ),
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
                "https://example.test/track/42",
                json.dumps({"label": "Label A"}),
                "USAAA1111111",
                "0.99",
                "2026-03-08T00:00:00Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_twin_flac_and_mp3_backfill_to_one_identity(tmp_path: Path) -> None:
    db_path = _db_fixture(tmp_path)
    artifacts_dir = tmp_path / "artifacts"

    rc = main(
        [
            "--db",
            str(db_path),
            "--execute",
            "--artifacts-dir",
            str(artifacts_dir),
            "--commit-every",
            "1",
            "--checkpoint-every",
            "1",
        ]
    )

    assert rc == 0

    conn = sqlite3.connect(str(db_path))
    try:
        track_identity_total = conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0]
        asset_total = conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0]
        link_total = conn.execute("SELECT COUNT(*) FROM asset_link WHERE active = 1").fetchone()[0]
        identity_keys = conn.execute(
            "SELECT identity_key FROM track_identity ORDER BY id ASC"
        ).fetchall()
        assert track_identity_total == 1
        assert asset_total == 2
        assert link_total == 2
        assert [row[0] for row in identity_keys] == ["isrc:usaaa1111111"]
    finally:
        conn.close()

    summary_files = sorted(artifacts_dir.glob("backfill_v3_summary_*.json"))
    checkpoint_files = sorted(artifacts_dir.glob("backfill_v3_checkpoint_*.json"))
    assert summary_files
    assert checkpoint_files

    summary = json.loads(summary_files[-1].read_text(encoding="utf-8"))
    assert summary["processed"] == 2
    assert summary["created"] == 1
    assert summary["reused"] == 1
    assert summary["samples"]["created"]
    assert summary["samples"]["reused"]
    assert "fuzzy_near_collision" in summary["samples"]


def test_resume_from_file_id_processes_remaining_rows(tmp_path: Path) -> None:
    db_path = _db_fixture(tmp_path)
    artifacts_dir = tmp_path / "artifacts"

    rc1 = main(
        [
            "--db",
            str(db_path),
            "--execute",
            "--artifacts-dir",
            str(artifacts_dir),
            "--commit-every",
            "1",
            "--checkpoint-every",
            "1",
            "--limit",
            "1",
        ]
    )
    assert rc1 == 0

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM asset_link WHERE active = 1").fetchone()[0] == 1
    finally:
        conn.close()

    rc2 = main(
        [
            "--db",
            str(db_path),
            "--execute",
            "--artifacts-dir",
            str(artifacts_dir),
            "--resume-from-file-id",
            "1",
            "--commit-every",
            "1",
            "--checkpoint-every",
            "1",
        ]
    )
    assert rc2 == 0

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("SELECT COUNT(*) FROM track_identity").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM asset_link WHERE active = 1").fetchone()[0] == 2
    finally:
        conn.close()


def test_summary_artifact_has_required_count_and_sample_keys(tmp_path: Path) -> None:
    db_path = _db_fixture(tmp_path)
    artifacts_dir = tmp_path / "artifacts"

    rc = main(
        [
            "--db",
            str(db_path),
            "--artifacts-dir",
            str(artifacts_dir),
            "--checkpoint-every",
            "1",
            "--limit",
            "1",
        ]
    )
    assert rc == 0

    summary_files = sorted(artifacts_dir.glob("backfill_v3_summary_*.json"))
    assert summary_files
    payload = json.loads(summary_files[-1].read_text(encoding="utf-8"))
    for key in (
        "created",
        "reused",
        "merged",
        "skipped",
        "conflicted",
        "fuzzy_near_collision",
        "errors",
    ):
        assert key in payload
        assert key in payload["samples"]
