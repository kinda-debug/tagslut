"""Metadata schema definitions."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from tagslut.core.models import Album, Artwork, Track


class EnrichedAlbum(BaseModel):
    """Album metadata enriched with artwork and supplemental notes."""

    album: Album = Field(
        ...,
        description="Album metadata extracted from a provider.",
    )
    artwork: Optional[Artwork] = Field(
        default=None,
        description="Downloaded artwork asset.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Supplemental information about the album.",
    )


class EnrichedTrack(BaseModel):
    """Track metadata with optional lyrics and artwork references."""

    track: Track = Field(
        ...,
        description="Raw track metadata from a provider.",
    )
    lyrics: Optional[str] = Field(
        default=None,
        description="Lyrics associated with the track.",
    )
    artwork: Optional[Artwork] = Field(
        default=None,
        description="Artwork best associated with the track or album.",
    )
    album: Optional[EnrichedAlbum] = Field(
        default=None,
        description="Album information if available for the track.",
    )


__all__ = ["EnrichedAlbum", "EnrichedTrack"]
