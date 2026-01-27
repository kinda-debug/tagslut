#!/usr/bin/env python3
"""
aggregate_metadata_full.py (template)

- Reads NDJSON from metadata_output_full.ndjson (from harvest_metadata_full.sh)
- Each line: { "tidal": {...}, "beatport": {...}, "qobuz": {...}, "spotify": {...}, "row_index": N }
- Extracts candidate BPM/key/genre from each service.
- Builds canonical fields with priority: Beatport > Qobuz > TIDAL > Spotify.
"""

import csv
import json
from pathlib import Path

INPUT_NDJSON = Path("metadata_output_full.ndjson")
OUTPUT_CSV = Path("metadata_canonical.csv")

def extract_tidal_track_info(tidal_json):
    """
    Adjust these paths to match your actual TIDAL JSON.

    Example assumption:
      {
        "data": {
          "id": "...",
          "attributes": {
            "bpm": 128,
            "key": "F#m",
            "genre": { "name": "Techno" }
          }
        }
      }
    """
    if not isinstance(tidal_json, dict):
        return None, None, None, None
    data = tidal_json.get("data") or {}
    tidal_id = data.get("id")
    attrs = data.get("attributes") or {}

    bpm = attrs.get("bpm")
    key = attrs.get("key")
    genre = None
    genre_obj = attrs.get("genre")
    if isinstance(genre_obj, dict):
        genre = genre_obj.get("name")
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return tidal_id, bpm, key, genre

def extract_beatport_track_info(bp_json):
    """
    Adjust these paths for Beatport JSON.

    Example assumption:
      {
        "id": 123,
        "bpm": 128,
        "key": "F#m",
        "genre": { "name": "Techno" }  # or list of genres
      }
    """
    if not isinstance(bp_json, dict):
        return None, None, None, None
    bp_id = bp_json.get("id")

    bpm = bp_json.get("bpm")
    key = bp_json.get("key")

    genre = None
    genre_obj = bp_json.get("genre") or bp_json.get("primary_genre")
    if isinstance(genre_obj, dict):
        genre = genre_obj.get("name")
    elif isinstance(genre_obj, list) and genre_obj:
        first = genre_obj[0]
        if isinstance(first, dict):
            genre = first.get("name")
        elif isinstance(first, str):
            genre = first
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return bp_id, bpm, key, genre

def extract_qobuz_track_info(qb_json):
    """
    Adjust these paths for Qobuz JSON.

    Example assumption:
      {
        "id": 260231933,
        "bpm": 128,
        "key": "F#m",
        "genre": { "name": "Jazz" }
      }
    """
    if not isinstance(qb_json, dict):
        return None, None, None, None
    qb_id = qb_json.get("id")

    bpm = qb_json.get("bpm")
    key = qb_json.get("key")

    genre = None
    genre_obj = qb_json.get("genre") or qb_json.get("genre_info")
    if isinstance(genre_obj, dict):
        genre = genre_obj.get("name")
    elif isinstance(genre_obj, list) and genre_obj:
        first = genre_obj[0]
        if isinstance(first, dict):
            genre = first.get("name")
        elif isinstance(first, str):
            genre = first
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return qb_id, bpm, key, genre

def extract_spotify_track_info(sp_json):
    """
    Adjust these paths for Spotify JSON.

    Example assumption for /v1/tracks:
      {
        "id": "3n3Ppam7vgaVa1iaRUc9Lp",
        "name": "...",
        "artists": [...],
        "album": {...}
      }

    For BPM/key, you might want to instead call /v1/audio-features/{id} and store
    that JSON under spotify.audio_features in the NDJSON. This template assumes
    those fields may be present at top-level for simplicity.
    """
    if not isinstance(sp_json, dict):
        return None, None, None, None
    sp_id = sp_json.get("id")

    # Placeholder extraction – adjust to real Spotify structure you store:
    bpm = sp_json.get("tempo")  # or from `audio_features["tempo"]`
    key = sp_json.get("key")    # or from `audio_features["key"]`, you might map numeric -> string

    genre = None
    genre_obj = sp_json.get("genre") or sp_json.get("genres")
    if isinstance(genre_obj, list) and genre_obj:
        genre = genre_obj[0]
    elif isinstance(genre_obj, str):
        genre = genre_obj

    return sp_id, bpm, key, genre

def choose_canonical(bpm_bp, bpm_qb, bpm_td, bpm_sp,
                     key_bp, key_qb, key_td, key_sp,
                     genre_bp, genre_qb, genre_td, genre_sp):
    """
    Canonical selection with priority:
      Beatport > Qobuz > TIDAL > Spotify
    """
    canonical_bpm = bpm_bp or bpm_qb or bpm_td or bpm_sp
    canonical_key = key_bp or key_qb or key_td or key_sp
    canonical_genre = genre_bp or genre_qb or genre_td or genre_sp
    return canonical_bpm, canonical_key, canonical_genre

def main():
    if not INPUT_NDJSON.exists():
        raise SystemExit(f"Input NDJSON not found: {INPUT_NDJSON}")

    rows = []

    with INPUT_NDJSON.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            tidal_json = obj.get("tidal")
            bp_json = obj.get("beatport")
            qb_json = obj.get("qobuz")
            sp_json = obj.get("spotify")
            row_index = obj.get("row_index")

            tidal_id, tidal_bpm, tidal_key, tidal_genre = extract_tidal_track_info(tidal_json)
            bp_id, bp_bpm, bp_key, bp_genre = extract_beatport_track_info(bp_json)
            qb_id, qb_bpm, qb_key, qb_genre = extract_qobuz_track_info(qb_json)
            sp_id, sp_bpm, sp_key, sp_genre = extract_spotify_track_info(sp_json)

            canonical_bpm, canonical_key, canonical_genre = choose_canonical(
                bp_bpm, qb_bpm, tidal_bpm, sp_bpm,
                bp_key, qb_key, tidal_key, sp_key,
                bp_genre, qb_genre, tidal_genre, sp_genre
            )

            rows.append({
                "row_index": row_index,
                "tidal_id": tidal_id,
                "beatport_id": bp_id,
                "qobuz_id": qb_id,
                "spotify_id": sp_id,
                "tidal_bpm": tidal_bpm,
                "beatport_bpm": bp_bpm,
                "qobuz_bpm": qb_bpm,
                "spotify_bpm": sp_bpm,
                "canonical_bpm": canonical_bpm,
                "tidal_key": tidal_key,
                "beatport_key": bp_key,
                "qobuz_key": qb_key,
                "spotify_key": sp_key,
                "canonical_key": canonical_key,
                "tidal_genre": tidal_genre,
                "beatport_genre": bp_genre,
                "qobuz_genre": qb_genre,
                "spotify_genre": sp_genre,
                "canonical_genre": canonical_genre,
            })

    fieldnames = [
        "row_index",
        "tidal_id", "beatport_id", "qobuz_id", "spotify_id",
        "tidal_bpm", "beatport_bpm", "qobuz_bpm", "spotify_bpm", "canonical_bpm",
        "tidal_key", "beatport_key", "qobuz_key", "spotify_key", "canonical_key",
        "tidal_genre", "beatport_genre", "qobuz_genre", "spotify_genre", "canonical_genre",
    ]

    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
