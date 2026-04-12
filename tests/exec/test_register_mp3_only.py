from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from tagslut.exec import register_mp3_only as module


class _Frame:
    def __init__(self, text: Optional[List[str]] = None):
        self.text = text or []


class _FakeID3:
    def __init__(self, frames: Optional[Dict[str, _Frame]] = None):
        self.frames = frames or {}

    def get(self, key: str, default=None):
        return self.frames.get(key, default)


class _StubID3Module:
    class ID3NoHeaderError(Exception):
        pass

    def __init__(self, mapping: Optional[Dict[str, _FakeID3]] = None):
        self.mapping = mapping or {}

    def ID3(self, path: str):
        if path not in self.mapping:
            self.mapping[path] = _FakeID3()
        return self.mapping[path]


class _FakeInfo:
    def __init__(self, length: Optional[int]):
        self.length = length


class _StubMP3Module:
    def __init__(self, durations: Optional[Dict[str, Optional[int]]] = None):
        self.durations = durations or {}

    def MP3(self, path: str):
        length = self.durations.get(path)
        obj = type("_Audio", (), {})()
        obj.info = _FakeInfo(length)
        return obj


def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "files.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE files (
            path TEXT PRIMARY KEY,
            zone TEXT,
            download_source TEXT,
            flac_ok INTEGER,
            duration INTEGER,
            metadata_json TEXT,
            canonical_isrc TEXT,
            ingestion_method TEXT,
            ingestion_source TEXT,
            ingestion_confidence TEXT
        )
        """
    )
    conn.commit()
    conn.close()
    return db


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return _make_db(tmp_path)


def _install_stubs(monkeypatch, mapping: Optional[Dict[str, _FakeID3]] = None, durations: Optional[Dict[str, Optional[int]]] = None):
    id3_stub = _StubID3Module(mapping=mapping)
    mp3_stub = _StubMP3Module(durations=durations)
    monkeypatch.setattr(module, "id3", id3_stub)
    monkeypatch.setattr(module, "mp3", mp3_stub)
    return id3_stub, mp3_stub


def test_inserts_with_full_tags(monkeypatch, tmp_path: Path, db_path: Path):
    mp3_path = tmp_path / "Artist - Title.mp3"
    mp3_path.touch()

    frames = {
        "TPE1": _Frame(["Artist"]),
        "TIT2": _Frame(["Title"]),
        "TALB": _Frame(["Album"]),
        "TDRC": _Frame(["2024"]),
        "TRCK": _Frame(["01"]),
        "TSRC": _Frame(["ABCD12345678"]),
        "TBPM": _Frame(["128"]),
        "TKEY": _Frame(["8A"]),
        "TCON": _Frame(["House"]),
        "TPUB": _Frame(["Label"]),
    }
    _install_stubs(monkeypatch, mapping={str(mp3_path): _FakeID3(frames)}, durations={str(mp3_path): 321})

    stats = module.register_mp3_only(
        root=tmp_path,
        db_path=db_path,
        source="legacy_mp3",
        zone="accepted",
        execute=True,
        verbose=False,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT * FROM files WHERE path = ?", (str(mp3_path.resolve()),)).fetchone()
    conn.close()

    assert stats.inserted == 1
    assert row is not None
    metadata = json.loads(row[5])
    assert metadata["artist"] == "Artist"
    assert metadata["title"] == "Title"
    assert metadata["album"] == "Album"
    assert metadata["bpm"] == "128"
    assert row[6] == "ABCD12345678"
    assert row[4] == 321


def test_parses_from_filename_when_tags_missing(monkeypatch, tmp_path: Path, db_path: Path):
    mp3_path = tmp_path / "Artist – (2024) Album – 07 Track.mp3"
    mp3_path.touch()

    _install_stubs(monkeypatch, mapping={str(mp3_path): _FakeID3({})}, durations={str(mp3_path): 200})

    stats = module.register_mp3_only(
        root=tmp_path,
        db_path=db_path,
        source="legacy_mp3",
        zone="accepted",
        execute=True,
        verbose=False,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT metadata_json FROM files WHERE path = ?", (str(mp3_path.resolve()),)).fetchone()
    conn.close()

    assert stats.inserted == 1
    metadata = json.loads(row[0])
    assert metadata["artist"] == "Artist"
    assert metadata["title"] == "Track"
    assert metadata["album"] == "Album"
    assert metadata["date"] == "2024"
    assert metadata["tracknumber"] == "07"


def test_extracts_isrc_from_filename(monkeypatch, tmp_path: Path, db_path: Path):
    mp3_path = tmp_path / "Song [GBAYE0000817].mp3"
    mp3_path.touch()

    frames = {
        "TPE1": _Frame(["Artist"]),
        "TIT2": _Frame(["Song"]),
    }
    _install_stubs(monkeypatch, mapping={str(mp3_path): _FakeID3(frames)}, durations={str(mp3_path): 123})

    module.register_mp3_only(
        root=tmp_path,
        db_path=db_path,
        source="legacy_mp3",
        zone="accepted",
        execute=True,
        verbose=False,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT canonical_isrc FROM files WHERE path = ?", (str(mp3_path.resolve()),)).fetchone()
    conn.close()

    assert row is not None
    assert row[0] == "GBAYE0000817"


def test_skips_existing_path(monkeypatch, tmp_path: Path, db_path: Path):
    mp3_path = tmp_path / "Existing.mp3"
    mp3_path.touch()

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO files (path) VALUES (?)",
        (str(mp3_path.resolve()),),
    )
    conn.commit()
    conn.close()

    _install_stubs(monkeypatch, mapping={str(mp3_path): _FakeID3({})}, durations={str(mp3_path): None})

    stats = module.register_mp3_only(
        root=tmp_path,
        db_path=db_path,
        source="legacy_mp3",
        zone="accepted",
        execute=True,
        verbose=False,
    )

    assert stats.skipped_existing == 1


def test_dry_run_does_not_insert(monkeypatch, tmp_path: Path, db_path: Path):
    mp3_path = tmp_path / "Dry.mp3"
    mp3_path.touch()
    _install_stubs(monkeypatch, mapping={str(mp3_path): _FakeID3({})}, durations={str(mp3_path): 50})

    stats = module.register_mp3_only(
        root=tmp_path,
        db_path=db_path,
        source="legacy_mp3",
        zone="accepted",
        execute=False,
        verbose=False,
    )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT COUNT(*) FROM files").fetchone()
    conn.close()

    assert stats.inserted == 0
    assert row[0] == 0
