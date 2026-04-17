from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tagslut.core.flac_scan_prep import _convert_to_flac
from tagslut.core.flac_scan_prep import prepare_flac_scan_input


def test_convert_to_flac_returns_verify_failure_without_name_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "input.wav"
    dest = tmp_path / "output.flac"
    source.write_bytes(b"wav")
    dest.write_bytes(b"bad flac")

    monkeypatch.setattr("tagslut.core.flac_scan_prep.shutil.which", lambda name: "/usr/bin/tool")

    def fake_run(cmd: list[str], **kwargs: object) -> SimpleNamespace:
        if cmd[0] == "ffmpeg":
            return SimpleNamespace(returncode=0, stderr="", stdout="")
        if cmd[0] == "flac":
            return SimpleNamespace(returncode=1, stderr="verify failed", stdout="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("tagslut.core.flac_scan_prep.subprocess.run", fake_run)

    converted, error = _convert_to_flac(source, dest)

    assert converted is False
    assert error == "verify failed"
    assert not dest.exists()


def test_prepare_flac_scan_input_allows_tidal_aac_m4a(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.m4a"
    source.write_bytes(b"m4a")

    monkeypatch.setattr(
        "tagslut.core.flac_scan_prep._probe_audio_stream",
        lambda _path: {
            "codec_name": "aac",
            "sample_rate": "44100",
            "bit_rate": "256000",
            "bits_per_sample": "16",
        },
    )

    def fake_convert_to_flac(_source: Path, dest: Path) -> tuple[bool, str | None]:
        dest.write_bytes(b"flac")
        return True, None

    monkeypatch.setattr("tagslut.core.flac_scan_prep._convert_to_flac", fake_convert_to_flac)
    monkeypatch.setattr("tagslut.core.flac_scan_prep.shutil.which", lambda _name: "/usr/bin/tool")

    prepared = prepare_flac_scan_input(source, persist=False)

    assert prepared.skip_reason is None
    assert prepared.converted is True
    assert prepared.scan_path is not None
    assert prepared.codec_name == "aac"
    assert prepared.classification == "provisional_lossy"
    assert prepared.bitrate_kbps == 256


def test_prepare_flac_scan_input_blocks_tidal_aac_m4a_when_sample_rate_too_low(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.m4a"
    source.write_bytes(b"m4a")

    monkeypatch.setattr(
        "tagslut.core.flac_scan_prep._probe_audio_stream",
        lambda _path: {
            "codec_name": "aac",
            "sample_rate": "22050",
            "bit_rate": "256000",
            "bits_per_sample": "16",
        },
    )
    monkeypatch.setattr("tagslut.core.flac_scan_prep.shutil.which", lambda _name: "/usr/bin/tool")

    prepared = prepare_flac_scan_input(source, persist=False)

    assert prepared.converted is False
    assert prepared.scan_path is None
    assert prepared.skip_reason == "sample_rate_too_low"


def test_prepare_flac_scan_input_allows_alac_m4a(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.m4a"
    source.write_bytes(b"m4a")

    monkeypatch.setattr(
        "tagslut.core.flac_scan_prep._probe_audio_stream",
        lambda _path: {
            "codec_name": "alac",
            "sample_rate": "44100",
            "bit_rate": "900000",
            "bits_per_sample": "24",
        },
    )

    def fake_convert_to_flac(_source: Path, dest: Path) -> tuple[bool, str | None]:
        dest.write_bytes(b"flac")
        return True, None

    monkeypatch.setattr("tagslut.core.flac_scan_prep._convert_to_flac", fake_convert_to_flac)
    monkeypatch.setattr("tagslut.core.flac_scan_prep.shutil.which", lambda _name: "/usr/bin/tool")

    prepared = prepare_flac_scan_input(source, persist=False)

    assert prepared.skip_reason is None
    assert prepared.converted is True
    assert prepared.scan_path is not None
    assert prepared.codec_name == "alac"
    assert prepared.classification == "canonical_lossless"


def test_prepare_flac_scan_input_accepts_high_quality_aac_extension(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.aac"
    source.write_bytes(b"aac")

    monkeypatch.setattr(
        "tagslut.core.flac_scan_prep._probe_audio_stream",
        lambda _path: {
            "codec_name": "aac",
            "sample_rate": "44100",
            "bit_rate": "256000",
            "bits_per_sample": "16",
        },
    )
    monkeypatch.setattr("tagslut.core.flac_scan_prep.shutil.which", lambda _name: "/usr/bin/tool")

    def fake_convert_to_flac(_source: Path, dest: Path) -> tuple[bool, str | None]:
        dest.write_bytes(b"flac")
        return True, None

    monkeypatch.setattr("tagslut.core.flac_scan_prep._convert_to_flac", fake_convert_to_flac)

    prepared = prepare_flac_scan_input(source, persist=False)

    assert prepared.skip_reason is None
    assert prepared.converted is True
    assert prepared.scan_path is not None
    assert prepared.classification == "provisional_lossy"


def test_prepare_flac_scan_input_blocks_low_quality_mp3_extension(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.mp3"
    source.write_bytes(b"mp3")

    monkeypatch.setattr(
        "tagslut.core.flac_scan_prep._probe_audio_stream",
        lambda _path: {
            "codec_name": "mp3",
            "sample_rate": "44100",
            "bit_rate": "128000",
            "bits_per_sample": "16",
        },
    )

    prepared = prepare_flac_scan_input(source, persist=False)

    assert prepared.skip_reason == "lossy_below_threshold"
    assert prepared.converted is False
    assert prepared.scan_path is None


def test_prepare_flac_scan_input_accepts_high_quality_mp3_extension(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "track.mp3"
    source.write_bytes(b"mp3")

    monkeypatch.setattr(
        "tagslut.core.flac_scan_prep._probe_audio_stream",
        lambda _path: {
            "codec_name": "mp3",
            "sample_rate": "44100",
            "bit_rate": "320000",
            "bits_per_sample": "16",
        },
    )
    monkeypatch.setattr("tagslut.core.flac_scan_prep.shutil.which", lambda _name: "/usr/bin/tool")

    def fake_convert_to_flac(_source: Path, dest: Path) -> tuple[bool, str | None]:
        dest.write_bytes(b"flac")
        return True, None

    monkeypatch.setattr("tagslut.core.flac_scan_prep._convert_to_flac", fake_convert_to_flac)

    prepared = prepare_flac_scan_input(source, persist=False)

    assert prepared.skip_reason is None
    assert prepared.converted is True
    assert prepared.scan_path is not None
    assert prepared.classification == "provisional_lossy"
