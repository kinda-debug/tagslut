#!/usr/bin/env python3
"""
Normalize genre/style for a path and backfill DB canonical_genre/canonical_sub_genre.
Also emit a report of original tags, dropped tags, and final normalized values.

Uses shared GenreNormalizer (tagslut.metadata.genre_normalization) for consistent
tag processing with tag_normalized_genres.py.

Usage:
    # Dry-run: scan and report
    python tools/review/normalize_genres.py /path/to/files \\
      --db music.db \\
      --rules tools/rules/genre_normalization.json

    # Execute: write to database
    python tools/review/normalize_genres.py /path/to/files \\
      --db music.db \\
      --rules tools/rules/genre_normalization.json \\
      --execute

Output:
    - Report: genre_normalization_report.md
    - CSV: genre_normalization_rows.csv (detailed row-by-row mapping)

For combined workflows (DB + in-place tags), pair with tag_normalized_genres.py.
"""
from __future__ import annotations

import argparse
import csv
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
    return list(root.rglob("*.flac"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize genre/style and backfill DB")
    ap.add_argument("path", type=Path, help="Root path to scan (FLAC) or a single file")
    ap.add_argument("--db", type=Path, required=True, help="SQLite DB path")
    ap.add_argument("--rules", type=Path, default=Path("tools/rules/genre_normalization.json"))
    ap.add_argument("--output", type=Path, default=Path("artifacts/genre_normalization_report.md"))
    ap.add_argument("--csv", type=Path, default=Path("artifacts/genre_normalization_rows.csv"))
    ap.add_argument("--execute", action="store_true", help="Write updates to DB")
    args = ap.parse_args()

    normalizer = GenreNormalizer(args.rules)
    root = args.path.expanduser().resolve()
    db_path = args.db.expanduser().resolve()

    flacs = iter_flac_paths(root)
    if not flacs:
        print("No FLAC files found.")
        return 1

    import sqlite3
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    rows = []
    updated = 0
    for p in flacs:
        try:
            audio = mutagen.File(str(p), easy=False)
            tags = audio.tags or {} if audio else {}

            genre_raw = GenreNormalizer.get_tag(tags, "GENRE")
            subgenre_raw = GenreNormalizer.get_tag(tags, "SUBGENRE")
            genre_pref = GenreNormalizer.get_tag(tags, "GENRE_PREFERRED")
            genre_full = GenreNormalizer.get_tag(tags, "GENRE_FULL")
            style_raw = GenreNormalizer.get_tag(tags, "STYLE")

            norm_genre, norm_style, dropped = normalizer.choose_normalized(tags)

            rows.append({
                "path": str(p),
                "genre_raw": " | ".join(genre_raw),
                "subgenre_raw": " | ".join(subgenre_raw),
                "genre_preferred": " | ".join(genre_pref),
                "genre_full": " | ".join(genre_full),
                "style_raw": " | ".join(style_raw),
                "dropped_tags": ",".join(dropped),
                "normalized_genre": norm_genre or "",
                "normalized_style": norm_style or "",
            })

            if args.execute:
                cur.execute(
                    """
                    UPDATE files SET canonical_genre = ?, canonical_sub_genre = ?
                    WHERE path = ?
                    """,
                    (norm_genre, norm_style, str(p)),
                )
                updated += cur.rowcount
        except Exception:
            continue

    if args.execute:
        conn.commit()
    conn.close()

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "path",
                "genre_raw",
                "subgenre_raw",
                "genre_preferred",
                "genre_full",
                "style_raw",
                "dropped_tags",
                "normalized_genre",
                "normalized_style",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(
            [
                "# Genre/Style Normalization Report",
                f"- Files scanned: {len(flacs)}",
                f"- DB updated: {updated if args.execute else 0}",
                f"- Rules: {args.rules}",
                f"- CSV: {args.csv}",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Scanned: {len(flacs)}")
    print(f"Updated DB rows: {updated if args.execute else 0}")
    print(f"Report: {args.output}")
    print(f"CSV: {args.csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
