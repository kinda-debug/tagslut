#!/usr/bin/env python3
"""
Generate audio analysis reports from the files table.
- Exact dupes by checksum/sha256/streaminfo_md5
- Duration spreads within duplicates
- Quality conflicts (bit_depth/sample_rate/bitrate)
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Audio analysis reports from dedupe DB")
    ap.add_argument("--db", required=True, help="SQLite DB path")
    ap.add_argument("--paths", nargs="*", help="Path prefixes to include")
    ap.add_argument("--out", default="artifacts/audio_analysis", help="Output directory")
    ap.add_argument("--duration-threshold", type=float, default=2.0, help="Seconds spread to flag")
    return ap.parse_args()


def _where_paths(prefixes: Iterable[str]) -> tuple[str, list[str]]:
    if not prefixes:
        return "1=1", []
    parts = []
    params = []
    for p in prefixes:
        parts.append("path LIKE ?")
        params.append(f"{p}%")
    return "(" + " OR ".join(parts) + ")", params


def main() -> int:
    args = parse_args()
    db_path = Path(args.db).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    where_paths, params = _where_paths(args.paths or [])

    # Choose best hash column available (sha256 -> checksum -> streaminfo_md5)
    hash_col = "sha256"
    cols = [row[1] for row in cur.execute("PRAGMA table_info(files)")]
    if "sha256" not in cols:
        hash_col = "checksum" if "checksum" in cols else "streaminfo_md5"

    # Build duplicate groups
    dupes_query = f"""
        SELECT {hash_col} AS h, COUNT(*) as c,
               MIN(duration) as min_d, MAX(duration) as max_d,
               MIN(bit_depth) as min_bd, MAX(bit_depth) as max_bd,
               MIN(sample_rate) as min_sr, MAX(sample_rate) as max_sr,
               MIN(bitrate) as min_br, MAX(bitrate) as max_br
        FROM files
        WHERE {hash_col} IS NOT NULL AND {hash_col} != '' AND {where_paths}
        GROUP BY {hash_col}
        HAVING c > 1
        ORDER BY c DESC
    """
    dupes = cur.execute(dupes_query, params).fetchall()

    dupes_csv = out_dir / "dupes_by_hash.csv"
    with dupes_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "hash",
            "count",
            "duration_spread_s",
            "bit_depth_range",
            "sample_rate_range",
            "bitrate_range",
        ])
        for h, c, min_d, max_d, min_bd, max_bd, min_sr, max_sr, min_br, max_br in dupes:
            spread = (max_d - min_d) if min_d is not None and max_d is not None else None
            w.writerow([
                h,
                c,
                f"{spread:.3f}" if spread is not None else "",
                f"{min_bd}-{max_bd}" if min_bd is not None and max_bd is not None else "",
                f"{min_sr}-{max_sr}" if min_sr is not None and max_sr is not None else "",
                f"{min_br}-{max_br}" if min_br is not None and max_br is not None else "",
            ])

    # Detailed duplicates
    detail_csv = out_dir / "dupes_detail.csv"
    detail_query = f"""
        SELECT {hash_col} AS h, path, duration, bit_depth, sample_rate, bitrate, zone
        FROM files
        WHERE {hash_col} IN (SELECT {hash_col} FROM files WHERE {hash_col} IS NOT NULL AND {hash_col} != '' AND {where_paths} GROUP BY {hash_col} HAVING COUNT(*) > 1)
          AND {where_paths}
        ORDER BY h, path
    """
    detail_params = params + params
    rows = cur.execute(detail_query, detail_params).fetchall()
    with detail_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hash", "path", "duration", "bit_depth", "sample_rate", "bitrate", "zone"])
        w.writerows(rows)

    # Duration conflicts
    duration_csv = out_dir / "duration_conflicts.csv"
    with duration_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hash", "count", "duration_spread_s"])
        for h, c, min_d, max_d, *_ in dupes:
            if min_d is None or max_d is None:
                continue
            spread = max_d - min_d
            if spread > args.duration_threshold:
                w.writerow([h, c, f"{spread:.3f}"])

    # Quality conflicts
    quality_csv = out_dir / "quality_conflicts.csv"
    with quality_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hash", "count", "bit_depth_range", "sample_rate_range", "bitrate_range"])
        for h, c, _, _, min_bd, max_bd, min_sr, max_sr, min_br, max_br in dupes:
            if (min_bd != max_bd) or (min_sr != max_sr) or (min_br != max_br):
                w.writerow([
                    h,
                    c,
                    f"{min_bd}-{max_bd}",
                    f"{min_sr}-{max_sr}",
                    f"{min_br}-{max_br}",
                ])

    print(f"Hash column: {hash_col}")
    print(f"Duplicate groups: {len(dupes)}")
    print(f"Reports: {out_dir}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
