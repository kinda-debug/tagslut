from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from tagslut.exec.dj_manifest_receipts import apply_dj_export_manifest
from tagslut.storage.schema import init_db
from tagslut.storage.v3 import create_schema_v3


def test_apply_dj_export_manifest_normalizes_receipt_paths(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "music.db"
    manifest_path = tmp_path / "dj_manifest.csv"
    playlist_inputs_path = tmp_path / "playlist_inputs.txt"
    flac_path = tmp_path / "source" / "track.flac"
    mp3_path = tmp_path / "exports" / "track.mp3"

    flac_path.parent.mkdir(parents=True, exist_ok=True)
    flac_path.write_bytes(b"fake")
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    mp3_path.write_bytes(b"mp3")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    init_db(conn)
    conn.execute("INSERT INTO asset_file (id, path) VALUES (1, ?)", (str(flac_path.resolve()),))
    conn.execute(
        """
        INSERT INTO track_identity (
            id, identity_key, canonical_artist, canonical_title, canonical_bpm, canonical_key
        ) VALUES (1, 'identity:1', 'Artist', 'Title', 128, 'Am')
        """
    )
    conn.execute(
        "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (1, 1, 1, '{}', 1)"
    )
    conn.execute("INSERT INTO files (path) VALUES (?)", (str(flac_path.resolve()),))
    conn.commit()
    conn.close()

    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["source_path", "dest_path", "identity_id", "action", "reason"])
        writer.writeheader()
        writer.writerow(
            {
                "source_path": "source/track.flac",
                "dest_path": "exports/track.mp3",
                "identity_id": "1",
                "action": "copy",
                "reason": "test",
            }
        )

    monkeypatch.chdir(tmp_path)

    count = apply_dj_export_manifest(db_path, manifest_path, playlist_inputs_path)

    assert count == 1

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            """
            SELECT source_path, dest_path, event_type, status
            FROM provenance_event
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[0] == str(flac_path.resolve())
        assert row[1] == str(mp3_path.resolve())
        assert row[2] == "dj_export"
        assert row[3] == "success"

        files_row = conn.execute("SELECT dj_pool_path FROM files WHERE path = ?", (str(flac_path.resolve()),)).fetchone()
        assert files_row is not None
        assert files_row[0] == str(mp3_path.resolve())
    finally:
        conn.close()

    assert playlist_inputs_path.read_text(encoding="utf-8") == f"{mp3_path.resolve()}\n"
