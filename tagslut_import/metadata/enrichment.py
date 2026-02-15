"""Metadata enrichment pipeline."""

from __future__ import annotations

from typing import Optional

from tagslut.core.models import Track

from .artwork import ArtworkFetcher
from .lyrics import LyricsFetcher
from .schema import EnrichedAlbum, EnrichedTrack


class MetadataEnricher:
    """Compose metadata enrichment steps for tracks."""

    def __init__(
        self,
        *,
        artwork_fetcher: Optional[ArtworkFetcher] = None,
        lyrics_fetcher: Optional[LyricsFetcher] = None,
    ) -> None:
        self._artwork_fetcher = artwork_fetcher
        self._lyrics_fetcher = lyrics_fetcher

    async def enrich_track(
        self,
        track: Track,
        *,
        fetch_artwork: bool = True,
        fetch_lyrics: bool = True,
    ) -> EnrichedTrack:
        """Enrich the provided track with optional artwork and lyrics."""

        album_enriched: Optional[EnrichedAlbum] = None
        artwork = None
        if fetch_artwork and self._artwork_fetcher and track.album and track.album.artwork:
            download = await self._artwork_fetcher.download(track.album.artwork)
            artwork = track.album.artwork
            album_enriched = EnrichedAlbum(
                album=track.album, artwork=track.album.artwork, notes=str(download.path)
            )
        lyrics = None
        if fetch_lyrics and self._lyrics_fetcher:
            lyrics = await self._lyrics_fetcher.fetch(track)
        return EnrichedTrack(track=track, lyrics=lyrics, artwork=artwork, album=album_enriched)


__all__ = ["MetadataEnricher"]
