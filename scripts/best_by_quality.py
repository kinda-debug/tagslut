#!/usr/bin/env python3
"""
best_by_quality.py

Global quality-based best-copy selection across all scanned sources.

- Reads artifacts/db/library.db (table: library_files).
- Groups files by a "track key" = basename without extension.
- For each group:
    - Scores each candidate by codec + technical parameters.
    - Picks ONE best copy per group.
    - Marks others as MOVE.

CSV output:
    artifacts/reports/quality_prune_decisions.csv

Columns:
    path,action,reason,track_key,score,codec,bit_rate,sample_rate,bit_depth,duration
"""

import argparse
import csv
import os
import sqlite3
from typing import Dict, List, Tuple, Optional


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


def track_key_for_path(path: str) -> str:
    """
    Group key: filename stem only.
    Example:
        /foo/bar/Artist - (2020) Album - 01. Title.flac
    ->  Artist - (2020) Album - 01. Title
    """
    base = os.path.basename(path)
    stem, _ = os.path.splitext(base)
    return stem


def score_candidate(
    codec: str,
    bit_rate: Optional[float],
    sample_rate: Optional[float],
    bit_depth: Optional[float],
    duration: Optional[float],
) -> Tuple:
    """
    Return a sortable tuple: lower is better.

    We do not special-case any root; everything is treated equally.
    """
    br = bit_rate or 0.0
    sr = sample_rate or 0.0
    bd = bit_depth or 0.0
    dur = duration or 0.0

    # Penalty for obviously very short tracks if there are competitors.
    short_flag = 1 if dur < 30.0 else 0

    return (
        codec_rank(codec),
        short_flag,       # prefer non-short over very short
        -bd,              # higher bit depth
        -sr,              # higher sample rate
        -br,              # higher bitrate
        -dur,             # longer duration
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Global best-by-quality selection.")
    parser.add_argument(
        "--db",
        default="artifacts/db/library.db",
        help="Path to SQLite library.db (default: artifacts/db/library.db)",
    )
    parser.add_argument(
        "--out",
        default="artifacts/reports/quality_prune_decisions.csv",
        help="Output CSV path (default: artifacts/reports/quality_prune_decisions.csv)",
    )
    args = parser.parse_args()

    db_path = args.db
    out_csv = args.out

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Consider all files that look like audio (by extension), using the DB.
    cur.execute(
        """
        SELECT
            path,
            checksum,
            duration,
            sample_rate,
            bit_rate,
            bit_depth
        FROM library_files
        """
    )

    groups: Dict[str, List[Dict]] = {}
    total_rows = 0
    for row in cur:
        path = row["path"]
        codec = get_codec_from_path(path)

        # Skip obviously non-audio.
        if codec == "":
            continue

        track_key = track_key_for_path(path)
        d = {
            "path": path,
            "track_key": track_key,
            "codec": codec,
            "duration": row["duration"],
            "sample_rate": row["sample_rate"],
            "bit_rate": row["bit_rate"],
            "bit_depth": row["bit_depth"],
        }
        groups.setdefault(track_key, []).append(d)
        total_rows += 1

    conn.close()

    print(f"Loaded {total_rows} candidate rows into {len(groups)} track_key groups.")

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "path",
                "action",
                "reason",
                "track_key",
                "score",
                "codec",
                "bit_rate",
                "sample_rate",
                "bit_depth",
                "duration",
            ]
        )

        total_keep = 0
        total_move = 0

        for track_key, rows in groups.items():
            if len(rows) == 1:
                row = rows[0]
                score = score_candidate(
                    row["codec"],
                    row["bit_rate"],
                    row["sample_rate"],
                    row["bit_depth"],
                    row["duration"],
                )
                writer.writerow(
                    [
                        row["path"],
                        "KEEP",
                        "only_entry_for_track_key",
                        track_key,
                        repr(score),
                        row["codec"],
                        row["bit_rate"] or "",
                        row["sample_rate"] or "",
                        row["bit_depth"] or "",
                        row["duration"] or "",
                    ]
                )
                total_keep += 1
                continue

            # Multi-candidate group: choose best by quality
            scored_rows = []
            for row in rows:
                s = score_candidate(
                    row["codec"],
                    row["bit_rate"],
                    row["sample_rate"],
                    row["bit_depth"],
                    row["duration"],
                )
                scored_rows.append((s, row))

            scored_rows.sort(key=lambda x: x[0])
            best_score, best_row = scored_rows[0]
            best_path = best_row["path"]

            for score, row in scored_rows:
                if row["path"] == best_path:
                    action = "KEEP"
                    reason = "best_in_track_key_group"
                    total_keep += 1
                else:
                    action = "MOVE"
                    reason = "worse_than_best_in_group"
                    total_move += 1

                writer.writerow(
                    [
                        row["path"],
                        action,
                        reason,
                        track_key,
                        repr(score),
                        row["codec"],
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