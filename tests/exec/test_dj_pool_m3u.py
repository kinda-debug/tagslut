from __future__ import annotations

from pathlib import Path

from tagslut.exec.dj_pool_m3u import write_dj_pool_m3u


class _FakeMP3Info:
    def __init__(self, length: float) -> None:
        self.length = length


class _FakeMP3:
    def __init__(self, _path: str) -> None:
        self.info = _FakeMP3Info(214.9)


class _FakeTextFrame:
    def __init__(self, value: str) -> None:
        self.text = [value]


class _FakeID3:
    def __init__(self, _path: str) -> None:
        self._frames = {
            "TPE1": _FakeTextFrame("Fouk"),
            "TIT2": _FakeTextFrame("Sunday"),
        }

    def get(self, frame_id: str):
        return self._frames.get(frame_id)


def test_batch_m3u_written_to_common_parent(tmp_path: Path, monkeypatch) -> None:
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Fouk" / "(2024) Sundays EP"
    album_dir.mkdir(parents=True, exist_ok=True)

    mp3_a = album_dir / "01 Sunday.mp3"
    mp3_b = album_dir / "02 Monday.mp3"
    mp3_a.write_bytes(b"")
    mp3_b.write_bytes(b"")

    monkeypatch.setattr("mutagen.mp3.MP3", _FakeMP3)
    monkeypatch.setattr("mutagen.id3.ID3", _FakeID3)

    batch_path, global_path = write_dj_pool_m3u([mp3_a, mp3_b], mp3_root)
    assert batch_path == (album_dir / "dj_pool.m3u").resolve()
    assert global_path == (mp3_root / "dj_pool.m3u").resolve()


def test_batch_m3u_named_from_playlist(tmp_path: Path, monkeypatch) -> None:
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Various Artists" / "(2024) Balearic Summer"
    album_dir.mkdir(parents=True, exist_ok=True)

    mp3_a = album_dir / "01 Track.mp3"
    mp3_b = album_dir / "02 Track.mp3"
    mp3_a.write_bytes(b"")
    mp3_b.write_bytes(b"")

    monkeypatch.setattr("mutagen.mp3.MP3", _FakeMP3)
    monkeypatch.setattr("mutagen.id3.ID3", _FakeID3)

    batch_path, _ = write_dj_pool_m3u([mp3_a, mp3_b], mp3_root, playlist_name="Balearic Summer")
    assert batch_path == (album_dir / "Balearic Summer.m3u").resolve()


def test_batch_m3u_default_name_when_playlist_missing(tmp_path: Path, monkeypatch) -> None:
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Artist" / "Album"
    album_dir.mkdir(parents=True, exist_ok=True)

    mp3_a = album_dir / "01 Track.mp3"
    mp3_a.write_bytes(b"")

    monkeypatch.setattr("mutagen.mp3.MP3", _FakeMP3)
    monkeypatch.setattr("mutagen.id3.ID3", _FakeID3)

    batch_path, _ = write_dj_pool_m3u([mp3_a], mp3_root)
    assert batch_path.name == "dj_pool.m3u"


def test_playlist_name_sanitized(tmp_path: Path, monkeypatch) -> None:
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Artist" / "Album"
    album_dir.mkdir(parents=True, exist_ok=True)

    mp3_a = album_dir / "01 Track.mp3"
    mp3_a.write_bytes(b"")

    monkeypatch.setattr("mutagen.mp3.MP3", _FakeMP3)
    monkeypatch.setattr("mutagen.id3.ID3", _FakeID3)

    batch_path, _ = write_dj_pool_m3u([mp3_a], mp3_root, playlist_name="  bad/na\\me:*?\"<>|  mix  ")
    assert batch_path.name == "bad_na_me_______ mix.m3u"


def test_playlist_name_truncated(tmp_path: Path, monkeypatch) -> None:
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Artist" / "Album"
    album_dir.mkdir(parents=True, exist_ok=True)

    mp3_a = album_dir / "01 Track.mp3"
    mp3_a.write_bytes(b"")

    long_name = "A" * 120

    monkeypatch.setattr("mutagen.mp3.MP3", _FakeMP3)
    monkeypatch.setattr("mutagen.id3.ID3", _FakeID3)

    batch_path, _ = write_dj_pool_m3u([mp3_a], mp3_root, playlist_name=long_name)
    assert len(batch_path.stem) == 100


def test_global_m3u_appends_and_skips_duplicates(tmp_path: Path, monkeypatch) -> None:
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Fouk" / "(2024) Sundays EP"
    album_dir.mkdir(parents=True, exist_ok=True)

    mp3_a = album_dir / "01 Sunday.mp3"
    mp3_b = album_dir / "02 Monday.mp3"
    mp3_a.write_bytes(b"")
    mp3_b.write_bytes(b"")

    monkeypatch.setattr("mutagen.mp3.MP3", _FakeMP3)
    monkeypatch.setattr("mutagen.id3.ID3", _FakeID3)

    global_path = (mp3_root / "dj_pool.m3u").resolve()
    global_path.parent.mkdir(parents=True, exist_ok=True)
    global_path.write_text(f"#EXTM3U\n{mp3_a.resolve()}\n", encoding="utf-8")

    _, updated_global = write_dj_pool_m3u([mp3_a, mp3_b], mp3_root)
    lines = [ln.strip() for ln in updated_global.read_text(encoding="utf-8").splitlines() if ln.strip()]
    paths = [ln for ln in lines if not ln.startswith("#")]

    assert paths.count(str(mp3_a.resolve())) == 1
    assert paths.count(str(mp3_b.resolve())) == 1


def test_extinf_format_duration_artist_title(tmp_path: Path, monkeypatch) -> None:
    mp3_root = tmp_path / "MP3_LIBRARY"
    album_dir = mp3_root / "Fouk" / "(2024) Sundays EP"
    album_dir.mkdir(parents=True, exist_ok=True)

    mp3_a = album_dir / "01 Sunday.mp3"
    mp3_a.write_bytes(b"")

    monkeypatch.setattr("mutagen.mp3.MP3", _FakeMP3)
    monkeypatch.setattr("mutagen.id3.ID3", _FakeID3)

    batch_path, _ = write_dj_pool_m3u([mp3_a], mp3_root)
    content = batch_path.read_text(encoding="utf-8")

    assert content.splitlines()[0].strip() == "#EXTM3U"
    assert "#EXTINF:214,Fouk - Sunday" in content
    assert str(mp3_a.resolve()) in content
