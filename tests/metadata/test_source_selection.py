from __future__ import annotations

from tagslut.metadata.models.types import ProviderTrack
from tagslut.metadata.source_selection import select_download_source_for_beatport_track


def _tidal_track(
    *,
    track_id: str,
    title: str,
    artist: str,
    isrc: str | None = None,
    duration_ms: int | None = None,
    album: str | None = None,
    audio_quality: str | None = None,
) -> ProviderTrack:
    return ProviderTrack(
        service="tidal",
        service_track_id=track_id,
        title=title,
        artist=artist,
        album=album,
        isrc=isrc,
        duration_ms=duration_ms,
        audio_quality=audio_quality,
        url=f"https://tidal.com/browse/track/{track_id}",
    )


def test_beatport_isrc_exact_match_selects_tidal_hires() -> None:
    decision = select_download_source_for_beatport_track(
        beatport_track_id="123",
        beatport_isrc="USTEST001",
        beatport_title="Test Track",
        beatport_artist="Test Artist",
        beatport_album=None,
        beatport_duration_ms=180_000,
        tidal_candidates=[
            _tidal_track(
                track_id="999",
                title="Test Track",
                artist="Test Artist",
                isrc="USTEST001",
                duration_ms=180_100,
                audio_quality="HIRES_LOSSLESS",
            )
        ],
    )
    assert decision.winner == "tidal"
    assert decision.tidal_match is not None
    assert decision.tidal_match.match_method == "isrc"


def test_beatport_neutral_mix_blocks_tidal_extended_mix() -> None:
    decision = select_download_source_for_beatport_track(
        beatport_track_id="123",
        beatport_isrc=None,
        beatport_title="Test Track (Original Mix)",
        beatport_artist="Test Artist",
        beatport_album=None,
        beatport_duration_ms=180_000,
        tidal_candidates=[
            _tidal_track(
                track_id="999",
                title="Test Track (Extended Mix)",
                artist="Test Artist",
                isrc=None,
                duration_ms=180_000,
                audio_quality="LOSSLESS",
            )
        ],
    )
    assert decision.winner == "beatport"
    assert decision.winner_reason == "tidal_unverified"


def test_beatport_isrc_multiple_verified_ties_are_ambiguous_and_retain_beatport() -> None:
    decision = select_download_source_for_beatport_track(
        beatport_track_id="123",
        beatport_isrc="USTEST001",
        beatport_title="Test Track",
        beatport_artist="Test Artist",
        beatport_album=None,
        beatport_duration_ms=180_000,
        tidal_candidates=[
            _tidal_track(
                track_id="100",
                title="Test Track",
                artist="Test Artist",
                isrc="USTEST001",
                duration_ms=180_000,
                audio_quality="LOSSLESS",
            ),
            _tidal_track(
                track_id="101",
                title="Test Track",
                artist="Test Artist",
                isrc="USTEST001",
                duration_ms=180_000,
                audio_quality="LOSSLESS",
            ),
        ],
    )
    assert decision.ambiguous is True
    assert decision.winner == "beatport"
    assert decision.winner_reason == "tidal_ambiguous_verified_candidates"

