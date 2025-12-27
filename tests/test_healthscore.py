from __future__ import annotations

from pathlib import Path
from typing import Any

from dedupe import cli, healthscore, metadata


def _fake_metadata(tmp_path: Path) -> metadata.FileMetadata:
    stream = metadata.AudioStreamInfo(
        duration=123.4,
        sample_rate=44100,
        bit_rate=256000,
        channels=2,
        bit_depth=16,
    )
    return metadata.FileMetadata(path=tmp_path, size_bytes=42, stream=stream, tags={"a": "b"})


def test_valid_flac(monkeypatch, tmp_path):
    target = tmp_path / "valid.flac"
    target.write_bytes(b"fLaC")

    fake_meta = _fake_metadata(target)
    monkeypatch.setattr(metadata, "probe_audio", lambda path: fake_meta)

    class FakeInfo:
        md5_signature = "abc123"

    class FakeFlac:
        def __init__(self, _path: Path):
            self.info = FakeInfo()

    monkeypatch.setattr(healthscore, "FLAC", FakeFlac)

    score, info = healthscore.score_file(str(target))
    assert score == 10
    assert info["duration"] == fake_meta.stream.duration
    assert info["sample_rate"] == fake_meta.stream.sample_rate
    assert info["channels"] == fake_meta.stream.channels
    assert info["bit_depth"] == fake_meta.stream.bit_depth
    assert info["tags_ok"] is True
    assert info["md5_ok"] is True


def test_nonexistent_file():
    score, info = healthscore.score_file("/no/such/file.flac")
    assert score == 0
    assert info["exists"] is False


def test_non_flac(tmp_path):
    target = tmp_path / "text.txt"
    target.write_text("hello")
    score, info = healthscore.score_file(str(target))
    assert score == 0
    assert info["is_flac"] is False


def test_corrupted_flac(monkeypatch, tmp_path):
    target = tmp_path / "corrupt.flac"
    target.write_bytes(b"broken")

    class BadFlac(Exception):
        pass

    def _broken_probe(_path: Path):
        raise BadFlac("boom")

    monkeypatch.setattr(metadata, "probe_audio", _broken_probe)
    score, info = healthscore.score_file(str(target))
    assert score == 0
    assert info["readable"] is True


def test_cli_order(monkeypatch, capsys):
    paths = ["first.flac", "second.flac", "third.flac"]
    scores: dict[str, tuple[int, dict[str, Any]]] = {
        p: (i, {}) for i, p in enumerate(paths)
    }

    monkeypatch.setattr(healthscore, "score_file", lambda p: scores[p])

    args = type("Args", (), {"paths": paths})
    cli.run_healthscore(args)

    captured = capsys.readouterr().out.strip().splitlines()
    assert captured == [f"{scores[p][0]}\t{p}" for p in paths]
