#!/usr/bin/env python3
"""
apply_moves_log_to_db.py

Apply `move_from_plan.py` JSONL logs to the dedupe DB, updating `files.path` to
match already-executed moves.

Use this when a move log exists (execute=true, result=moved) but the DB was not
updated at the time (e.g., the move was executed without `--db`).

This script does NOT move files. It only updates DB rows.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Apply move_from_plan JSONL logs to update DB paths/zones")
    ap.add_argument("moves_log", type=Path, nargs="+", help="move_from_plan JSONL log file(s)")
    ap.add_argument("--db", type=Path, default=None, help="SQLite DB path (default: $DEDUPE_DB)")
    ap.add_argument("--execute", action="store_true", help="Write updates to DB (default: dry-run)")
    ap.add_argument(
        "--require-dest-exists",
        action="store_true",
        help="Only apply an update if dest file exists on disk (safer; default: off)",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    db_path = (args.db or Path(os.environ.get("DEDUPE_DB", ""))).expanduser().resolve()
    if not str(db_path):
        raise SystemExit("ERROR: --db not provided and $DEDUPE_DB is not set")
    if not db_path.exists():
        raise SystemExit(f"ERROR: DB not found: {db_path}")

    logs = [p.expanduser().resolve() for p in args.moves_log]
    for p in logs:
        if not p.exists():
            raise SystemExit(f"ERROR: moves log not found: {p}")

    conn = sqlite3.connect(str(db_path))
    try:
        if args.execute:
            conn.execute("BEGIN")

        processed = 0
        eligible = 0
        applied = 0
        missing_rows = 0
        skipped_not_moved = 0
        skipped_dest_missing = 0
        skipped_no_src_dest = 0

        for log_path in logs:
            with log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    processed += 1
                    try:
                        evt = json.loads(line)
                    except Exception:
                        continue

                    if (evt.get("event") or "") != "move_from_plan":
                        continue
                    if not bool(evt.get("execute")):
                        continue
                    if (evt.get("result") or "") != "moved":
                        skipped_not_moved += 1
                        continue

                    src = (evt.get("src") or "").strip()
                    dest = (evt.get("dest_final") or evt.get("dest") or "").strip()
                    if not src or not dest:
                        skipped_no_src_dest += 1
                        continue

                    if args.require_dest_exists and not Path(dest).exists():
                        skipped_dest_missing += 1
                        continue

                    zone = (evt.get("zone") or "").strip() or "staging"
                    mgmt_status = (evt.get("mgmt_status") or "").strip() or "moved_from_plan"

                    eligible += 1

                    if not args.execute:
                        continue

                    cur = conn.execute(
                        """
                        UPDATE files
                        SET original_path = COALESCE(original_path, path),
                            path = ?,
                            zone = ?,
                            mgmt_status = ?
                        WHERE path = ?
                        """,
                        (dest, zone, mgmt_status, src),
                    )
                    if cur.rowcount == 0:
                        missing_rows += 1
                    else:
                        applied += int(cur.rowcount)

        if args.execute:
            conn.commit()
    finally:
        conn.close()

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"{mode}: processed_lines={processed} eligible_events={eligible} applied_updates={applied} missing_rows={missing_rows}")
    if args.require_dest_exists:
        print(f"skipped_dest_missing={skipped_dest_missing}")
    print(f"skipped_not_moved={skipped_not_moved} skipped_no_src_dest={skipped_no_src_dest}")
    print(f"DB: {db_path}")
    for p in logs:
        print(f"Log: {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

