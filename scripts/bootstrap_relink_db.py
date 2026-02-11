#!/usr/bin/env python3
"""Create a fresh relink DB seeded with authoritative reference tables.

This workflow is intended for path churn events (for example Picard rename/move):
- keep authoritative metadata entries and duration references
- rebuild files/path inventory from current filesystem state
- avoid deep scans (no full-file hashing by default in register phase)
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from dedupe.storage.schema import init_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a fresh DB for path relink by copying reference tables."
    )
    parser.add_argument("--from-db", type=Path, required=True, help="Source DB path.")
    parser.add_argument("--to-db", type=Path, required=True, help="Target DB path.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite target DB if it already exists.",
    )
    return parser.parse_args()


def _copy_track_duration_refs(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO track_duration_refs
            (ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at)
        SELECT
            ref_id, ref_type, duration_ref_ms, ref_source, ref_updated_at
        FROM olddb.track_duration_refs
        """
    )
    row = conn.execute("SELECT COUNT(*) FROM track_duration_refs").fetchone()
    return int(row[0]) if row else 0


def _copy_library_tracks(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO library_tracks
            (
                library_track_key, title, artist, album, duration_ms, isrc,
                release_date, explicit, best_cover_url, lyrics_excerpt,
                genre, bpm, musical_key, label, created_at, updated_at
            )
        SELECT
            library_track_key, title, artist, album, duration_ms, isrc,
            release_date, explicit, best_cover_url, lyrics_excerpt,
            genre, bpm, musical_key, label, created_at, updated_at
        FROM olddb.library_tracks
        """
    )
    row = conn.execute("SELECT COUNT(*) FROM library_tracks").fetchone()
    return int(row[0]) if row else 0


def _copy_library_track_sources(conn: sqlite3.Connection) -> int:
    conn.execute(
        """
        INSERT OR REPLACE INTO library_track_sources
            (
                library_track_key, service, service_track_id, url, metadata_json,
                duration_ms, isrc, album_art_url, pdf_companions, lyrics_excerpt,
                genre, bpm, musical_key, album_title, artist_name,
                track_number, disc_number, match_confidence, fetched_at
            )
        SELECT
            library_track_key, service, service_track_id, url, metadata_json,
            duration_ms, isrc, album_art_url, pdf_companions, lyrics_excerpt,
            genre, bpm, musical_key, album_title, artist_name,
            track_number, disc_number, match_confidence, fetched_at
        FROM olddb.library_track_sources
        """
    )
    row = conn.execute("SELECT COUNT(*) FROM library_track_sources").fetchone()
    return int(row[0]) if row else 0


def main() -> int:
    args = parse_args()
    src = args.from_db.expanduser().resolve()
    dst = args.to_db.expanduser().resolve()

    if not src.exists():
        raise SystemExit(f"Source DB not found: {src}")
    if dst.exists() and not args.force:
        raise SystemExit(f"Target DB already exists: {dst} (use --force to overwrite)")

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()

    conn = sqlite3.connect(str(dst))
    try:
        init_db(conn)
        conn.execute(f"ATTACH DATABASE '{src}' AS olddb")

        refs = _copy_track_duration_refs(conn)
        tracks = _copy_library_tracks(conn)
        sources = _copy_library_track_sources(conn)

        conn.commit()
        conn.execute("DETACH DATABASE olddb")

        print("Created relink DB:")
        print(f"  target: {dst}")
        print(f"  copied track_duration_refs:   {refs}")
        print(f"  copied library_tracks:        {tracks}")
        print(f"  copied library_track_sources: {sources}")
        print("Next step:")
        print(
            "  poetry run tagslut index register /Volumes/MUSIC/LIBRARY "
            f"--source legacy --db {dst} --execute --no-prompt"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
