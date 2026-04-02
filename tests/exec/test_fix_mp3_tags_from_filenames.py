from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from tagslut.exec import fix_mp3_tags_from_filenames as module


class _Frame:
    def __init__(self, name: str, text=None):
        self.name = name
        self.text = text or []


class _FakeID3:
    def __init__(self, path: str | None = None, preset: Dict[str, _Frame] | None = None):
        self.path = path
        self.frames: Dict[str, _Frame] = preset or {}
        self.saved = False
        self.save_args = None

    def get(self, key: str, default=None):
        return self.frames.get(key, default)

    def setall(self, key: str, frames):
        self.frames[key] = frames[0]

    def delall(self, key: str):
        self.frames.pop(key, None)

    def save(self, path: str, v2_version: int | None = None):
        self.saved = True
        self.save_args = (path, v2_version)


class _StubID3Module:
    class ID3NoHeaderError(Exception):
        pass

    def __init__(self, mapping: Dict[str, _FakeID3] | None = None, raise_for: set[str] | None = None):
        self.mapping = mapping or {}
        self.raise_for = raise_for or set()
        self.created: list[str] = []
        self.TPE1 = self._frame("TPE1")
        self.TIT2 = self._frame("TIT2")
        self.TALB = self._frame("TALB")
        self.TDRC = self._frame("TDRC")
        self.TRCK = self._frame("TRCK")

    @staticmethod
    def _frame(name: str):
        return lambda encoding=3, text=None: _Frame(name, text)

    def ID3(self, path: str | None = None):
        if path in self.raise_for:
            raise self.ID3NoHeaderError("no header")
        if path not in self.mapping:
            self.mapping[path] = _FakeID3(path)
        self.created.append(path)
        return self.mapping[path]


def _install_stub(monkeypatch, mapping: Dict[str, _FakeID3] | None = None):
    stub = _StubID3Module(mapping=mapping)
    monkeypatch.setattr(module, "id3", stub)
    return stub


def test_parse_schema_a():
    parsed = module.parse_filename("Kölsch – (2025) KINEMA – 02 Nacht Und Träume")

    assert parsed is not None
    assert parsed.schema == "A"
    assert parsed.artist == "Kölsch"
    assert parsed.album == "KINEMA"
    assert parsed.year == "2025"
    assert parsed.track == "02"
    assert parsed.title == "Nacht Und Träume"


def test_parse_schema_b_strips_bpm_suffix():
    parsed = module.parse_filename("New Order - Blue Monday (2011 Total Version) (130)")

    assert parsed is not None
    assert parsed.schema == "B"
    assert parsed.artist == "New Order"
    assert parsed.title == "Blue Monday (2011 Total Version)"
    assert parsed.album is None
    assert parsed.year is None
    assert parsed.track is None


def test_skip_when_artist_and_title_already_present(monkeypatch, tmp_path: Path):
    mp3_path = tmp_path / "Artist – (2024) Album – 01 Title.mp3"
    mp3_path.touch()

    preset_frames = {
        "TPE1": _Frame("TPE1", ["Existing Artist"]),
        "TIT2": _Frame("TIT2", ["Existing Title"]),
    }
    stub = _install_stub(monkeypatch, mapping={str(mp3_path): _FakeID3(str(mp3_path), preset_frames)})

    stats = module.Stats()
    module.process_path(mp3_path, execute=True, verbose=False, stats=stats)

    fake = stub.mapping[str(mp3_path)]
    assert stats.already_tagged == 1
    assert not fake.saved


def test_execute_writes_schema_a_frames(monkeypatch, tmp_path: Path):
    mp3_path = tmp_path / "Artist – (2024) Album – 01 Title.mp3"
    mp3_path.touch()
    stub = _install_stub(monkeypatch)

    stats = module.Stats()
    module.process_path(mp3_path, execute=True, verbose=False, stats=stats)

    fake = stub.mapping[str(mp3_path)]
    assert stats.schema_a_fixed == 1
    assert fake.saved
    assert fake.frames["TPE1"].text == ["Artist"]
    assert fake.frames["TIT2"].text == ["Title"]
    assert fake.frames["TALB"].text == ["Album"]
    assert fake.frames["TDRC"].text == ["2024"]
    assert fake.frames["TRCK"].text == ["01"]


def test_dry_run_does_not_save(monkeypatch, tmp_path: Path):
    mp3_path = tmp_path / "Artist – (2024) Album – 01 Title.mp3"
    mp3_path.touch()
    stub = _install_stub(monkeypatch)

    stats = module.Stats()
    module.process_path(mp3_path, execute=False, verbose=False, stats=stats)

    fake = stub.mapping[str(mp3_path)]
    assert stats.schema_a_fixed == 1
    assert not fake.saved
    assert fake.frames == {}


def test_unparseable_filename_is_counted(monkeypatch, tmp_path: Path):
    mp3_path = tmp_path / "untagged.mp3"
    mp3_path.touch()
    stub = _install_stub(monkeypatch)

    stats = module.Stats()
    module.process_path(mp3_path, execute=True, verbose=False, stats=stats)

    assert stats.unparseable == 1
    assert not stub.mapping[str(mp3_path)].saved


def test_schema_b_counts_and_writes(monkeypatch, tmp_path: Path):
    mp3_path = tmp_path / "Juana Molina - intringulado (128).mp3"
    mp3_path.touch()
    stub = _install_stub(monkeypatch)

    stats = module.Stats()
    module.process_path(mp3_path, execute=True, verbose=False, stats=stats)

    fake = stub.mapping[str(mp3_path)]
    assert stats.schema_b_fixed == 1
    assert fake.saved
    assert fake.frames["TPE1"].text == ["Juana Molina"]
    assert fake.frames["TIT2"].text == ["intringulado"]
    assert "TALB" not in fake.frames
    assert "TDRC" not in fake.frames
    assert "TRCK" not in fake.frames
