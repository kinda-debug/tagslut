from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

from tagslut.exec.enrich_dj_tags import enrich_dj_tags
from tagslut.storage.v3.schema import create_schema_v3


class _FakeFlac(dict):
    def __init__(self) -> None:
        super().__init__()
        self.saved = False

    def save(self) -> None:
        self.saved = True


def _create_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema_v3(conn)
    return conn


def _seed_asset_and_identity(
    conn: sqlite3.Connection,
    flac_path: Path,
    *,
    canonical_bpm: float | None = None,
    canonical_key: str | None = None,
    link_identity: bool = True,
) -> tuple[int, int]:
    conn.execute("INSERT INTO asset_file(path) VALUES (?)", (str(flac_path),))
    asset_id = int(conn.execute("SELECT id FROM asset_file").fetchone()["id"])

    conn.execute(
        """
        INSERT INTO track_identity (identity_key, canonical_bpm, canonical_key)
        VALUES (?, ?, ?)
        """,
        (f"asset:{asset_id}", canonical_bpm, canonical_key),
    )
    identity_id = int(conn.execute("SELECT id FROM track_identity").fetchone()["id"])

    if link_identity:
        conn.execute(
            """
            INSERT INTO asset_link (asset_id, identity_id, confidence, link_source, active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (asset_id, identity_id, 1.0, "test"),
        )

    return asset_id, identity_id


def test_db_cache_hit(tmp_path: Path) -> None:
    conn = _create_conn()
    flac_path = tmp_path / "cache-hit.flac"
    _seed_asset_and_identity(conn, flac_path, canonical_bpm=128.0, canonical_key="Am")
    fake_flac = _FakeFlac()

    with patch("tagslut.exec.enrich_dj_tags.FLAC", return_value=fake_flac) as mock_flac, patch(
        "tagslut.exec.enrich_dj_tags.subprocess.run"
    ) as mock_run:
        result = enrich_dj_tags(conn, flac_path)

    assert result == {"bpm": "128", "key": "Am", "energy": None}
    assert fake_flac["bpm"] == ["128"]
    assert fake_flac["initialkey"] == ["Am"]
    assert "energy" not in fake_flac
    assert fake_flac.saved is True
    mock_flac.assert_called_once_with(flac_path)
    mock_run.assert_not_called()


def test_essentia_fallback(tmp_path: Path) -> None:
    conn = _create_conn()
    flac_path = tmp_path / "fallback.flac"
    _asset_id, identity_id = _seed_asset_and_identity(conn, flac_path)
    fake_flac = _FakeFlac()

    def fake_run(cmd: list[str], capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        Path(cmd[2]).write_text(
            json.dumps(
                {
                    "rhythm": {"bpm": 127.6},
                    "tonal": {"key_key": "A", "key_scale": "minor"},
                    "lowlevel": {"average_loudness": 0.63},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("tagslut.exec.enrich_dj_tags.FLAC", return_value=fake_flac), patch(
        "tagslut.exec.enrich_dj_tags.shutil.which",
        return_value="/usr/local/bin/essentia_streaming_extractor_music",
    ), patch("tagslut.exec.enrich_dj_tags.subprocess.run", side_effect=fake_run) as mock_run:
        result = enrich_dj_tags(conn, flac_path)

    row = conn.execute(
        "SELECT canonical_bpm, canonical_key FROM track_identity WHERE id = ?",
        (identity_id,),
    ).fetchone()

    assert result == {"bpm": "128", "key": "Am", "energy": "7"}
    assert fake_flac["bpm"] == ["128"]
    assert fake_flac["initialkey"] == ["Am"]
    assert fake_flac["energy"] == ["7"]
    assert fake_flac.saved is True
    assert row is not None
    assert float(row["canonical_bpm"]) == 128.0
    assert row["canonical_key"] == "Am"
    assert mock_run.call_count == 1


def test_no_identity_link(tmp_path: Path, caplog) -> None:  # type: ignore[no-untyped-def]
    conn = _create_conn()
    flac_path = tmp_path / "no-link.flac"
    _seed_asset_and_identity(conn, flac_path, link_identity=False)

    with caplog.at_level(logging.WARNING), patch("tagslut.exec.enrich_dj_tags.FLAC") as mock_flac, patch(
        "tagslut.exec.enrich_dj_tags.subprocess.run"
    ) as mock_run:
        result = enrich_dj_tags(conn, flac_path)

    assert result == {}
    assert f"no identity link for {flac_path}, skipping enrichment" in caplog.text
    mock_flac.assert_not_called()
    mock_run.assert_not_called()


def test_dry_run(tmp_path: Path) -> None:
    conn = _create_conn()
    flac_path = tmp_path / "dry-run.flac"
    _asset_id, identity_id = _seed_asset_and_identity(conn, flac_path)

    def fake_run(cmd: list[str], capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess[str]:
        Path(cmd[2]).write_text(
            json.dumps(
                {
                    "rhythm": {"bpm": 129.9},
                    "tonal": {"key_key": "F#", "key_scale": "major"},
                    "lowlevel": {"average_loudness": 1.0},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with patch("tagslut.exec.enrich_dj_tags.FLAC") as mock_flac, patch(
        "tagslut.exec.enrich_dj_tags.shutil.which",
        return_value="/usr/local/bin/essentia_streaming_extractor_music",
    ), patch("tagslut.exec.enrich_dj_tags.subprocess.run", side_effect=fake_run):
        result = enrich_dj_tags(conn, flac_path, dry_run=True)

    row = conn.execute(
        "SELECT canonical_bpm, canonical_key FROM track_identity WHERE id = ?",
        (identity_id,),
    ).fetchone()

    assert result == {"bpm": "130", "key": "F#", "energy": "10"}
    assert row is not None
    assert row["canonical_bpm"] is None
    assert row["canonical_key"] is None
    mock_flac.assert_not_called()
