"""Unit tests for intake_orchestrator."""
from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

from tagslut.cli.commands.intake import register_intake_group
from tagslut.exec.intake_orchestrator import (
    IntakeResult,
    IntakeStageResult,
    _parse_precheck_csv,
    run_intake,
)


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
            artist_norm TEXT
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

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def mock_precheck_csv(tmp_path: Path) -> Path:
    """Create a mock precheck CSV with all tracks blocked."""
    csv_path = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260315_140000.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    csv_content = (
        "domain,source_link,track_id,isrc,title,artist,album,decision,confidence,match_method,reason,db_path,db_download_source,existing_quality_rank,candidate_quality_rank\n"
        'beatport,https://www.beatport.com/release/test/123,456,USTEST001,Test Track,Test Artist,Test Album,skip,high,isrc,"matched by isrc; existing rank 3 is equal or better than candidate rank 3",/path/to/file.flac,beatport,3,3\n'
    )
    csv_path.write_text(csv_content, encoding="utf-8")

    return csv_path


@pytest.fixture
def mock_precheck_csv_new(tmp_path: Path) -> Path:
    """Create a mock precheck CSV with new tracks to download."""
    csv_path = tmp_path / "artifacts" / "compare" / "precheck_decisions_20260315_140001.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    csv_content = (
        "domain,source_link,track_id,isrc,title,artist,album,decision,confidence,match_method,reason,db_path,db_download_source,existing_quality_rank,candidate_quality_rank\n"
        'beatport,https://www.beatport.com/release/test/123,456,USTEST001,Test Track,Test Artist,Test Album,keep,,,,"no inventory match",,,3\n'
        'beatport,https://www.beatport.com/release/test/123,789,USTEST002,Test Track 2,Test Artist 2,Test Album,keep,,,,"no inventory match",,,3\n'
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


def test_precheck_block_returns_disposition_blocked(
    temp_db: Path, tmp_path: Path, mock_precheck_csv: Path
) -> None:
    """Test that when all tracks blocked, disposition is 'blocked'."""
    with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch(
            "tagslut.exec.intake_orchestrator._find_latest_precheck_csv"
        ) as mock_find:
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


def test_artifact_written_on_block(
    temp_db: Path, tmp_path: Path, mock_precheck_csv: Path
) -> None:
    """Test that artifact JSON is written even when all tracks blocked."""
    artifact_dir = tmp_path / "artifacts"

    with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch(
            "tagslut.exec.intake_orchestrator._find_latest_precheck_csv"
        ) as mock_find:
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
    """Test --mp3 with identity in DB calls build_mp3_from_identity."""
    dj_root = tmp_path / "dj"
    dj_root.mkdir()

    # Add a test identity to DB
    conn = sqlite3.connect(str(temp_db))
    conn.execute(
        "INSERT INTO track_identity (isrc, beatport_id, title_norm, artist_norm) VALUES (?, ?, ?, ?)",
        ("USTEST001", "456", "test track", "test artist"),
    )
    identity_id = conn.lastrowid

    # Add asset
    asset_path = tmp_path / "test.flac"
    asset_path.write_text("fake flac", encoding="utf-8")
    conn.execute(
        "INSERT INTO asset_file (path, file_hash) VALUES (?, ?)",
        (str(asset_path), "fakehash123"),
    )
    asset_id = conn.lastrowid

    # Link asset to identity
    conn.execute(
        "INSERT INTO asset_link (identity_id, asset_id, confidence, active) VALUES (?, ?, ?, ?)",
        (identity_id, asset_id, 0.95, 1),
    )
    conn.commit()
    conn.close()

    with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch(
            "tagslut.exec.intake_orchestrator._find_latest_precheck_csv"
        ) as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            with patch(
                "tagslut.exec.intake_orchestrator.build_mp3_from_identity"
            ) as mock_mp3_build:
                mock_mp3_build.return_value = Mock(built=1, skipped=0, failed=0, errors=[])

                result = run_intake(
                    url="https://www.beatport.com/release/test/123",
                    db_path=temp_db,
                    mp3=True,
                    dry_run=False,
                    dj_root=dj_root,
                    artifact_dir=tmp_path / "artifacts",
                )

    # Verify build_mp3_from_identity was called
    assert mock_mp3_build.called
    assert mock_mp3_build.call_count == 1
    call_kwargs = mock_mp3_build.call_args.kwargs
    assert call_kwargs["dj_root"] == dj_root
    assert call_kwargs["dry_run"] is False

    # Find MP3 stage
    mp3_stage = next((s for s in result.stages if s.stage == "mp3"), None)
    assert mp3_stage is not None
    assert mp3_stage.status == "ok"
    assert "1 built" in mp3_stage.detail


def test_mp3_skips_gracefully_if_identity_not_registered(
    temp_db: Path, tmp_path: Path, mock_precheck_csv_new: Path
) -> None:
    """Test --mp3 when no identity exists in DB (promote produced nothing)."""
    dj_root = tmp_path / "dj"
    dj_root.mkdir()

    with patch("tagslut.exec.intake_orchestrator.subprocess.run") as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch(
            "tagslut.exec.intake_orchestrator._find_latest_precheck_csv"
        ) as mock_find:
            mock_find.return_value = mock_precheck_csv_new

            with patch(
                "tagslut.exec.intake_orchestrator.build_mp3_from_identity"
            ) as mock_mp3_build:
                # No identities found, nothing built
                mock_mp3_build.return_value = Mock(built=0, skipped=0, failed=0, errors=[])

                result = run_intake(
                    url="https://www.beatport.com/release/test/123",
                    db_path=temp_db,
                    mp3=True,
                    dry_run=False,
                    dj_root=dj_root,
                    artifact_dir=tmp_path / "artifacts",
                )

    # Should complete successfully even with 0 built
    assert result.disposition == "completed"
    mp3_stage = next((s for s in result.stages if s.stage == "mp3"), None)
    assert mp3_stage is not None
    assert mp3_stage.status == "ok"


def test_mp3_without_dj_root_raises_click_exception(
    temp_db: Path, tmp_path: Path
) -> None:
    """Test --mp3 without --dj-root raises ClickException before subprocess."""
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
    assert "--mp3 requires --dj-root" in result.output


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
