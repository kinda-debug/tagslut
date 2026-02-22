from __future__ import annotations

from tagslut.dj.curation import DjCurationConfig, filter_candidates


def test_duration_filter():
    config = DjCurationConfig(duration_min=180, duration_max=720)
    candidates = [
        {"artist": "A", "duration_sec": 100, "genre": "house"},
        {"artist": "B", "duration_sec": 200, "genre": "house"},
        {"artist": "C", "duration_sec": 900, "genre": "house"},
    ]
    result = filter_candidates(candidates, config)
    assert len(result.passed) == 1
    assert result.passed[0]["artist"] == "B"
    assert len(result.rejected_duration) == 2


def test_blocklist():
    config = DjCurationConfig(artist_blocklist=frozenset({"bad artist"}))
    candidates = [
        {"artist": "Bad Artist", "duration_sec": 200, "genre": "house"},
        {"artist": "Good Artist", "duration_sec": 200, "genre": "house"},
    ]
    result = filter_candidates(candidates, config)
    assert len(result.rejected_blocklist) == 1
    assert result.rejected_blocklist[0]["artist"] == "Bad Artist"
    assert len(result.passed) == 1


def test_reviewlist_flags_but_passes():
    config = DjCurationConfig(artist_reviewlist=frozenset({"borderline"}))
    candidates = [
        {"artist": "Borderline", "duration_sec": 200, "genre": "house"},
    ]
    result = filter_candidates(candidates, config)
    assert len(result.passed) == 1
    assert len(result.flagged_reviewlist) == 1


def test_genre_filter():
    config = DjCurationConfig(genre_filters=("ambient", "downtempo"))
    candidates = [
        {"artist": "A", "duration_sec": 200, "genre": "Ambient"},
        {"artist": "B", "duration_sec": 200, "genre": "Tech House"},
    ]
    result = filter_candidates(candidates, config)
    assert len(result.rejected_genre) == 1
    assert result.rejected_genre[0]["artist"] == "A"
    assert len(result.passed) == 1
