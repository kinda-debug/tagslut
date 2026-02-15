"""Shared data models used across the Tagslut application."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl


class ProviderInfo(BaseModel):
    """Metadata describing the provider that supplied a record."""

    name: str = Field(..., description="Unique identifier for the provider.")
    url: Optional[HttpUrl] = Field(default=None, description="Provider homepage URL.")
    external_id: Optional[str] = Field(default=None, description="Provider-specific identifier.")


class Artwork(BaseModel):
    """Represents artwork assets for a release."""

    url: HttpUrl = Field(..., description="URL pointing to the artwork file.")
    mime_type: str = Field(default="image/jpeg", description="MIME type for the artwork file.")
    width: Optional[int] = Field(default=None, description="Artwork width in pixels.")
    height: Optional[int] = Field(default=None, description="Artwork height in pixels.")


class Artist(BaseModel):
    """Represents an artist in the Tagslut domain model."""

    name: str = Field(..., description="Human readable artist name.")
    providers: List[ProviderInfo] = Field(
        default_factory=list,
        description="Provider references contributing information about the artist.",
    )


class Album(BaseModel):
    """Represents an album release."""

    title: str = Field(..., description="Album title.")
    artists: List[Artist] = Field(
        default_factory=list,
        description="Artists credited on the album.",
    )
    release_date: Optional[datetime] = Field(
        default=None, description="Release date parsed from provider metadata."
    )
    artwork: Optional[Artwork] = Field(
        default=None,
        description="Primary artwork asset for the album.",
    )
    providers: List[ProviderInfo] = Field(
        default_factory=list,
        description="Provider references contributing information about the album.",
    )


class Track(BaseModel):
    """Represents an individual track."""

    title: str = Field(..., description="Track title.")
    artists: List[Artist] = Field(
        default_factory=list,
        description="Artists credited on the track.",
    )
    album: Optional[Album] = Field(
        default=None,
        description="Album the track belongs to, if any.",
    )
    duration_ms: Optional[int] = Field(
        default=None,
        description="Track duration in milliseconds.",
    )
    track_number: Optional[int] = Field(
        default=None,
        description="Track number within the album.",
    )
    disc_number: Optional[int] = Field(
        default=None,
        description="Disc number when part of multi-disc release.",
    )
    explicit: bool = Field(
        default=False,
        description="Whether the track is flagged as explicit.",
    )
    providers: List[ProviderInfo] = Field(
        default_factory=list,
        description="Provider references contributing information about the track.",
    )
    isrc: Optional[str] = Field(default=None, description="ISRC identifier when available.")
    upc: Optional[str] = Field(default=None, description="UPC/EAN identifier when available.")


__all__ = [
    "Album",
    "Artist",
    "Artwork",
    "ProviderInfo",
    "Track",
]
