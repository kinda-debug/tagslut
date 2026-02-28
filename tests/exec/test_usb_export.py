from pathlib import Path

import pytest

from tagslut.exec.usb_export import copy_to_usb, scan_source, write_manifest


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    d = tmp_path / "source"
    d.mkdir()
    (d / "track1.mp3").write_bytes(b"mp3data")
    (d / "track2.flac").write_bytes(b"flacdata")
    (d / "cover.jpg").write_bytes(b"imgdata")  # should be ignored
    return d


def test_scan_source_finds_audio_only(source_dir: Path):
    tracks = scan_source(source_dir)
    names = [t.name for t in tracks]
    assert "track1.mp3" in names
    assert "track2.flac" in names
    assert "cover.jpg" not in names


def test_copy_to_usb_dry_run_no_write(tmp_path: Path, source_dir: Path):
    tracks = scan_source(source_dir)
    usb = tmp_path / "usb"
    usb.mkdir()
    copied = copy_to_usb(tracks, usb, "Test Crate", dry_run=True)
    assert not (usb / "MUSIC" / "Test Crate").exists()
    assert len(copied) == 2


def test_copy_to_usb_writes_files(tmp_path: Path, source_dir: Path):
    tracks = scan_source(source_dir)
    usb = tmp_path / "usb"
    usb.mkdir()
    copied = copy_to_usb(tracks, usb, "Test Crate", dry_run=False)
    assert len(copied) == 2
    for dest in copied:
        assert dest.exists()


def test_write_manifest(tmp_path: Path, source_dir: Path):
    tracks = scan_source(source_dir)
    usb = tmp_path / "usb"
    usb.mkdir()
    manifest = write_manifest(tracks, usb, "Test Crate")
    assert manifest.exists()
    content = manifest.read_text()
    assert "Test Crate" in content
    assert "track1.mp3" in content
