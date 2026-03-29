from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from tagslut.cli.commands.dj import dj_group
from tagslut.exec import dj_pool_wizard as wizard
from tagslut.storage.v3 import create_schema_v3


MASTER = Path("/MASTER")


def _create_files_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            library TEXT,
            zone TEXT,
            mtime REAL,
            size INTEGER,
            checksum TEXT,
            streaminfo_md5 TEXT,
            sha256 TEXT,
            duration REAL,
            bit_depth INTEGER,
            sample_rate INTEGER,
            bitrate INTEGER,
            metadata_json TEXT,
            flac_ok INTEGER,
            integrity_state TEXT,
            integrity_checked_at TEXT,
            streaminfo_checked_at TEXT,
            sha256_checked_at TEXT,
            acoustid TEXT,
            is_dj_material INTEGER DEFAULT 0,
            dj_flag INTEGER DEFAULT 0,
            canonical_artist TEXT,
            canonical_title TEXT,
            canonical_genre TEXT,
            canonical_label TEXT,
            canonical_bpm REAL,
            canonical_key TEXT,
            canonical_year INTEGER,
            download_source TEXT,
            download_date TEXT,
            bpm REAL,
            key_camelot TEXT,
            genre TEXT,
            duration_status TEXT,
            quality_rank INTEGER,
            dj_pool_path TEXT,
            dj_set_role TEXT
        );
        """
    )


def _fixed_datetime(year: int, month: int, day: int, hour: int, minute: int, second: int) -> type[datetime]:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            if tz is not None:
                return datetime(year, month, day, hour, minute, second, tzinfo=tz)
            return datetime(year, month, day, hour, minute, second)

    return FixedDateTime


def _run_dir(out_root: Path) -> Path:
    candidates = sorted(path for path in out_root.iterdir() if path.is_dir())
    assert len(candidates) == 1
    return candidates[0]


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def insert_track(
    conn: sqlite3.Connection,
    path: str,
    is_dj_material: int = 1,
    dj_flag: int = 0,
    dj_pool_path: str | None = None,
    identity_id: int | None = None,
    artist: str | None = "Test Artist",
    title: str | None = "Test Title",
    genre: str | None = "House",
    label: str | None = "Test Label",
    bpm: float | None = 128.0,
    musical_key: str | None = "8A",
    year: int | None = 2023,
    rating: int | None = None,
    energy: int | None = None,
    dj_set_role: str | None = None,
    set_role: str | None = None,
    download_source: str | None = None,
    download_date: str | None = None,
    flac_ok: int = 1,
    integrity_state: str = "ok",
    quality_rank: int | None = None,
) -> None:
    uid = int(hashlib.md5(path.encode("utf-8")).hexdigest()[:8], 16) % 100000

    conn.execute(
        """
        INSERT OR IGNORE INTO files
        (
            path, is_dj_material, dj_flag, canonical_artist, canonical_title,
            canonical_genre, canonical_label, canonical_bpm, canonical_key,
            canonical_year, download_source, download_date, bpm, key_camelot,
            genre, quality_rank, dj_pool_path, dj_set_role
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path,
            is_dj_material,
            dj_flag,
            artist,
            title,
            genre,
            label,
            bpm,
            musical_key,
            year,
            download_source,
            download_date,
            bpm,
            musical_key,
            genre,
            quality_rank,
            dj_pool_path,
            dj_set_role,
        ),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO asset_file
        (id, path, flac_ok, integrity_state, download_source, download_date)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (uid, path, flac_ok, integrity_state, download_source, download_date),
    )

    if identity_id is not None:
        conn.execute(
            """
            INSERT OR IGNORE INTO track_identity
            (id, identity_key, canonical_artist, canonical_title,
             canonical_genre, canonical_label, canonical_bpm,
             canonical_key, canonical_year,
             ingested_at, ingestion_method, ingestion_source, ingestion_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                '2026-01-01T00:00:00+00:00', 'migration', 'test_fixture', 'legacy')
            """,
            (
                identity_id,
                f"ikey_{identity_id}",
                artist,
                title,
                genre,
                label,
                bpm,
                musical_key,
                year,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO asset_link
            (asset_id, identity_id, active)
            VALUES (?, ?, 1)
            """,
            (uid, identity_id),
        )
        if any(value is not None for value in (rating, energy, set_role)):
            conn.execute(
                """
                INSERT OR IGNORE INTO dj_track_profile
                (identity_id, rating, energy, set_role)
                VALUES (?, ?, ?, ?)
                """,
                (identity_id, rating, energy, set_role),
            )
    conn.commit()


@pytest.fixture
def wizard_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema_v3(conn)
    _create_files_table(conn)
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema_v3(conn)
    _create_files_table(conn)
    conn.commit()
    conn.close()
    return db_file


def test_validate_rejects_out_root_eq_master_root(tmp_path: Path) -> None:
    master = tmp_path / "MASTER"
    with pytest.raises(ValueError, match="must not be MASTER_LIBRARY"):
        wizard.validate_wizard_environment(
            db_path=tmp_path / "db.sqlite",
            master_root=master,
            dj_cache_root=tmp_path / "DJ",
            out_root=master,
            pool_name="pool",
            overwrite_run=False,
        )


def test_validate_rejects_out_root_inside_master_root(tmp_path: Path) -> None:
    master = tmp_path / "MASTER"
    with pytest.raises(ValueError, match="must not be inside MASTER_LIBRARY"):
        wizard.validate_wizard_environment(
            db_path=tmp_path / "db.sqlite",
            master_root=master,
            dj_cache_root=tmp_path / "DJ",
            out_root=master / "subdir",
            pool_name="pool",
            overwrite_run=False,
        )


def test_validate_rejects_out_root_eq_dj_library(tmp_path: Path) -> None:
    dj_root = tmp_path / "DJ"
    with pytest.raises(ValueError, match="must not be DJ_LIBRARY"):
        wizard.validate_wizard_environment(
            db_path=tmp_path / "db.sqlite",
            master_root=tmp_path / "MASTER",
            dj_cache_root=dj_root,
            out_root=dj_root,
            pool_name="pool",
            overwrite_run=False,
        )


def test_validate_rejects_out_root_inside_dj_library(tmp_path: Path) -> None:
    dj_root = tmp_path / "DJ"
    with pytest.raises(ValueError, match="must not be inside DJ_LIBRARY"):
        wizard.validate_wizard_environment(
            db_path=tmp_path / "db.sqlite",
            master_root=tmp_path / "MASTER",
            dj_cache_root=dj_root,
            out_root=dj_root / "subdir",
            pool_name="pool",
            overwrite_run=False,
        )


def test_validate_rejects_out_root_eq_db_parent(tmp_path: Path) -> None:
    db_file = tmp_path / "db" / "music.sqlite"
    with pytest.raises(ValueError, match="must not be the DB parent"):
        wizard.validate_wizard_environment(
            db_path=db_file,
            master_root=tmp_path / "MASTER",
            dj_cache_root=tmp_path / "DJ",
            out_root=db_file.parent,
            pool_name="pool",
            overwrite_run=False,
        )


def test_validate_rejects_existing_manifest_without_overwrite(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        wizard,
        "datetime",
        _fixed_datetime(2026, 1, 1, 0, 0, 0),
    )
    run_dir = tmp_path / "out" / "pool_20260101_000000"
    run_dir.mkdir(parents=True)
    (run_dir / "pool_manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="pool_manifest.json"):
        wizard.validate_wizard_environment(
            db_path=tmp_path / "db.sqlite",
            master_root=tmp_path / "MASTER",
            dj_cache_root=tmp_path / "DJ",
            out_root=tmp_path / "out",
            pool_name="pool",
            overwrite_run=False,
        )


def test_validate_returns_run_dir_on_clean_inputs(tmp_path: Path) -> None:
    run_dir = wizard.validate_wizard_environment(
        db_path=tmp_path / "db.sqlite",
        master_root=tmp_path / "MASTER",
        dj_cache_root=tmp_path / "DJ",
        out_root=tmp_path / "out",
        pool_name="my pool",
        overwrite_run=False,
    )
    assert str(run_dir).startswith(str((tmp_path / "out").resolve()))
    assert "my_pool_" in run_dir.name


def test_select_returns_is_dj_material_rows(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1)
    result = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    assert len(result) == 1
    assert result[0]["master_path"] == "/MASTER/a.flac"


def test_select_returns_dj_pool_path_rows(wizard_db: sqlite3.Connection) -> None:
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=0,
        dj_pool_path="/DJ/b.mp3",
        identity_id=2,
    )
    result = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    assert len(result) == 1
    assert result[0]["master_path"] == "/MASTER/b.flac"


def test_select_returns_dj_flag_rows(wizard_db: sqlite3.Connection) -> None:
    insert_track(
        wizard_db,
        "/MASTER/c.flac",
        is_dj_material=0,
        dj_flag=1,
        identity_id=None,
    )
    result = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    assert [row["master_path"] for row in result] == ["/MASTER/c.flac"]


def test_select_union_both_flags(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1)
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=0,
        dj_pool_path="/DJ/b.mp3",
        identity_id=2,
    )
    result = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac", "/MASTER/b.flac"]


def test_select_excludes_non_master_paths(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/OTHER/a.flac", is_dj_material=1, identity_id=1)
    result = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    assert result == []


def test_select_filter_require_artist_title_excludes_missing(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=1,
        artist=None,
        title=None,
    )
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"require_artist_title": True}
    )
    assert result == []


def test_select_filter_require_artist_title_uses_legacy_files_fallback(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/legacy_title.flac",
        is_dj_material=0,
        dj_flag=1,
        identity_id=None,
        artist="Legacy Artist",
        title="Legacy Title",
    )
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"require_artist_title": True}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/legacy_title.flac"]


def test_select_tolerates_missing_dj_set_role_column() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema_v3(conn)
    conn.executescript(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            is_dj_material INTEGER DEFAULT 0,
            dj_pool_path TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO files (path, is_dj_material, dj_pool_path) VALUES (?, ?, ?)",
        ("/MASTER/a.flac", 1, None),
    )
    conn.execute(
        """
        INSERT INTO asset_file (id, path, flac_ok, integrity_state)
        VALUES (?, ?, ?, ?)
        """,
        (1, "/MASTER/a.flac", 1, "ok"),
    )
    conn.commit()
    try:
        result = wizard.select_flagged_master_paths(conn, MASTER, {})
    finally:
        conn.close()

    assert len(result) == 1
    assert result[0]["dj_set_role"] is None


def test_select_filter_require_bpm_excludes_missing(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, bpm=None)
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, bpm=128.0)
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"require_bpm": True}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/b.flac"]


def test_select_filter_require_key_excludes_missing(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=1,
        musical_key=None,
    )
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=1,
        identity_id=2,
        musical_key="8A",
    )
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"require_key": True}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/b.flac"]


def test_select_filter_require_genre_excludes_missing(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, genre=None)
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, genre="House")
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"require_genre": True}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/b.flac"]


def test_select_filter_genre_include(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, genre="House")
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, genre="Techno")
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"genre_include": ["House"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_genre_exclude(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, genre="House")
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, genre="Techno")
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"genre_exclude": ["Techno"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_bpm_band(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, bpm=120.0)
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, bpm=140.0)
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"bpm_min": 125.0, "bpm_max": 145.0}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/b.flac"]


def test_select_filter_key_include(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, musical_key="8A")
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, musical_key="9B")
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"key_include": ["8A"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_label_include(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, label="Drumcode")
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, label="Other")
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"label_include": ["Drumcode"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_year_range(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, year=2019)
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, year=2023)
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"year_min": 2021}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/b.flac"]


def test_select_filter_min_rating(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, rating=3)
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, rating=1)
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"min_rating": 3}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_min_energy(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, energy=8)
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, energy=4)
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"min_energy": 7}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_download_source_include(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=1,
        download_source="bpdl",
    )
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=1,
        identity_id=2,
        download_source="qobuz",
    )
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"download_source_include": ["bpdl"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_download_source_include_uses_legacy_files_fallback(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=0,
        dj_flag=1,
        identity_id=None,
        download_source="bpdl",
    )
    wizard_db.execute(
        "UPDATE asset_file SET download_source = NULL WHERE path = ?",
        ("/MASTER/a.flac",),
    )
    wizard_db.commit()

    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"download_source_include": ["bpdl"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_download_date_bounds(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=1,
        download_date="2026-03-01T00:00:00Z",
    )
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=1,
        identity_id=2,
        download_date="2026-03-10T00:00:00Z",
    )
    insert_track(
        wizard_db,
        "/MASTER/c.flac",
        is_dj_material=1,
        identity_id=3,
        download_date="2026-03-15T00:00:00Z",
    )
    result = wizard.select_flagged_master_paths(
        wizard_db,
        MASTER,
        {
            "download_date_since": "2026-03-05",
            "download_date_until": "2026-03-12",
        },
    )
    assert [row["master_path"] for row in result] == ["/MASTER/b.flac"]


def test_select_filter_download_date_bounds_use_legacy_files_fallback(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=0,
        dj_flag=1,
        identity_id=None,
        download_date="2026-03-11T00:00:00Z",
    )
    wizard_db.execute(
        "UPDATE asset_file SET download_date = NULL WHERE path = ?",
        ("/MASTER/a.flac",),
    )
    wizard_db.commit()

    result = wizard.select_flagged_master_paths(
        wizard_db,
        MASTER,
        {"download_date_since": "2026-03-10", "download_date_until": "2026-03-12"},
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_download_date_bounds_falls_back_to_first_seen_at(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=0,
        dj_flag=1,
        identity_id=None,
        download_date=None,
        artist="Legacy Artist",
        title="Legacy Title",
    )
    wizard_db.execute(
        "UPDATE asset_file SET download_date = NULL, first_seen_at = '2026-03-11 11:19:47' WHERE path = ?",
        ("/MASTER/a.flac",),
    )
    wizard_db.commit()

    result = wizard.select_flagged_master_paths(
        wizard_db,
        MASTER,
        {"download_date_since": "2026-03-10", "download_date_until": "2026-03-12"},
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_quality_rank_max(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=1,
        quality_rank=2,
    )
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=1,
        identity_id=2,
        quality_rank=6,
    )
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"quality_rank_max": 4}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_genre_include_uses_legacy_files_fallback(
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/legacy_genre.flac",
        is_dj_material=0,
        dj_flag=1,
        identity_id=1,
        genre="Afro House",
    )
    wizard_db.execute(
        "UPDATE track_identity SET canonical_genre = NULL WHERE id = ?",
        (1,),
    )
    wizard_db.commit()

    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"genre_include": ["Afro House"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/legacy_genre.flac"]


def test_select_filter_set_role_include(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, set_role="peak")
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2, set_role="warmup")
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"set_role_include": ["peak"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_only_profiled(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, rating=4)
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=2)
    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"only_profiled": True}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac"]


def test_select_filter_only_roles(wizard_db: sqlite3.Connection) -> None:
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=1,
        dj_set_role="groove",
    )
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=1,
        identity_id=2,
        dj_set_role="prime",
    )
    insert_track(
        wizard_db,
        "/MASTER/c.flac",
        is_dj_material=1,
        identity_id=3,
        dj_set_role=None,
    )

    result = wizard.select_flagged_master_paths(
        wizard_db, MASTER, {"only_roles": ["groove", "prime"]}
    )
    assert [row["master_path"] for row in result] == ["/MASTER/a.flac", "/MASTER/b.flac"]


def test_select_filter_only_roles_invalid_value_raises_before_query() -> None:
    class QueryFailConnection:
        def execute(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("unexpected DB query")

    with pytest.raises(ValueError, match="Invalid only_roles value"):
        wizard.select_flagged_master_paths(
            QueryFailConnection(),  # type: ignore[arg-type]
            MASTER,
            {"only_roles": ["groove", "emergency"]},
        )


def test_prompt_available_value_filter_supports_search_and_number_selection(
    wizard_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=1, genre="House")
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=1,
        identity_id=2,
        genre="Afro House",
    )
    insert_track(wizard_db, "/MASTER/c.flac", is_dj_material=1, identity_id=3, genre="Techno")

    answers = iter(["/house", "2,1"])
    monkeypatch.setattr(
        wizard.click,
        "prompt",
        lambda *args, **kwargs: next(answers),
    )

    result = wizard._prompt_available_value_filter(
        wizard_db,
        MASTER,
        {},
        field="genre",
        label="genre include",
        value_label="genre",
    )
    output = capsys.readouterr().out

    assert result == ["House", "Afro House"]
    assert "Available genre values matching 'house'" in output


def test_resolve_prefers_relink_over_legacy(tmp_path: Path, wizard_db: sqlite3.Connection) -> None:
    relink_path = tmp_path / "relink.mp3"
    relink_path.write_bytes(b"new")
    legacy_path = tmp_path / "legacy.mp3"
    legacy_path.write_bytes(b"old")
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        dj_pool_path=str(legacy_path),
        identity_id=10,
    )
    wizard_db.execute(
        """
        INSERT INTO provenance_event
        (event_type, status, identity_id, source_path, dest_path, event_time)
        VALUES ('dj_pool_relink', 'success', 10, '/MASTER/a.flac', ?, CURRENT_TIMESTAMP)
        """,
        (str(relink_path),),
    )
    wizard_db.commit()

    source_type, source_path, _, warning = wizard.resolve_mp3_source(
        wizard_db, "/MASTER/a.flac", 10
    )
    assert source_type == "relink"
    assert source_path == relink_path.resolve()
    assert warning is None


def test_resolve_falls_back_to_legacy_when_no_relink(
    tmp_path: Path,
    wizard_db: sqlite3.Connection,
) -> None:
    legacy_path = tmp_path / "legacy.mp3"
    legacy_path.write_bytes(b"old")
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        dj_pool_path=str(legacy_path),
        identity_id=11,
    )

    source_type, source_path, _, warning = wizard.resolve_mp3_source(
        wizard_db, "/MASTER/a.flac", 11
    )
    assert source_type == "legacy"
    assert source_path == legacy_path.resolve()
    assert warning == "legacy_cache_fallback"


def test_resolve_returns_none_when_no_cache(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=12)
    source_type, source_path, _, warning = wizard.resolve_mp3_source(
        wizard_db, "/MASTER/a.flac", 12
    )
    assert source_type == "none"
    assert source_path is None
    assert warning is None


def test_resolve_relink_skipped_when_file_missing(wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=13)
    wizard_db.execute(
        """
        INSERT INTO provenance_event
        (event_type, status, identity_id, source_path, dest_path, event_time)
        VALUES ('dj_pool_relink', 'success', 13, '/MASTER/a.flac', '/nonexistent/path.mp3', CURRENT_TIMESTAMP)
        """
    )
    wizard_db.commit()

    source_type, source_path, _, _ = wizard.resolve_mp3_source(
        wizard_db, "/MASTER/a.flac", 13
    )
    assert source_type == "none"
    assert source_path is None


def test_build_flat_layout(tmp_path: Path) -> None:
    dest = wizard.build_pool_dest_path(
        tmp_path,
        {
            "artist": "DJ A",
            "title": "Track B",
            "genre": "House",
            "label": "X",
            "dj_set_role": "groove",
        },
        {"layout": "flat"},
    )
    assert dest.parent == tmp_path / "pool"
    assert dest.name == "DJ_A_-_Track_B.mp3"


def test_build_layout_accepts_canonical_export_shape(tmp_path: Path) -> None:
    dest = wizard.build_pool_dest_path(
        tmp_path,
        {
            "canonical_artist": "DJ Canon",
            "canonical_title": "Track Prime",
            "canonical_genre": "Afro House",
            "canonical_label": "Innervisions",
            "dj_set_role": "groove",
        },
        {"layout": "by_genre"},
    )
    assert dest.parent == tmp_path / "pool" / "Afro_House"
    assert dest.name == "DJ_Canon_-_Track_Prime.mp3"


def test_build_cache_dest_accepts_canonical_export_shape(tmp_path: Path) -> None:
    dest = wizard._build_cache_dest(
        tmp_path,
        {
            "identity_id": 42,
            "canonical_artist": "DJ Canon",
            "canonical_title": "Track Prime",
        },
        {"bitrate": 320},
    )
    assert dest == tmp_path / "cache" / "DJ_Canon__Track_Prime__42_320k.mp3"


def test_build_layout_variants(tmp_path: Path) -> None:
    genre_dest = wizard.build_pool_dest_path(
        tmp_path,
        {"artist": "DJ A", "title": "Track B", "genre": "Techno", "label": "X", "dj_set_role": None},
        {"layout": "by_genre"},
    )
    role_dest = wizard.build_pool_dest_path(
        tmp_path,
        {"artist": "DJ A", "title": "Track B", "genre": "House", "label": "X", "dj_set_role": "groove"},
        {"layout": "by_role"},
    )
    label_dest = wizard.build_pool_dest_path(
        tmp_path,
        {"artist": "DJ A", "title": "Track B", "genre": "House", "label": "Drumcode", "dj_set_role": None},
        {"layout": "by_label"},
    )
    assert "Techno" in str(genre_dest)
    assert "groove" in str(role_dest)
    assert "Drumcode" in str(label_dest)


def test_build_by_role_null_role_routes_to_unassigned_with_warning(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    with caplog.at_level("WARNING"):
        dest = wizard.build_pool_dest_path(
            tmp_path,
            {
                "master_path": "/MASTER/a.flac",
                "artist": "DJ A",
                "title": "Track B",
                "genre": "House",
                "label": "X",
                "dj_set_role": None,
            },
            {"layout": "by_role"},
        )

    assert dest.parent == tmp_path / "pool" / "_unassigned"
    assert "routing to _unassigned" in caplog.text


def test_build_sanitizes_special_chars(tmp_path: Path) -> None:
    dest = wizard.build_pool_dest_path(
        tmp_path,
        {"artist": "A/B:C", "title": "T?R*K", "genre": "House", "label": "X", "dj_set_role": None},
        {},
    )
    assert "/" not in dest.name
    assert ":" not in dest.name
    assert "?" not in dest.name


def test_plan_relink_row_is_selected(tmp_path: Path, wizard_db: sqlite3.Connection) -> None:
    mp3 = tmp_path / "a.mp3"
    mp3.write_bytes(b"fake")
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=1,
        artist="A",
        title="B",
    )
    wizard_db.execute(
        """
        INSERT INTO provenance_event
        (event_type, status, identity_id, source_path, dest_path, event_time)
        VALUES ('dj_pool_relink', 'success', 1, '/MASTER/a.flac', ?, CURRENT_TIMESTAMP)
        """,
        (str(mp3),),
    )
    wizard_db.commit()

    tracks = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    plan = wizard.plan_actions(wizard_db, tracks, tmp_path, {})
    assert len(plan) == 1
    row = plan[0]
    assert row["selected"] is True
    assert row["cache_action"] == "use_relink"
    assert row["pool_action"] == "copy"
    assert row["reason"] is None


def test_plan_no_identity_is_not_selected(tmp_path: Path, wizard_db: sqlite3.Connection) -> None:
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=None)
    tracks = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    plan = wizard.plan_actions(wizard_db, tracks, tmp_path, {})
    assert len(plan) == 1
    assert plan[0]["selected"] is False
    assert plan[0]["reason"] == "no_v3_identity"


def test_plan_duplicate_identity_second_row_is_skipped(
    tmp_path: Path,
    wizard_db: sqlite3.Connection,
) -> None:
    first_mp3 = tmp_path / "a.mp3"
    first_mp3.write_bytes(b"x")
    second_mp3 = tmp_path / "b.mp3"
    second_mp3.write_bytes(b"y")
    insert_track(wizard_db, "/MASTER/a.flac", is_dj_material=1, identity_id=99, artist="A", title="T")
    insert_track(wizard_db, "/MASTER/b.flac", is_dj_material=1, identity_id=99, artist="A", title="T")
    for path, mp3 in (("/MASTER/a.flac", first_mp3), ("/MASTER/b.flac", second_mp3)):
        wizard_db.execute(
            """
            INSERT INTO provenance_event
            (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_pool_relink', 'success', 99, ?, ?, CURRENT_TIMESTAMP)
            """,
            (path, str(mp3)),
        )
    wizard_db.commit()

    tracks = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    plan = wizard.plan_actions(wizard_db, tracks, tmp_path, {})
    selected = [row for row in plan if row["selected"]]
    skipped = [row for row in plan if not row["selected"]]
    assert len(selected) == 1
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "duplicate_identity"
    assert selected[0]["master_path"] == "/MASTER/a.flac"


def test_plan_legacy_fallback_sets_warning(tmp_path: Path, wizard_db: sqlite3.Connection) -> None:
    mp3 = tmp_path / "legacy.mp3"
    mp3.write_bytes(b"x")
    insert_track(
        wizard_db,
        "/MASTER/c.flac",
        is_dj_material=1,
        dj_pool_path=str(mp3),
        identity_id=50,
        artist="A",
        title="T",
    )
    tracks = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    plan = wizard.plan_actions(wizard_db, tracks, tmp_path, {})
    assert plan[0]["selected"] is True
    assert plan[0]["cache_action"] == "use_legacy"
    assert plan[0]["warning"] == "legacy_cache_fallback"


def test_plan_no_cache_with_identity_is_transcode(
    tmp_path: Path,
    wizard_db: sqlite3.Connection,
) -> None:
    insert_track(
        wizard_db,
        "/MASTER/d.flac",
        is_dj_material=1,
        identity_id=60,
        artist="A",
        title="T",
    )
    tracks = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    plan = wizard.plan_actions(wizard_db, tracks, tmp_path, {})
    assert plan[0]["selected"] is True
    assert plan[0]["cache_action"] == "transcode"
    assert plan[0]["transcode_ready"] is True


def test_plan_collision_resolved_with_suffix(
    tmp_path: Path,
    wizard_db: sqlite3.Connection,
) -> None:
    first_mp3 = tmp_path / "a.mp3"
    first_mp3.write_bytes(b"x")
    second_mp3 = tmp_path / "b.mp3"
    second_mp3.write_bytes(b"y")
    insert_track(
        wizard_db,
        "/MASTER/a.flac",
        is_dj_material=1,
        identity_id=71,
        artist="SameArtist",
        title="SameTitle",
        genre="House",
    )
    insert_track(
        wizard_db,
        "/MASTER/b.flac",
        is_dj_material=1,
        identity_id=72,
        artist="SameArtist",
        title="SameTitle",
        genre="House",
    )
    for identity_id, path, mp3 in (
        (71, "/MASTER/a.flac", first_mp3),
        (72, "/MASTER/b.flac", second_mp3),
    ):
        wizard_db.execute(
            """
            INSERT INTO provenance_event
            (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_pool_relink', 'success', ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (identity_id, path, str(mp3)),
        )
    wizard_db.commit()

    tracks = wizard.select_flagged_master_paths(wizard_db, MASTER, {})
    plan = wizard.plan_actions(wizard_db, tracks, tmp_path, {})
    selected = [row for row in plan if row["selected"]]
    assert len(selected) == 2
    assert len({row["final_dest_path"] for row in selected}) == 2
    assert any("filename_collision_resolved" in (row["warning"] or "") for row in selected)


def test_non_interactive_empty_profile_exits_2(tmp_path: Path, db_path: Path) -> None:
    profile_path = tmp_path / "empty.json"
    profile_path.write_text("{}", encoding="utf-8")
    result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            "/MASTER",
            "--dj-cache-root",
            "/DJ",
            "--out-root",
            str(tmp_path / "out"),
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 2
    assert "profile missing required fields: ['pool_name']" in result.output


def test_non_interactive_missing_out_root_exits_2(db_path: Path) -> None:
    result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            "/MASTER",
            "--dj-cache-root",
            "/DJ",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 2
    assert "--out-root is required" in result.output


@pytest.mark.integration
def test_integration_transcode_path_plan_and_execute_artifacts(
    tmp_path: Path,
    db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conn = open_db(db_path)
    master_root = tmp_path / "MASTER"
    source_path = master_root / "transcode_only.flac"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"flac")

    insert_track(
        conn,
        str(source_path),
        is_dj_material=1,
        identity_id=200,
        artist="Tx Artist",
        title="Tx Title",
        genre="House",
    )
    conn.commit()
    conn.close()

    class _Snapshot:
        bpm = 126.0
        musical_key = "8A"
        energy_1_10 = 7
        bpm_source = "fixture"
        key_source = "fixture"
        energy_source = "fixture"

        def as_dict(self) -> dict:
            return {
                "bpm": self.bpm,
                "musical_key": self.musical_key,
                "energy_1_10": self.energy_1_10,
            }

    def _fake_resolve_snapshot(
        _conn: sqlite3.Connection,
        identity_id: int,
        run_essentia: bool,
        dry_run: bool,
    ) -> _Snapshot:
        assert identity_id == 200
        assert run_essentia is True
        assert dry_run is False
        return _Snapshot()

    def _fake_transcode(
        source: Path,
        _cache_dir: Path,
        _snapshot: _Snapshot,
        *,
        bitrate: int,
        overwrite: bool,
        ffmpeg_path: str | None,
        dest_path: Path | None,
    ) -> None:
        assert source == source_path
        assert bitrate == 320
        assert overwrite is True
        assert ffmpeg_path is None
        assert dest_path is not None
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(b"mp3-transcoded")

    monkeypatch.setattr(wizard, "resolve_dj_tag_snapshot", _fake_resolve_snapshot)
    monkeypatch.setattr(wizard, "transcode_to_mp3_from_snapshot", _fake_transcode)

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "pool_name": "transcode-proof",
                "pool_overwrite_policy": "always",
                "cache_overwrite_policy": "always",
            }
        ),
        encoding="utf-8",
    )

    plan_out = tmp_path / "plan_out"
    plan_result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--dj-cache-root",
            str(tmp_path / "DJ"),
            "--out-root",
            str(plan_out),
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert plan_result.exit_code == 0
    assert "transcode: 1" in plan_result.output

    plan_run_dir = _run_dir(plan_out)
    assert (plan_run_dir / "selected.csv").exists()
    assert (plan_run_dir / "plan.csv").exists()
    assert (plan_run_dir / "pool_manifest.json").exists()

    with (plan_run_dir / "plan.csv").open("r", encoding="utf-8", newline="") as fh:
        plan_rows = list(csv.DictReader(fh))
    assert len(plan_rows) == 1
    assert plan_rows[0]["identity_id"] == "200"
    assert plan_rows[0]["selected"] == "True"
    assert plan_rows[0]["cache_action"] == "transcode"
    assert plan_rows[0]["pool_action"] == "copy_after_transcode"

    exec_out = tmp_path / "exec_out"
    exec_result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--dj-cache-root",
            str(tmp_path / "DJ"),
            "--out-root",
            str(exec_out),
            "--execute",
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert exec_result.exit_code == 0
    assert "executed=1" in exec_result.output
    assert "failed=0" in exec_result.output

    run_dir = _run_dir(exec_out)
    for artifact in (
        "selected.csv",
        "plan.csv",
        "pool_manifest.json",
        "receipts.jsonl",
        "failures.jsonl",
    ):
        assert (run_dir / artifact).exists()

    receipts = [
        json.loads(line)
        for line in (run_dir / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failures = [
        json.loads(line)
        for line in (run_dir / "failures.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert failures == []
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["cache_action"] == "transcode"
    assert receipt["pool_action"] == "copy_after_transcode"
    assert receipt["cache_source_type"] == "none"

    final_dest = Path(receipt["final_dest_path"])
    assert final_dest.exists()
    assert final_dest == Path(receipt["final_dest_path"])
    assert final_dest.is_relative_to(run_dir.resolve())
    assert not final_dest.is_relative_to(master_root.resolve())
    assert not final_dest.is_relative_to((tmp_path / "DJ").resolve())

    manifest = json.loads((run_dir / "pool_manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution_summary"]["selected"] == 1
    assert manifest["execution_summary"]["executed"] == 1
    assert manifest["execution_summary"]["failed"] == 0
    assert len(manifest["rows"]) == 1
    assert manifest["rows"][0]["status"] == "executed"
    assert manifest["rows"][0]["final_dest_path"] == receipt["final_dest_path"]

    conn = open_db(db_path)
    file_row = conn.execute(
        "SELECT dj_pool_path FROM files WHERE path = ?",
        (str(source_path),),
    ).fetchone()
    event_row = conn.execute(
        (
            "SELECT COUNT(*) AS n FROM provenance_event "
            "WHERE identity_id = ? "
            "AND event_type = 'dj_export' "
            "AND status = 'success'"
        ),
        (200,),
    ).fetchone()
    conn.close()

    assert file_row is not None
    assert file_row["dj_pool_path"] == receipt["cache_source_path"]
    assert event_row is not None
    assert int(event_row["n"]) == 1


@pytest.mark.integration
def test_integration_relink_copies_file(tmp_path: Path, db_path: Path) -> None:
    conn = open_db(db_path)
    master_root = tmp_path / "MASTER"
    dj_root = tmp_path / "DJ"
    out_root = tmp_path / "out"
    source_path = master_root / "a.flac"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"flac")
    relink_mp3 = tmp_path / "cache" / "a.mp3"
    relink_mp3.parent.mkdir(parents=True, exist_ok=True)
    relink_mp3.write_bytes(b"mp3data")

    insert_track(
        conn,
        str(source_path),
        is_dj_material=1,
        identity_id=1,
        artist="X",
        title="Y",
    )
    conn.execute(
        """
        INSERT INTO provenance_event
        (event_type, status, identity_id, source_path, dest_path, event_time)
        VALUES ('dj_pool_relink', 'success', 1, ?, ?, CURRENT_TIMESTAMP)
        """,
        (str(source_path), str(relink_mp3)),
    )
    conn.commit()
    conn.close()

    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"pool_name": "inttest", "pool_overwrite_policy": "always"}),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--dj-cache-root",
            str(dj_root),
            "--out-root",
            str(out_root),
            "--execute",
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 0
    assert "executed=1" in result.output

    run_dir = _run_dir(out_root)
    receipts = [
        json.loads(line)
        for line in (run_dir / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(receipts) == 1
    final_dest = Path(receipts[0]["final_dest_path"])
    assert final_dest.exists()
    assert final_dest.is_relative_to(run_dir.resolve())
    assert not final_dest.is_relative_to(master_root.resolve())
    assert not final_dest.is_relative_to(dj_root.resolve())

    conn = open_db(db_path)
    row = conn.execute(
        "SELECT dj_pool_path FROM files WHERE path = ?",
        (str(source_path),),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["dj_pool_path"] is None


@pytest.mark.integration
def test_integration_no_identity_is_skipped_not_failed(
    tmp_path: Path,
    db_path: Path,
) -> None:
    conn = open_db(db_path)
    master_root = tmp_path / "MASTER"
    source_path = master_root / "b.flac"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"flac")
    insert_track(conn, str(source_path), is_dj_material=1, identity_id=None)
    conn.close()

    out_root = tmp_path / "out"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"pool_name": "inttest2", "pool_overwrite_policy": "always"}),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--dj-cache-root",
            str(tmp_path / "DJ"),
            "--out-root",
            str(out_root),
            "--execute",
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 0
    assert "selected=0" in result.output
    assert "skipped=1" in result.output
    assert "failed=0" in result.output

    run_dir = _run_dir(out_root)
    failures_text = (run_dir / "failures.jsonl").read_text(encoding="utf-8")
    assert failures_text == ""
    manifest = json.loads((run_dir / "pool_manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution_summary"]["skipped"] == 1
    assert manifest["rows"][0]["status"] == "skipped"


@pytest.mark.integration
def test_integration_duplicate_identity_one_copy(tmp_path: Path, db_path: Path) -> None:
    conn = open_db(db_path)
    master_root = tmp_path / "MASTER"
    for suffix, path in (("a", master_root / "a.flac"), ("b", master_root / "b.flac")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"flac")
        mp3 = tmp_path / "cache" / f"{suffix}.mp3"
        mp3.parent.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(b"x")
        insert_track(conn, str(path), is_dj_material=1, identity_id=99, artist="A", title="T")
        conn.execute(
            """
            INSERT INTO provenance_event
            (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_pool_relink', 'success', 99, ?, ?, CURRENT_TIMESTAMP)
            """,
            (str(path), str(mp3)),
        )
    conn.commit()
    conn.close()

    out_root = tmp_path / "out"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"pool_name": "duptest", "pool_overwrite_policy": "always"}),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--dj-cache-root",
            str(tmp_path / "DJ"),
            "--out-root",
            str(out_root),
            "--execute",
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 0
    assert "selected=1" in result.output
    assert "executed=1" in result.output
    assert "skipped=1" in result.output

    run_dir = _run_dir(out_root)
    receipts = [
        json.loads(line)
        for line in (run_dir / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(receipts) == 1


@pytest.mark.integration
def test_integration_by_role_creates_playlists_only_for_non_empty_roles(
    tmp_path: Path,
    db_path: Path,
) -> None:
    conn = open_db(db_path)
    master_root = tmp_path / "MASTER"
    rows = [
        (1, "a.flac", "a.mp3", "Alpha", "Groove", "groove"),
        (2, "b.flac", "b.mp3", "Beta", "Bridge", "bridge"),
        (3, "c.flac", "c.mp3", "Gamma", "Unassigned", None),
    ]
    for identity_id, source_name, mp3_name, artist, title, dj_set_role in rows:
        source_path = master_root / source_name
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"flac")
        relink_mp3 = tmp_path / "cache" / mp3_name
        relink_mp3.parent.mkdir(parents=True, exist_ok=True)
        relink_mp3.write_bytes(b"x")
        insert_track(
            conn,
            str(source_path),
            is_dj_material=1,
            identity_id=identity_id,
            artist=artist,
            title=title,
            dj_set_role=dj_set_role,
        )
        conn.execute(
            """
            INSERT INTO provenance_event
            (event_type, status, identity_id, source_path, dest_path, event_time)
            VALUES ('dj_pool_relink', 'success', ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (identity_id, str(source_path), str(relink_mp3)),
        )
    conn.commit()
    conn.close()

    out_root = tmp_path / "out"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps(
            {
                "pool_name": "role-playlists",
                "layout": "by_role",
                "create_playlist": True,
                "playlist_mode": "relative",
                "pool_overwrite_policy": "always",
            }
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--dj-cache-root",
            str(tmp_path / "DJ"),
            "--out-root",
            str(out_root),
            "--execute",
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 0

    run_dir = _run_dir(out_root)
    pool_root = run_dir / "pool"
    groove_playlist = pool_root / "10_GROOVE.m3u"
    bridge_playlist = pool_root / "30_BRIDGE.m3u"
    assert groove_playlist.exists()
    assert bridge_playlist.exists()
    assert not (pool_root / "20_PRIME.m3u").exists()
    assert not (pool_root / "40_CLUB.m3u").exists()
    assert not (run_dir / "playlist.m3u8").exists()

    groove_lines = [
        line for line in groove_playlist.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    bridge_lines = [
        line for line in bridge_playlist.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert groove_lines == ["groove/Alpha_-_Groove.mp3"]
    assert bridge_lines == ["bridge/Beta_-_Bridge.mp3"]
    assert (pool_root / "_unassigned").is_dir()


@pytest.mark.integration
def test_integration_missing_artist_excluded_with_gate(
    tmp_path: Path,
    db_path: Path,
) -> None:
    conn = open_db(db_path)
    master_root = tmp_path / "MASTER"
    source_path = master_root / "c.flac"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"flac")
    relink_mp3 = tmp_path / "cache" / "c.mp3"
    relink_mp3.parent.mkdir(parents=True, exist_ok=True)
    relink_mp3.write_bytes(b"x")
    insert_track(
        conn,
        str(source_path),
        is_dj_material=1,
        identity_id=5,
        artist=None,
        title=None,
    )
    conn.execute(
        """
        INSERT INTO provenance_event
        (event_type, status, identity_id, source_path, dest_path, event_time)
        VALUES ('dj_pool_relink', 'success', 5, ?, ?, CURRENT_TIMESTAMP)
        """,
        (str(source_path), str(relink_mp3)),
    )
    conn.commit()
    conn.close()

    out_root = tmp_path / "out"
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(
        json.dumps({"pool_name": "gatetest", "require_artist_title": True}),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        dj_group,
        [
            "pool-wizard",
            "--db",
            str(db_path),
            "--master-root",
            str(master_root),
            "--dj-cache-root",
            str(tmp_path / "DJ"),
            "--out-root",
            str(out_root),
            "--non-interactive",
            "--profile",
            str(profile_path),
        ],
    )
    assert result.exit_code == 2
    assert "profile filter produces empty cohort" in result.output
