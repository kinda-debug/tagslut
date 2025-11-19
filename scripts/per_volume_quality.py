#!/usr/bin/env python3
"""
per_volume_quality.py

Quality-based master selection, restricted to a single volume root.

- Reads library.db
- Filters rows where path starts with --root
- Defines a track_key = basename without extension
- Groups by track_key
- Scores each item by codec_rank, duration, sample_rate, bit_depth, bitrate
- Best = lowest score tuple
- Writes CSV same format as best_by_quality.py
"""

import argparse
import csv
import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple


def get_codec(path: str) -> str:
    return Path(path).suffix.lower().lstrip(".")


def codec_rank(ext: str) -> int:
    ext = ext.lower()
    ranks = {
        "flac": 0,
        "alac": 1,
        "wav": 2,
        "aiff": 3,
        "aif": 3,
        "ape": 4,
        "m4a": 10,
        "aac": 11,
        "ogg": 12,
        "opus": 13,
        "mp3": 14,
    }
    return ranks.get(ext, 100)


def score(row: dict) -> Tuple:
    return (
        codec_rank(get_codec(row["path"])),
        -(row["bit_rate"] or 0),
        -(row["sample_rate"] or 0),
        -(row["bit_depth"] or 0),
        -(row["duration"] or 0.0),
        row["path"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-volume quality-based selection")
    parser.add_argument("--db", required=True, help="library.db path")
    parser.add_argument("--root", required=True, help="Volume prefix to filter by")
    parser.add_argument("--out", required=True, help="CSV output")
    args = parser.parse_args()

    root = args.root.rstrip("/")
    db = args.db
    out_csv = args.out

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            path, duration, sample_rate, bit_rate, bit_depth
        FROM library_files
        WHERE path LIKE ?
        """,
        (f"{root}%",),
    )

    groups: Dict[str, List[dict]] = {}
    total = 0

    for r in cur:
        p = r["path"]
        basename = os.path.splitext(os.path.basename(p))[0]
        entry = {
            "path": p,
            "duration": r["duration"],
            "sample_rate": r["sample_rate"],
            "bit_rate": r["bit_rate"],
            "bit_depth": r["bit_depth"],
            "track_key": basename,
        }
        groups.setdefault(basename, []).append(entry)
        total += 1

    conn.close()

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "path","action","reason","track_key","score",
            "codec","bit_rate","sample_rate","bit_depth","duration"
        ])

        keep = 0
        move = 0

        for key, rows in groups.items():
            if len(rows) == 1:
                r = rows[0]
                w.writerow([
                    r["path"], "KEEP", "only_entry_for_track_key",
                    key, str(score(r)), get_codec(r["path"]),
                    r["bit_rate"] or "", r["sample_rate"] or "",
                    r["bit_depth"] or "", r["duration"] or "",
                ])
                keep += 1
                continue

            best = min(rows, key=score)
            best_path = best["path"]

            for r in rows:
                if r["path"] == best_path:
                    action = "KEEP"
                    reason = "best_in_track_key_group"
                    keep += 1
                else:
                    action = "MOVE"
                    reason = "worse_than_best_in_group"
                    move += 1

                w.writerow([
                    r["path"], action, reason, key,
                    str(score(r)), get_codec(r["path"]),
                    r["bit_rate"] or "", r["sample_rate"] or "",
                    r["bit_depth"] or "", r["duration"] or "",
                ])

    print(f"Per-volume rows: {total}")
    print(f"KEEP: {keep}, MOVE: {move}")
    print(f"Wrote: {out_csv}")


if __name__ == "__main__":
    main()
