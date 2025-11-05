from __future__ import annotations

from pathlib import Path
from scripts.lib.common import choose_winner, plan_trash_destination, load_broken_playlist_set, FileInfo


def make_info(id: int, name: str, healthy=None, lossless=True, duration=None, bitrate=None, mtime=0.0) -> FileInfo:
    from __future__ import annotations

    from pathlib import Path
    import tempfile

    from scripts.lib.common import (
        choose_winner,
        plan_trash_destination,
        load_broken_playlist_set,
        FileInfo,
    )


    def make_info(fid: int, name: str, healthy=None, lossless=True, duration=None, bitrate=None, mtime=0.0) -> FileInfo:
        return FileInfo(
            id=fid,
            path=Path(name),
            inode=0,
            size_bytes=1000,
            mtime=mtime,
            codec="flac",
            lossless=lossless,
            duration=duration,
            bitrate_kbps=bitrate,
            healthy=healthy,
        )


    def test_choose_winner_prefers_healthy_and_lossless() -> None:
        a = make_info(1, "a.flac", healthy=False, lossless=False, duration=180.0, bitrate=128.0, mtime=1.0)
        b = make_info(2, "b.flac", healthy=True, lossless=False, duration=179.0, bitrate=128.0, mtime=2.0)
        c = make_info(3, "c.flac", healthy=True, lossless=True, duration=180.0, bitrate=320.0, mtime=3.0)

        winner = choose_winner([a, b, c])
        assert winner == c


    def test_plan_trash_destination_preserves_name() -> None:
        with tempfile.TemporaryDirectory() as td:
            trash = Path(td) / "trash"
            file_path = Path("/Volumes/dotad/MUSIC/Artist/Album/song.flac")
            dest = plan_trash_destination(trash, file_path)
            assert dest.name == file_path.name
            assert str(dest).startswith(str(trash))


    def test_load_broken_playlist_set_reads_lines() -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "broken.m3u"
            p.write_text("# header\n/one/path.flac\n/another/path.flac\n", encoding="utf-8")
            s = load_broken_playlist_set(str(p))
            assert "/one/path.flac" in s
            assert "/another/path.flac" in s
