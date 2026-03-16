from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from tagslut.metadata.enricher import Enricher
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.metadata.providers.tidal import TidalProvider


class DummyResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


def _mock_tidal_playlist_export(monkeypatch, track_payload: dict[str, Any]) -> None:
    def fake_make_request(self, method: str, url: str, params=None, **kwargs):  # type: ignore[no-untyped-def]
        return DummyResponse({"items": [{"item": track_payload}]})

    monkeypatch.setattr(TidalProvider, "_make_request", fake_make_request)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _provider_track_from_raw(raw: dict[str, Any]) -> ProviderTrack:
    release = raw.get("release", {})
    return ProviderTrack(
        service="beatport",
        service_track_id=str(raw["id"]),
        title=raw.get("name"),
        artist=", ".join(artist["name"] for artist in raw.get("artists", [])),
        album=release.get("name"),
        album_id=str(release["id"]) if release.get("id") is not None else None,
        isrc=raw.get("isrc"),
        url=raw.get("url"),
        bpm=raw.get("bpm"),
        key=(raw.get("key") or {}).get("name"),
        genre=(raw.get("genre") or {}).get("name"),
        sub_genre=(raw.get("sub_genre") or {}).get("name"),
        label=((release.get("label") or {}).get("name")),
        catalog_number=release.get("catalog_number"),
        release_date=release.get("new_release_date"),
        match_confidence=MatchConfidence.EXACT,
        raw=raw,
    )


def test_tidal_seed_to_beatport_enrichment_happy_path(tmp_path: Path, monkeypatch) -> None:
    _mock_tidal_playlist_export(
        monkeypatch,
        {
            "id": "tidal-track-1",
            "title": "High Street",
            "artists": [{"name": "Charlotte de Witte"}],
            "isrc": "BE4JP2300002",
            "url": "https://tidal.com/browse/track/tidal-track-1",
        },
    )

    beatport_raw = {
        "id": 17606729,
        "name": "High Street",
        "artists": [{"name": "Charlotte de Witte"}],
        "isrc": "BE4JP2300002",
        "bpm": 138,
        "key": {"name": "C Minor"},
        "genre": {"name": "Techno (Peak Time / Driving)"},
        "sub_genre": {"name": "Peak Time / Driving"},
        "url": "https://www.beatport.com/track/high-street/17606729",
        "release": {
            "id": 4089968,
            "name": "High Street",
            "label": {"name": "KNTXT"},
            "catalog_number": "KNTXT021S",
            "upc": "123456789012",
            "new_release_date": "2023-04-21",
        },
    }

    monkeypatch.setattr(
        BeatportProvider,
        "search_by_isrc",
        lambda self, isrc: [_provider_track_from_raw(beatport_raw)],
    )
    monkeypatch.setattr(
        BeatportProvider,
        "search_by_artist_and_title",
        lambda self, artist, title, limit=5: [],
    )

    seed_csv = tmp_path / "tidal_seed.csv"
    output_csv = tmp_path / "tidal_beatport_enriched.csv"

    with Enricher(Path("__vendor_only__"), providers=["tidal", "beatport"], dry_run=True, mode="hoarding") as enricher:
        enricher.export_tidal_seed_csv("https://tidal.com/browse/playlist/test-playlist-1", seed_csv)
        enricher.enrich_tidal_seed_csv(seed_csv, output_csv)

    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1

    row = rows[0]
    assert row["tidal_playlist_id"] == "test-playlist-1"
    assert row["tidal_track_id"] == "tidal-track-1"
    assert row["tidal_url"] == "https://tidal.com/browse/track/tidal-track-1"
    assert row["title"] == "High Street"
    assert row["artist"] == "Charlotte de Witte"
    assert row["isrc"] == "BE4JP2300002"
    assert row["beatport_track_id"] == "17606729"
    assert row["beatport_release_id"] == "4089968"
    assert row["beatport_url"] == "https://www.beatport.com/track/high-street/17606729"
    assert row["beatport_bpm"] == "138"
    assert row["beatport_key"] == "C Minor"
    assert row["beatport_genre"] == "Techno (Peak Time / Driving)"
    assert row["beatport_subgenre"] == "Peak Time / Driving"
    assert row["beatport_label"] == "KNTXT"
    assert row["beatport_catalog_number"] == "KNTXT021S"
    assert row["beatport_upc"] == "123456789012"
    assert row["beatport_release_date"] == "2023-04-21"
    assert row["match_method"] == "isrc"
    assert float(row["match_confidence"]) == 1.0


def test_tidal_seed_to_beatport_enrichment_no_match(tmp_path: Path, monkeypatch) -> None:
    _mock_tidal_playlist_export(
        monkeypatch,
        {
            "id": "tidal-track-2",
            "title": "Unknown Track",
            "artists": [{"name": "Unknown Artist"}],
            "isrc": "US1234567890",
            "url": "https://tidal.com/browse/track/tidal-track-2",
        },
    )

    monkeypatch.setattr(BeatportProvider, "search_by_isrc", lambda self, isrc: [])
    monkeypatch.setattr(
        BeatportProvider,
        "search_by_artist_and_title",
        lambda self, artist, title, limit=5: [],
    )

    seed_csv = tmp_path / "tidal_seed.csv"
    output_csv = tmp_path / "tidal_beatport_enriched.csv"

    with Enricher(Path("__vendor_only__"), providers=["tidal", "beatport"], dry_run=True, mode="hoarding") as enricher:
        enricher.export_tidal_seed_csv("https://tidal.com/browse/playlist/test-playlist-2", seed_csv)
        enricher.enrich_tidal_seed_csv(seed_csv, output_csv)

    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1

    row = rows[0]
    assert row["tidal_playlist_id"] == "test-playlist-2"
    assert row["tidal_track_id"] == "tidal-track-2"
    assert row["title"] == "Unknown Track"
    assert row["artist"] == "Unknown Artist"
    assert row["isrc"] == "US1234567890"
    assert row["beatport_track_id"] == ""
    assert row["beatport_release_id"] == ""
    assert row["beatport_url"] == ""
    assert row["beatport_bpm"] == ""
    assert row["beatport_key"] == ""
    assert row["beatport_genre"] == ""
    assert row["beatport_subgenre"] == ""
    assert row["beatport_label"] == ""
    assert row["beatport_catalog_number"] == ""
    assert row["beatport_upc"] == ""
    assert row["beatport_release_date"] == ""
    assert row["match_method"] == "no_match"
    assert float(row["match_confidence"]) == 0.0


def test_tidal_seed_to_beatport_enrichment_title_artist_fallback(tmp_path: Path, monkeypatch) -> None:
    _mock_tidal_playlist_export(
        monkeypatch,
        {
            "id": "tidal-track-3",
            "title": "Fallback Track",
            "artists": [{"name": "Fallback Artist"}],
            "url": "https://tidal.com/browse/track/tidal-track-3",
        },
    )

    beatport_raw = {
        "id": 9999,
        "name": "Fallback Track",
        "artists": [{"name": "Fallback Artist"}],
        "url": "https://www.beatport.com/track/fallback-track/9999",
        "release": {
            "id": 1111,
            "name": "Fallback Release",
            "label": {"name": "Fallback Label"},
            "catalog_number": "FB-001",
            "new_release_date": "2024-01-01",
        },
    }

    monkeypatch.setattr(BeatportProvider, "search_by_isrc", lambda self, isrc: [])
    monkeypatch.setattr(
        BeatportProvider,
        "search_by_artist_and_title",
        lambda self, artist, title, limit=5: [_provider_track_from_raw(beatport_raw)],
    )

    seed_csv = tmp_path / "tidal_seed.csv"
    output_csv = tmp_path / "tidal_beatport_enriched.csv"

    with Enricher(Path("__vendor_only__"), providers=["tidal", "beatport"], dry_run=True, mode="hoarding") as enricher:
        enricher.export_tidal_seed_csv("https://tidal.com/browse/playlist/test-playlist-3", seed_csv)
        enricher.enrich_tidal_seed_csv(seed_csv, output_csv)

    rows = _read_csv_rows(output_csv)
    assert len(rows) == 1

    row = rows[0]
    assert row["match_method"] == "title_artist_fallback"
    assert float(row["match_confidence"]) == 0.6
    assert row["beatport_track_id"] == "9999"
