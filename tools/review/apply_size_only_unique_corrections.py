#!/usr/bin/env python3
"""
Apply size-only unique matches to relink DB paths and update duration fields.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to music.db")
    ap.add_argument("--report", required=True, help="Checksum match report xlsx")
    ap.add_argument("--out", required=True, help="CSV log output")
    ap.add_argument("--execute", action="store_true", help="Apply updates")
    args = ap.parse_args()

    db_path = Path(args.db)
    report_path = Path(args.report)
    out_path = Path(args.out)

    df = pd.read_excel(report_path)
    df = df.rename(columns={
        "path_missing": "path_missing",
        "db_path": "db_path",
        "match_type": "match_type",
    })

    df = df[df["match_type"] == "size_only_unique"].copy()

    now = iso_now()

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    updates = 0
    skipped_db_path_exists = 0
    skipped_missing_path_absent = 0
    missing_db_row = 0

    out_rows = []

    for row in df.itertuples(index=False):
        path_missing = str(row.path_missing)
        db_path_val = str(row.db_path)

        missing_exists = os.path.exists(path_missing)
        db_exists = os.path.exists(db_path_val)

        if not missing_exists:
            skipped_missing_path_absent += 1
            out_rows.append({
                "path_missing": path_missing,
                "db_path": db_path_val,
                "action": "skip_missing_path_absent",
            })
            continue

        if db_exists and os.path.normpath(db_path_val) != os.path.normpath(path_missing):
            skipped_db_path_exists += 1
            out_rows.append({
                "path_missing": path_missing,
                "db_path": db_path_val,
                "action": "skip_db_path_exists",
            })
            continue

        cur.execute("SELECT path FROM files WHERE path = ?", (db_path_val,))
        got = cur.fetchone()
        if not got:
            missing_db_row += 1
            out_rows.append({
                "path_missing": path_missing,
                "db_path": db_path_val,
                "action": "skip_db_row_missing",
            })
            continue

        # Update path and duration fields from the report
        duration_status = row.duration_status if hasattr(row, "duration_status") else None
        duration_ref_ms = int(row.duration_ref_ms) if getattr(row, "duration_ref_ms", None) == getattr(row, "duration_ref_ms", None) else None
        duration_ref_source = row.duration_ref_source if hasattr(row, "duration_ref_source") else None
        duration_delta_ms = int(row.duration_delta_ms) if getattr(row, "duration_delta_ms", None) == getattr(row, "duration_delta_ms", None) else None
        duration_measured_ms = int(row.duration_measured_ms) if getattr(row, "duration_measured_ms", None) == getattr(row, "duration_measured_ms", None) else None

        if args.execute:
            cur.execute(
                """
                UPDATE files
                SET path = ?,
                    duration_status = COALESCE(?, duration_status),
                    duration_ref_ms = COALESCE(?, duration_ref_ms),
                    duration_ref_source = COALESCE(?, duration_ref_source),
                    duration_delta_ms = COALESCE(?, duration_delta_ms),
                    duration_measured_ms = COALESCE(?, duration_measured_ms),
                    duration_ref_updated_at = ?
                WHERE path = ?
                """,
                (
                    path_missing,
                    duration_status,
                    duration_ref_ms,
                    duration_ref_source,
                    duration_delta_ms,
                    duration_measured_ms,
                    now,
                    db_path_val,
                ),
            )
        updates += 1
        out_rows.append({
            "path_missing": path_missing,
            "db_path": db_path_val,
            "action": "updated" if args.execute else "would_update",
        })

    if args.execute:
        conn.commit()
    conn.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path_missing", "db_path", "action"])
        w.writeheader()
        w.writerows(out_rows)

    print("size_only_unique", len(df))
    print("updated", updates)
    print("skipped_missing_path_absent", skipped_missing_path_absent)
    print("skipped_db_path_exists", skipped_db_path_exists)
    print("skipped_db_row_missing", missing_db_row)


if __name__ == "__main__":
    main()
