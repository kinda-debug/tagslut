"""Tests for scripts/migrate_legacy_db.py — legacy DB → v2 migration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tagslut.storage.schema import init_db

# Import migration helpers directly from the script
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_legacy_db.py"

# We test the individual helper functions by importing the script as a module
import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("migrate_legacy_db", _SCRIPT)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

migrate = _mod.migrate
_backfill_genre = _mod._backfill_genre
_backfill_dj_flag = _mod._backfill_dj_flag
_backfill_quality_rank = _mod._backfill_quality_rank
_fix_download_sources = _mod._fix_download_sources
_remap_paths = _mod._remap_paths
_upgrade_schema_migrations_table = _mod._upgrade_schema_migrations_table


def _init_legacy_db(conn: sqlite3.Connection) -> None:
    """Upgrade legacy schema_migrations and run init_db (simulates migration step 2)."""
    _upgrade_schema_migrations_table(conn)
    init_db(conn)


# ── Fixtures ────────────────────────────────────────────────────────────────

def _create_legacy_db(path: Path, rows: list[dict] | None = None) -> Path:
    """Create a minimal legacy-shaped DB (before v2 migration)."""
    db = path / "legacy.db"
    conn = sqlite3.connect(str(db))

    # Create a legacy-style files table (subset of columns)
    conn.execute("""
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            library TEXT,
            zone TEXT,
            mtime REAL,
            size INTEGER,
            checksum TEXT,
            sha256 TEXT,
            duration REAL,
            bit_depth INTEGER,
            sample_rate INTEGER,
            bitrate INTEGER,
            metadata_json TEXT,
            integrity_state TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_isrc TEXT,
            canonical_genre TEXT,
            canonical_title TEXT,
            canonical_artist TEXT,
            is_dj_material INTEGER DEFAULT 0,
            download_source TEXT,
            enriched_at TEXT,
            beatport_id TEXT
        )
    """)

    # Schema migrations table (legacy format — different from v2)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT
        )
    """)

    if rows:
        for row in rows:
            cols = ", ".join(row.keys())
            placeholders = ", ".join(["?"] * len(row))
            conn.execute(
                f"INSERT INTO files ({cols}) VALUES ({placeholders})",
                list(row.values()),
            )

    conn.commit()
    conn.close()
    return db


_SAMPLE_ROWS = [
    {
        "path": "/Volumes/MUSIC/LIBRARY/Artist A/track1.flac",
        "library": "default",
        "zone": "accepted",
        "size": 50_000_000,
        "bit_depth": 24,
        "sample_rate": 96000,
        "bitrate": 0,
        "canonical_bpm": 128.0,
        "canonical_key": "8A",
        "canonical_isrc": "USRC17607839",
        "canonical_genre": "Deep House",
        "is_dj_material": 1,
        "download_source": "legacy",
    },
    {
        "path": "/Volumes/MUSIC/LIBRARY/Artist B/track2.flac",
        "library": "default",
        "zone": "accepted",
        "size": 30_000_000,
        "bit_depth": 16,
        "sample_rate": 44100,
        "bitrate": 0,
        "canonical_bpm": 132.5,
        "canonical_key": "10B",
        "canonical_isrc": "GBAYE0400123",
        "canonical_genre": "Techno",
        "is_dj_material": 1,
        "download_source": "bpdl",
    },
    {
        "path": "/Volumes/MUSIC/LIBRARY/Artist C/track3.mp3",
        "library": "default",
        "zone": "accepted",
        "size": 8_000_000,
        "bit_depth": None,
        "sample_rate": None,
        "bitrate": 320000,
        "canonical_bpm": None,
        "canonical_key": None,
        "canonical_isrc": None,
        "canonical_genre": None,
        "is_dj_material": 0,
        "download_source": "John Digweed",  # Bad source — artist name
    },
    {
        "path": "/Volumes/MUSIC/LIBRARY/Artist D/track4.flac",
        "library": "default",
        "zone": "quarantine",
        "size": 45_000_000,
        "bit_depth": 24,
        "sample_rate": 44100,
        "bitrate": 0,
        "canonical_bpm": 125.0,
        "canonical_key": "5A",
        "canonical_isrc": "USRC19900001",
        "canonical_genre": "House",
        "is_dj_material": 1,
        "download_source": "dropbox_hires",
        "metadata_json": '{"BPM": "126.0", "TKEY": "5Am"}',
    },
]


# ── Tests ───────────────────────────────────────────────────────────────────


class TestBackfillGenre:
    def test_copies_canonical_genre_to_genre(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)  # add v2 columns
        count = _backfill_genre(conn, execute=True)
        conn.commit()

        row = conn.execute(
            "SELECT genre FROM files WHERE path LIKE '%track1%'"
        ).fetchone()
        conn.close()

        assert count >= 1
        assert row[0] == "Deep House"

    def test_does_not_overwrite_existing_genre(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)
        conn.execute(
            "UPDATE files SET genre = 'Minimal' WHERE path LIKE '%track1%'"
        )
        conn.commit()

        _backfill_genre(conn, execute=True)
        conn.commit()
        row = conn.execute(
            "SELECT genre FROM files WHERE path LIKE '%track1%'"
        ).fetchone()
        conn.close()

        assert row[0] == "Minimal"  # not overwritten

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)
        count = _backfill_genre(conn, execute=False)
        row = conn.execute(
            "SELECT genre FROM files WHERE path LIKE '%track1%'"
        ).fetchone()
        conn.close()

        assert count >= 1
        assert row[0] is None  # not written


class TestBackfillDjFlag:
    def test_copies_is_dj_material_to_dj_flag(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)
        count = _backfill_dj_flag(conn, execute=True)
        conn.commit()

        row = conn.execute(
            "SELECT dj_flag FROM files WHERE path LIKE '%track1%'"
        ).fetchone()
        non_dj = conn.execute(
            "SELECT dj_flag FROM files WHERE path LIKE '%track3%'"
        ).fetchone()
        conn.close()

        assert count == 3  # track1, track2, track4
        assert row[0] == 1
        assert non_dj[0] is None or non_dj[0] == 0


class TestBackfillQualityRank:
    def test_hires_lossless_gets_rank_2(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)
        count = _backfill_quality_rank(conn, execute=True)
        conn.commit()

        # track1: 24bit/96kHz → HIRES_LOSSLESS (2)
        row = conn.execute(
            "SELECT quality_rank FROM files WHERE path LIKE '%track1%'"
        ).fetchone()
        conn.close()

        assert count >= 1
        assert row[0] == 2

    def test_cd_lossless_gets_rank_4(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)
        _backfill_quality_rank(conn, execute=True)
        conn.commit()

        # track2: 16bit/44.1kHz/bitrate=0 → CD_LOSSLESS (4)
        row = conn.execute(
            "SELECT quality_rank FROM files WHERE path LIKE '%track2%'"
        ).fetchone()
        conn.close()

        assert row[0] == 4

    def test_hires_standard_gets_rank_3(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)
        _backfill_quality_rank(conn, execute=True)
        conn.commit()

        # track4: 24bit/44.1kHz → HIRES_STANDARD (3)
        row = conn.execute(
            "SELECT quality_rank FROM files WHERE path LIKE '%track4%'"
        ).fetchone()
        conn.close()

        assert row[0] == 3

    def test_skips_rows_without_bit_depth(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _init_legacy_db(conn)
        _backfill_quality_rank(conn, execute=True)
        conn.commit()

        # track3: bit_depth=NULL → should be skipped
        row = conn.execute(
            "SELECT quality_rank FROM files WHERE path LIKE '%track3%'"
        ).fetchone()
        conn.close()

        assert row[0] is None


class TestFixDownloadSources:
    def test_replaces_artist_name_with_legacy(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        bad = _fix_download_sources(conn, execute=True)
        conn.commit()

        row = conn.execute(
            "SELECT download_source FROM files WHERE path LIKE '%track3%'"
        ).fetchone()
        conn.close()

        assert "John Digweed" in bad
        assert row[0] == "legacy"

    def test_does_not_touch_valid_sources(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        _fix_download_sources(conn, execute=True)
        conn.commit()

        row = conn.execute(
            "SELECT download_source FROM files WHERE path LIKE '%track2%'"
        ).fetchone()
        conn.close()

        assert row[0] == "bpdl"

    def test_dry_run_returns_bad_but_no_write(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        bad = _fix_download_sources(conn, execute=False)

        row = conn.execute(
            "SELECT download_source FROM files WHERE path LIKE '%track3%'"
        ).fetchone()
        conn.close()

        assert "John Digweed" in bad
        assert row[0] == "John Digweed"  # unchanged


class TestRemapPaths:
    def test_remaps_path_prefix(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        count = _remap_paths(
            conn,
            "/Volumes/MUSIC/LIBRARY",
            "/Volumes/DJSSD/LIBRARY",
            execute=True,
        )
        conn.commit()

        row = conn.execute(
            "SELECT path FROM files WHERE path LIKE '%track1%'"
        ).fetchone()
        conn.close()

        assert count == 4
        assert row[0].startswith("/Volumes/DJSSD/LIBRARY/")

    def test_dry_run_does_not_remap(self, tmp_path: Path) -> None:
        db_path = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        conn = sqlite3.connect(str(db_path))
        count = _remap_paths(
            conn,
            "/Volumes/MUSIC/LIBRARY",
            "/Volumes/DJSSD/LIBRARY",
            execute=False,
        )

        row = conn.execute(
            "SELECT path FROM files WHERE path LIKE '%track1%'"
        ).fetchone()
        conn.close()

        assert count == 4
        assert row[0].startswith("/Volumes/MUSIC/LIBRARY/")


class TestFullMigration:
    def test_end_to_end_execute(self, tmp_path: Path) -> None:
        src = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        dest = tmp_path / "migrated.db"

        summary = migrate(src, dest, execute=True)

        assert summary["execute"] is True
        assert summary["total_rows"] == 4
        assert summary["genre_backfilled"] >= 1
        assert summary["dj_flag_backfilled"] >= 1
        assert summary["quality_rank_computed"] >= 1
        assert dest.exists()

        # Verify the migrated DB has the v2 columns populated
        conn = sqlite3.connect(str(dest))
        conn.row_factory = sqlite3.Row
        row = dict(conn.execute(
            "SELECT * FROM files WHERE path LIKE '%track1%'"
        ).fetchone())
        conn.close()

        assert row["bpm"] == 128.0
        assert row["key_camelot"] == "8A"
        assert row["isrc"] == "USRC17607839"
        assert row["genre"] == "Deep House"
        assert row["dj_flag"] == 1
        assert row["quality_rank"] == 2

    def test_end_to_end_dry_run(self, tmp_path: Path) -> None:
        src = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        dest = tmp_path / "migrated.db"

        summary = migrate(src, dest, execute=False)

        assert summary["execute"] is False
        assert summary["total_rows"] == 4
        assert not dest.exists()  # dry-run: no file created

    def test_with_remap_root(self, tmp_path: Path) -> None:
        src = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        dest = tmp_path / "migrated.db"

        summary = migrate(
            src, dest,
            execute=True,
            remap_root=("/Volumes/MUSIC/LIBRARY", "/Volumes/DJSSD/LIBRARY"),
        )

        assert summary.get("paths_remapped") == 4

        conn = sqlite3.connect(str(dest))
        paths = [r[0] for r in conn.execute("SELECT path FROM files").fetchall()]
        conn.close()

        for p in paths:
            assert p.startswith("/Volumes/DJSSD/LIBRARY/")

    def test_post_stats_populated(self, tmp_path: Path) -> None:
        src = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        dest = tmp_path / "migrated.db"

        summary = migrate(src, dest, execute=True)
        ps = summary["post_stats"]

        assert ps["total"] == 4
        assert ps["with_bpm"] >= 2
        assert ps["with_key"] >= 2
        assert ps["with_isrc"] >= 2
        assert ps["with_genre"] >= 2
        assert ps["with_dj_flag"] >= 3
        assert ps["with_quality_rank"] >= 3

    def test_idempotent_rerun(self, tmp_path: Path) -> None:
        """Running the migration twice should not break anything."""
        src = _create_legacy_db(tmp_path, _SAMPLE_ROWS)
        dest = tmp_path / "migrated.db"

        migrate(src, dest, execute=True)
        # Run again on the already-migrated DB
        summary2 = migrate(dest, dest, execute=True)

        # No new backfills expected (already populated)
        assert summary2["genre_backfilled"] == 0
        assert summary2["dj_flag_backfilled"] == 0
