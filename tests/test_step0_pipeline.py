"""Tests for Step-0 ingestion helpers."""

from __future__ import annotations

from dedupe.step0 import (
    IntegrityResult,
    ScannedFile,
    build_canonical_path,
    choose_canonical,
    classify_integrity,
)


def _integrity(status: str) -> IntegrityResult:
    return IntegrityResult(status=status, stderr_excerpt="", return_code=0)


def test_classify_integrity_detects_signatures() -> None:
    result = classify_integrity("ERROR: LOST_SYNC at 0x00", 1)

    assert result.status == "fail"
    assert "LOST_SYNC" in result.stderr_excerpt


def test_classify_integrity_passes_clean_run() -> None:
    result = classify_integrity("", 0)

    assert result.status == "pass"


def test_build_canonical_path_sanitizes_components() -> None:
    tags = {
        "artist": "AC/DC",
        "album": "Live/Set",
        "title": "Track: 1",
        "date": "2020-01-01",
        "tracknumber": "1/12",
        "discnumber": "2/2",
    }

    path = build_canonical_path(tags)

    assert path == "AC_DC/(2020) Live_Set/2-01. Track_ 1.flac"


def test_choose_canonical_prefers_higher_bit_depth() -> None:
    candidates = [
        ScannedFile(
            path="a.flac",
            content_hash="aaa",
            streaminfo_md5="111",
            duration=200.0,
            sample_rate=44100,
            bit_depth=16,
            channels=2,
            tags={"artist": "Artist", "title": "Track"},
            integrity=_integrity("pass"),
        ),
        ScannedFile(
            path="b.flac",
            content_hash="bbb",
            streaminfo_md5="111",
            duration=200.0,
            sample_rate=44100,
            bit_depth=24,
            channels=2,
            tags={"artist": "Artist", "title": "Track"},
            integrity=_integrity("pass"),
        ),
    ]

    winner = choose_canonical(candidates)

    assert winner is not None
    assert winner.content_hash == "bbb"
