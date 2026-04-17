#!/usr/bin/env python3
"""
Write canonical fields from the v3 identity graph into FLAC file tags.

Defaults are conservative:
- Only write missing tags (does not overwrite existing values).
- Uses linked track_identity canonical fields first via asset_link/asset_file.
- Falls back to files.canonical_* when identity fields are blank or no identity
  link exists yet.
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

from tagslut.exec.canonical_writeback import iter_flacs_from_m3u, iter_flacs_from_root, write_canonical_tags


def main() -> int:
    ap = argparse.ArgumentParser(description="Write canonical identity/fallback fields into FLAC tags")
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

    try:
        stats = write_canonical_tags(
            conn,
            sources,
            force=bool(args.force),
            execute=bool(args.execute),
            progress_interval=int(args.progress_interval),
            echo=print,
        )
    finally:
        conn.close()

    print(f"Scanned:  {stats.scanned}")
    print(f"Updated:  {stats.updated}")
    print(f"Skipped:  {stats.skipped}")
    print(f"Missing:  {stats.missing}")
    if not args.execute:
        print("DRY-RUN: use --execute to write tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
