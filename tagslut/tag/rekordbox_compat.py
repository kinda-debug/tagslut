from __future__ import annotations

REKORDBOX_TESTED_FIELDS = frozenset(
    {
        "canonical_title",
        "canonical_artist_credit",
        "bpm",
        "musical_key",
        "rating",
        "comments",
    }
)

REKORDBOX_XML_FIELD_MAP = {
    "canonical_title": "Name",
    "canonical_artist_credit": "Artist",
    "bpm": "BPM",
    "musical_key": "Key",
    "rating": "Rating",
    "comments": "Comments",
}
