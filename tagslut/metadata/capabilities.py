"""Typed capability model for metadata provider routing."""

from __future__ import annotations

from enum import Enum


class Capability(str, Enum):
    # Metadata
    METADATA_FETCH_TRACK_BY_ID = "metadata.fetch_track_by_id"
    METADATA_SEARCH_BY_ISRC = "metadata.search_by_isrc"
    METADATA_SEARCH_BY_TEXT = "metadata.search_by_text"
    METADATA_EXPORT_PLAYLIST_SEED = "metadata.export_playlist_seed"
    METADATA_FETCH_ARTWORK = "metadata.fetch_artwork"

    # Auth
    AUTH_REFRESH = "auth.refresh"
    AUTH_VALIDATE_CREDENTIALS = "auth.validate_credentials"

