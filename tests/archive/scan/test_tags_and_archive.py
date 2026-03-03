import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tagslut.scan.archive import upsert_archive
from tagslut.scan.tags import (
    compute_quality_rank_from_technical,
    compute_sha256,
    extract_isrc_from_tags,
    read_raw_tags,
    read_technical,
)
from tagslut.storage.schema import init_db


@pytest.fixture
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    yield conn
    conn.close()


def test_compute_sha256(tmp_path: Path):
    file_path = tmp_path / "test.flac"
    file_path.write_bytes(b"hello")
    checksum = compute_sha256(file_path)
    assert len(checksum) == 64
    assert checksum == compute_sha256(file_path)


def test_read_raw_tags_uses_mutagen_file_mock():
    fake = SimpleNamespace(tags={"ISRC": ["USABC1234567"], "TITLE": "Track"})
    with patch("tagslut.scan.tags.MutagenFile", return_value=fake):
        raw = read_raw_tags(Path("/fake/track.flac"))
    assert raw["ISRC"] == ["USABC1234567"]
    assert raw["TITLE"] == ["Track"]


def test_read_technical_uses_mutagen_file_mock():
    info = SimpleNamespace(length=240.0, bits_per_sample=24,
                           sample_rate=96000, bitrate=0, channels=2)
    fake = SimpleNamespace(info=info)
    with patch("tagslut.scan.tags.MutagenFile", return_value=fake):
        technical = read_technical(Path("/fake/track.flac"))
    assert technical["duration_tagged"] == 240.0
    assert technical["bit_depth"] == 24


def test_extract_isrc_from_tags_single():
    raw = {"ISRC": ["USABC1234567"]}
    assert extract_isrc_from_tags(raw) == ["USABC1234567"]


def test_extract_isrc_from_tags_multi_value():
    raw = {"TSRC": ["USABC1234567", "GBXYZ9876543"]}
    result = extract_isrc_from_tags(raw)
    assert len(result) == 2


def test_extract_isrc_from_tags_empty():
    raw = {"TITLE": ["Some Track"], "ARTIST": ["Someone"]}
    assert extract_isrc_from_tags(raw) == []


def test_quality_rank_from_technical():
    tech = {"bit_depth": 24, "sample_rate": 96000, "bitrate": 0}
    assert compute_quality_rank_from_technical(tech) == 2


def test_archive_is_append_only(mem_db, tmp_path: Path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"data")
    original_tags = {"TITLE": ["Original"]}

    upsert_archive(
        mem_db,
        checksum="abc123",
        path=path,
        raw_tags=original_tags,
        technical={},
        durations={},
        isrc_candidates=[],
        identity_confidence=70,
        quality_rank=4,
    )
    upsert_archive(
        mem_db,
        checksum="abc123",
        path=path,
        raw_tags={"TITLE": ["Modified"]},
        technical={},
        durations={},
        isrc_candidates=[],
        identity_confidence=70,
        quality_rank=4,
    )
    row = mem_db.execute(
        "SELECT raw_tags_json FROM file_metadata_archive WHERE checksum = 'abc123'"
    ).fetchone()
    stored = json.loads(row["raw_tags_json"])
    assert stored["TITLE"] == ["Original"]


def test_path_history_updated_on_second_scan(mem_db, tmp_path: Path):
    path = tmp_path / "track.flac"
    path.write_bytes(b"data")
    for _ in range(2):
        upsert_archive(
            mem_db,
            checksum="abc123",
            path=path,
            raw_tags={},
            technical={},
            durations={},
            isrc_candidates=[],
            identity_confidence=50,
            quality_rank=None,
        )
    rows = mem_db.execute(
        "SELECT * FROM file_path_history WHERE checksum = 'abc123'"
    ).fetchall()
    assert len(rows) == 1
