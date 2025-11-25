from __future__ import annotations

from pathlib import Path

from mutagen.flac import FLAC

from dedupe.health_score import score_flac


TEST_DATA = Path(__file__).parent / "data"


def test_happy_path_score() -> None:
    target = TEST_DATA / "healthy.flac"
    result = score_flac(str(target))

    assert result["health_score"] >= 8.0
    assert result["metrics"]["md5_audio_present"] is True
    assert result["metrics"]["structure"]["prefix_ok"] is True


def test_corrupted_file_scores_zero() -> None:
    target = TEST_DATA / "corrupt.flac"
    result = score_flac(str(target))

    assert result["health_score"] == 0.0
    assert result["metrics"]["mutagen_ok"] is False


def test_missing_fields_reduce_score(monkeypatch, tmp_path: Path) -> None:
    source = TEST_DATA / "healthy.flac"
    temp = tmp_path / "temp.flac"
    temp.write_bytes(source.read_bytes())

    class FakeInfo:
        def __init__(self) -> None:
            self.sample_rate = None
            self.bits_per_sample = None
            self.channels = None
            self.length = 10.0
            self.md5_signature = None

    class FakeFlac:
        def __init__(self, _path: Path) -> None:
            self.info = FakeInfo()
            self.tags: dict[str, list[str]] = {}

    monkeypatch.setattr("dedupe.health_score.FLAC", FakeFlac)

    result = score_flac(str(temp))
    assert result["health_score"] <= 7.0
    assert result["metrics"]["replaygain_present"] is False


def test_replaygain_bonus(tmp_path: Path) -> None:
    tagged = tmp_path / "rg.flac"
    tagged.write_bytes((TEST_DATA / "healthy.flac").read_bytes())

    audio = FLAC(str(tagged))
    audio["replaygain_track_gain"] = "-7.0 dB"
    audio.save()

    result = score_flac(str(tagged))
    assert result["metrics"]["replaygain_present"] is True
    assert result["health_score"] > 8.0


def test_md5_detection() -> None:
    target = TEST_DATA / "healthy.flac"
    result = score_flac(str(target))

    assert result["metrics"]["md5_audio_present"] is True


def test_structural_penalty(monkeypatch, tmp_path: Path) -> None:
    damaged = tmp_path / "bad.flac"
    data = b"BAD!" + (TEST_DATA / "healthy.flac").read_bytes()[4:]
    damaged.write_bytes(data)

    class FakeInfo:
        def __init__(self) -> None:
            self.sample_rate = 44100
            self.bits_per_sample = 16
            self.channels = 2
            self.length = 30.0
            self.md5_signature = None

    class FakeFlac:
        def __init__(self, _path: Path) -> None:
            self.info = FakeInfo()
            self.tags: dict[str, list[str]] = {}

    monkeypatch.setattr("dedupe.health_score.FLAC", FakeFlac)

    result = score_flac(str(damaged))
    assert result["metrics"]["structure"]["prefix_ok"] is False
    assert result["health_score"] < 10.0
