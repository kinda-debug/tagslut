from __future__ import annotations

import sqlite3
from pathlib import Path

from tagslut.exec.mp3_consolidate import Source, consolidate_mp3s


def _make_db(db_path: Path, initial_paths: list[Path]) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE files (path TEXT PRIMARY KEY)")
        for p in initial_paths:
            conn.execute("INSERT INTO files (path) VALUES (?)", (str(p.resolve()),))
        conn.commit()
    finally:
        conn.close()


def _paths(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT path FROM files").fetchall()
    return {str(r[0]) for r in rows}


def test_moves_mp3_and_updates_db(tmp_path: Path) -> None:
    source_root = tmp_path / "DJ_LIBRARY"
    mp3_library = tmp_path / "MP3_LIBRARY"
    src = source_root / "Artist" / "Track.mp3"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"mp3-a")

    db_path = tmp_path / "music.db"
    _make_db(db_path, [src])

    stats = consolidate_mp3s(
        mp3_library=mp3_library,
        sources=[Source(source_root, "_legacy_dj")],
        db_path=db_path,
        execute=True,
        verbose=False,
    )

    dest = mp3_library / "_legacy_dj" / "Artist" / "Track.mp3"
    assert not src.exists()
    assert dest.exists()
    assert stats.files_moved == 1

    conn = sqlite3.connect(str(db_path))
    try:
        assert _paths(conn) == {str(dest.resolve())}
    finally:
        conn.close()


def test_collision_identical_deletes_src_and_updates_db(tmp_path: Path) -> None:
    source_root = tmp_path / "DJ_LIBRARY"
    mp3_library = tmp_path / "MP3_LIBRARY"
    src = source_root / "Track.mp3"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"same")

    dest = mp3_library / "_legacy_dj" / "Track.mp3"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"same")

    db_path = tmp_path / "music.db"
    _make_db(db_path, [src])

    stats = consolidate_mp3s(
        mp3_library=mp3_library,
        sources=[Source(source_root, "_legacy_dj")],
        db_path=db_path,
        execute=True,
        verbose=False,
    )

    assert not src.exists()
    assert dest.exists()
    assert stats.duplicates_removed == 1

    conn = sqlite3.connect(str(db_path))
    try:
        assert _paths(conn) == {str(dest.resolve())}
    finally:
        conn.close()


def test_collision_different_renames_dest_conflict_and_updates_db(tmp_path: Path) -> None:
    source_root = tmp_path / "DJ_LIBRARY"
    mp3_library = tmp_path / "MP3_LIBRARY"
    src = source_root / "Track.mp3"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"src")

    dest = mp3_library / "_legacy_dj" / "Track.mp3"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"dest")

    conflict = mp3_library / "_legacy_dj" / "Track_conflict.mp3"

    db_path = tmp_path / "music.db"
    _make_db(db_path, [src, dest])

    stats = consolidate_mp3s(
        mp3_library=mp3_library,
        sources=[Source(source_root, "_legacy_dj")],
        db_path=db_path,
        execute=True,
        verbose=False,
    )

    assert not src.exists()
    assert dest.read_bytes() == b"src"
    assert conflict.exists()
    assert conflict.read_bytes() == b"dest"
    assert stats.conflicts_renamed == 1

    conn = sqlite3.connect(str(db_path))
    try:
        assert _paths(conn) == {str(dest.resolve()), str(conflict.resolve())}
    finally:
        conn.close()


def test_dry_run_does_not_move_or_update_db(tmp_path: Path) -> None:
    source_root = tmp_path / "DJ_LIBRARY"
    mp3_library = tmp_path / "MP3_LIBRARY"
    src = source_root / "Track.mp3"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"mp3-a")

    db_path = tmp_path / "music.db"
    _make_db(db_path, [src])

    stats = consolidate_mp3s(
        mp3_library=mp3_library,
        sources=[Source(source_root, "_legacy_dj")],
        db_path=db_path,
        execute=False,
        verbose=False,
    )

    dest = mp3_library / "_legacy_dj" / "Track.mp3"
    assert src.exists()
    assert not dest.exists()
    assert stats.db_rows_updated == 0

    conn = sqlite3.connect(str(db_path))
    try:
        assert _paths(conn) == {str(src.resolve())}
    finally:
        conn.close()

