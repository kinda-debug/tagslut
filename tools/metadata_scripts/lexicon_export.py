#!/usr/bin/env python3
"""Export a Lexicon DJ-compatible CSV for DJ-eligible tracks.

Filters:
- duration between min/max seconds
- bpm within min/max (half-tempo allowed)
- exclude genre keywords
- exclude title/album keywords (unless remix/edit/rework)
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path

DEFAULT_OUT_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "exports"
DEFAULT_MIN_DURATION_SEC = 240
DEFAULT_MAX_DURATION_SEC = 900
DEFAULT_MIN_BPM = 90.0
DEFAULT_MAX_BPM = 190.0
DEFAULT_EXCLUDE_GENRES = "classical,opera,symphony,concerto,folk,acoustic,singer-songwriter,soundtrack,film score,score,spoken word,audiobook,gospel,sermon"
DEFAULT_EXCLUDE_TITLE_KEYWORDS = "mix,mixed,dj mix,radio mix,continuous mix,mixset"

MIX_EXCEPTIONS = ("remix", "rework", "edit")


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _duration_ok(duration: float | None, min_sec: int, max_sec: int) -> bool:
    if duration is None:
        return True
    if duration <= 0:
        return False
    return min_sec <= duration <= max_sec


def _bpm_ok(bpm: float | None, min_bpm: float, max_bpm: float) -> bool:
    if bpm is None:
        return True
    if bpm <= 0:
        return False
    if min_bpm <= bpm <= max_bpm:
        return True
    if min_bpm <= bpm * 2 <= max_bpm:
        return True
    return False


def _genre_blocked(genre: str, excluded: list[str]) -> bool:
    if not genre:
        return False
    g = genre.lower()
    return any(token in g for token in excluded)


def _title_blocked(title: str, album: str, keywords: list[str]) -> bool:
    hay = f"{title} {album}".lower()
    if not hay.strip():
        return False
    if any(word in hay for word in MIX_EXCEPTIONS):
        return False
    return any(key in hay for key in keywords)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Lexicon DJ CSV for DJ-eligible tracks.")
    parser.add_argument("--db", help="Path to tagslut SQLite DB.")
    parser.add_argument("--output", default="", help="Output path (CSV or M3U).")
    parser.add_argument("--format", choices=["m3u", "csv"], default="m3u", help="Export format.")
    parser.add_argument("--min-duration", type=int, default=DEFAULT_MIN_DURATION_SEC)
    parser.add_argument("--max-duration", type=int, default=DEFAULT_MAX_DURATION_SEC)
    parser.add_argument("--min-bpm", type=float, default=DEFAULT_MIN_BPM)
    parser.add_argument("--max-bpm", type=float, default=DEFAULT_MAX_BPM)
    parser.add_argument("--exclude-genres", default=DEFAULT_EXCLUDE_GENRES)
    parser.add_argument("--exclude-title-keywords", default=DEFAULT_EXCLUDE_TITLE_KEYWORDS)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose="read", source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db_path = db_resolution.path
    print(f"Resolved DB path: {db_path}")

    suffix = "m3u" if args.format == "m3u" else "csv"
    out_path = Path(args.output).expanduser().resolve() if args.output else (DEFAULT_OUT_DIR / f"lexicon_export_{_now_stamp()}.{suffix}")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    exclude_genres = [part.strip().lower() for part in args.exclude_genres.split(",") if part.strip()]
    exclude_title_keywords = [part.strip().lower() for part in args.exclude_title_keywords.split(",") if part.strip()]

    fields = [
        "Location",
        "Title",
        "Artist",
        "AlbumTitle",
        "Genre",
        "Key",
        "BPM",
        "Energy",
        "Danceability",
        "Label",
        "Remixer",
        "Mix",
        "Year",
        "ISRC",
        "Duration",
    ]

    sql = """
    SELECT
        path,
        canonical_title,
        canonical_artist,
        canonical_album,
        canonical_genre,
        canonical_key,
        canonical_bpm,
        canonical_energy,
        canonical_danceability,
        canonical_label,
        canonical_mix_name,
        canonical_year,
        canonical_isrc,
        canonical_duration,
        canonical_catalog_number
    FROM files
    WHERE path IS NOT NULL AND trim(path) != ''
    ORDER BY path
    """

    written = 0
    with sqlite3.connect(str(db_path)) as conn, out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = None
        if args.format == "csv":
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
        for row in conn.execute(sql):
            (
                path,
                title,
                artist,
                album,
                genre,
                key,
                bpm,
                energy,
                dance,
                label,
                mix,
                year,
                isrc,
                duration,
                _catalog,
            ) = row

            if not _duration_ok(duration, args.min_duration, args.max_duration):
                continue
            if not _bpm_ok(bpm, args.min_bpm, args.max_bpm):
                continue
            if _genre_blocked(str(genre or ""), exclude_genres):
                continue
            if _title_blocked(str(title or ""), str(album or ""), exclude_title_keywords):
                continue

            if args.format == "csv" and writer is not None:
                writer.writerow(
                    {
                        "Location": str(path),
                        "Title": str(title or ""),
                        "Artist": str(artist or ""),
                        "AlbumTitle": str(album or ""),
                        "Genre": str(genre or ""),
                        "Key": str(key or ""),
                        "BPM": "" if bpm is None else bpm,
                        "Energy": "" if energy is None else energy,
                        "Danceability": "" if dance is None else dance,
                        "Label": str(label or ""),
                        "Remixer": "",
                        "Mix": str(mix or ""),
                        "Year": "" if year is None else year,
                        "ISRC": str(isrc or ""),
                        "Duration": "" if duration is None else duration,
                    }
                )
            else:
                handle.write(f"{path}\\n")
            written += 1
            if args.limit and written >= args.limit:
                break

    print(f"Wrote: {out_path}")
    print(f"Rows: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
