#!/usr/bin/env python3
"""
per_volume_hash.py

Hash-based duplicate pruning restricted to a single volume root.

- Reads library.db (table: library_files)
- Filters rows where path starts with --root
- Groups by `checksum`
- In each group:
    - KEEP the best entry (codec_rank, duration, lex path)
    - Mark the rest MOVE

Output CSV:
    path,action,reason,checksum,group_size,codec,bit_rate,sample_rate,bit_depth,duration
"""

import argparse
import csv
import os
import sqlite3
from typing import Dict, List


def get_codec(path: str) -> str:
    _, ext = os.path.splitext(path)
    return ext.lower().lstrip(".")


def codec_rank(ext: str) -> int:
    ext = ext.lower()
    ranking = {
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
    return ranking.get(ext, 100)


def choose_keeper(rows: List[dict]) -> dict:
    def key(r):
        return (
            codec_rank(get_codec(r["path"])),
            -(r["duration"] or 0.0),
            r["path"],
        )
    return min(rows, key=key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Per-volume best-by-hash pruning")
    parser.add_argument("--db", required=True, help="Path to library.db")
    parser.add_argument("--root", required=True, help="Volume root path prefix to filter by")
    parser.add_argument("--out", required=True, help="Where to write the CSV")
    args = parser.parse_args()

    db = args.db
    root = args.root.rstrip("/")
    out_csv = args.out

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute(
        """
        SELECT path, checksum, duration, sample_rate, bit_rate, bit_depth
        FROM library_files
        WHERE checksum IS NOT NULL
          AND TRIM(checksum) != ''
          AND path LIKE ?
        """,
        (f"{root}%",),
    )

    groups: Dict[str, List[dict]] = {}
    total = 0

    for row in cur:
        ch = row["checksum"]
        entry = {
            "path": row["path"],
            "checksum": ch,
            "duration": row["duration"],
            "sample_rate": row["sample_rate"],
            "bit_rate": row["bit_rate"],
            "bit_depth": row["bit_depth"],
        }
        groups.setdefault(ch, []).append(entry)
        total += 1

    conn.close()

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "path","action","reason","checksum","group_size",
            "codec","bit_rate","sample_rate","bit_depth","duration"
        ])

        keep_count = 0
        move_count = 0

        for checksum, rows in groups.items():
            group_size = len(rows)

            if group_size == 1:
                r = rows[0]
                w.writerow([
                    r["path"], "KEEP", "only_entry_for_checksum", checksum,
                    group_size, get_codec(r["path"]),
                    r["bit_rate"] or "", r["sample_rate"] or "",
                    r["bit_depth"] or "", r["duration"] or "",
                ])
                keep_count += 1
                continue

            keeper = choose_keeper(rows)
            kp = keeper["path"]

            for r in rows:
                act = "KEEP" if r["path"] == kp else "MOVE"
                reason = "best_in_group" if act == "KEEP" else "duplicate_same_checksum"

                if act == "KEEP":
                    keep_count += 1
                else:
                    move_count += 1

                w.writerow([
                    r["path"], act, reason, checksum, group_size,
                    get_codec(r["path"]),
                    r["bit_rate"] or "", r["sample_rate"] or "",
                    r["bit_depth"] or "", r["duration"] or "",
                ])

    print(f"Rows from volume: {total}")
    print(f"KEEP: {keep_count}, MOVE: {move_count}")
    print(f"Wrote: {out_csv}")


if __name__ == "__main__":
    main()
