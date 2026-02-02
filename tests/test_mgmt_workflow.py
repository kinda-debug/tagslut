#!/usr/bin/env python3
"""
Integration tests for dedupe mgmt (management mode) workflow.

Tests:
1. Register files from a directory
2. Detect duplicates before re-download
3. Verify database schema changes
4. Query management metadata
"""

import pytest
import sqlite3
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone
from click.testing import CliRunner

from dedupe.cli.main import cli, mgmt
from dedupe.storage.schema import get_connection, init_db
from dedupe.storage.queries import get_file
from dedupe.core.hashing import calculate_file_hash


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        conn = sqlite3.connect(str(db_path))
        init_db(conn)
        conn.close()
        yield db_path


@pytest.fixture
def temp_flac_files():
    """Create temporary FLAC test files."""
    # Use the same test file we created earlier
    source = Path("/tmp/test_dedupe/test_track.flac")
    if not source.exists():
        pytest.skip("Test FLAC file not found")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Copy test file multiple times with different names
        file1 = tmpdir / "track1.flac"
        file2 = tmpdir / "track2.flac"
        file3 = tmpdir / "subdir" / "track3.flac"

        file3.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy(source, file1)
        shutil.copy(source, file2)
        shutil.copy(source, file3)

        yield tmpdir, [file1, file2, file3]


class TestMgmtRegister:
    """Test the register subcommand."""

    def test_register_dry_run(self, temp_db, temp_flac_files):
        """Test register in dry-run mode (default)."""
        tmpdir, files = temp_flac_files

        runner = CliRunner()
        result = runner.invoke(
            mgmt,
            ["register", str(tmpdir), "--source", "bpdl", "--db", str(temp_db)]
        )

        assert result.exit_code == 0
        assert "DRY-RUN MODE" in result.output
        assert "Registered:" in result.output and "3" in result.output

        # Verify nothing was saved (dry-run)
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute("SELECT COUNT(*) FROM files WHERE download_source='bpdl'")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "Dry-run should not save to database"

    def test_register_execute(self, temp_db, temp_flac_files):
        """Test register with --execute flag."""
        tmpdir, files = temp_flac_files

        runner = CliRunner()
        result = runner.invoke(
            mgmt,
            ["register", str(tmpdir), "--source", "bpdl", "--db", str(temp_db), "--execute"]
        )

        assert result.exit_code == 0
        assert "Registered:" in result.output and "3" in result.output

        # Verify files were saved
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM files WHERE download_source='bpdl'"
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 3, "Should register 3 files"

    def test_register_skip_duplicates(self, temp_db, temp_flac_files):
        """Test that register skips already-registered files."""
        tmpdir, files = temp_flac_files

        runner = CliRunner()

        # First registration
        result1 = runner.invoke(
            mgmt,
            ["register", str(tmpdir), "--source", "bpdl", "--db", str(temp_db), "--execute"]
        )
        assert result1.exit_code == 0
        assert "Registered:" in result1.output and "3" in result1.output

        # Second registration (should skip all)
        result2 = runner.invoke(
            mgmt,
            ["register", str(tmpdir), "--source", "bpdl", "--db", str(temp_db), "--execute"]
        )
        assert result2.exit_code == 0
        assert "Skipped:" in result2.output and "3" in result2.output

    def test_register_metadata_fields(self, temp_db, temp_flac_files):
        """Test that register populates all management metadata fields."""
        tmpdir, files = temp_flac_files

        runner = CliRunner()
        result = runner.invoke(
            mgmt,
            ["register", str(tmpdir), "--source", "tidal", "--db", str(temp_db), "--execute"]
        )

        assert result.exit_code == 0

        # Verify metadata fields
        conn = sqlite3.connect(str(temp_db))
        cursor = conn.execute(
            """
            SELECT download_source, mgmt_status, original_path, download_date,
                   fingerprint, m3u_exported
            FROM files WHERE download_source='tidal'
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        source, status, orig_path, dl_date, fp, m3u = row


        # Now check the same files (should find conflicts)
        result2 = runner.invoke(
            mgmt,
            ["check", str(tmpdir), "--source", "bpdl", "--db", str(temp_db)]
        )

        assert result2.exit_code == 0
        assert "Duplicates:" in result2.output and "3" in result2.output
        assert "Unique:" in result2.output and "0" in result2.output

    def test_check_allows_new_files(self, temp_db, temp_flac_files):
        """Test that check allows new files not in database."""
        tmpdir, files = temp_flac_files

        runner = CliRunner()

        # Check without registering first (should allow all)
        result = runner.invoke(
            mgmt,
            ["check", str(tmpdir), "--source", "bpdl", "--db", str(temp_db)]
        )

        assert result.exit_code == 0
        assert "Unique:" in result.output and "3" in result.output
        assert "Duplicates:" in result.output and "0" in result.output

    def test_check_source_filter(self, temp_db, temp_flac_files):
        """Test that check respects source filter."""
        tmpdir, files = temp_flac_files

        runner = CliRunner()

        # Register with source A
        result1 = runner.invoke(
            mgmt,
            ["register", str(tmpdir), "--source", "bpdl", "--db", str(temp_db), "--execute"]
        )
        assert result1.exit_code == 0

        # Check with source B filter (should allow despite matching SHA256)
        result2 = runner.invoke(
            mgmt,
            ["check", str(tmpdir), "--source", "tidal", "--db", str(temp_db)]
        )

        assert result2.exit_code == 0
        assert "Unique:" in result2.output and "3" in result2.output
        assert "Duplicates:" in result2.output and "0" in result2.output

    def test_check_strict_mode(self, temp_db, temp_flac_files):
        """Test that check --strict rejects duplicates regardless of source."""
        tmpdir, files = temp_flac_files

        runner = CliRunner()

        # Register with source A
        result1 = runner.invoke(
            mgmt,
            ["register", str(tmpdir), "--source", "bpdl", "--db", str(temp_db), "--execute"]
        )
        assert result1.exit_code == 0

        # Check with strict mode (should find conflicts even with different source)
        result2 = runner.invoke(
            mgmt,
            ["check", str(tmpdir), "--strict", "--db", str(temp_db)]
        )

        assert result2.exit_code == 0
        assert "Duplicates:" in result2.output and "3" in result2.output


class TestDatabaseSchema:
    """Test database schema changes."""

    def test_new_columns_exist(self, temp_db):
        """Test that new management columns were added to files table."""
        conn = sqlite3.connect(str(temp_db))

        # Get column names
        cursor = conn.execute("PRAGMA table_info(files)")
        columns = {row[1] for row in cursor.fetchall()}

        conn.close()

        # Check for new columns
        assert "download_source" in columns
        assert "download_date" in columns
        assert "original_path" in columns
        assert "mgmt_status" in columns
        assert "fingerprint" in columns
        assert "m3u_exported" in columns

    def test_new_indices_exist(self, temp_db):
        """Test that new indices were created for performance."""
        conn = sqlite3.connect(str(temp_db))

        # Get index names
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='files'"
        )
        indices = {row[0] for row in cursor.fetchall()}

        conn.close()

        # Check for new indices
        assert "idx_download_source" in indices
        assert "idx_mgmt_status" in indices
        assert "idx_fingerprint" in indices
        assert "idx_original_path" in indices
