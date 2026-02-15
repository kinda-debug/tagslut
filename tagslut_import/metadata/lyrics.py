"""Lyrics fetcher abstractions."""

from __future__ import annotations

import abc
from typing import Optional

from tagslut.core.models import Track


class LyricsFetcher(abc.ABC):
    """Abstract base class for fetching lyrics for a track."""

    @abc.abstractmethod
    async def fetch(self, track: Track) -> Optional[str]:
        """Return lyrics for the provided track, if available."""


class StaticLyricsFetcher(LyricsFetcher):
    """Lyrics fetcher returning a preconfigured lyrics mapping."""

    def __init__(self, lyrics_map: dict[str, str] | None = None) -> None:
        self._lyrics_map = lyrics_map or {}

    async def fetch(self, track: Track) -> Optional[str]:
        key = f"{','.join(artist.name for artist in track.artists)}::{track.title}".lower()
        return self._lyrics_map.get(key)


__all__ = ["LyricsFetcher", "StaticLyricsFetcher"]
