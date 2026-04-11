"""Unit tests for intake_orchestrator."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from tagslut.cli.commands.intake import register_intake_group
from tagslut.exec.intake_orchestrator import (
    IntakeResult,
    IntakeStageResult,
    _GetIntakeHumanSummarizer,
    _parse_precheck_csv,
    run_intake,
)


@pytest.fixture(autouse=True)
def _set_artifacts_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TAGSLUT_ARTIFACTS", str(tmp_path / "artifacts"))


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a minimal test database."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))

    # Create minimal schema
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS track_identity (
            id INTEGER PRIMARY KEY,
            isrc TEXT,
            beatport_id TEXT,
            tidal_id TEXT,
            title_norm TEXT,
            artist_norm TEXT,
            ingested_at TEXT NOT NULL,
            ingestion_method TEXT NOT NULL,
            ingestion_source TEXT NOT NULL,
            ingestion_confidence TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_file (
            id INTEGER PRIMARY KEY,
            path TEXT,
            file_hash TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS asset_link (
            id INTEGER PRIMARY KEY,
            identity_id INTEGER,
            asset_id INTEGER,
            confidence REAL,
            active INTEGER
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mp3_asset (
            id INTEGER PRIMARY KEY,
            identity_id INTEGER,
            asset_id INTEGER,
            profile TEXT,
            path TEXT,
            status TEXT,
            transcoded_at TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dj_admission (
            id INTEGER PRIMARY KEY,
            identity_id INTEGER UNIQUE,
            mp3_asset_id INTEGER,
            status TEXT,
            admitted_at TEXT,
            notes TEXT
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS dj_track_id_map (
            id INTEGER PRIMARY KEY,
            dj_admission_id INTEGER UNIQUE,
            rekordbox_track_id INTEGER NOT NULL UNIQUE,
            assigned_at TEXT
        )
        """
    )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def mock_precheck_csv(tmp_path: Path) -> Path:
    """Create a mock precheck CSV with all tracks blocked."""
    csv_path = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260315_140000.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    csv_content = (
        "domain,source_link,track_id,isrc,title,artist,album,decision,confidence,match_method,"
        "reason,db_path,db_download_source,existing_quality_rank,candidate_quality_rank\n"
        "beatport,https://www.beatport.com/release/test/123,456,USTEST001,Test Track,Test Artist,"
        "Test Album,skip,high,isrc,"
        "\"matched by isrc; existing rank 3 is equal or better than candidate rank 3\","
        "/path/to/file.flac,beatport,3,3\n"
    )
    csv_path.write_text(csv_content, encoding="utf-8")

    return csv_path


@pytest.fixture
def mock_precheck_csv_new(tmp_path: Path) -> Path:
    """Create a mock precheck CSV with new tracks to download."""
    csv_path = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260315_140001.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    csv_content = (
        "domain,source_link,track_id,isrc,title,artist,album,decision,confidence,match_method,"
        "reason,db_path,db_download_source,existing_quality_rank,candidate_quality_rank\n"
        "beatport,https://www.beatport.com/release/test/123,456,USTEST001,Test Track,Test Artist,"
        "Test Album,keep,,,," "\"no inventory match\"" ",,,3\n"
        "beatport,https://www.beatport.com/release/test/123,789,USTEST002,Test Track 2,"
        "Test Artist 2,Test Album,keep,,,," "\"no inventory match\"" ",,,3\n"
    )
    csv_path.write_text(csv_content, encoding="utf-8")

    return csv_path


def test_parse_precheck_csv_blocked(mock_precheck_csv: Path) -> None:
    """Test parsing precheck CSV with blocked tracks."""
    summary = _parse_precheck_csv(mock_precheck_csv)

    assert summary["total"] == 1
    assert summary["new"] == 0
    assert summary["upgrade"] == 0
    assert summary["blocked"] == 1


def test_parse_precheck_csv_new(mock_precheck_csv_new: Path) -> None:
    """Test parsing precheck CSV with new tracks."""
    summary = _parse_precheck_csv(mock_precheck_csv_new)

    assert summary["total"] == 2
    assert summary["new"] == 2
    assert summary["upgrade"] == 0
    assert summary["blocked"] == 0


def test_get_intake_human_summarizer_is_path_free(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "artifacts" / "compare"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    precheck_csv = artifacts_dir / "precheck_decisions_20260316_200000.csv"
    precheck_csv.write_text(
        (
            "decision,title,artist,reason\n"
            "keep,Bullet Time,Matt Egbert,no inventory match\n"
            "skip,Korova Bar,Huerta,matched by isrc; existing rank 3 is equal or better than candidate rank 3\n"
        ),
        encoding="utf-8",
    )

    roon_inputs = artifacts_dir / "roon_m3u_inputs_20260316_200001.txt"
    roon_inputs.write_text(
        "library/Bullet Time.flac\nlibrary/Korova Bar.flac\n",
        encoding="utf-8",
    )

    tag_keys = tmp_path / "tags_keys.txt"
    tag_keys.write_text("artist\ntitle\nisrc\n", encoding="utf-8")

    emitted: list[str] = []
    summarizer = _GetIntakeHumanSummarizer(
        verbose=True,
        run_started=time.time(),
        emit=emitted.append,
    )

    sample = [
        "[1/10] Pre-download check\n",
        "Precheck summary: keep=23 skip=1 total=24\n",
        "[2/10] Download from Tidal\n",
        "Selected for download: 23 track(s)\n",
        "[1/23] https://tidal.com/browse/track/123\n",
        "│ ⠧ Disorientation  16-bit, 44.1 kHz 17.1 MB 176.1 kB/s                                │\n",
        "Downloaded Disorientation  16-bit, 44.1 kHz /Volumes/MUSIC/staging/tidal/Simon & Shaker/foo.flac\n",
        "[2/23] https://tidal.com/browse/track/456\n",
        "Exists Tokyo Shanghai /Volumes/MUSIC/staging/tidal/Shlomi Aber/Tokyo Shanghai EP\n",
        "[3/23] https://tidal.com/browse/track/789\n",
        "Error: Response payload is not completed: <ContentLengthError> (track/85305930)\n",
        "[3/10] Quick duplicate check (index check, strict)\n",
        "Total:            24\n",
        "Duplicates:        0\n",
        "Errors:            0\n",
        "[4/10] Trust scan + integrity registration\n",
        "Discovered: 24\n",
        "Succeeded: 22\n",
        "Failed: 2\n",
        "[5/10] Local identify + tag prep\n",
        "OK: scanned_files=27\n",
        f"OK: wrote {tag_keys}\n",
        "Updated DB rows: 22\n",
        "Tagged:  0\n",
        "[8/10] Apply plans\n",
        "EXECUTE: planned=22 moved=22 skipped_missing=0 skipped_exists=0 failed=0\n",
        "[9/10] Generate Roon M3U\n",
        "Named playlist: /Volumes/MUSIC/MASTER_LIBRARY/playlists/roon-foo.m3u\n",
        "[10/10] Launch background enrich + art\n",
        "Background enrich/art started: pid=75512\n",
        "Run summary\n",
        "  promoted:     22\n",
        "  stashed:      2\n",
        "  quarantined:  0\n",
        "  discarded:    0\n",
    ]
    for line in sample:
        summarizer.feed_line(line)
    summarizer.finalize()

    out = "\n".join(emitted)
    assert "/Volumes/" not in out
    assert str(tmp_path) not in out
    assert "Precheck:" in out
    assert "Download:" in out
    assert "Index check:" in out
    assert "M3U:" in out
    assert "Enrich/art:" in out
    assert "decision" in out
    assert "result" in out
    assert "playlist items" in out
    assert "-+-" in out
    assert "[1/23] active: Disorientation at 176.1 kB/s" in out
    assert "[1/23] downloaded: Disorientation" in out
    assert "[2/23] present in staging: Tokyo Shanghai" in out
    assert "[3/23] failed: track/85305930" in out
    assert "already present in staging" in out
    assert "resume candidate" in out


def test_precheck_block_returns_disposition_blocked(
    temp_db: Path, tmp_path: Path, mock_precheck_csv: Path
) -> None:
    """Test that when all tracks blocked, disposition is 'blocked'."""
    os.utime(mock_precheck_csv, (time.time() + 5, time.time() + 5))
    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = mock_precheck_csv

            result = run_intake(
                url="https://www.beatport.com/release/test/123",
                db_path=temp_db,
                mp3=False,
                dry_run=False,
                artifact_dir=tmp_path / "artifacts",
            )

    assert result.disposition == "blocked"
    assert len(result.stages) >= 1
    assert result.stages[0].stage == "precheck"
    assert result.stages[0].status == "blocked"
    assert result.precheck_summary["blocked"] == 1
    assert result.precheck_summary["new"] == 0


def test_precheck_new_dry_run_no_subprocess(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    """Test --dry-run with new tracks doesn't call download subprocess."""
    with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch(
            "tagslut.exec.intake_orchestrator._find_latest_precheck_csv"
        ) as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            result = run_intake(
                url="https://www.beatport.com/release/test/123",
                db_path=temp_db,
                mp3=False,
                dry_run=True,
                artifact_dir=tmp_path / "artifacts",
            )

    # Precheck subprocess called, but not download
    assert mock_run.call_count == 1
    assert "pre_download_check.py" in str(mock_run.call_args_list[0])

    assert result.disposition == "completed"
    assert result.precheck_summary["new"] == 2

    # Find download stage
    download_stage = next((s for s in result.stages if s.stage == "download"), None)
    assert download_stage is not None
    assert download_stage.status == "skipped"
    assert "--dry-run" in download_stage.detail


def test_download_does_not_waive_precheck_by_default(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    """Non-dry-run should not implicitly pass --no-precheck to tools/get."""
    os.utime(mock_precheck_csv_new, (time.time() + 5, time.time() + 5))

    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            run_intake(
                url="https://www.beatport.com/release/test/123",
                db_path=temp_db,
                mp3=False,
                dry_run=False,
                artifact_dir=tmp_path / "artifacts",
            )

    assert mock_get.call_count == 1
    called_cmd = mock_get.call_args.args[0]
    assert "--no-precheck" not in called_cmd


def test_artifact_written_on_block(
    temp_db: Path, tmp_path: Path, mock_precheck_csv: Path
) -> None:
    """Test that artifact JSON is written even when all tracks blocked."""
    artifact_dir = tmp_path / "artifacts"

    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = mock_precheck_csv

            result = run_intake(
                url="https://www.beatport.com/release/test/123",
                db_path=temp_db,
                mp3=False,
                dry_run=False,
                artifact_dir=artifact_dir,
            )

    assert result.artifact_path is not None
    assert result.artifact_path.exists()

    artifact_data = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert artifact_data["disposition"] == "blocked"
    assert artifact_data["url"] == "https://www.beatport.com/release/test/123"
    assert "timestamp" in artifact_data
    assert "stages" in artifact_data


def test_precheck_csv_path_in_artifact(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    """Test that precheck_csv field points to existing file."""
    artifact_dir = tmp_path / "artifacts"

    with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch(
            "tagslut.exec.intake_orchestrator._find_latest_precheck_csv"
        ) as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            result = run_intake(
                url="https://www.beatport.com/release/test/123",
                db_path=temp_db,
                mp3=False,
                dry_run=True,
                artifact_dir=artifact_dir,
            )

    assert result.precheck_csv is not None
    assert result.precheck_csv.exists()
    assert result.precheck_csv == mock_precheck_csv_new

    artifact_data = json.loads(result.artifact_path.read_text(encoding="utf-8"))
    assert artifact_data["precheck_csv"] == str(mock_precheck_csv_new)


def test_mp3_flag_calls_build_mp3_from_identity(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    """PR2: --mp3 builds full-tag MP3 assets and registers them in mp3_asset."""
    os.utime(mock_precheck_csv_new, (time.time() + 5, time.time() + 5))

    # Register a master FLAC in DB and mark it as promoted for this run.
    flac_path = tmp_path / "master.flac"
    flac_path.write_text("not a real flac", encoding="utf-8")

    conn = sqlite3.connect(str(temp_db))
    cur = conn.execute(
        "INSERT INTO track_identity (isrc, beatport_id, title_norm, artist_norm, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("USTEST001", "456", "test track", "test artist", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
    )
    identity_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO asset_file (path, file_hash) VALUES (?, ?)",
        (str(flac_path), "fakehash123"),
    )
    asset_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence, active) VALUES (?, ?, ?, ?)",
        (identity_id, asset_id, 0.95, 1),
    )
    conn.commit()
    conn.close()

    promoted_txt = tmp_path / "artifacts" / "compare" / "promoted_flacs_20260315_140002.txt"
    promoted_txt.parent.mkdir(parents=True, exist_ok=True)
    promoted_txt.write_text(str(flac_path) + "\n", encoding="utf-8")
    os.utime(promoted_txt, (time.time() + 5, time.time() + 5))

    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            with patch(
                "tagslut.exec.intake_orchestrator._find_latest_promoted_flacs_txt"
            ) as mock_find_promoted:
                mock_find_promoted.return_value = promoted_txt

                def _fake_transcode(source: Path, dest_path: Path, **_kwargs: object) -> Path:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_text("mp3-bytes", encoding="utf-8")
                    return dest_path

                with patch("tagslut.exec.transcoder.transcode_to_mp3_full_tags", new=_fake_transcode):

                    result = run_intake(
                        url="https://www.beatport.com/release/test/123",
                        db_path=temp_db,
                        mp3=True,
                        dry_run=False,
                        mp3_root=tmp_path / "mp3_assets",
                        artifact_dir=tmp_path / "artifacts",
                    )

    assert result.disposition == "completed"
    mp3_stage = next((s for s in result.stages if s.stage == "mp3"), None)
    assert mp3_stage is not None
    assert mp3_stage.status == "ok"

    conn = sqlite3.connect(str(temp_db))
    row = conn.execute(
        "SELECT identity_id, asset_id, profile, path, status FROM mp3_asset ORDER BY id LIMIT 1"
    ).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == identity_id
    assert row[1] == asset_id
    assert row[2] == "mp3_asset_320_cbr_full"
    assert row[4] == "verified"


def test_mp3_skips_gracefully_if_identity_not_registered(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    """PR1: --dj must imply --mp3 stage ordering, even as placeholders."""
    os.utime(mock_precheck_csv_new, (time.time() + 5, time.time() + 5))

    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            with patch(
                "tagslut.exec.intake_orchestrator._find_latest_promoted_flacs_txt"
            ) as mock_find_promoted:
                mock_find_promoted.return_value = None

                result = run_intake(
                    url="https://www.beatport.com/release/test/123",
                    db_path=temp_db,
                    mp3=False,
                    dj=True,
                    dry_run=False,
                    mp3_root=tmp_path / "mp3_assets",
                    dj_root=tmp_path / "dj_library",
                    artifact_dir=tmp_path / "artifacts",
                )

    mp3_idx = next(i for i, s in enumerate(result.stages) if s.stage == "mp3")
    dj_idx = next(i for i, s in enumerate(result.stages) if s.stage == "dj")
    assert mp3_idx < dj_idx


def test_mp3_without_dj_root_raises_click_exception(
    temp_db: Path, tmp_path: Path
) -> None:
    """Test --mp3 without --mp3-root raises ClickException before subprocess."""
    import click

    runner = CliRunner()

    # Register intake group
    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    result = runner.invoke(
        cli,
        [
            "intake",
            "url",
            "https://www.beatport.com/release/test/123",
            "--db",
            str(temp_db),
            "--mp3",
        ],
    )

    assert result.exit_code != 0
    assert "--mp3 requires --mp3-root" in result.output


def test_tag_flag_is_accepted_without_mp3_root(temp_db: Path) -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    fake_result = IntakeResult(
        url="https://www.beatport.com/release/test/123",
        stages=[IntakeStageResult(stage="enrich", status="ok")],
        disposition="completed",
        precheck_summary={"total": 0, "new": 0, "upgrade": 0, "blocked": 0},
        precheck_csv=None,
        artifact_path=None,
    )

    with patch("tagslut.cli.commands.intake.run_intake", return_value=fake_result) as mock_run:
        result = runner.invoke(
            cli,
            [
                "intake",
                "url",
                "https://www.beatport.com/release/test/123",
                "--db",
                str(temp_db),
                "--tag",
            ],
        )

    assert result.exit_code == 0
    assert mock_run.call_count == 1
    assert mock_run.call_args.kwargs["tag"] is True
    assert mock_run.call_args.kwargs["mp3"] is False


def test_mp3_placeholder_falls_back_to_precheck_skip_db_paths_when_no_promoted_file(
    temp_db: Path, tmp_path: Path, mock_precheck_csv: Path
) -> None:
    # Override the fixture CSV so the skip db_path points to a real FLAC on disk.
    flac_path = tmp_path / "existing.flac"
    flac_path.write_text("not a real flac", encoding="utf-8")

    decisions_csv = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260315_150000.csv"
    decisions_csv.parent.mkdir(parents=True, exist_ok=True)
    decisions_csv.write_text(
        (
            "domain,source_link,track_id,isrc,title,artist,album,decision,confidence,match_method,"
            "reason,db_path,db_download_source,existing_quality_rank,candidate_quality_rank\n"
            "beatport,https://www.beatport.com/release/test/123,456,USTEST001,Test Track,Test Artist,"
            "Test Album,skip,high,isrc," "\"matched\"" f",\"{flac_path}\",beatport,3,3\n"
        ),
        encoding="utf-8",
    )
    os.utime(decisions_csv, (time.time() + 5, time.time() + 5))

    conn = sqlite3.connect(str(temp_db))
    cur = conn.execute(
        "INSERT INTO track_identity (isrc, beatport_id, title_norm, artist_norm, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("USTEST001", "456", "test track", "test artist", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
    )
    identity_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO asset_file (path, file_hash) VALUES (?, ?)",
        (str(flac_path), "fakehash123"),
    )
    asset_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence, active) VALUES (?, ?, ?, ?)",
        (identity_id, asset_id, 0.95, 1),
    )
    conn.commit()
    conn.close()

    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = decisions_csv

            with patch(
                "tagslut.exec.intake_orchestrator._find_latest_promoted_flacs_txt"
            ) as mock_find_promoted:
                mock_find_promoted.return_value = None

                def _fake_transcode(source: Path, dest_path: Path, **_kwargs: object) -> Path:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_text("mp3-bytes", encoding="utf-8")
                    return dest_path

                with patch("tagslut.exec.transcoder.transcode_to_mp3_full_tags", new=_fake_transcode):
                    result = run_intake(
                        url="https://www.beatport.com/release/test/123",
                        db_path=temp_db,
                        mp3=True,
                        dry_run=False,
                        mp3_root=tmp_path / "mp3_assets",
                        artifact_dir=tmp_path / "artifacts",
                    )

    # Precheck blocked, but --mp3 fallback cohort exists => completed (resume semantics).
    assert result.disposition == "completed"
    precheck_stage = next(s for s in result.stages if s.stage == "precheck")
    assert precheck_stage.status == "blocked"

    mp3_stage = next(s for s in result.stages if s.stage == "mp3")
    assert mp3_stage.status == "ok"

    conn = sqlite3.connect(str(temp_db))
    row = conn.execute(
        "SELECT identity_id, asset_id, profile, status FROM mp3_asset ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row == (identity_id, asset_id, "mp3_asset_320_cbr_full", "verified")


def test_tag_runs_enrich_without_mp3(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    flac_path = tmp_path / "promoted.flac"
    flac_path.write_text("fake flac bytes", encoding="utf-8")

    promoted_txt = tmp_path / "artifacts" / "compare" / "promoted_flacs_20260315_150001.txt"
    promoted_txt.parent.mkdir(parents=True, exist_ok=True)
    promoted_txt.write_text(f"{flac_path}\n", encoding="utf-8")

    fresh_mtime = time.time() + 5
    os.utime(mock_precheck_csv_new, (fresh_mtime, fresh_mtime))
    os.utime(promoted_txt, (fresh_mtime, fresh_mtime))

    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            with patch(
                "tagslut.exec.intake_orchestrator._find_latest_promoted_flacs_txt"
            ) as mock_find_promoted:
                mock_find_promoted.return_value = promoted_txt

                with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
                    mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

                    result = run_intake(
                        url="https://www.beatport.com/release/test/123",
                        db_path=temp_db,
                        tag=True,
                        mp3=False,
                        dry_run=False,
                        artifact_dir=tmp_path / "artifacts",
                    )

    enrich_stage = next((s for s in result.stages if s.stage == "enrich"), None)
    mp3_stage = next((s for s in result.stages if s.stage == "mp3"), None)

    assert result.disposition == "completed"
    assert enrich_stage is not None
    assert enrich_stage.status == "ok"
    assert enrich_stage.artifact_path is not None
    assert enrich_stage.artifact_path.read_text(encoding="utf-8").strip() == str(flac_path.resolve())
    assert mp3_stage is not None
    assert mp3_stage.status == "skipped"
    assert "--mp3 not passed" in (mp3_stage.detail or "")
    assert mock_run.call_count == 1
    enrich_cmd = mock_run.call_args.args[0]
    assert "post_move_enrich_art.py" in " ".join(str(part) for part in enrich_cmd)
    assert "--providers" in enrich_cmd


def test_dj_build_registers_separate_profile_and_path(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    os.utime(mock_precheck_csv_new, (time.time() + 5, time.time() + 5))

    flac_path = tmp_path / "master.flac"
    flac_path.write_text("not a real flac", encoding="utf-8")

    conn = sqlite3.connect(str(temp_db))
    cur = conn.execute(
        "INSERT INTO track_identity (isrc, beatport_id, title_norm, artist_norm, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("USTEST001", "456", "test track", "test artist", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
    )
    identity_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO asset_file (path, file_hash) VALUES (?, ?)",
        (str(flac_path), "fakehash123"),
    )
    asset_id = int(cur.lastrowid)
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence, active) VALUES (?, ?, ?, ?)",
        (identity_id, asset_id, 0.95, 1),
    )
    conn.commit()
    conn.close()

    promoted_txt = tmp_path / "artifacts" / "compare" / "promoted_flacs_20260315_140010.txt"
    promoted_txt.parent.mkdir(parents=True, exist_ok=True)
    promoted_txt.write_text(str(flac_path) + "\n", encoding="utf-8")
    os.utime(promoted_txt, (time.time() + 5, time.time() + 5))

    mp3_root = tmp_path / "mp3_assets"
    dj_root = tmp_path / "dj_library"
    mp3_root.mkdir(parents=True, exist_ok=True)
    dj_root.mkdir(parents=True, exist_ok=True)

    with patch("tagslut.exec.intake_orchestrator._run_tools_get") as mock_get:
        mock_get.return_value = None

        with patch("tagslut.exec.intake_orchestrator._find_latest_precheck_csv") as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            with patch(
                "tagslut.exec.intake_orchestrator._find_latest_promoted_flacs_txt"
            ) as mock_find_promoted:
                mock_find_promoted.return_value = promoted_txt

                def _fake_transcode(source: Path, dest_path: Path, **_kwargs: object) -> Path:
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_text("mp3-bytes", encoding="utf-8")
                    return dest_path

                with patch("tagslut.exec.transcoder.transcode_to_mp3_full_tags", new=_fake_transcode):
                    with patch("tagslut.exec.transcoder.build_dj_copy_filename") as mock_name:
                        mock_name.return_value = "dj-copy.mp3"
                        with patch("tagslut.exec.transcoder.tag_mp3_as_dj_copy") as mock_tag:
                            result = run_intake(
                                url="https://www.beatport.com/release/test/123",
                                db_path=temp_db,
                                mp3=False,
                                dj=True,
                                dry_run=False,
                                mp3_root=mp3_root,
                                dj_root=dj_root,
                                artifact_dir=tmp_path / "artifacts",
                            )

    assert result.disposition == "completed"
    mp3_stage = next(s for s in result.stages if s.stage == "mp3")
    dj_stage = next(s for s in result.stages if s.stage == "dj")
    assert mp3_stage.status == "ok"
    assert dj_stage.status == "ok"
    assert mock_tag.call_count == 1

    conn = sqlite3.connect(str(temp_db))
    rows = conn.execute(
        "SELECT profile, path FROM mp3_asset WHERE identity_id = ? ORDER BY id",
        (identity_id,),
    ).fetchall()
    conn.close()

    assert len(rows) == 2
    full = next(p for p in rows if p[0] == "mp3_asset_320_cbr_full")
    dj = next(p for p in rows if p[0] == "dj_copy_320_cbr")
    full_path = Path(full[1]).resolve()
    dj_path = Path(dj[1]).resolve()
    assert full_path.is_relative_to(mp3_root.resolve())
    assert dj_path.is_relative_to(dj_root.resolve())
    assert full_path != dj_path

    # `tagslut intake --dj` must not silently auto-admit to DJ (`dj_admission` is separate, opt-in stage).
    conn = sqlite3.connect(str(temp_db))
    admitted = conn.execute("SELECT COUNT(*) FROM dj_admission").fetchone()[0]
    conn.close()
    assert admitted == 0


def test_backfill_prefers_dj_copy_profile_when_both_exist(temp_db: Path, tmp_path: Path) -> None:
    from tagslut.dj.admission import backfill_admissions

    conn = sqlite3.connect(str(temp_db))
    cur = conn.execute(
        "INSERT INTO track_identity (isrc, beatport_id, title_norm, artist_norm, ingested_at, ingestion_method, ingestion_source, ingestion_confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("USTEST001", "456", "test track", "test artist", '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy'),
    )
    identity_id = int(cur.lastrowid)
    cur = conn.execute(
        "INSERT INTO asset_file (path, file_hash) VALUES (?, ?)",
        (str(tmp_path / "master.flac"), "fakehash123"),
    )
    asset_id = int(cur.lastrowid)

    # Full-tag MP3 asset and DJ copy both present; backfill must pick DJ copy.
    cur = conn.execute(
        """
        INSERT INTO mp3_asset (identity_id, asset_id, profile, path, status, transcoded_at)
        VALUES (?, ?, ?, ?, 'verified', datetime('now'))
        """,
        (identity_id, asset_id, "mp3_asset_320_cbr_full", str(tmp_path / "full.mp3")),
    )
    cur = conn.execute(
        """
        INSERT INTO mp3_asset (identity_id, asset_id, profile, path, status, transcoded_at)
        VALUES (?, ?, ?, ?, 'verified', datetime('now'))
        """,
        (identity_id, asset_id, "dj_copy_320_cbr", str(tmp_path / "dj.mp3")),
    )
    dj_id = int(cur.lastrowid)
    conn.commit()

    admitted, skipped = backfill_admissions(conn)
    assert admitted == 1
    assert skipped == 0

    row = conn.execute(
        "SELECT identity_id, mp3_asset_id, status FROM dj_admission WHERE identity_id = ?",
        (identity_id,),
    ).fetchone()
    conn.close()

    assert row == (identity_id, dj_id, "admitted")


def test_cli_intake_direct_url_routes_to_intake_url_command(temp_db: Path) -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    url = "https://tidal.com/playlist/abc"
    fake_result = IntakeResult(
        url=url,
        stages=[],
        disposition="completed",
        precheck_summary={},
        precheck_csv=None,
        artifact_path=None,
    )

    with patch("tagslut.cli.commands.intake.run_intake") as mock_run:
        mock_run.return_value = fake_result
        result = runner.invoke(cli, ["intake", url, "--db", str(temp_db)])

    assert result.exit_code == 0
    assert mock_run.call_count == 1
    assert mock_run.call_args.kwargs["url"] == url


def test_cli_intake_url_alias_still_works(temp_db: Path) -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    url = "https://tidal.com/playlist/abc"
    fake_result = IntakeResult(
        url=url,
        stages=[],
        disposition="completed",
        precheck_summary={},
        precheck_csv=None,
        artifact_path=None,
    )

    with patch("tagslut.cli.commands.intake.run_intake") as mock_run:
        mock_run.return_value = fake_result
        result = runner.invoke(cli, ["intake", "url", url, "--db", str(temp_db)])

    assert result.exit_code == 0
    assert mock_run.call_count == 1
    assert mock_run.call_args.kwargs["url"] == url


def test_cli_hides_artifact_footers_without_debug_raw(temp_db: Path, tmp_path: Path) -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    url = "https://tidal.com/playlist/abc"
    fake_result = IntakeResult(
        url=url,
        stages=[],
        disposition="completed",
        precheck_summary={},
        precheck_csv=tmp_path / "precheck.csv",
        artifact_path=tmp_path / "artifact.json",
    )

    with patch("tagslut.cli.commands.intake.run_intake") as mock_run:
        mock_run.return_value = fake_result
        result = runner.invoke(cli, ["intake", url, "--db", str(temp_db)])

    assert result.exit_code == 0
    assert "Artifact:" not in result.output
    assert "Precheck CSV:" not in result.output


def test_cli_intake_subcommands_not_hijacked() -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    with patch("tagslut.cli.commands.intake.run_intake") as mock_run:
        result = runner.invoke(cli, ["intake", "resolve"])

    assert result.exit_code != 0
    assert "Missing option '--db'" in result.output
    assert mock_run.call_count == 0


def test_cli_mp3_root_deprecated_alias_is_dj_root_in_mp3_only_mode(
    temp_db: Path, tmp_path: Path
) -> None:
    import click

    runner = CliRunner(mix_stderr=False)

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    url = "https://tidal.com/playlist/abc"
    mp3_root = tmp_path / "mp3_assets"
    mp3_root.mkdir(parents=True, exist_ok=True)

    fake_result = IntakeResult(
        url=url,
        stages=[],
        disposition="completed",
        precheck_summary={},
        precheck_csv=None,
        artifact_path=None,
    )

    with patch("tagslut.cli.commands.intake.run_intake") as mock_run:
        mock_run.return_value = fake_result
        result = runner.invoke(
            cli,
            [
                "intake",
                url,
                "--db",
                str(temp_db),
                "--mp3",
                "--dj-root",
                str(mp3_root),
            ],
        )

    assert result.exit_code == 0
    assert "DEPRECATION:" in result.stderr
    assert mock_run.call_args.kwargs["mp3_root"] == mp3_root.resolve()
    assert mock_run.call_args.kwargs["dj_root"] is None


def test_cli_both_roots_without_dj_fails(temp_db: Path, tmp_path: Path) -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    url = "https://tidal.com/playlist/abc"
    mp3_root = tmp_path / "mp3_assets"
    dj_root = tmp_path / "dj_library"
    mp3_root.mkdir(parents=True, exist_ok=True)
    dj_root.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        cli,
        [
            "intake",
            url,
            "--db",
            str(temp_db),
            "--mp3",
            "--mp3-root",
            str(mp3_root),
            "--dj-root",
            str(dj_root),
        ],
    )

    assert result.exit_code != 0
    assert "--dj-root is DJ-output-only" in result.output


def test_cli_dj_requires_both_roots(temp_db: Path, tmp_path: Path) -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    url = "https://tidal.com/playlist/abc"
    mp3_root = tmp_path / "mp3_assets"
    dj_root = tmp_path / "dj_library"
    mp3_root.mkdir(parents=True, exist_ok=True)
    dj_root.mkdir(parents=True, exist_ok=True)

    result_missing_mp3_root = runner.invoke(
        cli,
        [
            "intake",
            url,
            "--db",
            str(temp_db),
            "--dj",
            "--dj-root",
            str(dj_root),
        ],
    )
    assert result_missing_mp3_root.exit_code != 0
    assert "requires --mp3-root" in result_missing_mp3_root.output

    result_missing_dj_root = runner.invoke(
        cli,
        [
            "intake",
            url,
            "--db",
            str(temp_db),
            "--dj",
            "--mp3-root",
            str(mp3_root),
        ],
    )
    assert result_missing_dj_root.exit_code != 0
    assert "requires --dj-root" in result_missing_dj_root.output


def test_cli_dj_rejects_equal_roots(temp_db: Path, tmp_path: Path) -> None:
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    url = "https://tidal.com/playlist/abc"
    root = tmp_path / "root"
    root.mkdir(parents=True, exist_ok=True)

    result = runner.invoke(
        cli,
        [
            "intake",
            url,
            "--db",
            str(temp_db),
            "--dj",
            "--mp3-root",
            str(root),
            "--dj-root",
            str(root),
        ],
    )

    assert result.exit_code != 0
    assert "must be different" in result.output


def test_exit_code_mapping(temp_db: Path, tmp_path: Path, mock_precheck_csv: Path) -> None:
    """Test CLI maps disposition to correct exit codes."""
    import click

    runner = CliRunner()

    @click.group()
    def cli():
        pass

    register_intake_group(cli)

    with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch(
            "tagslut.exec.intake_orchestrator._find_latest_precheck_csv"
        ) as mock_find:
            mock_find.return_value = mock_precheck_csv

            result = runner.invoke(
                cli,
                [
                    "intake",
                    "url",
                    "https://www.beatport.com/release/test/123",
                    "--db",
                    str(temp_db),
                    "--dry-run",
                ],
            )

    # blocked disposition → exit code 2
    assert result.exit_code == 2
