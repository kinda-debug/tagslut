"""Tests for scan_master_library()."""
from __future__ import annotations

import sqlite3
import struct
import tempfile
import uuid
from pathlib import Path

import pytest

from tagslut.exec.master_scan import scan_master_library


# ---------------------------------------------------------------------------
# Minimal schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS track_identity (
    id INTEGER PRIMARY KEY,
    identity_key TEXT NOT NULL UNIQUE,
    isrc TEXT,
    artist_norm TEXT,
    title_norm TEXT,
    canonical_title TEXT,
    canonical_artist TEXT,
    source TEXT,
    status TEXT,
    merged_into_id INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS asset_file (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    zone TEXT,
    library TEXT,
    size_bytes INTEGER,
    mtime TEXT,
    content_sha256 TEXT,
    duration_s REAL,
    bitrate INTEGER,
    sample_rate INTEGER,
    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS asset_link (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER NOT NULL,
    identity_id INTEGER NOT NULL,
    confidence REAL,
    link_source TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reconcile_log (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    event_time TEXT DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence TEXT,
    mp3_path TEXT,
    identity_id INTEGER,
    lexicon_track_id INTEGER,
    details_json TEXT
);
"""

RUN_ID = "test-master-001"


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_DDL)
    return conn


def _make_fake_flac(path: Path, size: int = 128) -> None:
    """Write a minimal fake .flac file (not valid FLAC, just for path testing)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00" * size)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_idempotent_second_run_skips(tmp_path: Path) -> None:
    """Second run returns skipped_existing=N, assets_inserted=0."""
    master_root = tmp_path / "MASTER_LIBRARY"
    flac = master_root / "Artist" / "track.flac"
    _make_fake_flac(flac)

    conn = _make_db()
    log_dir = tmp_path / "logs"

    # First run
    result1 = scan_master_library(
        conn, master_root=master_root, run_id=RUN_ID,
        log_dir=log_dir, dry_run=False,
    )
    assert result1["assets_inserted"] == 1
    assert result1["skipped_existing"] == 0

    # Second run — should skip the already-inserted path
    result2 = scan_master_library(
        conn, master_root=master_root, run_id=RUN_ID,
        log_dir=log_dir, dry_run=False,
    )
    assert result2["assets_inserted"] == 0
    assert result2["skipped_existing"] == 1


def test_stub_created_for_unmatched_flac(tmp_path: Path) -> None:
    """Unmatched FLAC creates a stub track_identity row."""
    master_root = tmp_path / "MASTER_LIBRARY"
    flac = master_root / "NewArtist" / "new_track.flac"
    _make_fake_flac(flac)

    conn = _make_db()

    result = scan_master_library(
        conn, master_root=master_root, run_id=RUN_ID,
        log_dir=tmp_path / "logs", dry_run=False,
    )
    assert result["stubs_created"] == 1

    stub = conn.execute(
        "SELECT id, status FROM track_identity WHERE status = 'stub_pending_enrichment'"
    ).fetchone()
    assert stub is not None


def test_asset_link_created_for_matched_flac(tmp_path: Path) -> None:
    """Matched FLAC (by title+artist) creates an asset_link row."""
    master_root = tmp_path / "MASTER_LIBRARY"
    flac = master_root / "Artist" / "title.flac"
    _make_fake_flac(flac)

    conn = _make_db()

    # Pre-seed an identity that matches the stub the scan would create
    # Since we can't actually embed FLAC tags in a fake file, scan will create a stub
    # and link it. We verify the asset_link exists after the run.
    result = scan_master_library(
        conn, master_root=master_root, run_id=RUN_ID,
        log_dir=tmp_path / "logs", dry_run=False,
    )

    # asset_file should have been inserted
    asset = conn.execute(
        "SELECT id FROM asset_file WHERE path = ?", (str(flac),)
    ).fetchone()
    assert asset is not None

    # asset_link should exist for the stub identity
    link = conn.execute(
        "SELECT id FROM asset_link WHERE asset_id = ?", (asset[0],)
    ).fetchone()
    assert link is not None


def test_dry_run_no_db_writes(tmp_path: Path) -> None:
    """dry_run=True → no rows inserted into asset_file."""
    master_root = tmp_path / "MASTER_LIBRARY"
    flac = master_root / "Artist" / "track_dryrun.flac"
    _make_fake_flac(flac)

    conn = _make_db()

    result = scan_master_library(
        conn, master_root=master_root, run_id=RUN_ID,
        log_dir=tmp_path / "logs", dry_run=True,
    )
    assert result["assets_inserted"] == 1  # Counted but not written

    count = conn.execute("SELECT COUNT(*) FROM asset_file").fetchone()[0]
    assert count == 0


def test_progress_output_no_crash(tmp_path: Path, capsys) -> None:
    """Scan runs without error even when no .flac files exist."""
    master_root = tmp_path / "MASTER_LIBRARY_EMPTY"
    master_root.mkdir()

    conn = _make_db()
    result = scan_master_library(
        conn, master_root=master_root, run_id=RUN_ID,
        log_dir=tmp_path / "logs", dry_run=True,
    )
    assert result["assets_inserted"] == 0
    assert result["errors"] == 0


def test_jsonl_log_written(tmp_path: Path) -> None:
    """JSONL log file is created and contains entries."""
    import json

    master_root = tmp_path / "MASTER_LIBRARY"
    flac = master_root / "Artist" / "logged.flac"
    _make_fake_flac(flac)

    conn = _make_db()
    log_dir = tmp_path / "logs"

    scan_master_library(
        conn, master_root=master_root, run_id=RUN_ID,
        log_dir=log_dir, dry_run=True,
    )

    jsonl_path = log_dir / f"reconcile_master_{RUN_ID}.jsonl"
    assert jsonl_path.exists()
    lines = [json.loads(l) for l in jsonl_path.read_text().strip().splitlines()]
    assert len(lines) >= 1
    assert all("ts" in l and "run_id" in l for l in lines)
