"""Rank duration mismatches from a quarantine duration CSV.

Usage:
    python3 scripts/rank_duration_deltas.py \
        --input /tmp/quarantine_length.csv \
        --output /tmp/top_duration_deltas.csv \
        --top 50

Input CSV expected columns: path,reported,decoded,ratio
Outputs a CSV with header including delta_seconds and abs_delta_seconds.
"""
from __future__ import annotations

import argparse
import csv
from typing import List, Tuple


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--top", type=int, default=50)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rows: List[Tuple[float, dict]] = []
    with open(args.input, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            reported = 0.0
            decoded = 0.0
            reported_str = r.get("reported")
            decoded_str = r.get("decoded")
            if reported_str:
                try:
                    reported = float(reported_str)
                except ValueError:
                    reported = 0.0
            if decoded_str:
                try:
                    decoded = float(decoded_str)
                except ValueError:
                    decoded = 0.0
            delta = decoded - reported
            enriched = dict(r)
            enriched["delta_seconds"] = f"{delta:.6f}"
            enriched["abs_delta_seconds"] = f"{abs(delta):.6f}"
            rows.append((abs(delta), enriched))

    rows.sort(key=lambda v: v[0], reverse=True)
    top = [r for _, r in rows[: args.top]]

    if top:
        fieldnames = list(top[0].keys())
    else:
        fieldnames = [
            "path",
            "reported",
            "decoded",
            "ratio",
            "delta_seconds",
            "abs_delta_seconds",
        ]

    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in top:
            writer.writerow(r)

    print(f"Wrote {args.output} ({len(top)} rows)")


if __name__ == "__main__":
    main()
