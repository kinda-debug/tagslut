"""Pure metadata validation helpers."""

from __future__ import annotations

from typing import Any, Mapping

REQUIRED_TAGS = ("artist", "album", "title", "date")
TRACK_TAG_CANDIDATES = ("tracknumber", "track")


def normalise_tags(tags: Mapping[str, Any]) -> dict[str, Any]:
    """Return tag keys normalised to lowercase for consistent checks."""

    return {key.lower(): value for key, value in tags.items()}


def tags_are_valid(tags: Mapping[str, Any]) -> bool:
    """Return ``True`` when *tags* includes required metadata fields."""

    normalised = normalise_tags(tags)
    if not all(tag in normalised for tag in REQUIRED_TAGS):
        return False
    if not any(tag in normalised for tag in TRACK_TAG_CANDIDATES):
        return False
    return True
