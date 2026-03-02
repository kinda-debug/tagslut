from __future__ import annotations

import csv
from pathlib import Path

import pytest

from tagslut.dj import lexicon
from tagslut.dj.lexicon import LexiconTrack


def test_detect_columns_handles_standard_reordered_and_missing() -> None:
    standard = [{"path": "a.flac", "artist": "A", "title": "T", "bpm": "126"}]
    reordered = [{"Performer": "A", "Track": "T", "File Path": "a.flac", "Tempo": "126"}]
    missing = [{"foo": "x"}]

    cols_standard = lexicon._detect_columns(standard)
    cols_reordered = lexicon._detect_columns(reordered)
    cols_missing = lexicon._detect_columns(missing)

    assert cols_standard["path"] == "path"
    assert cols_standard["artist"] == "artist"
    assert cols_standard["title"] == "title"
    assert cols_reordered["path"] == "File Path"
    assert cols_reordered["artist"] == "Performer"
    assert cols_reordered["title"] == "Track"
    assert cols_missing["path"] is None
    assert cols_missing["artist"] is None


def test_load_track_overrides_skips_comments_invalid_and_short_rows(tmp_path: Path) -> None:
    overrides = tmp_path / "overrides.csv"
    overrides.write_text(
        "\n".join(
            [
                "# comment",
                "",
                "track1.flac,Artist 1,Title 1,safe,reason-a,crate-a",
                "track2.flac,Artist 2,Title 2,unsafe,reason-b,crate-b",
                "track3.flac,Artist 3,Title 3,safe",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    tracks = lexicon.load_track_overrides(overrides)

    assert [t.path for t in tracks] == ["track1.flac", "track3.flac"]
    assert tracks[1].crate == ""


def test_enrich_prefers_path_then_artist_title_match() -> None:
    columns = {
        "path": "path", "artist": "artist", "title": "title",
        "bpm": "bpm", "key": "key", "genre": "genre", "duration": "duration",
    }
    rows = [
        {
            "path": "known.flac", "artist": "X", "title": "Y",
            "bpm": "124", "key": "8A", "genre": "Techno", "duration": "372",
        },
        {
            "path": "other.flac", "artist": "Artist Name", "title": "Track Name",
            "bpm": "126", "key": "9B", "genre": "House", "duration": "401",
        },
    ]
    index = lexicon._scan_index(rows, columns)

    by_path = LexiconTrack(
        path="known.flac", artist="Nope", title="Nope", verdict="safe", reason="", crate=""
    )
    by_artist_title = LexiconTrack(
        path="", artist="  artist  name ", title="track   name", verdict="safe", reason="", crate=""
    )

    lexicon._enrich(by_path, index, columns)
    lexicon._enrich(by_artist_title, index, columns)

    assert by_path.bpm == 124.0
    assert by_path.key == "8A"
    assert by_artist_title.bpm == 126.0
    assert by_artist_title.genre == "House"


def test_normalize_trims_whitespace_and_case() -> None:
    assert lexicon._normalize("  HeLLo   WoRLD  ") == "hello world"


def test_load_scan_report_reads_temp_csv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = tmp_path / "dj_scan_report_20260301_120000.csv"
    report.write_text("path,artist,title,bpm\nx.flac,A,T,125\n", encoding="utf-8")
    monkeypatch.setattr(lexicon, "_latest_scan_report", lambda: report)

    rows, columns = lexicon.load_scan_report()

    assert len(rows) == 1
    assert rows[0]["path"] == "x.flac"
    assert columns["bpm"] == "bpm"


def test_load_scan_report_missing_and_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing_file = tmp_path / "does-not-exist.csv"
    monkeypatch.setattr(lexicon, "_latest_scan_report", lambda: missing_file)
    with pytest.raises(FileNotFoundError):
        lexicon.load_scan_report()

    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setattr(lexicon, "_latest_scan_report", lambda: empty)
    rows, columns = lexicon.load_scan_report()
    assert rows == []
    assert columns["path"] is None


def test_load_scan_report_malformed_csv_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    malformed = tmp_path / "bad.csv"
    malformed.write_text("path,artist,title\na.flac,Artist,Title,EXTRA\n", encoding="utf-8")
    monkeypatch.setattr(lexicon, "_latest_scan_report", lambda: malformed)

    with pytest.raises(csv.Error):
        lexicon.load_scan_report()
