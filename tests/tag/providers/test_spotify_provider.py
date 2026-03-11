from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from tagslut.cli.commands.tag import run_tag_batch_create
from tagslut.library import create_library_engine, ensure_library_schema
from tagslut.library.matcher import TrackQuery
from tagslut.library.models import SourceProvenance, Track, TrackAlias
from tagslut.library.repositories import upsert_track, upsert_track_alias
from tagslut.metadata.models.types import MatchConfidence, ProviderTrack
from tagslut.tag.providers.base import ProviderConfigError, RawResult
from tagslut.tag.providers.spotify import SpotifyProvider


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'spotify_provider.db').resolve()}"


def _seed_track(session: Session, *, title: str, artist: str) -> Track:
    track = upsert_track(
        session,
        Track(
            canonical_title=title,
            sort_title=title.casefold(),
            canonical_artist_credit=artist,
            sort_artist_credit=artist.casefold(),
            status="active",
        ),
    )
    session.flush()
    return track


def test_spotify_search_wraps_existing_client(monkeypatch) -> None:
    calls: dict[str, Any] = {}

    class FakeTokenManager:
        def is_configured(self, provider: str) -> bool:
            calls["provider"] = provider
            return True

        def get_token(self, provider: str):
            return SimpleNamespace(access_token="token", is_expired=False)

        def refresh_spotify_token(self):
            raise AssertionError("refresh_spotify_token should not be called when token is already valid")

    class FakeLegacySpotifyProvider:
        BASE_URL = "https://api.spotify.test/v1"

        def __init__(self, token_manager: Any) -> None:
            calls["init"] = token_manager

        def fetch_by_id(self, track_id: str):
            calls["fetch_by_id"] = track_id
            return None

        def search_by_isrc(self, isrc: str):
            calls["search_by_isrc"] = isrc
            return []

        def search_advanced(
            self,
            *,
            title: str | None = None,
            artist: str | None = None,
            limit: int = 10,
        ) -> list[ProviderTrack]:
            calls["search_advanced"] = (title, artist, limit)
            return [
                ProviderTrack(
                    service="spotify",
                    service_track_id="sp-track-1",
                    title=title,
                    artist=artist,
                    match_confidence=MatchConfidence.STRONG,
                    raw={
                        "id": "sp-track-1",
                        "name": title,
                        "artists": [{"name": artist}],
                        "album": {"id": "album-1"},
                    },
                )
            ]

        def get_audio_features(self, track_id: str) -> dict[str, Any]:
            calls["get_audio_features"] = track_id
            return {"tempo": 128.0}

    monkeypatch.setattr("tagslut.tag.providers.spotify._LegacySpotifyProvider", FakeLegacySpotifyProvider)

    provider = SpotifyProvider(token_manager=FakeTokenManager())
    results = provider.search(TrackQuery(title="Track Name", artist="Artist Name"))

    assert calls["provider"] == "spotify"
    assert calls["search_advanced"] == ("Track Name", "Artist Name", 10)
    assert calls["get_audio_features"] == "sp-track-1"
    assert len(results) == 1
    assert results[0].external_id == "sp-track-1"
    assert results[0].payload["track"]["id"] == "sp-track-1"


def test_spotify_normalize_extracts_bpm_key() -> None:
    provider = SpotifyProvider(token_manager=SimpleNamespace())
    raw = RawResult(
        provider="spotify",
        external_id="sp-track-1",
        query_text="Artist Name Track Name",
        payload={
            "track": {
                "id": "sp-track-1",
                "name": "Track Name",
                "artists": [{"name": "Artist Name"}],
                "album": {"id": "album-1"},
            },
            "audio_features": {
                "tempo": 128.0,
                "key": 9,
                "mode": 0,
                "energy": 0.75,
                "danceability": 0.62,
                "valence": 0.33,
            },
        },
    )

    candidates = {candidate.field_name: candidate.normalized_value for candidate in provider.normalize(raw)}

    assert candidates["canonical_title"] == "Track Name"
    assert candidates["canonical_artist_credit"] == "Artist Name"
    assert candidates["canonical_release_id"] == "album-1"
    assert candidates["bpm"] == 128.0
    assert candidates["musical_key"] == "8A"
    assert candidates["spotify_id"] == "sp-track-1"


@pytest.mark.parametrize(
    ("energy", "expected"),
    [
        (0.0, 0),
        (1.0, 100),
        (0.5, 50),
    ],
)
def test_spotify_normalize_energy_scaling(energy: float, expected: int) -> None:
    provider = SpotifyProvider(token_manager=SimpleNamespace())
    raw = RawResult(
        provider="spotify",
        external_id="sp-track-1",
        query_text="Artist Name Track Name",
        payload={
            "track": {
                "id": "sp-track-1",
                "name": "Track Name",
                "artists": [{"name": "Artist Name"}],
                "album": {"id": "album-1"},
            },
            "audio_features": {"energy": energy},
        },
    )

    candidates = {candidate.field_name: candidate.normalized_value for candidate in provider.normalize(raw)}

    assert candidates["energy"] == expected


def test_batch_create_queues_tracks(tmp_path: Path, monkeypatch) -> None:
    db_url = _db_url(tmp_path)
    ensure_library_schema(db_url)
    engine = create_library_engine(db_url)

    with Session(engine) as session:
        track = _seed_track(session, title="Known Track", artist="Known Artist")
        upsert_track_alias(
            session,
            TrackAlias(
                track_id=track.id,
                alias_type="spotify_id",
                value="spotify-known",
                provider="spotify",
                source="test",
                confidence=1.0,
            ),
        )
        session.commit()

    playlist_tracks = [
        {"id": "spotify-known", "name": "Known Track"},
        {"id": "spotify-missing", "name": "Missing Track"},
    ]
    monkeypatch.setattr(
        SpotifyProvider,
        "fetch_playlist_tracks",
        lambda self, playlist_id: playlist_tracks,
    )

    queued = run_tag_batch_create("spotify-playlist", "playlist-1", "batch-1", db_url=db_url)

    assert queued == 2

    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(SourceProvenance)
                .where(SourceProvenance.source_type == "tag_batch")
                .order_by(SourceProvenance.payload_ref.asc())
            )
        )
        assert len(rows) == 2
        assert {row.source_key for row in rows} == {"batch-1"}
        assert [row.payload_ref for row in rows] == ["spotify-known", "spotify-missing"]
        assert rows[0].track_id is not None
        assert rows[1].track_id is None


def test_provider_config_error_on_missing_credentials() -> None:
    class MissingTokenManager:
        def is_configured(self, provider: str) -> bool:
            return False

        def get_token(self, provider: str):
            return None

        def refresh_spotify_token(self):
            return None

    provider = SpotifyProvider(token_manager=MissingTokenManager())

    with pytest.raises(ProviderConfigError):
        provider.search(TrackQuery(title="Track Name", artist="Artist Name"))
