from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from mutagen.id3 import ID3, TALB, TIT2, TPE1


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = PROJECT_ROOT / "tools" / "dj" / "build_special_pool_from_m3u.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("build_special_pool_from_m3u_under_test", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_dummy_mp3(path: Path, *, title: str, artist: str, album: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=artist))
    tags.add(TALB(encoding=3, text=album))
    tags.save(path)


def test_build_special_pool_copies_unique_tracks_and_rewrites_playlists(tmp_path: Path) -> None:
    module = _load_module()
    source_root = tmp_path / "DJ_LIBRARY"
    song_a = source_root / "Artist A" / "Album A" / "Artist A - Song A.mp3"
    song_b = source_root / "Artist B" / "Album B" / "Artist B - Song B.mp3"
    _write_dummy_mp3(song_a, title="Song A", artist="Artist A", album="Album A")
    _write_dummy_mp3(song_b, title="Song B", artist="Artist B", album="Album B")

    playlist_one = source_root / "Playlist One.m3u"
    playlist_one.write_text(f"#EXTM3U\n{song_a}\n{song_b}\n{song_a}\n", encoding="utf-8")
    playlist_two = source_root / "Playlist Two.m3u"
    playlist_two.write_text(f"#EXTM3U\n{song_b}\n", encoding="utf-8")

    out_root = tmp_path / "gig_runs" / "gig_2026_03_13"
    summary = module.build_special_pool(
        playlist_paths=[playlist_one, playlist_two],
        out_root=out_root,
        pool_name="tomorrow-special",
        source_root=source_root,
    )

    assert summary["playlist_count"] == 2
    assert summary["unique_tracks"] == 2
    assert summary["copied_tracks"] == 2
    assert summary["missing_sources"] == 0

    run_root = Path(str(summary["run_root"]))
    copied_a = run_root / "pool" / "Artist A" / "Album A" / "Artist A - Song A.mp3"
    copied_b = run_root / "pool" / "Artist B" / "Album B" / "Artist B - Song B.mp3"
    assert copied_a.exists()
    assert copied_b.exists()

    playlist_one_out = run_root / "playlists" / "Playlist One.m3u"
    merged_out = run_root / "playlists" / "tomorrow-special_all.m3u"
    one_text = playlist_one_out.read_text(encoding="utf-8")
    merged_text = merged_out.read_text(encoding="utf-8")
    assert "../pool/Artist A/Album A/Artist A - Song A.mp3" in one_text
    assert "../pool/Artist B/Album B/Artist B - Song B.mp3" in one_text
    assert merged_text.count("../pool/") == 2
