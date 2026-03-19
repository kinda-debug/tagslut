#!/usr/bin/env python3
"""
beatport_normalize.py

Normalizes Beatport track JSON into the ProviderTrack-like structure
defined in metadata_guide.md.

This module provides:
- BeatportTrack dataclass matching the ProviderTrack schema
- normalize_beatport_track() to convert raw Beatport JSON
- extract_beatport_track_info() for use in aggregate_metadata_full.py

Usage:
    from beatport_normalize import normalize_beatport_track, BeatportTrack

    raw_json = {...}  # Beatport track JSON
    track = normalize_beatport_track(raw_json)
    print(track.bpm, track.key, track.genre, track.duration_s)
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class BeatportTrack:
    """
    Normalized Beatport track structure matching ProviderTrack schema.

    Fields align with metadata_guide.md Section 10.5.1 ProviderTrack:
    - service: always 'beatport'
    - service_track_id: Beatport track ID
    - title, artist, album: basic metadata
    - duration_s: duration in seconds (converted from length_ms)
    - isrc: International Standard Recording Code
    - bpm, key, genre: DJ-relevant metadata
    - match_confidence: for resolution state machine
    - raw: original JSON for re-parsing

    Additional Beatport-specific fields:
    - key_camelot: Camelot wheel notation (e.g., "8A")
    - subgenre: Beatport subgenre
    - mix_name: e.g., "Original Mix", "Extended Mix"
    - label_name: record label
    - release_id, release_name: release info
    - sample_url: preview audio URL
    - catalog_number: label catalog number
    - publish_date: release date
    - artwork_url: cover art URL
    - artists: list of artist names
    - remixers: list of remixer names
    """
    service: str = "beatport"
    service_track_id: Optional[str] = None
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    duration_s: Optional[float] = None
    duration_ms: Optional[int] = None
    isrc: Optional[str] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    key_camelot: Optional[str] = None
    genre: Optional[str] = None
    subgenre: Optional[str] = None
    mix_name: Optional[str] = None
    label_name: Optional[str] = None
    release_id: Optional[int] = None
    release_name: Optional[str] = None
    sample_url: Optional[str] = None
    catalog_number: Optional[str] = None
    publish_date: Optional[str] = None
    artwork_url: Optional[str] = None
    artists: List[str] = field(default_factory=list)
    remixers: List[str] = field(default_factory=list)
    match_confidence: str = "none"
    raw: Dict[str, Any] = field(default_factory=dict)


def normalize_beatport_track(bp_json: Dict[str, Any]) -> BeatportTrack:
    """
    Convert raw Beatport track JSON to normalized BeatportTrack.

    Handles both /v4/catalog/tracks/{id}/ and /v4/my/beatport/tracks/ responses.

    Args:
        bp_json: Raw Beatport track JSON object

    Returns:
        BeatportTrack with normalized fields
    """
    if not isinstance(bp_json, dict):
        return BeatportTrack(raw=bp_json if bp_json else {})

    # Extract track ID
    track_id = bp_json.get("id")
    service_track_id = str(track_id) if track_id is not None else None

    # Basic metadata
    title = bp_json.get("name")
    mix_name = bp_json.get("mix_name")

    # Artists - can be a list of objects with 'name' field
    artists_raw = bp_json.get("artists", [])
    artists = []
    if isinstance(artists_raw, list):
        for artist_entry in artists_raw:
            if isinstance(artist_entry, dict) and artist_entry.get("name"):
                artists.append(artist_entry["name"])
            elif isinstance(artist_entry, str):
                artists.append(artist_entry)

    # Primary artist string
    artist = ", ".join(artists) if artists else None

    # Remixers
    remixers_raw = bp_json.get("remixers", [])
    remixers = []
    if isinstance(remixers_raw, list):
        for remixer_entry in remixers_raw:
            if isinstance(remixer_entry, dict) and remixer_entry.get("name"):
                remixers.append(remixer_entry["name"])
            elif isinstance(remixer_entry, str):
                remixers.append(remixer_entry)

    # Release info (album equivalent)
    release = bp_json.get("release", {})
    if not isinstance(release, dict):
        release = {}
    release_id = release.get("id")
    release_name = release.get("name")
    album = release_name  # Use release name as album

    # Label
    label = release.get("label", {}) or bp_json.get("label", {})
    if isinstance(label, dict):
        label_name = label.get("name")
    else:
        label_name = None

    # Duration - Beatport uses length_ms
    length_ms = bp_json.get("length_ms")
    duration_ms = None
    duration_s = None
    if length_ms is not None:
        try:
            duration_ms = int(length_ms)
            duration_s = duration_ms / 1000.0
        except (TypeError, ValueError):
            pass

    # ISRC
    isrc = bp_json.get("isrc")

    # BPM
    bpm = None
    bpm_raw = bp_json.get("bpm")
    if bpm_raw is not None:
        try:
            bpm = float(bpm_raw)
        except (TypeError, ValueError):
            pass

    # Key - can be object with 'name' and 'camelot_number' or string
    key_obj = bp_json.get("key")
    key = None
    key_camelot = None
    if isinstance(key_obj, dict):
        key = key_obj.get("name")
        # Camelot can be number or string like "8A"
        camelot = key_obj.get("camelot_number") or key_obj.get("camelot")
        if camelot is not None:
            key_camelot = str(camelot)
    elif isinstance(key_obj, str):
        key = key_obj

    # Genre - can be object with 'name' or list of genre objects
    genre = None
    genre_obj = bp_json.get("genre")
    if isinstance(genre_obj, dict):
        genre = genre_obj.get("name")
    elif isinstance(genre_obj, str):
        genre = genre_obj
    else:
        # Try genres array
        genres = bp_json.get("genres", [])
        if isinstance(genres, list) and genres:
            first = genres[0]
            if isinstance(first, dict):
                genre = first.get("name")
            elif isinstance(first, str):
                genre = first

    # Subgenre
    subgenre = None
    subgenre_obj = bp_json.get("sub_genre")
    if isinstance(subgenre_obj, dict):
        subgenre = subgenre_obj.get("name")
    elif isinstance(subgenre_obj, str):
        subgenre = subgenre_obj
    else:
        subgenres = bp_json.get("sub_genres", [])
        if isinstance(subgenres, list) and subgenres:
            first = subgenres[0]
            if isinstance(first, dict):
                subgenre = first.get("name")
            elif isinstance(first, str):
                subgenre = first

    # Sample/preview URL
    sample_url = bp_json.get("sample_url")
    if not sample_url:
        preview = bp_json.get("preview", {})
        if isinstance(preview, dict):
            sample_url = preview.get("sample_url")

    # Catalog number
    catalog_number = bp_json.get("catalog_number") or release.get("catalog_number")

    # Publish date
    publish_date = bp_json.get("publish_date") or bp_json.get("new_release_date")

    # Artwork URL
    artwork_url = None
    image = release.get("image", {}) or bp_json.get("image", {})
    if isinstance(image, dict):
        artwork_url = image.get("uri") or image.get("url")

    return BeatportTrack(
        service="beatport",
        service_track_id=service_track_id,
        title=title,
        artist=artist,
        album=album,
        duration_s=duration_s,
        duration_ms=duration_ms,
        isrc=isrc,
        bpm=bpm,
        key=key,
        key_camelot=key_camelot,
        genre=genre,
        subgenre=subgenre,
        mix_name=mix_name,
        label_name=label_name,
        release_id=release_id,
        release_name=release_name,
        sample_url=sample_url,
        catalog_number=catalog_number,
        publish_date=publish_date,
        artwork_url=artwork_url,
        artists=artists,
        remixers=remixers,
        match_confidence="exact" if service_track_id else "none",
        raw=bp_json,
    )


def extract_beatport_track_info(bp_json: Dict[str, Any]) -> tuple:  # type: ignore  # TODO: mypy-strict
    """
    Extract key fields from Beatport JSON for use in aggregate_metadata_full.py.

    Returns:
        Tuple of (track_id, bpm, key, genre, duration_s, isrc, label)

    This function matches the signature pattern used by other extract_*_track_info
    functions in aggregate_metadata_full.py.
    """
    track = normalize_beatport_track(bp_json)
    return (
        track.service_track_id,
        track.bpm,
        track.key,
        track.genre,
        track.duration_s,
        track.isrc,
        track.label_name,
    )


def beatport_track_to_dict(track: BeatportTrack) -> Dict[str, Any]:
    """
    Convert BeatportTrack to dictionary for JSON serialization.

    Useful for writing to NDJSON or inserting into database.
    """
    return {
        "service": track.service,
        "track_id": track.service_track_id,
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "duration_s": track.duration_s,
        "duration_ms": track.duration_ms,
        "isrc": track.isrc,
        "bpm": track.bpm,
        "key": track.key,
        "key_camelot": track.key_camelot,
        "genre": track.genre,
        "subgenre": track.subgenre,
        "mix_name": track.mix_name,
        "label_name": track.label_name,
        "release_id": track.release_id,
        "release_name": track.release_name,
        "sample_url": track.sample_url,
        "catalog_number": track.catalog_number,
        "publish_date": track.publish_date,
        "artwork_url": track.artwork_url,
        "artists": track.artists,
        "remixers": track.remixers,
        "match_confidence": track.match_confidence,
        "raw": track.raw,
    }


if __name__ == "__main__":
    # Simple test with sample data

    sample = {
        "id": 12345678,
        "name": "Test Track",
        "mix_name": "Original Mix",
        "artists": [{"name": "Artist One"}, {"name": "Artist Two"}],
        "remixers": [],
        "bpm": 128,
        "key": {"name": "A minor", "camelot_number": "8A"},
        "genre": {"name": "Techno"},
        "sub_genre": {"name": "Peak Time"},
        "length_ms": 360000,
        "isrc": "USRC12345678",
        "release": {
            "id": 9999,
            "name": "Test EP",
            "label": {"name": "Test Label"},
            "catalog_number": "TL001",
            "image": {"uri": "https://example.com/cover.jpg"}
        },
        "sample_url": "https://example.com/preview.mp3",
        "publish_date": "2024-01-15"
    }

    track = normalize_beatport_track(sample)
    print("Normalized BeatportTrack:")
    print(f"  ID: {track.service_track_id}")
    print(f"  Title: {track.title} ({track.mix_name})")
    print(f"  Artist: {track.artist}")
    print(f"  BPM: {track.bpm}")
    print(f"  Key: {track.key} (Camelot: {track.key_camelot})")
    print(f"  Genre: {track.genre} / {track.subgenre}")
    print(f"  Duration: {track.duration_s}s ({track.duration_ms}ms)")
    print(f"  ISRC: {track.isrc}")
    print(f"  Label: {track.label_name}")
    print(f"  Release: {track.release_name} (ID: {track.release_id})")
