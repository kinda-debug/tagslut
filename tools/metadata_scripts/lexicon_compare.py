#!/usr/bin/env python3
"""Compare Lexicon CSV tags against current file tags and DB canonical values.

Matches by (artist, title, albumTitle) since Lexicon CSV lacks Location.
Outputs a report with ambiguous/missing matches.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from mutagen import File as MutagenFile

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tagslut.utils.db import DbResolutionError, resolve_cli_env_db_path


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _key(artist: str, title: str, album: str) -> str:
    return f"{_norm(artist)}|{_norm(title)}|{_norm(album)}"


def _read_easy(path: Path) -> Dict[str, List[str]]:
    try:
        audio = MutagenFile(str(path), easy=True)
    except Exception:
        return {}
    if audio is None or not audio.tags:
        return {}
    return {str(k).lower(): [str(v) for v in vals] for k, vals in audio.tags.items()}


def _first(tags: Dict[str, List[str]], *keys: str) -> str:
    for key in keys:
        vals = tags.get(key.lower())
        if vals:
            return str(vals[0])
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Lexicon CSV tags with current tags and DB.")
    parser.add_argument("--csv", required=True, help="Lexicon CSV path.")
    parser.add_argument("--db", help="tagslut DB path.")
    parser.add_argument("--output", default="", help="Output CSV path.")
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")

    try:
        db_resolution = resolve_cli_env_db_path(args.db, purpose="read", source_label="--db")
    except DbResolutionError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    db_path = db_resolution.path
    print(f"Resolved DB path: {db_path}")

    out_path = Path(args.output).expanduser().resolve() if args.output else csv_path.with_name(csv_path.stem + "_compare.csv")

    # Build DB index by artist/title/album
    db_index: Dict[str, List[Tuple[str, Dict[str, str]]]] = defaultdict(list)
    with sqlite3.connect(str(db_path)) as conn:
        for row in conn.execute(
            """
            SELECT path, canonical_title, canonical_artist, canonical_album,
                   canonical_bpm, canonical_key, canonical_genre, canonical_energy, canonical_danceability
            FROM files
            WHERE canonical_title IS NOT NULL AND canonical_artist IS NOT NULL
            """
        ):
            path, title, artist, album, bpm, key, genre, energy, dance = row
            k = _key(str(artist or ""), str(title or ""), str(album or ""))
            db_index[k].append(
                (
                    str(path),
                    {
                        "db_bpm": "" if bpm is None else str(bpm),
                        "db_key": str(key or ""),
                        "db_genre": str(genre or ""),
                        "db_energy": "" if energy is None else str(energy),
                        "db_danceability": "" if dance is None else str(dance),
                    },
                )
            )

    fields = [
        "match_status",
        "path",
        "artist",
        "title",
        "albumTitle",
        "lex_bpm",
        "lex_key",
        "lex_genre",
        "lex_energy",
        "file_bpm",
        "file_key",
        "file_genre",
        "file_energy",
        "file_danceability",
        "file_comment",
        "db_bpm",
        "db_key",
        "db_genre",
        "db_energy",
        "db_danceability",
        "candidates",
    ]

    with csv_path.open("r", encoding="utf-8", errors="replace") as src, out_path.open("w", newline="", encoding="utf-8") as out:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(out, fieldnames=fields)
        writer.writeheader()

        for row in reader:
            artist = row.get("artist", "") or row.get("Artist", "")
            title = row.get("title", "") or row.get("Title", "")
            album = row.get("albumTitle", "") or row.get("AlbumTitle", "")
            k = _key(artist, title, album)
            candidates = db_index.get(k, [])

            if not candidates:
                writer.writerow(
                    {
                        "match_status": "missing",
                        "artist": artist,
                        "title": title,
                        "albumTitle": album,
                        "lex_bpm": row.get("bpm", ""),
                        "lex_key": row.get("key", ""),
                        "lex_genre": row.get("genre", ""),
                        "lex_energy": row.get("energy", ""),
                        "candidates": "0",
                    }
                )
                continue

            if len(candidates) > 1:
                writer.writerow(
                    {
                        "match_status": "ambiguous",
                        "artist": artist,
                        "title": title,
                        "albumTitle": album,
                        "lex_bpm": row.get("bpm", ""),
                        "lex_key": row.get("key", ""),
                        "lex_genre": row.get("genre", ""),
                        "lex_energy": row.get("energy", ""),
                        "candidates": ";".join([c[0] for c in candidates[:5]]),
                    }
                )
                continue

            path, db_vals = candidates[0]
            tags = _read_easy(Path(path))
            writer.writerow(
                {
                    "match_status": "ok",
                    "path": path,
                    "artist": artist,
                    "title": title,
                    "albumTitle": album,
                    "lex_bpm": row.get("bpm", ""),
                    "lex_key": row.get("key", ""),
                    "lex_genre": row.get("genre", ""),
                    "lex_energy": row.get("energy", ""),
                    "file_bpm": _first(tags, "bpm"),
                    "file_key": _first(tags, "key", "initialkey"),
                    "file_genre": _first(tags, "genre"),
                    "file_energy": _first(tags, "1t_energy", "energy"),
                    "file_danceability": _first(tags, "1t_danceability", "danceability"),
                    "file_comment": _first(tags, "comment"),
                    "db_bpm": db_vals["db_bpm"],
                    "db_key": db_vals["db_key"],
                    "db_genre": db_vals["db_genre"],
                    "db_energy": db_vals["db_energy"],
                    "db_danceability": db_vals["db_danceability"],
                    "candidates": "1",
                }
            )

    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
