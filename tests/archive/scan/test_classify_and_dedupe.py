import sqlite3
from pathlib import Path

import pytest

from tagslut.scan.classify import classify_primary_status, compute_identity_confidence
from tagslut.scan.dedupe import FileCandidate, elect_canonical, mark_format_duplicates
from tagslut.storage.schema import init_db


def test_confidence_full_score():
    raw = {
        "ARTIST": ["Test Artist"],
        "TITLE": ["Test Title"],
        "ALBUM": ["Test Album"],
        "DATE": ["2020"],
        "BPM": ["128"],
        "INITIALKEY": ["8A"],
    }
    score = compute_identity_confidence(raw, ["USABC1234567"], duration_delta=0.5)
    assert score >= 70


def test_confidence_multi_isrc_no_bonus():
    raw = {"ARTIST": ["A"], "TITLE": ["T"]}
    score_single = compute_identity_confidence(raw, ["USABC1234567"], duration_delta=0.5)
    score_multi = compute_identity_confidence(
        raw, ["USABC1234567", "GBXYZ9876543"], duration_delta=0.5)
    assert score_single > score_multi


def test_classify_corrupt_on_decode_errors():
    status, _ = classify_primary_status(False, ["Invalid data"], None)
    assert status == "CORRUPT"


def test_classify_truncated():
    status, _ = classify_primary_status(False, [], -30.0)
    assert status == "TRUNCATED"


def test_classify_extended():
    status, _ = classify_primary_status(False, [], 60.0)
    assert status == "EXTENDED"


def test_classify_clean():
    status, _flags = classify_primary_status(False, [], 0.5)
    assert status == "CLEAN"


@pytest.fixture
def db_with_duplicates():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    for i, (qr, conf) in enumerate([(4, 70), (2, 85)]):
        conn.execute(
            """
            INSERT INTO files (path, checksum, duration, bit_depth, sample_rate, bitrate,
                metadata_json, quality_rank, identity_confidence, canonical_isrc, size)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"/music/track{i}.flac",
                f"checksum{i}",
                240.0,
                16,
                44100,
                0,
                "{}",
                qr,
                conf,
                "USABC1234567",
                10000000 + i,
            ),
        )
    conn.commit()
    yield conn
    conn.close()


def test_mark_format_duplicates(db_with_duplicates):
    marked = mark_format_duplicates(db_with_duplicates)
    assert marked == 1
    row = db_with_duplicates.execute(
        "SELECT scan_status, duplicate_of_checksum FROM files WHERE quality_rank = 4"
    ).fetchone()
    assert row["scan_status"] == "FORMAT_DUPLICATE"
    assert row["duplicate_of_checksum"] == "checksum1"


def test_elect_canonical_prefers_better_quality():
    candidates = [
        FileCandidate(Path("/a.flac"), "c1", quality_rank=4, identity_confidence=80, size_bytes=10),
        FileCandidate(Path("/b.flac"), "c2", quality_rank=2, identity_confidence=70, size_bytes=8),
    ]
    assert elect_canonical(candidates) == "c2"
