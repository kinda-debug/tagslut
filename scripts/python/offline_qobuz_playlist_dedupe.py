#!/usr/bin/env python3
"""
Offline Qobuz playlist deduper.

This script works on local playlist exports (CSV and/or JSON) without calling the Qobuz API.

Supported input formats
-----------------------
1) CSV playlist exports with columns (at minimum):
   - playlist_id
   - playlist_name
   - track_id
   - artist
   - title
   - album (optional)
   - isrc (optional)
   - duration_seconds (optional)
   - qobuz_url (optional)

   Example (one row per track per playlist):
       playlist_name,playlist_id,position,track_id,isrc,artist,title,album,duration_seconds,qobuz_url
       An Introduction to Qobuz,504746,1,41805683,FRX851700792,Melanie De Biasio,Your Freedom Is the End of Me,Lilies,230,https://...

2) Qobuz playlist JSON payloads, each file containing a single playlist
   in the format returned by Qobuz's /playlist/get API:
       {
         "id": 504746,
         "name": "An Introduction to Qobuz",
         "tracks": {
             "items": [
                 { "id": 41805683, "isrc": "...", "title": "...",
                   "performer": {"name": "..."}, "album": {"title": "..."}, ... },
                 ...
             ],
             ...
         },
         ...
       }

What the script does
--------------------
- Scans an input directory for:
    * *.csv files containing playlist_id + playlist_name (treated as playlist track tables)
    * *.json files with Qobuz playlist payloads
- Builds a unified in-memory representation:
    playlist_id -> {
        "name": <playlist_name>,
        "tracks": [ { "track_id": ..., "isrc": ..., "artist": ..., "title": ..., "album": ..., ... }, ... ]
    }
- For each playlist:
    - Deduplicates tracks using three-tier keys:
        1. ISRC (case-insensitive, stripped)
        2. (normalized artist, normalized title)
        3. track_id
      A track is removed as a duplicate if any of these keys have been seen before in that playlist.
    - Preserves original order of first occurrences.
- Writes outputs:
    - <output_dir>/playlists_csv/<playlist_name>__<playlist_id>.csv
    - <output_dir>/playlists_json/<playlist_name>__<playlist_id>.json
    - <output_dir>/summary.csv

Usage
-----
    python3 offline_qobuz_playlist_dedupe.py \
        --input-dir /path/to/playlist_exports \
        --output-dir /path/to/deduped_output

Options
-------
    --input-dir     Directory containing CSV/JSON playlist exports.
    --output-dir    Directory to write deduped playlists and summary.
    --include-empty Also write outputs for playlists that end up with 0 tracks (default: skip).
    --strict        Fail if an input CSV does not contain required columns instead of skipping it.
"""

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from typing import Dict, List, Any, Tuple, Optional


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def normalize_text(s: Optional[str]) -> str:
    """
    Basic normalization for dedupe keys:
    - None -> ""
    - strip whitespace
    - Unicode NFKC normalization
    - lowercasing
    - collapse internal whitespace
    """
    if not s:
        return ""
    s = str(s)
    s = unicodedata.normalize("NFKC", s)
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def safe_filename(name: str) -> str:
    """
    Convert playlist name into a filesystem-safe base name.
    """
    if not name:
        name = "unnamed_playlist"
    name = str(name).strip()
    # Replace path separators and problematic chars
    name = re.sub(r"[<>:\"/\\|?*]", "_", name)
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    # Truncate to a reasonable length
    if len(name) > 120:
        name = name[:120].rstrip()
    return name or "unnamed_playlist"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class Playlist:
    """
    In-memory representation of a playlist.
    """
    def __init__(self, playlist_id: str, name: str):
        self.id = str(playlist_id) if playlist_id is not None else ""
        self.name = name or f"playlist_{self.id or 'unknown'}"
        self.tracks: List[Dict[str, Any]] = []
        self.source_files: List[str] = []

    def add_track(self, track: Dict[str, Any]) -> None:
        self.tracks.append(track)

    def add_source_file(self, path: str) -> None:
        if path not in self.source_files:
            self.source_files.append(path)


# ---------------------------------------------------------------------------
# Loading CSV playlist exports
# ---------------------------------------------------------------------------

REQUIRED_PLAYLIST_CSV_COLS = {"playlist_id", "playlist_name", "track_id", "artist", "title"}


def load_csv_playlists(path: str,
                       playlists: Dict[str, Playlist],
                       strict: bool = False) -> None:
    """
    Load playlists from a CSV file in the "An Introduction to Qobuz.csv" schema.

    A file is treated as a playlist-track table if it contains at least
    the REQUIRED_PLAYLIST_CSV_COLS columns.

    Multiple files can contain rows for the same playlist_id; they will be merged.
    """
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])

        if not REQUIRED_PLAYLIST_CSV_COLS.issubset(cols):
            msg = (f"Skipping CSV '{path}': missing required columns. "
                   f"Found: {sorted(cols)}, required: {sorted(REQUIRED_PLAYLIST_CSV_COLS)}")
            if strict:
                raise ValueError(msg)
            else:
                print(msg, file=sys.stderr)
                return

        for row in reader:
            playlist_id = str(row.get("playlist_id", "")).strip()
            playlist_name = (row.get("playlist_name") or "").strip()

            if not playlist_id and not playlist_name:
                # Can't associate this row to a playlist; skip
                continue

            key = playlist_id or playlist_name
            if key not in playlists:
                playlists[key] = Playlist(playlist_id=playlist_id or key,
                                          name=playlist_name or key)
            pl = playlists[key]
            pl.add_source_file(path)

            # Prepare normalized track dict
            track = {
                "playlist_id": pl.id,
                "playlist_name": pl.name,
                "position": row.get("position"),
                "track_id": str(row.get("track_id") or "").strip(),
                "isrc": (row.get("isrc") or "").strip(),
                "artist": (row.get("artist") or "").strip(),
                "title": (row.get("title") or "").strip(),
                "album": (row.get("album") or "").strip(),
                "duration_seconds": row.get("duration_seconds"),
                "qobuz_url": (row.get("qobuz_url") or "").strip(),
            }
            pl.add_track(track)


# ---------------------------------------------------------------------------
# Loading JSON playlist exports
# ---------------------------------------------------------------------------

def load_json_playlist(path: str,
                       playlists: Dict[str, Playlist],
                       strict: bool = False) -> None:
    """
    Load a single Qobuz playlist JSON payload.

    The file is expected to be a dict with:
        - "id" (playlist id)
        - "name" (playlist title)
        - "tracks": either:
            * dict with "items": [track, ...], or
            * list of tracks directly, or
            * absent/empty
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        msg = f"Skipping JSON '{path}': invalid JSON ({e})"
        if strict:
            raise
        else:
            print(msg, file=sys.stderr)
            return

    if not isinstance(data, dict):
        msg = f"Skipping JSON '{path}': top-level JSON is not an object."
        if strict:
            raise ValueError(msg)
        else:
            print(msg, file=sys.stderr)
            return

    playlist_id = data.get("id")
    playlist_name = data.get("name") or data.get("title") or f"playlist_{playlist_id or 'unknown'}"

    if playlist_id is None and not playlist_name:
        msg = f"Skipping JSON '{path}': missing 'id' and 'name'/'title'."
        if strict:
            raise ValueError(msg)
        else:
            print(msg, file=sys.stderr)
            return

    key = str(playlist_id) if playlist_id is not None else playlist_name
    if key not in playlists:
        playlists[key] = Playlist(playlist_id=str(playlist_id) if playlist_id is not None else key,
                                  name=playlist_name)
    pl = playlists[key]
    pl.add_source_file(path)

    # Extract tracks
    tracks_obj = data.get("tracks")
    if isinstance(tracks_obj, dict):
        items = tracks_obj.get("items") or []
    elif isinstance(tracks_obj, list):
        items = tracks_obj
    else:
        items = []

    if not isinstance(items, list):
        msg = f"JSON '{path}': 'tracks' not a list or dict with 'items'; got {type(tracks_obj)}."
        if strict:
            raise ValueError(msg)
        else:
            print(msg, file=sys.stderr)
            items = []

    for item in items:
        if not isinstance(item, dict):
            continue

        track_id = item.get("id") or item.get("track_id") or ""
        isrc = item.get("isrc") or ""
        title = item.get("title") or item.get("track_title") or ""

        # Artist name
        artist_name = ""
        performer = item.get("performer")
        if isinstance(performer, dict) and performer.get("name"):
            artist_name = performer["name"]
        elif isinstance(item.get("artist"), dict) and item["artist"].get("name"):
            artist_name = item["artist"]["name"]
        elif isinstance(item.get("artist"), str):
            artist_name = item["artist"]

        # Album title
        album_title = ""
        album = item.get("album")
        if isinstance(album, dict) and album.get("title"):
            album_title = album["title"]
        elif isinstance(item.get("release"), dict) and item["release"].get("title"):
            album_title = item["release"]["title"]

        duration = item.get("duration")
        url = item.get("url") or item.get("permalink") or ""

        track = {
            "playlist_id": pl.id,
            "playlist_name": pl.name,
            "position": item.get("position"),
            "track_id": str(track_id),
            "isrc": str(isrc).strip(),
            "artist": str(artist_name).strip(),
            "title": str(title).strip(),
            "album": str(album_title).strip(),
            "duration_seconds": duration,
            "qobuz_url": str(url).strip(),
        }
        pl.add_track(track)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def build_track_keys(track: Dict[str, Any]) -> Tuple[Optional[str], Optional[Tuple[str, str]], Optional[str]]:
    """
    Build a tuple of dedupe keys for a single track:
      - primary: ISRC (uppercased, stripped) if available
      - secondary: (normalized artist, normalized title) if any
      - tertiary: track_id (string) if available
    """
    isrc = track.get("isrc") or ""
    isrc_key = isrc.strip().upper() or None

    artist = normalize_text(track.get("artist"))
    title = normalize_text(track.get("title"))
    secondary = (artist, title) if artist or title else None

    track_id = str(track.get("track_id") or "").strip() or None

    return isrc_key, secondary, track_id


def dedupe_tracks(tracks: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    """
    Deduplicate a list of tracks while preserving original order.

    Returns:
        (deduped_tracks, duplicates_removed_count)
    """
    seen_isrc = set()
    seen_artist_title = set()
    seen_track_id = set()

    deduped: List[Dict[str, Any]] = []
    removed = 0

    for t in tracks:
        isrc_key, secondary, track_id = build_track_keys(t)

        duplicate = False
        if isrc_key and isrc_key in seen_isrc:
            duplicate = True
        elif secondary and secondary in seen_artist_title:
            duplicate = True
        elif track_id and track_id in seen_track_id:
            duplicate = True

        if duplicate:
            removed += 1
            continue

        if isrc_key:
            seen_isrc.add(isrc_key)
        if secondary:
            seen_artist_title.add(secondary)
        if track_id:
            seen_track_id.add(track_id)

        deduped.append(t)

    return deduped, removed


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_playlist_csv(out_dir: str, playlist: Playlist, tracks: List[Dict[str, Any]]) -> str:
    """
    Write a single playlist as CSV and return the path.
    """
    os.makedirs(out_dir, exist_ok=True)
    base = f"{safe_filename(playlist.name)}__{playlist.id or 'noid'}.csv"
    path = os.path.join(out_dir, base)

    fieldnames = [
        "playlist_name",
        "playlist_id",
        "position",
        "track_id",
        "isrc",
        "artist",
        "title",
        "album",
        "duration_seconds",
        "qobuz_url",
    ]

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for idx, t in enumerate(tracks, start=1):
            row = {
                "playlist_name": playlist.name,
                "playlist_id": playlist.id,
                "position": t.get("position") if t.get("position") not in (None, "", 0) else idx,
                "track_id": t.get("track_id"),
                "isrc": t.get("isrc"),
                "artist": t.get("artist"),
                "title": t.get("title"),
                "album": t.get("album"),
                "duration_seconds": t.get("duration_seconds"),
                "qobuz_url": t.get("qobuz_url"),
            }
            writer.writerow(row)
    return path


def write_playlist_json(out_dir: str, playlist: Playlist, tracks: List[Dict[str, Any]]) -> str:
    """
    Write a single playlist as a JSON payload (simple, tool-friendly).
    """
    os.makedirs(out_dir, exist_ok=True)
    base = f"{safe_filename(playlist.name)}__{playlist.id or 'noid'}.json"
    path = os.path.join(out_dir, base)

    payload = {
        "playlist_id": playlist.id,
        "playlist_name": playlist.name,
        "tracks": tracks,
        "source_files": playlist.source_files,
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def write_summary(out_dir: str, rows: List[Dict[str, Any]]) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "summary.csv")

    fieldnames = [
        "playlist_id",
        "playlist_name",
        "track_count_original",
        "track_count_deduped",
        "duplicates_removed",
    ]

    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scan_input_directory(input_dir: str,
                         strict: bool = False) -> Dict[str, Playlist]:
    """
    Discover playlists from all CSV and JSON files in input_dir.
    """
    playlists: Dict[str, Playlist] = {}

    for root, _dirs, files in os.walk(input_dir):
        for name in files:
            path = os.path.join(root, name)
            lower = name.lower()

            try:
                if lower.endswith(".csv"):
                    # Only treat CSVs as playlist-track exports if they have the required columns
                    # (checked inside load_csv_playlists).
                    load_csv_playlists(path, playlists, strict=strict)
                elif lower.endswith(".json"):
                    load_json_playlist(path, playlists, strict=strict)
                else:
                    continue
            except Exception as e:
                msg = f"Error reading '{path}': {e}"
                if strict:
                    raise
                else:
                    print(msg, file=sys.stderr)

    return playlists


def process_all(input_dir: str,
                output_dir: str,
                include_empty: bool = False,
                strict: bool = False) -> None:
    """
    Full pipeline: scan, dedupe, write outputs.
    """
    print(f"Scanning input directory: {input_dir}")
    playlists = scan_input_directory(input_dir, strict=strict)
    print(f"Discovered {len(playlists)} playlists.")

    if not playlists:
        print("No playlists found. Exiting.")
        return

    csv_out = os.path.join(output_dir, "playlists_csv")
    json_out = os.path.join(output_dir, "playlists_json")

    summary_rows: List[Dict[str, Any]] = []

    for idx, key in enumerate(sorted(playlists.keys()), start=1):
        pl = playlists[key]
        original_count = len(pl.tracks)
        print(f"[{idx}/{len(playlists)}] Playlist '{pl.name}' (id={pl.id}): {original_count} tracks before dedupe")

        deduped_tracks, removed = dedupe_tracks(pl.tracks)
        deduped_count = len(deduped_tracks)
        print(f"    -> {deduped_count} tracks after dedupe, {removed} duplicates removed")

        if deduped_count == 0 and not include_empty:
            print("    -> Empty after dedupe; skipping output files (use --include-empty to keep).")
        else:
            csv_path = write_playlist_csv(csv_out, pl, deduped_tracks)
            json_path = write_playlist_json(json_out, pl, deduped_tracks)
            print(f"    -> Wrote CSV:  {csv_path}")
            print(f"    -> Wrote JSON: {json_path}")

        summary_rows.append({
            "playlist_id": pl.id,
            "playlist_name": pl.name,
            "track_count_original": original_count,
            "track_count_deduped": deduped_count,
            "duplicates_removed": removed,
        })

    summary_path = write_summary(output_dir, summary_rows)
    print(f"\nSummary written to: {summary_path}")
    print("Done.")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline Qobuz playlist deduper (CSV/JSON, no API calls)."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing playlist CSV/JSON exports."
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where deduped playlists and summary will be written."
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Also write outputs for playlists that end up with zero tracks after dedupe."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on malformed files instead of skipping with a warning."
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        process_all(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            include_empty=args.include_empty,
            strict=args.strict,
        )
        return 0
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
