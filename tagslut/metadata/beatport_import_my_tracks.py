#!/usr/bin/env python3
"""
beatport_import_my_tracks.py

Imports Beatport tracks from beatport_my_tracks.ndjson into the SQLite database.
Each row is inserted into library_track_sources with service='beatport'.

Usage:
    source ./env_exports.sh
    python3 beatport_import_my_tracks.py

    # Or with explicit paths:
    python3 beatport_import_my_tracks.py --input beatport_my_tracks.ndjson --db /path/to/music.db

Environment Variables:
    MUSIC_DB: Path to SQLite database (default from metadata_guide.md)
    BEATPORT_MY_TRACKS_NDJSON: Input NDJSON file (default: beatport_my_tracks.ndjson)

The script:
1. Reads NDJSON rows from beatport_my_tracks.ndjson
2. For each track, creates/updates library_track_key (using ISRC or artist::title)
3. Inserts into library_track_sources with full metadata
4. Optionally updates library_tracks canonical table

Schema follows metadata_guide.md Section 2.3.
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Default paths - prefer environment variables for safety
# MUSIC_DB should be set to avoid accidental writes to wrong database
DEFAULT_NDJSON_PATH = "beatport_my_tracks.ndjson"


def get_db_path() -> Path:
    """
    Get database path from environment.

    Requires MUSIC_DB environment variable to be set for safety.
    Falls back to ./music.db (relative path) if not set, but warns.
    """
    db_path = os.environ.get("MUSIC_DB")
    if not db_path:
        print(
            "WARNING: MUSIC_DB environment variable not set. "
            "Using ./music.db as fallback. Set MUSIC_DB to specify database path.",
            file=sys.stderr
        )
        return Path("./music.db")
    return Path(db_path)


def get_ndjson_path() -> Path:
    """Get NDJSON input path from environment or default."""
    return Path(os.environ.get("BEATPORT_MY_TRACKS_NDJSON", DEFAULT_NDJSON_PATH))


def generate_library_track_key(row: Dict[str, Any]) -> str:
    """
    Generate a library_track_key for the track.

    Priority:
    1. ISRC if available (most reliable cross-service identifier)
    2. Fallback to "artist::title" normalized

    Matches the strategy in metadata_guide.md Section 5.3.
    """
    isrc = row.get("isrc")
    if isrc and isinstance(isrc, str) and isrc.strip():
        return isrc.strip().upper()  # type: ignore  # TODO: mypy-strict

    # Fallback: artist::title
    artists = row.get("artists", [])
    if isinstance(artists, list) and artists:
        artist = ", ".join(str(a) for a in artists if a)
    else:
        artist = row.get("artist", "")

    title = row.get("title", "")
    mix_name = row.get("mix_name", "")

    # Include mix name in title for uniqueness
    if mix_name and mix_name.lower() not in (title or "").lower():
        full_title = f"{title} ({mix_name})" if title else mix_name
    else:
        full_title = title or ""

    if artist and full_title:
        return f"{artist}::{full_title}".lower().strip()
    elif full_title:
        return f"unknown::{full_title}".lower().strip()
    elif row.get("track_id"):
        return f"beatport::{row['track_id']}"
    else:
        return f"unknown::{datetime.now().isoformat()}"


def ensure_library_track(
    conn: sqlite3.Connection,
    library_track_key: str,
    row: Dict[str, Any]
) -> None:
    """
    Ensure a library_tracks row exists for this track key.

    Creates if not exists, updates if Beatport data is better.
    """
    cur = conn.cursor()

    # Check if exists
    cur.execute(
        "SELECT id FROM library_tracks WHERE library_track_key = ?",
        (library_track_key,)
    )
    existing = cur.fetchone()

    # Build canonical fields from Beatport data
    artists = row.get("artists", [])
    if isinstance(artists, list) and artists:
        artist = ", ".join(str(a) for a in artists if a)
    else:
        artist = None

    title = row.get("title")
    mix_name = row.get("mix_name")
    if mix_name and title:
        full_title = f"{title} ({mix_name})"
    else:
        full_title = title  # type: ignore  # TODO: mypy-strict

    duration_ms = row.get("length_ms")
    if duration_ms is None and row.get("duration_ms"):
        duration_ms = row.get("duration_ms")

    if existing:
        # Update with Beatport data (Beatport is high priority for BPM/key/genre)
        cur.execute("""
            UPDATE library_tracks SET
                bpm = COALESCE(?, bpm),
                musical_key = COALESCE(?, musical_key),
                genre = COALESCE(?, genre),
                label = COALESCE(?, label),
                isrc = COALESCE(?, isrc),
                duration_ms = COALESCE(?, duration_ms),
                updated_at = CURRENT_TIMESTAMP
            WHERE library_track_key = ?
        """, (
            row.get("bpm"),
            row.get("key_name") or row.get("key"),
            row.get("genre"),
            row.get("label_name"),
            row.get("isrc"),
            duration_ms,
            library_track_key,
        ))
    else:
        # Insert new
        cur.execute("""
            INSERT INTO library_tracks (
                library_track_key, title, artist, album, duration_ms,
                isrc, release_date, genre, bpm, musical_key, label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            library_track_key,
            full_title,
            artist,
            row.get("release_name"),
            duration_ms,
            row.get("isrc"),
            row.get("publish_date"),
            row.get("genre"),
            row.get("bpm"),
            row.get("key_name") or row.get("key"),
            row.get("label_name"),
        ))


def insert_library_track_source(
    conn: sqlite3.Connection,
    library_track_key: str,
    row: Dict[str, Any]
) -> None:
    """
    Insert a library_track_sources row for this Beatport track.

    Schema matches metadata_guide.md Section 2.3.
    """
    cur = conn.cursor()

    # Build artist name string
    artists = row.get("artists", [])
    if isinstance(artists, list) and artists:
        artist_name = ", ".join(str(a) for a in artists if a)
    else:
        artist_name = None

    # Duration in ms
    duration_ms = row.get("length_ms")
    if duration_ms is None and row.get("duration_ms"):
        duration_ms = row.get("duration_ms")

    # Raw JSON - get from 'raw' field or serialize the whole row
    raw_json = row.get("raw", {})
    if not raw_json:
        # Create a copy without 'raw' to avoid recursion
        raw_json = {k: v for k, v in row.items() if k != "raw"}
    metadata_json = json.dumps(raw_json, ensure_ascii=False)

    # Musical key - prefer key_name, fall back to key
    musical_key = row.get("key_name") or row.get("key")

    # Build URL for the track
    track_id = row.get("track_id")
    url = f"https://www.beatport.com/track/-/{track_id}" if track_id else None

    cur.execute("""
        INSERT INTO library_track_sources (
            library_track_key,
            service,
            service_track_id,
            url,
            metadata_json,
            duration_ms,
            isrc,
            album_art_url,
            genre,
            bpm,
            musical_key,
            album_title,
            artist_name,
            match_confidence,
            fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (
        library_track_key,
        "beatport",
        str(track_id) if track_id else None,
        url,
        metadata_json,
        duration_ms,
        row.get("isrc"),
        row.get("artwork_url"),
        row.get("genre"),
        row.get("bpm"),
        musical_key,
        row.get("release_name"),
        artist_name,
        "exact",  # Direct from Beatport API = exact match
    ))


def import_ndjson(ndjson_path: Path, db_path: Path, dry_run: bool = False) -> int:
    """
    Import all tracks from NDJSON file into database.

    Args:
        ndjson_path: Path to beatport_my_tracks.ndjson
        db_path: Path to SQLite database
        dry_run: If True, don't commit changes

    Returns:
        Number of tracks imported
    """
    if not ndjson_path.exists():
        print(f"ERROR: NDJSON file not found: {ndjson_path}", file=sys.stderr)
        return 0

    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    imported = 0
    skipped = 0
    errors = 0

    print(f"Importing from: {ndjson_path}")
    print(f"Database: {db_path}")
    print(f"Dry run: {dry_run}")
    print("-" * 60)

    # Wrap entire import in a transaction for atomicity
    try:
        with ndjson_path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    row = json.loads(line)
                except json.JSONDecodeError as e:
                    print(f"  Line {line_num}: JSON parse error: {e}", file=sys.stderr)
                    errors += 1
                    continue

                # Skip if not a beatport track
                if row.get("service") != "beatport":
                    skipped += 1
                    continue

                track_id = row.get("track_id")
                title = row.get("title", "Unknown")

                try:
                    library_track_key = generate_library_track_key(row)

                    if not dry_run:
                        ensure_library_track(conn, library_track_key, row)
                        insert_library_track_source(conn, library_track_key, row)

                    imported += 1

                    if imported % 100 == 0:
                        print(f"  Imported {imported} tracks...")

                except sqlite3.Error as e:
                    print(f"  Line {line_num}: DB error for track {track_id} ({title}): {e}", file=sys.stderr)
                    errors += 1
                    # Continue processing other tracks, but don't commit partial work
                    continue

        # Commit only if no critical errors and not dry run
        if not dry_run:
            conn.commit()
            print("Transaction committed successfully.")

    except Exception as e:
        # Rollback on any unexpected error
        conn.rollback()
        print(f"ERROR: Import failed, transaction rolled back: {e}", file=sys.stderr)
        conn.close()
        return 0

    conn.close()

    print("-" * 60)
    print("Import complete:")
    print(f"  Imported: {imported}")
    print(f"  Skipped:  {skipped}")
    print(f"  Errors:   {errors}")

    return imported


def main():  # type: ignore  # TODO: mypy-strict
    parser = argparse.ArgumentParser(
        description="Import Beatport tracks from NDJSON into SQLite database"
    )
    parser.add_argument(
        "--input", "-i",
        type=Path,
        default=None,
        help=f"Input NDJSON file (default: {DEFAULT_NDJSON_PATH} or BEATPORT_MY_TRACKS_NDJSON env)"
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite database path (default: MUSIC_DB env, or ./music.db with warning)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing to database"
    )

    args = parser.parse_args()

    ndjson_path = args.input or get_ndjson_path()
    db_path = args.db or get_db_path()

    count = import_ndjson(ndjson_path, db_path, dry_run=args.dry_run)

    sys.exit(0 if count > 0 else 1)


if __name__ == "__main__":
    main()  # type: ignore  # TODO: mypy-strict
