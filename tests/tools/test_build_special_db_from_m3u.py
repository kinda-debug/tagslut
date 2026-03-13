from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

from mutagen.id3 import ID3, TALB, TBPM, TIT2, TKEY, TPE1, TSRC


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "dj" / "build_special_db_from_m3u.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_special_db_from_m3u_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_dummy_mp3(path: Path, *, title: str, artist: str, album: str, bpm: str, key: str, isrc: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    tags.add(TBPM(encoding=3, text=bpm))
    tags.add(TKEY(encoding=3, text=key))
    tags.add(TSRC(encoding=3, text=isrc))
    tags.save(path)


def test_build_special_db_reads_relative_playlist_entries_and_populates_files_table(tmp_path: Path) -> None:
    module = _load_module()
    run_root = tmp_path / "special_pool_from_playlists_20260312_184742"
    pool_root = run_root / "pool"
    playlists_root = run_root / "playlists"
    song = pool_root / "Artist A" / "Album A" / "Artist A - Song A.mp3"
    _write_dummy_mp3(
        song,
        title="Song A",
        artist="Artist A",
        album="Album A",
        bpm="124",
        key="8A",
        isrc="USRC17607839",
    )

    playlist = playlists_root / "special_pool_from_playlists_20260312_184742_all.m3u"
    playlist.parent.mkdir(parents=True, exist_ok=True)
    playlist.write_text(
        "#EXTM3U\n"
        "#EXTINF:-1,Artist A - Song A\n"
        "../pool/Artist A/Album A/Artist A - Song A.mp3\n",
        encoding="utf-8",
    )

    db_path = run_root / "special_pool_from_playlists_20260312_184742_metadata.db"
    summary = module.build_special_db(
        playlist_path=playlist,
        db_path=db_path,
        overwrite=True,
    )

    assert summary["playlist_entries"] == 1
    assert summary["existing_entries"] == 1
    assert summary["missing_entries"] == 0
    assert summary["unique_files"] == 1
    assert db_path.exists()
    assert db_path.with_suffix(".summary.json").exists()

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        file_row = conn.execute(
            """
            SELECT
                path,
                library,
                m3u_path,
                dj_pool_path,
                canonical_title,
                canonical_artist,
                canonical_album,
                canonical_bpm,
                key_camelot,
                isrc,
                metadata_json
            FROM files
            """
        ).fetchone()
        assert file_row is not None
        assert file_row["path"] == str(song.resolve())
        assert file_row["library"] == run_root.name
        assert file_row["m3u_path"] == str(playlist.resolve())
        assert file_row["dj_pool_path"] == str(song.resolve())
        assert file_row["canonical_title"] == "Song A"
        assert file_row["canonical_artist"] == "Artist A"
        assert file_row["canonical_album"] == "Album A"
        assert file_row["canonical_bpm"] == 124.0
        assert file_row["key_camelot"] == "8A"
        assert file_row["isrc"] == "USRC17607839"

        metadata = json.loads(str(file_row["metadata_json"]))
        assert metadata["playlist"]["raw_entry"] == "../pool/Artist A/Album A/Artist A - Song A.mp3"
        assert metadata["easy_tags"]["title"] == ["Song A"]
        assert "TIT2" in metadata["raw_tags"]

        playlist_row = conn.execute(
            """
            SELECT playlist_name, item_index, raw_entry, resolved_path, file_exists
            FROM playlist_items
            """
        ).fetchone()
        assert playlist_row is not None
        assert playlist_row["playlist_name"] == playlist.stem
        assert playlist_row["item_index"] == 1
        assert playlist_row["raw_entry"] == "../pool/Artist A/Album A/Artist A - Song A.mp3"
        assert playlist_row["resolved_path"] == str(song.resolve())
        assert playlist_row["file_exists"] == 1
    finally:
        conn.close()


def test_build_special_db_can_index_pool_root_and_preserve_playlist_membership(tmp_path: Path) -> None:
    module = _load_module()
    run_root = tmp_path / "special_pool_from_playlists_20260312_184742"
    pool_root = run_root / "pool"
    playlists_root = run_root / "playlists"
    song_a = pool_root / "Artist A" / "Album A" / "Artist A - Song A.mp3"
    song_b = pool_root / "Artist B" / "Album B" / "Artist B - Song B.mp3"
    _write_dummy_mp3(
        song_a,
        title="Song A",
        artist="Artist A",
        album="Album A",
        bpm="124",
        key="8A",
        isrc="USRC17607839",
    )
    _write_dummy_mp3(
        song_b,
        title="Song B",
        artist="Artist B",
        album="Album B",
        bpm="126",
        key="9A",
        isrc="USRC17607840",
    )

    playlist = playlists_root / "special_pool_from_playlists_20260312_184742_all.m3u"
    playlist.parent.mkdir(parents=True, exist_ok=True)
    playlist.write_text(
        "#EXTM3U\n"
        "#EXTINF:-1,Artist A - Song A\n"
        "../pool/Artist A/Album A/Artist A - Song A.mp3\n",
        encoding="utf-8",
    )

    db_path = run_root / "special_pool_from_playlists_20260312_184742_metadata.db"
    summary = module.build_special_db(
        playlist_path=playlist,
        pool_root=pool_root,
        db_path=db_path,
        overwrite=True,
    )

    assert summary["source_mode"] == "pool+playlist"
    assert summary["playlist_entries"] == 1
    assert summary["pool_files"] == 2
    assert summary["unique_files"] == 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM playlist_items").fetchone()[0] == 1

        row_a = conn.execute(
            "SELECT m3u_path, metadata_json FROM files WHERE path = ?",
            (str(song_a.resolve()),),
        ).fetchone()
        row_b = conn.execute(
            "SELECT m3u_path, metadata_json FROM files WHERE path = ?",
            (str(song_b.resolve()),),
        ).fetchone()
        assert row_a is not None
        assert row_b is not None
        assert row_a["m3u_path"] == str(playlist.resolve())
        assert row_b["m3u_path"] is None

        metadata_a = json.loads(str(row_a["metadata_json"]))
        metadata_b = json.loads(str(row_b["metadata_json"]))
        assert metadata_a["source"]["kind"] == "playlist"
        assert metadata_b["source"]["kind"] == "pool"
        assert metadata_b["pool"]["pool_root"] == str(pool_root.resolve())
    finally:
        conn.close()
