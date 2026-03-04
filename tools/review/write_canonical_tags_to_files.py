#!/usr/bin/env python3
"""
Write canonical_* fields from the tagslut DB into FLAC file tags.

Defaults are conservative:
- Only write missing tags (does not overwrite existing values).
- Uses canonical_* fields from files table.
- Supports --path (root) or --m3u list of paths.

Example:
  PYTHONPATH=/path/to/tagslut \
  python3 tools/review/write_canonical_tags_to_files.py \
    --db /path/to/music.db \
    --m3u /Volumes/MUSIC/LIBRARY/MDL_NEW_TRACKS.m3u \
    --execute
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable

from mutagen.flac import FLAC
from _progress import ProgressTracker


def iter_flacs_from_root(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    yield from root.rglob("*.flac")


def iter_flacs_from_m3u(m3u_path: Path) -> Iterable[Path]:
    for raw in m3u_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        p = Path(line)
        if p.suffix.lower() == ".flac":
            yield p


def get_row(conn: sqlite3.Connection, path: Path) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute("SELECT * FROM files WHERE path = ?", (str(path),)).fetchone()


def tag_exists(tags, key: str) -> bool:
    if tags is None:
        return False
    # mutagen tags are case-sensitive keys but mapping is best-effort
    return key in tags and tags[key]


def set_tag(tags, key: str, value: str) -> None:
    tags[key] = [value]


def main() -> int:
    ap = argparse.ArgumentParser(description="Write canonical_* fields into FLAC tags")
    ap.add_argument("--db", type=Path, required=True, help="SQLite DB path")
    ap.add_argument("--path", type=Path, help="Root path to scan (FLAC)")
    ap.add_argument("--m3u", type=Path, help="M3U file listing FLAC paths")
    ap.add_argument("--force", action="store_true", help="Overwrite existing tags")
    ap.add_argument("--execute", action="store_true", help="Write tags to files")
    ap.add_argument("--progress-interval", type=int, default=100, help="Progress print interval")
    args = ap.parse_args()

    if not args.path and not args.m3u:
        raise SystemExit("Provide --path or --m3u")

    db_path = args.db.expanduser().resolve()
    if not db_path.exists():
        raise SystemExit(f"DB not found: {db_path}")

    if args.m3u:
        sources = list(iter_flacs_from_m3u(args.m3u.expanduser().resolve()))
    else:
        sources = list(iter_flacs_from_root(args.path.expanduser().resolve()))

    if not sources:
        print("No FLAC files found.")
        return 1

    conn = sqlite3.connect(str(db_path))

    updated = 0
    skipped = 0
    missing = 0
    progress = ProgressTracker(total=len(sources), interval=int(args.progress_interval), label="Writeback")
    for idx, p in enumerate(sources, start=1):
        if not p.exists():
            missing += 1
            if progress.should_print(idx):
                print(progress.line(idx, extra=f"updated={updated} skipped={skipped} missing={missing}"))
            continue
        row = get_row(conn, p)
        if not row:
            skipped += 1
            if progress.should_print(idx):
                print(progress.line(idx, extra=f"updated={updated} skipped={skipped} missing={missing}"))
            continue

        audio = FLAC(p)
        tags = audio.tags

        updates = []

        def maybe_set(tag_key: str, value: str | None):
            if not value:
                return
            if args.force or not tag_exists(tags, tag_key):
                set_tag(tags, tag_key, str(value))
                updates.append(tag_key)

        # Core identity
        maybe_set("ARTIST", row["canonical_artist"])
        maybe_set("TITLE", row["canonical_title"])
        maybe_set("ALBUM", row["canonical_album"])

        # Dates
        date_val = row["canonical_release_date"] or row["canonical_year"]
        if date_val is not None:
            maybe_set("DATE", str(date_val))

        # IDs
        maybe_set("ISRC", row["canonical_isrc"])
        maybe_set("LABEL", row["canonical_label"])
        maybe_set("CATALOGNUMBER", row["canonical_catalog_number"])
        maybe_set("BEATPORT_TRACK_ID", row["beatport_id"])

        # Musical metadata
        if row["canonical_bpm"] is not None:
            maybe_set("BPM", str(row["canonical_bpm"]))
        if row["canonical_key"]:
            # Use INITIALKEY for DJ software compatibility
            maybe_set("INITIALKEY", row["canonical_key"])

        # Genre hierarchy
        genre = row["canonical_genre"]
        sub = row["canonical_sub_genre"]
        if genre:
            maybe_set("GENRE", genre)
        if sub:
            maybe_set("SUBGENRE", sub)
        if genre and sub:
            maybe_set("GENRE_FULL", f"{genre} | {sub}")
            maybe_set("GENRE_PREFERRED", genre)

        if updates:
            if args.execute:
                audio.save()
            updated += 1
        else:
            skipped += 1

        if progress.should_print(idx):
            print(progress.line(idx, extra=f"updated={updated} skipped={skipped} missing={missing}"))

    conn.close()

    print(f"Scanned:  {len(sources)}")
    print(f"Updated:  {updated}")
    print(f"Skipped:  {skipped}")
    print(f"Missing:  {missing}")
    if not args.execute:
        print("DRY-RUN: use --execute to write tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
