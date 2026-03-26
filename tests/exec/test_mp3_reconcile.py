"""Tests for reconcile_mp3_scan() — Tier 1/2/3/orphan/conflict/dry-run/JSONL."""
from __future__ import annotations

import csv
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from tagslut.exec.mp3_build import reconcile_mp3_scan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_DDL = """
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
CREATE TABLE IF NOT EXISTS mp3_asset (
    id INTEGER PRIMARY KEY,
    identity_id INTEGER,
    asset_id INTEGER,
    path TEXT NOT NULL UNIQUE,
    content_sha256 TEXT,
    size_bytes INTEGER,
    bitrate INTEGER,
    sample_rate INTEGER,
    duration_s REAL,
    profile TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'unverified',
    source TEXT NOT NULL DEFAULT 'unknown',
    zone TEXT,
    transcoded_at TEXT,
    reconciled_at TEXT,
    lexicon_track_id INTEGER,
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
CREATE INDEX IF NOT EXISTS idx_reconcile_log_run ON reconcile_log(run_id);
CREATE INDEX IF NOT EXISTS idx_reconcile_log_identity ON reconcile_log(identity_id);
"""


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(_MINIMAL_DDL)
    return conn


def _seed_identity(conn: sqlite3.Connection, *, key: str, artist_norm: str,
                   title_norm: str, isrc: str | None = None) -> int:
    conn.execute(
        "INSERT INTO track_identity (identity_key, artist_norm, title_norm, isrc) VALUES (?, ?, ?, ?)",
        (key, artist_norm, title_norm, isrc),
    )
    conn.commit()
    row = conn.execute("SELECT id FROM track_identity WHERE identity_key = ?", (key,)).fetchone()
    return row[0]


def _write_scan_csv(rows: list[dict], path: Path) -> None:
    from tagslut.exec.mp3_build import _SCAN_CSV_HEADERS
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_SCAN_CSV_HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _default_row(path: str, **kwargs) -> dict:
    base = {
        "path": path, "zone": "DJ_LIBRARY", "size_bytes": 1024, "mtime": "2026-01-01T00:00:00+00:00",
        "sha256": "abc123", "bitrate": 320, "sample_rate": 44100, "duration_s": 300.0,
        "id3_title": None, "id3_artist": None, "id3_album": None, "id3_year": None,
        "id3_bpm": None, "id3_key": None, "id3_genre": None, "id3_label": None,
        "id3_remixer": None, "id3_isrc": None, "id3_comment": None,
    }
    base.update(kwargs)
    return base


RUN_ID = "test-run-001"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tier1_filename_match(tmp_path: Path) -> None:
    """Tier 1: Artist – Title.mp3 filename → matched_t1 += 1."""
    conn = _make_db()
    iid = _seed_identity(conn, key="k1", artist_norm="daft punk", title_norm="around the world")

    rows = [_default_row("/path/Daft Punk – Around The World.mp3")]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    result = reconcile_mp3_scan(
        conn,
        scan_csv=csv_path,
        run_id=RUN_ID,
        log_dir=tmp_path / "logs",
        out_json=tmp_path / "out.json",
        dry_run=True,
    )
    assert result["matched_t1"] == 1
    assert result["stubs"] == 0


def test_tier2_isrc_match(tmp_path: Path) -> None:
    """Tier 2: ISRC in ID3 tag → matched_t2 += 1."""
    conn = _make_db()
    _seed_identity(conn, key="k2", artist_norm="", title_norm="", isrc=" us abc 12 34567 ")

    rows = [_default_row("/path/some_file.mp3", id3_isrc="us abc 12 34567")]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    result = reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=True,
    )
    assert result["matched_t2"] == 1


def test_tier3_id3_tag_match(tmp_path: Path) -> None:
    """Tier 3: ID3 title+artist normalised → matched_t3 += 1."""
    conn = _make_db()
    _seed_identity(conn, key="k3", artist_norm="bicep", title_norm="glue")

    rows = [_default_row("/path/random_filename.mp3",
                         id3_title="Glue", id3_artist="Bicep")]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    result = reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=True,
    )
    assert result["matched_t3"] == 1


def test_no_match_creates_stub(tmp_path: Path) -> None:
    """No match → stubs += 1 and stub row created in track_identity (with --execute)."""
    conn = _make_db()

    rows = [_default_row("/path/UnknownArtist – UnknownTitle.mp3",
                         id3_title="UnknownTitle", id3_artist="UnknownArtist")]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    result = reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=False,
    )
    assert result["stubs"] == 1
    stub = conn.execute(
        "SELECT id FROM track_identity WHERE status='stub_pending_master'"
    ).fetchone()
    assert stub is not None


def test_conflict_not_linked(tmp_path: Path) -> None:
    """Multiple ISRC candidates → conflicts += 1, no mp3_asset row."""
    conn = _make_db()
    _seed_identity(conn, key="k4a", artist_norm="artist a", title_norm="t1", isrc="CONFLICT001")
    _seed_identity(conn, key="k4b", artist_norm="artist b", title_norm="t2", isrc="CONFLICT001")

    rows = [_default_row("/path/conflicted.mp3", id3_isrc="CONFLICT001")]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    result = reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=False,
    )
    assert result["conflicts"] == 1
    assert conn.execute("SELECT COUNT(*) FROM mp3_asset").fetchone()[0] == 0


def test_duplicate_mp3_lower_bitrate_superseded(tmp_path: Path) -> None:
    """Duplicate MP3 for same identity: lower bitrate → status='superseded'."""
    conn = _make_db()
    iid = _seed_identity(conn, key="k5", artist_norm="dj shadow", title_norm="endtroducing")

    # Pre-insert a lower-bitrate row
    conn.execute(
        "INSERT INTO mp3_asset (identity_id, path, bitrate, status, source, profile) VALUES (?, '/path/low.mp3', 128, 'unverified', 'mp3_reconcile', 'standard')",
        (iid,),
    )
    conn.commit()

    rows = [_default_row("/path/high.mp3",
                         id3_title="Endtroducing", id3_artist="DJ Shadow",
                         bitrate=320)]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=False,
    )

    rows_db = conn.execute(
        "SELECT path, status FROM mp3_asset WHERE identity_id = ? ORDER BY bitrate DESC",
        (iid,),
    ).fetchall()
    statuses = {r[0]: r[1] for r in rows_db}
    assert statuses["/path/high.mp3"] == "verified"
    assert statuses["/path/low.mp3"] == "superseded"


def test_dry_run_zero_db_writes(tmp_path: Path) -> None:
    """dry_run=True → zero DB writes, returns correct counts."""
    conn = _make_db()
    _seed_identity(conn, key="k6", artist_norm="burial", title_norm="archangel")

    rows = [_default_row("/path/Burial – Archangel.mp3")]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    result = reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=True,
    )
    assert result["matched_t1"] == 1
    # No rows written
    assert conn.execute("SELECT COUNT(*) FROM mp3_asset").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM reconcile_log").fetchone()[0] == 0


def test_reconcile_log_one_row_per_decision(tmp_path: Path) -> None:
    """reconcile_log has 1 row per decision (with --execute)."""
    conn = _make_db()
    _seed_identity(conn, key="k7", artist_norm="four tet", title_norm="her")

    rows = [
        _default_row("/path/Four Tet – Her.mp3"),
        _default_row("/path/unknown_mystery_track.mp3"),
    ]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=False,
    )

    log_count = conn.execute(
        "SELECT COUNT(*) FROM reconcile_log WHERE run_id = ?", (RUN_ID,)
    ).fetchone()[0]
    assert log_count == 2


def test_jsonl_log_written(tmp_path: Path) -> None:
    """JSONL log is written alongside reconcile_log."""
    conn = _make_db()
    _seed_identity(conn, key="k8", artist_norm="arca", title_norm="piel")

    rows = [_default_row("/path/Arca – Piel.mp3")]
    csv_path = tmp_path / "scan.csv"
    log_dir = tmp_path / "logs"
    _write_scan_csv(rows, csv_path)

    reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=log_dir, out_json=tmp_path / "out.json",
        dry_run=True,
    )

    jsonl_path = log_dir / f"reconcile_reconcile_{RUN_ID}.jsonl"
    assert jsonl_path.exists()
    lines = [json.loads(l) for l in jsonl_path.read_text().strip().splitlines()]
    assert len(lines) >= 1
    assert all("ts" in l and "run_id" in l and "action" in l for l in lines)


def test_idempotent_skips_existing(tmp_path: Path) -> None:
    """Paths already in mp3_asset are skipped on re-run."""
    conn = _make_db()
    iid = _seed_identity(conn, key="k9", artist_norm="moderat", title_norm="bad kingdom")
    conn.execute(
        "INSERT INTO mp3_asset (identity_id, path, status, source, profile) VALUES (?, '/path/existing.mp3', 'verified', 'test', 'standard')",
        (iid,),
    )
    conn.commit()

    rows = [_default_row("/path/existing.mp3")]
    csv_path = tmp_path / "scan.csv"
    _write_scan_csv(rows, csv_path)

    result = reconcile_mp3_scan(
        conn, scan_csv=csv_path, run_id=RUN_ID,
        log_dir=tmp_path / "logs", out_json=tmp_path / "out.json",
        dry_run=False,
    )
    assert result["skipped"] == 1
    assert result["matched_t1"] == 0
