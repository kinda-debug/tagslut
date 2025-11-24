from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Sequence

from tools.db_upgrade import LIBRARY_COLUMNS, upgrade_db


def _create_legacy_db(path: Path, columns: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    conn = sqlite3.connect(path)
    columns_sql = ", ".join(f"{col} TEXT" for col in columns)
    conn.execute(f"CREATE TABLE library_files ({columns_sql})")
    placeholders = ", ".join("?" for _ in columns)
    for row in rows:
        conn.execute(
            f"INSERT INTO library_files ({', '.join(columns)}) VALUES ({placeholders})",
            tuple(row),
        )
    conn.commit()
    conn.close()


def _fetch_rows(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM library_files").fetchall()
    conn.close()
    return rows


def test_upgrade_minimal_columns(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy_minimal.db"
    upgraded_db = tmp_path / "upgraded_minimal.db"
    _create_legacy_db(
        legacy_db,
        ["path", "checksum"],
        [("/music/track.flac", "abc123")],
    )

    upgrade_db(str(legacy_db), str(upgraded_db))

    rows = _fetch_rows(upgraded_db)
    assert len(rows) == 1
    upgraded = rows[0]
    assert upgraded["path"] == "/music/track.flac"
    assert upgraded["checksum"] == "abc123"
    assert upgraded["tags_json"] == "{}"
    assert upgraded["size_bytes"] is None


def test_upgrade_missing_tags_json(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy_missing_tags.db"
    upgraded_db = tmp_path / "upgraded_missing_tags.db"
    _create_legacy_db(
        legacy_db,
        ["path", "size_bytes"],
        [("/music/untagged.flac", 1234)],
    )

    upgrade_db(str(legacy_db), str(upgraded_db))

    upgraded = _fetch_rows(upgraded_db)[0]
    assert upgraded["tags_json"] in (None, "{}")
    assert upgraded["size_bytes"] == 1234


def test_upgrade_sanitises_invalid_utf8(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy_invalid_utf8.db"
    upgraded_db = tmp_path / "upgraded_invalid_utf8.db"
    _create_legacy_db(
        legacy_db,
        ["path", "checksum"],
        [(b"/music/bad\x80path.flac", "deadbeef")],
    )

    upgrade_db(str(legacy_db), str(upgraded_db))

    upgraded = _fetch_rows(upgraded_db)[0]
    assert upgraded["path"].endswith("bad�path.flac")


def test_upgrade_ignores_extra_columns(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy_extra.db"
    upgraded_db = tmp_path / "upgraded_extra.db"
    _create_legacy_db(
        legacy_db,
        ["path", "checksum", "extra_field"],
        [("/music/extra.flac", "ff", "ignored")],
    )

    upgrade_db(str(legacy_db), str(upgraded_db))

    upgraded = _fetch_rows(upgraded_db)[0]
    assert upgraded["path"] == "/music/extra.flac"
    assert upgraded["checksum"] == "ff"


def test_upgrade_preserves_row_count(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy_count.db"
    upgraded_db = tmp_path / "upgraded_count.db"
    rows = [(f"/music/track_{idx}.flac", None) for idx in range(5)]
    _create_legacy_db(legacy_db, ["path", "checksum"], rows)

    upgrade_db(str(legacy_db), str(upgraded_db))

    upgraded_rows = _fetch_rows(upgraded_db)
    assert len(upgraded_rows) == len(rows)


def test_upgraded_schema_matches_expected(tmp_path: Path) -> None:
    legacy_db = tmp_path / "legacy_schema.db"
    upgraded_db = tmp_path / "upgraded_schema.db"
    _create_legacy_db(legacy_db, ["path"], [("/music/only_path.flac",)])

    upgrade_db(str(legacy_db), str(upgraded_db))

    conn = sqlite3.connect(upgraded_db)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(library_files);").fetchall()]
    conn.close()

    assert tuple(columns) == tuple(LIBRARY_COLUMNS)
