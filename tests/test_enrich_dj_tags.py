from __future__ import annotations

import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

from tagslut.exec.enrich_dj_tags import enrich_dj_tags
from tagslut.storage.v3.analysis_service import resolve_dj_tag_snapshot
from tagslut.storage.v3.schema import create_schema_v3


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
    profile_energy: int | None = None,
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
    conn.execute(
        "INSERT INTO preferred_asset (identity_id, asset_id, score, reason_json, version) VALUES (?, ?, 1.0, '{}', 1)",
        (identity_id, asset_id),
    )
    if profile_energy is not None:
        conn.execute(
            """
            INSERT INTO dj_track_profile (identity_id, energy, dj_tags_json)
            VALUES (?, ?, '[]')
            """,
            (identity_id, profile_energy),
        )

    if link_identity:
        conn.execute(
            """
            INSERT INTO asset_link (asset_id, identity_id, confidence, link_source, active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (asset_id, identity_id, 1.0, "test"),
        )

    return asset_id, identity_id


def test_snapshot_cache_hit_uses_identity_and_profile_without_subprocess(tmp_path: Path) -> None:
    conn = _create_conn()
    flac_path = tmp_path / "cache-hit.flac"
    _seed_asset_and_identity(conn, flac_path, canonical_bpm=128.0, canonical_key="Am", profile_energy=7)

    with patch("tagslut.storage.v3.analysis_service.subprocess.run") as mock_run:
        snapshot = resolve_dj_tag_snapshot(conn, 1)

    assert snapshot.bpm == "128"
    assert snapshot.musical_key == "Am"
    assert snapshot.energy_1_10 == 7
    assert snapshot.bpm_source == "identity"
    assert snapshot.key_source == "identity"
    assert snapshot.energy_source == "dj_profile"
    mock_run.assert_not_called()


def test_snapshot_partial_cache_runs_essentia_and_inserts_asset_analysis(tmp_path: Path) -> None:
    conn = _create_conn()
    flac_path = tmp_path / "partial-cache.flac"
    _asset_id, identity_id = _seed_asset_and_identity(conn, flac_path, canonical_bpm=128.0)

    def fake_run(cmd: list[str], capture_output: bool, text: bool, check: bool) -> subprocess.CompletedProcess[str]:
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

    with patch(
        "tagslut.storage.v3.analysis_service.shutil.which",
        return_value="/usr/local/bin/essentia_streaming_extractor_music",
    ), patch("tagslut.storage.v3.analysis_service.subprocess.run", side_effect=fake_run) as mock_run:
        snapshot = resolve_dj_tag_snapshot(conn, identity_id)

    row = conn.execute(
        """
        SELECT bpm, musical_key, analysis_energy_1_10
        FROM asset_analysis
        WHERE asset_id = 1 AND analysis_scope = 'dj'
        """
    ).fetchone()
    identity_row = conn.execute(
        "SELECT canonical_bpm, canonical_key FROM track_identity WHERE id = ?",
        (identity_id,),
    ).fetchone()

    assert snapshot.bpm == "128"
    assert snapshot.musical_key == "Am"
    assert snapshot.energy_1_10 == 7
    assert snapshot.bpm_source == "identity"
    assert snapshot.key_source == "analysis"
    assert snapshot.energy_source == "analysis"
    assert row is not None
    assert float(row["bpm"]) == 127.6
    assert row["musical_key"] == "Am"
    assert int(row["analysis_energy_1_10"]) == 7
    assert identity_row is not None
    assert float(identity_row["canonical_bpm"]) == 128.0
    assert identity_row["canonical_key"] is None
    assert mock_run.call_count == 1


def test_snapshot_essentia_failure_returns_partial_and_inserts_nothing(tmp_path: Path, caplog) -> None:  # type: ignore[no-untyped-def]
    conn = _create_conn()
    flac_path = tmp_path / "failure.flac"
    _asset_id, identity_id = _seed_asset_and_identity(conn, flac_path, canonical_bpm=128.0)

    with caplog.at_level(logging.WARNING), patch(
        "tagslut.storage.v3.analysis_service.shutil.which",
        return_value="/usr/local/bin/essentia_streaming_extractor_music",
    ), patch(
        "tagslut.storage.v3.analysis_service.subprocess.run",
        return_value=subprocess.CompletedProcess(["essentia"], 1, "", "boom"),
    ):
        snapshot = resolve_dj_tag_snapshot(conn, identity_id)

    row = conn.execute("SELECT COUNT(*) AS n FROM asset_analysis").fetchone()
    assert "Essentia failed" in caplog.text
    assert snapshot.bpm == "128"
    assert snapshot.musical_key is None
    assert snapshot.energy_1_10 is None
    assert row is not None
    assert int(row["n"]) == 0


def test_snapshot_dry_run_does_not_insert_asset_analysis(tmp_path: Path) -> None:
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

    with patch(
        "tagslut.storage.v3.analysis_service.shutil.which",
        return_value="/usr/local/bin/essentia_streaming_extractor_music",
    ), patch("tagslut.storage.v3.analysis_service.subprocess.run", side_effect=fake_run):
        snapshot = resolve_dj_tag_snapshot(conn, identity_id, dry_run=True)

    row = conn.execute("SELECT COUNT(*) AS n FROM asset_analysis").fetchone()
    assert snapshot.bpm == "130"
    assert snapshot.musical_key == "F#"
    assert snapshot.energy_1_10 == 10
    assert row is not None
    assert int(row["n"]) == 0


def test_enrich_dj_tags_wrapper_returns_snapshot_fields_without_flac_writes(tmp_path: Path) -> None:
    conn = _create_conn()
    flac_path = tmp_path / "wrapper.flac"
    _seed_asset_and_identity(conn, flac_path, canonical_bpm=126.0, canonical_key="Cm", profile_energy=5)

    with patch("tagslut.exec.enrich_dj_tags.resolve_dj_tag_snapshot_for_path") as mock_snapshot:
        class _Snapshot:
            bpm = "126"
            musical_key = "Cm"
            energy_1_10 = 5

        mock_snapshot.return_value = _Snapshot()
        result = enrich_dj_tags(conn, flac_path, dry_run=False)

    assert result == {"bpm": "126", "key": "Cm", "energy": "5"}
