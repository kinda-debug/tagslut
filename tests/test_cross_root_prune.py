import sqlite3
from pathlib import Path


from scripts.prune_cross_root_duplicates import (
    build_cross_root_prune_plan,
    choose_keeper,
)


def make_db(tmp_path: Path, rows: list[tuple[str, str, int]]) -> Path:
    db_path = tmp_path / "file_dupes.db"
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE file_hashes (
                file_path TEXT PRIMARY KEY,
                file_md5 TEXT NOT NULL,
                file_size INTEGER,
                scan_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.executemany(
            (
                "INSERT INTO file_hashes(file_path, file_md5, file_size) "
                "VALUES(?,?,?)"
            ),
            rows,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_choose_keeper_prefers_music_root(tmp_path: Path) -> None:
    music = tmp_path / "MUSIC"
    quarantine = tmp_path / "Quarantine"
    garbage = tmp_path / "Garbage"
    for p in (music, quarantine, garbage):
        p.mkdir(parents=True, exist_ok=True)

    paths = [
        music / "Artist/Album/track.flac",
        quarantine / "Artist/Album/track.flac",
        garbage / "Artist/Album/track.flac",
    ]
    k = choose_keeper(paths, library_root=music)
    assert str(k).startswith(str(music))


def test_build_plan_classifies_reasons(tmp_path: Path) -> None:
    music = tmp_path / "MUSIC"
    quarantine = tmp_path / "Quarantine"
    garbage = tmp_path / "Garbage"
    for p in (music, quarantine, garbage):
        (p / "Artist/Album").mkdir(parents=True, exist_ok=True)

    # Build a small DB with a duplicate group of 3 files (same md5)
    md5 = "deadbeef"
    rows = [
        (str(music / "Artist/Album/track.flac"), md5, 1000),
        (str(quarantine / "Artist/Album/track.flac"), md5, 1000),
        (str(garbage / "Artist/Album/track.flac"), md5, 1000),
    ]
    db_path = make_db(tmp_path, rows)

    conn = sqlite3.connect(db_path)
    try:
        plan = build_cross_root_prune_plan(
            conn,
            library_root=music,
            quarantine_root=quarantine,
            garbage_root=garbage,
        )
    finally:
        conn.close()

    reasons = {i.reason for i in plan}
    # We should have two extras: one quarantine, one garbage
    assert reasons == {"extra_quarantine", "extra_garbage"}
    # Ensure keeper is the MUSIC path
    for item in plan:
        assert str(item.keeper).startswith(str(music))
