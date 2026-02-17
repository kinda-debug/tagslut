#!/usr/bin/env python3
"""
Normalize Beatport-style genre tags in-place for FLAC files.

Uses shared GenreNormalizer (tagslut.metadata.genre_normalization) for consistent
tag processing with normalize_genres.py.

This script reads genre/style from tags, applies normalization rules, and writes
Beatport-compatible tags directly to files (no database required).

Output Tags (Beatport-compatible format):
    - GENRE: Primary genre (e.g., "House")
    - SUBGENRE: Style/sub-genre (e.g., "Deep House")
    - GENRE_PREFERRED: Preferred for cascading
    - GENRE_FULL: Hierarchical format "genre | style"

Usage:
    # Dry-run: scan and report
    python tools/review/tag_normalized_genres.py /path/to/files \\
      --rules tools/rules/genre_normalization.json

    # Execute: write tags to files
    python tools/review/tag_normalized_genres.py /path/to/files \\
      --rules tools/rules/genre_normalization.json \\
      --execute

For combined workflows (DB backfill + in-place tags), pair with normalize_genres.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

try:
    import mutagen
except Exception as e:
    raise SystemExit("mutagen is required (pip install mutagen)") from e

# Add tagslut package to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tagslut.metadata.genre_normalization import GenreNormalizer


def iter_flac_paths(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    return [p for p in root.rglob("*.flac") if not p.name.startswith("._")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize Beatport-style genre tags (GENRE/SUBGENRE/GENRE_PREFERRED/GENRE_FULL)")
    ap.add_argument("path", type=Path, help="Root path to scan (FLAC) or a single file")
    ap.add_argument("--rules", type=Path, default=Path("tools/rules/genre_normalization.json"))
    ap.add_argument("--execute", action="store_true", help="Write tags in-place")
    ap.add_argument("--limit", type=int, help="Limit number of files")
    args = ap.parse_args()

    normalizer = GenreNormalizer(args.rules)
    root = args.path.expanduser().resolve()
    flacs = iter_flac_paths(root)
    if args.limit:
        flacs = flacs[: args.limit]

    if not flacs:
        print("No FLAC files found.")
        return 1

    changed = 0
    for idx, p in enumerate(flacs, start=1):
        try:
            audio = mutagen.File(str(p), easy=False)
        except Exception:
            continue
        if audio is None or audio.tags is None:
            continue
        tags = audio.tags

        norm_genre, norm_style, _ = normalizer.choose_normalized(tags)
        if not norm_genre:
            continue

        if args.execute:
            normalizer.apply_tags_to_file(audio, norm_genre, norm_style)
            changed += 1

        if idx % 50 == 0 or idx == len(flacs):
            print(f"[{idx}/{len(flacs)}] {p.name}")

    print(f"Scanned: {len(flacs)}")
    print(f"Tagged:  {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
