from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tagslut.intake.spotify import SpotifyCollection, SpotifyTrack


def _load_extract_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "extract_tracklists_from_links.py"
    spec = importlib.util.spec_from_file_location("extract_tracklists_from_links_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _FakeSpotifyClient:
    def __init__(self, collection: SpotifyCollection) -> None:
        self.collection = collection

    def fetch_collection(self, url: str) -> SpotifyCollection:
        return self.collection


def _make_track(spotify_id: str, *, index: int) -> SpotifyTrack:
    return SpotifyTrack(
        spotify_id=spotify_id,
        spotify_url=f"https://open.spotify.com/track/{spotify_id}",
        title=f"Track {index}",
        artist="Artist",
        album="Album",
        album_artist="Artist",
        release_date="2025-01-01",
        duration_ms=180000,
        isrc=f"USABC00000{index}",
        track_number=index,
        total_tracks=2,
        disc_number=1,
        total_discs=1,
        cover_url="",
        copyright="",
        publisher="",
        collection_type="playlist",
        collection_title="Collection",
        playlist_index=index,
    )


@pytest.mark.parametrize("kind", ["track", "album", "playlist"])
def test_extract_from_spotify_expands_collection(kind: str) -> None:
    module = _load_extract_module()
    collection = SpotifyCollection(
        url=f"https://open.spotify.com/{kind}/abc123",
        kind=kind,
        title="Collection",
        tracks=[_make_track("spotify-1", index=1), _make_track("spotify-2", index=2)],
    )

    domain, link_type, rows, note = module.extract_from_spotify(
        f"https://open.spotify.com/{kind}/abc123",
        _FakeSpotifyClient(collection),
    )

    assert domain == "spotify"
    assert link_type == kind
    assert note == ""
    assert [row.track_id for row in rows] == ["spotify-1", "spotify-2"]
    assert all(row.domain == "spotify" for row in rows)
    assert all(row.link_type == kind for row in rows)
