from __future__ import annotations

import sqlite3
from pathlib import Path

from click.testing import CliRunner

from tagslut.cli.main import cli
from tagslut.storage.schema import init_db
from tagslut.storage.v3 import create_schema_v3


class _FakeFlac:
    def __init__(self) -> None:
        self.tags: dict[str, list[str]] = {}
        self.saved = False

    def save(self) -> None:
        self.saved = True


def test_ops_writeback_canonical_uses_v3_identity_data(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "music.db"
    flac_path = tmp_path / "track.flac"
    flac_path.write_bytes(b"fake")

    conn = sqlite3.connect(str(db_path))
    create_schema_v3(conn)
    init_db(conn)
    conn.execute(
        """
        INSERT INTO files (path, canonical_label)
        VALUES (?, ?)
        """,
        (str(flac_path), "Legacy Label"),
    )
    conn.execute(
        """
        INSERT INTO asset_file (path, library, zone)
        VALUES (?, 'MASTER_LIBRARY', 'library')
        """,
        (str(flac_path),),
    )
    asset_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO track_identity (
            identity_key,
            canonical_artist,
            canonical_title,
            canonical_label,
            canonical_bpm,
            canonical_key,
            ingested_at,
            ingestion_method,
            ingestion_source,
            ingestion_confidence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("artist::title", "Artist", "Title", "V3 Label", 128.0, "Am", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
    )
    identity_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.execute(
        """
        INSERT INTO asset_link (asset_id, identity_id, active)
        VALUES (?, ?, 1)
        """,
        (asset_id, identity_id),
    )
    conn.commit()
    conn.close()

    fake_audio = _FakeFlac()
    monkeypatch.setattr("tagslut.exec.canonical_writeback.FLAC", lambda *_args, **_kwargs: fake_audio)
    monkeypatch.setenv("TAGSLUT_DB", str(db_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["ops", "writeback-canonical", "--path", str(flac_path), "--execute"])

    assert result.exit_code == 0, result.output
    assert fake_audio.saved is True
    assert fake_audio.tags["LABEL"] == ["V3 Label"]
    assert fake_audio.tags["ARTIST"] == ["Artist"]
    assert fake_audio.tags["TITLE"] == ["Title"]
    assert fake_audio.tags["BPM"] == ["128.0"]
    assert fake_audio.tags["INITIALKEY"] == ["Am"]
    assert "Updated: 1" in result.output
