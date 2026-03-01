from __future__ import annotations

from tagslut.metadata.beatport_normalize import (
    BeatportTrack,
    beatport_track_to_dict,
    extract_beatport_track_info,
    normalize_beatport_track,
)


def _sample_payload() -> dict:
    return {
        "id": 12345,
        "name": "Test Cut",
        "mix_name": "Extended Mix",
        "artists": [{"name": "Artist A"}, {"name": "Artist B"}],
        "remixers": ["Remixer X"],
        "bpm": "128",
        "key": {"name": "A minor", "camelot_number": "8A"},
        "genre": {"name": "Techno"},
        "sub_genre": {"name": "Peak Time / Driving"},
        "length_ms": 390000,
        "isrc": "USRC17607839",
        "release": {
            "id": 999,
            "name": "Warehouse EP",
            "label": {"name": "Toolroom"},
            "catalog_number": "TR-001",
            "image": {"uri": "https://img/cover.jpg"},
        },
        "sample_url": "https://sample",
        "publish_date": "2025-04-20",
    }


def test_normalize_beatport_track_populates_core_fields() -> None:
    track = normalize_beatport_track(_sample_payload())

    assert track.service == "beatport"
    assert track.service_track_id == "12345"
    assert track.title == "Test Cut"
    assert track.artist == "Artist A, Artist B"
    assert track.duration_s == 390.0
    assert track.bpm == 128.0
    assert track.match_confidence == "exact"


def test_normalize_beatport_track_handles_non_dict_input() -> None:
    track = normalize_beatport_track([])  # type: ignore[arg-type]

    assert isinstance(track, BeatportTrack)
    assert track.service_track_id is None
    assert track.match_confidence == "none"


def test_normalize_beatport_track_uses_genres_array_fallback() -> None:
    payload = {
        "id": 7,
        "name": "Fallback",
        "artists": ["Solo"],
        "genres": [{"name": "House"}],
        "sub_genres": ["Deep House"],
        "preview": {"sample_url": "https://preview"},
    }

    track = normalize_beatport_track(payload)

    assert track.genre == "House"
    assert track.subgenre == "Deep House"
    assert track.sample_url == "https://preview"


def test_extract_beatport_track_info_returns_expected_tuple() -> None:
    info = extract_beatport_track_info(_sample_payload())

    assert info == (
        "12345",
        128.0,
        "A minor",
        "Techno",
        390.0,
        "USRC17607839",
        "Toolroom",
    )


def test_beatport_track_to_dict_round_trip_keys() -> None:
    track = normalize_beatport_track(_sample_payload())
    payload = beatport_track_to_dict(track)

    assert payload["track_id"] == "12345"
    assert payload["title"] == "Test Cut"
    assert payload["artists"] == ["Artist A", "Artist B"]
    assert payload["match_confidence"] == "exact"


def test_normalize_beatport_track_parses_string_key_field() -> None:
    payload = {
        "id": 88,
        "name": "String Key",
        "artists": ["X"],
        "key": "F Minor",
    }

    track = normalize_beatport_track(payload)
    assert track.key == "F Minor"
    assert track.key_camelot is None
