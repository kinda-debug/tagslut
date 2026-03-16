from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from tagslut.metadata.enricher import Enricher
from tagslut.metadata.models.types import (
    MatchConfidence,
    ProviderTrack,
    TIDAL_BEATPORT_MERGED_COLUMNS,
    TIDAL_SEED_COLUMNS,
)
from tagslut.metadata.providers.beatport import BeatportProvider
from tagslut.metadata.providers.tidal import TidalProvider


class DummyResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._payload


def _mock_tidal_make_request(monkeypatch, responses: list[DummyResponse]) -> None:
    queue = list(responses)

    def fake_make_request(self, method: str, url: str, params=None, **kwargs):  # type: ignore[no-untyped-def]
        assert queue, f"Unexpected extra TIDAL request for {url}"
        return queue.pop(0)

    monkeypatch.setattr(TidalProvider, "_make_request", fake_make_request)


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_csv_header(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return next(csv.reader(handle))


def _write_seed_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(TIDAL_SEED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


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


def test_header_constants_are_stable() -> None:
    assert TIDAL_SEED_COLUMNS == (
        "tidal_playlist_id",
        "tidal_track_id",
        "tidal_url",
        "title",
        "artist",
        "isrc",
    )
    assert TIDAL_BEATPORT_MERGED_COLUMNS == (
        "tidal_playlist_id",
        "tidal_track_id",
        "tidal_url",
        "title",
        "artist",
        "isrc",
        "beatport_track_id",
        "beatport_release_id",
        "beatport_url",
        "beatport_bpm",
        "beatport_key",
        "beatport_genre",
        "beatport_subgenre",
        "beatport_label",
        "beatport_catalog_number",
        "beatport_upc",
        "beatport_release_date",
        "match_method",
        "match_confidence",
        "last_synced_at",
    )


def test_tidal_seed_export_counts_malformed_missing_duplicate_and_short_page_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    valid_item = {
        "id": "tidal-track-1",
        "title": "Track One",
        "artists": [{"name": "Artist One"}],
        "isrc": "AAA111111111",
        "url": "https://tidal.com/browse/track/tidal-track-1",
    }
    missing_required_item = {
        "id": "tidal-track-2",
        "artists": [{"name": "Artist Two"}],
    }
    _mock_tidal_make_request(
        monkeypatch,
        [
            DummyResponse(
                {
                    "items": [
                        {"item": valid_item},
                        {"item": valid_item},
                        {"item": missing_required_item},
                        "malformed",
                    ]
                }
            )
        ],
    )

    seed_csv = tmp_path / "tidal_seed.csv"
    with Enricher(Path("__vendor_only__"), providers=["tidal"], dry_run=True, mode="hoarding") as enricher:
        stats = enricher.export_tidal_seed_csv(
            "https://tidal.com/browse/playlist/test-playlist-1",
            seed_csv,
        )

    assert _read_csv_header(seed_csv) == list(TIDAL_SEED_COLUMNS)
    assert stats.playlist_id == "test-playlist-1"
    assert stats.exported_rows == 1
    assert stats.missing_isrc_rows == 0
    assert stats.malformed_playlist_items == 1
    assert stats.rows_missing_required_fields == 1
    assert stats.duplicate_rows == 1
    assert stats.pages_fetched == 1
    assert stats.endpoint_fallback_used == 0
    assert stats.pagination_stop_non_200 == 0
    assert stats.pagination_stop_empty_page == 0
    assert stats.pagination_stop_repeated_next == 0
    assert stats.pagination_stop_short_page_no_next == 1


def test_tidal_seed_export_surfaces_non_200_pagination_stop(tmp_path: Path, monkeypatch) -> None:
    first_page_track = {
        "id": "tidal-track-1",
        "title": "Track One",
        "artists": [{"name": "Artist One"}],
        "url": "https://tidal.com/browse/track/tidal-track-1",
    }
    _mock_tidal_make_request(
        monkeypatch,
        [
            DummyResponse(
                {
                    "items": [{"item": first_page_track}],
                    "next": "/v1/playlists/test-playlist-2/items?offset=1",
                }
            ),
            DummyResponse({}, status_code=500),
        ],
    )

    seed_csv = tmp_path / "tidal_seed.csv"
    with Enricher(Path("__vendor_only__"), providers=["tidal"], dry_run=True, mode="hoarding") as enricher:
        stats = enricher.export_tidal_seed_csv(
            "https://tidal.com/browse/playlist/test-playlist-2",
            seed_csv,
        )

    assert stats.pages_fetched == 1
    assert stats.pagination_stop_non_200 == 1
    assert stats.pagination_stop_short_page_no_next == 0


def test_beatport_enrichment_discards_incomplete_seed_rows_and_preserves_header(
    tmp_path: Path,
    monkeypatch,
) -> None:
    seed_csv = tmp_path / "tidal_seed.csv"
    _write_seed_csv(
        seed_csv,
        [
            {
                "tidal_playlist_id": "playlist-1",
                "tidal_track_id": "123",
                "tidal_url": "https://tidal.com/browse/track/123",
                "title": "Track",
                "artist": "Artist",
                "isrc": "AAA111111111",
            },
            {
                "tidal_playlist_id": "playlist-1",
                "tidal_track_id": "124",
                "tidal_url": "https://tidal.com/browse/track/124",
                "title": "",
                "artist": "Artist",
                "isrc": "BBB222222222",
            },
        ],
    )

    beatport_raw = {
        "id": 999,
        "name": "Track",
        "artists": [{"name": "Artist"}],
        "isrc": "AAA111111111",
        "url": "https://www.beatport.com/track/example/999",
        "release": {"id": 1000, "name": "Release"},
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

    output_csv = tmp_path / "tidal_beatport_enriched.csv"
    with Enricher(Path("__vendor_only__"), providers=["beatport"], dry_run=True, mode="hoarding") as enricher:
        stats = enricher.enrich_tidal_seed_csv(seed_csv, output_csv)

    assert _read_csv_header(output_csv) == list(TIDAL_BEATPORT_MERGED_COLUMNS)
    assert stats.input_rows == 2
    assert stats.discarded_seed_rows == 1
    assert stats.output_rows == 1


def test_beatport_enrichment_surfaces_ambiguous_isrc_rows(tmp_path: Path, monkeypatch) -> None:
    seed_csv = tmp_path / "tidal_seed.csv"
    _write_seed_csv(
        seed_csv,
        [
            {
                "tidal_playlist_id": "playlist-1",
                "tidal_track_id": "123",
                "tidal_url": "https://tidal.com/browse/track/123",
                "title": "Track",
                "artist": "Artist",
                "isrc": "AAA111111111",
            }
        ],
    )

    beatport_raw_1 = {
        "id": 999,
        "name": "Track",
        "artists": [{"name": "Artist"}],
        "isrc": "AAA111111111",
        "url": "https://www.beatport.com/track/example/999",
        "release": {"id": 1000, "name": "Release"},
    }
    beatport_raw_2 = {
        "id": 1001,
        "name": "Track",
        "artists": [{"name": "Artist"}],
        "isrc": "AAA111111111",
        "url": "https://www.beatport.com/track/example/1001",
        "release": {"id": 1002, "name": "Release"},
    }
    monkeypatch.setattr(
        BeatportProvider,
        "search_by_isrc",
        lambda self, isrc: [
            _provider_track_from_raw(beatport_raw_1),
            _provider_track_from_raw(beatport_raw_2),
        ],
    )
    monkeypatch.setattr(
        BeatportProvider,
        "search_by_artist_and_title",
        lambda self, artist, title, limit=5: [],
    )

    output_csv = tmp_path / "tidal_beatport_enriched.csv"
    with Enricher(Path("__vendor_only__"), providers=["beatport"], dry_run=True, mode="hoarding") as enricher:
        stats = enricher.enrich_tidal_seed_csv(seed_csv, output_csv)

    rows = _read_csv_rows(output_csv)
    assert rows[0]["match_method"] == "isrc"
    assert stats.isrc_matches == 1
    assert stats.ambiguous_isrc_rows == 1


def test_beatport_enrichment_propagates_fallback_confidence(tmp_path: Path, monkeypatch) -> None:
    seed_csv = tmp_path / "tidal_seed.csv"
    _write_seed_csv(
        seed_csv,
        [
            {
                "tidal_playlist_id": "playlist-1",
                "tidal_track_id": "123",
                "tidal_url": "https://tidal.com/browse/track/123",
                "title": "Fallback Track",
                "artist": "Fallback Artist",
                "isrc": "",
            }
        ],
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

    output_csv = tmp_path / "tidal_beatport_enriched.csv"
    with Enricher(Path("__vendor_only__"), providers=["beatport"], dry_run=True, mode="hoarding") as enricher:
        stats = enricher.enrich_tidal_seed_csv(seed_csv, output_csv)

    rows = _read_csv_rows(output_csv)
    assert rows[0]["match_method"] == "title_artist_fallback"
    assert float(rows[0]["match_confidence"]) == 0.85
    assert stats.title_artist_fallback_matches == 1

