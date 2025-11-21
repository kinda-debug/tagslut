#!/usr/bin/env python3
"""
best_by_hash.py

Global hash-based duplicate pruning across all scanned sources.

- Reads artifacts/db/library.db (table: library_files).
- Groups files by `checksum`.
- For each group with >1 member:
    - Picks ONE keeper (deterministic tie-break).
    - Marks others as MOVE.
- Writes CSV:
    artifacts/reports/hash_prune_decisions.csv

CSV columns:
    path,action,reason,checksum,group_size,codec,bit_rate,sample_rate,bit_depth,duration

Only rows with action == "MOVE" will be acted on by move_by_csv.sh.
"""

import argparse
import csv
import os
from typing import Dict, List, Tuple

from scripts.lib import db as libdb


def get_codec_from_path(path: str) -> str:
    _, ext = os.path.splitext(path)
    return ext.lower().lstrip(".")


def codec_rank(ext: str) -> int:
    """
    Lower is better.
    """
    ext = ext.lower()
    ranking = {
        "flac": 0,
        "alac": 1,
        "wav": 2,
        "aiff": 3,
        "aif": 3,
        "ape": 4,
        # lossy
        "m4a": 10,
        "aac": 11,
        "ogg": 12,
        "opus": 13,
        "mp3": 14,
    }
    return ranking.get(ext, 100)


def select_keeper_for_group(rows: List[Dict]) -> Dict:
    """
    rows: list of dicts with keys:
        path, checksum, duration, sample_rate, bit_rate, bit_depth
    For hash-duplicates the audio is identical, so we mostly care about
    deterministic tiebreak, not quality.

    Strategy:
    - Prefer lower codec_rank (in case extensions differ),
    - Then prefer longer duration,
    - Then lexicographically smallest path (deterministic).
    """
    def key(row: Dict) -> Tuple[int, float, str]:
        ext = get_codec_from_path(row["path"])
        return (
            codec_rank(ext),
            -(row["duration"] or 0.0),
            row["path"],
        )

    return min(rows, key=key)


def main() -> None:
    parser = argparse.ArgumentParser(description="Global best-by-hash pruning.")
    parser.add_argument(
        "--db",
        default="artifacts/db/library.db",
        help="Path to SQLite library.db (default: artifacts/db/library.db)",
    )
    parser.add_argument(
        "--out",
        default="artifacts/reports/hash_prune_decisions.csv",
        help="Output CSV path (default: artifacts/reports/hash_prune_decisions.csv)",
    )
    args = parser.parse_args()

    db_path = args.db
    out_csv = args.out

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    groups: Dict[str, List[Dict]] = {}
    count = 0
    with libdb.connect_context(db_path) as conn:
        cur = conn.execute(
            """
        SELECT
            path,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            bit_depth
        FROM library_files
        WHERE checksum IS NOT NULL
          AND TRIM(checksum) != ''
        """
        )
        for row in cur:
            checksum = row["checksum"]
            d = {
                "path": row["path"],
                "checksum": checksum,
                "duration": row["duration"],
                "sample_rate": row["sample_rate"],
                "bit_rate": row["bit_rate"],
                "bit_depth": row["bit_depth"],
            }
            groups.setdefault(checksum, []).append(d)
            count += 1

    print(f"Loaded {count} rows with non-empty checksum.")
    print(f"Unique checksum groups: {len(groups)}")

    total_keep = 0
    total_move = 0
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "path",
                "action",
                "reason",
                "checksum",
                "group_size",
                "codec",
                "bit_rate",
                "sample_rate",
                "bit_depth",
                "duration",
            ]
        )

        for checksum, rows in groups.items():
            group_size = len(rows)
            if group_size == 1:
                row = rows[0]
                codec = get_codec_from_path(row["path"])
                writer.writerow(
                    [
                        row["path"],
                        "KEEP",
                        "only_entry_for_checksum",
                        checksum,
                        group_size,
                        codec,
                        row["bit_rate"] or "",
                        row["sample_rate"] or "",
                        row["bit_depth"] or "",
                        row["duration"] or "",
                    ]
                )
                total_keep += 1
                continue

            keeper = select_keeper_for_group(rows)
            keeper_path = keeper["path"]

            for row in rows:
                codec = get_codec_from_path(row["path"])
                if row["path"] == keeper_path:
                    action = "KEEP"
                    reason = "best_in_checksum_group"
                    total_keep += 1
                else:
                    action = "MOVE"
                    reason = "duplicate_same_checksum"
                    total_move += 1

                writer.writerow(
                    [
                        row["path"],
                        action,
                        reason,
                        checksum,
                        group_size,
                        codec,
                        row["bit_rate"] or "",
                        row["sample_rate"] or "",
                        row["bit_depth"] or "",
                        row["duration"] or "",
                    ]
                )

    print(f"Wrote decisions to {out_csv}")
    print(f"KEEP: {total_keep}, MOVE: {total_move}")


if __name__ == "__main__":
    main()