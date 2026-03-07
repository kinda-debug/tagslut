from pathlib import Path

from tagslut.cli.commands._index_helpers import collect_audio_inputs, write_m3u


def test_write_m3u_uses_absolute_paths(tmp_path: Path, monkeypatch) -> None:
    audio_file = tmp_path / "library" / "Artist" / "track.flac"
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"")
    output_dir = tmp_path / "playlists"

    monkeypatch.setattr(
        "tagslut.cli.commands._index_helpers.format_extinf",
        lambda file_path: (123, file_path.stem),
    )

    output = write_m3u(
        playlist_name="test-absolute",
        files=[audio_file],
        output_dir=output_dir,
        path_mode="absolute",
    )

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == str(audio_file.resolve())


def test_write_m3u_uses_playlist_relative_paths(tmp_path: Path, monkeypatch) -> None:
    audio_file = tmp_path / "library" / "Artist" / "track.flac"
    audio_file.parent.mkdir(parents=True, exist_ok=True)
    audio_file.write_bytes(b"")
    output_dir = tmp_path / "library" / "playlists"

    monkeypatch.setattr(
        "tagslut.cli.commands._index_helpers.format_extinf",
        lambda file_path: (123, file_path.stem),
    )

    output = write_m3u(
        playlist_name="test-relative",
        files=[audio_file],
        output_dir=output_dir,
        path_mode="relative",
    )

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "../Artist/track.flac"


def test_collect_audio_inputs_accepts_mp3_and_flac(tmp_path: Path) -> None:
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    flac_file = audio_root / "one.flac"
    mp3_file = audio_root / "two.mp3"
    txt_file = audio_root / "skip.txt"
    flac_file.write_bytes(b"")
    mp3_file.write_bytes(b"")
    txt_file.write_text("ignore", encoding="utf-8")

    found = collect_audio_inputs((str(audio_root),))

    assert found == [flac_file, mp3_file]
