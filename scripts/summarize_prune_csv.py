#!/usr/bin/env python3
"""Summarize a prune plan or executed CSV.

Detects status/error columns and aggregates counts & sizes by (reason, status).
Provides overall totals and human-readable byte summary.

Usage:
    python scripts/summarize_prune_csv.py \
        artifacts/reports/garbage_prune_plan.csv
    python scripts/summarize_prune_csv.py \
        artifacts/reports/garbage_prune_executed.csv

Exit code 0 on success, >0 on error.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path
from typing import Dict, Tuple


def fmt_bytes(n: int) -> str:
    gib = n / (1024 ** 3)
    mib = n / (1024 ** 2)
    if gib >= 1:
        return f"{gib:.2f} GiB"
    if mib >= 1:
        return f"{mib:.2f} MiB"
    return f"{n} B"


def main(argv: list[str]) -> int:

    if len(argv) != 2:
        print("Usage: summarize_prune_csv.py <csv_path>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 2

    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header:
            print("Empty CSV", file=sys.stderr)
            return 3
        cols = {c: i for i, c in enumerate(header)}
        required = {"md5", "path", "size_bytes", "reason"}
        if not required.issubset(cols):
            print(
                f"Missing required columns. Need {required}. Have: {header}",
                file=sys.stderr,
            )
            return 4
        has_status = "status" in cols
        has_error = "error" in cols

        # Aggregation key uses reason + optional status
        agg: Dict[Tuple[str, str], Dict[str, int]] = {}
        total_bytes = 0
        total_rows = 0
        for row in reader:
            if not row or len(row) < len(header):
                continue
            try:
                size = int(row[cols["size_bytes"]])
            except ValueError:
                size = 0
            reason = row[cols["reason"]]
            status = row[cols["status"]] if has_status else ""
            key = (reason, status)
            bucket = agg.setdefault(key, {"count": 0, "bytes": 0})
            bucket["count"] += 1
            bucket["bytes"] += size
            total_rows += 1
            total_bytes += size

    print(f"File: {path}")
    print(
        f"Rows: {total_rows}; Total bytes: {total_bytes} "
        f"({fmt_bytes(total_bytes)})"
    )
    print("Breakdown:")
    for (reason, status), data in sorted(
        agg.items(), key=lambda kv: (-kv[1]["bytes"], kv[0])
    ):
        status_part = f", status={status}" if status else ""
        print(
            f"  reason={reason}{status_part}: count={data['count']}, "
            f"bytes={data['bytes']} ({fmt_bytes(data['bytes'])})"
        )

    if has_error:
        # Optional: count error rows
        error_count = sum(1 for (r, s), d in agg.items() if s == 'error')
        if error_count:
            print(f"Error rows: {error_count}")
    return 0

if __name__ == '__main__':  # noqa: E305
    raise SystemExit(main(sys.argv))
