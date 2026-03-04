#!/usr/bin/env python3
"""
Fix files ending with .flac.flac and optionally update matching DB rows.

Default is dry-run. Use --execute to apply filesystem moves and DB updates.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class FixRow:
    old_path: str
    new_path: str
    file_action: str
    db_action: str
    detail: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fix .flac.flac filenames and DB paths")
    parser.add_argument("--root", type=Path, required=True, help="Root to scan")
    parser.add_argument("--db", type=Path, help="Optional DB path to update files.path")
    parser.add_argument("--execute", action="store_true", help="Apply moves and DB updates")
    return parser.parse_args()


def fixed_name(path: Path) -> Path:
    name = path.name
    lower = name.lower()
    if not lower.endswith(".flac.flac"):
        return path
    trimmed = name[:-5]
    return path.with_name(trimmed)


def find_candidates(root: Path) -> list[Path]:
    files = [p for p in root.rglob("*.flac*") if p.is_file() and p.name.lower().endswith(".flac.flac")]
    return sorted(files)


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    db_path = args.db.expanduser().resolve() if args.db else None
    conn = None
    if db_path:
        if not db_path.exists():
            raise SystemExit(f"DB not found: {db_path}")
        conn = sqlite3.connect(str(db_path))

    candidates = find_candidates(root)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = Path("artifacts") / f"fix_double_flac_{ts}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    print(f"Found candidates: {len(candidates)}")
    rows: list[FixRow] = []

    try:
        if conn and args.execute:
            conn.execute("BEGIN")

        for old_path in candidates:
            new_path = fixed_name(old_path)
            if new_path == old_path:
                continue

            file_action = "plan_rename"
            db_action = "skip"
            detail = "dry_run"

            if new_path.exists() and new_path != old_path:
                file_action = "skip"
                detail = "destination exists"
                rows.append(FixRow(str(old_path), str(new_path), file_action, db_action, detail))
                continue

            if args.execute:
                old_path.rename(new_path)
                file_action = "renamed"
                detail = "ok"

            if conn is not None:
                if args.execute:
                    cur = conn.execute("UPDATE files SET path = ? WHERE path = ?", (str(new_path), str(old_path)))
                    db_action = "updated" if cur.rowcount > 0 else "missing"
                else:
                    cur = conn.execute("SELECT 1 FROM files WHERE path = ? LIMIT 1", (str(old_path),))
                    db_action = "plan_update" if cur.fetchone() else "missing"

            rows.append(FixRow(str(old_path), str(new_path), file_action, db_action, detail))

        if conn and args.execute:
            conn.commit()
    finally:
        if conn:
            conn.close()

    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["old_path", "new_path", "file_action", "db_action", "detail"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)

    renamed = sum(1 for r in rows if r.file_action == "renamed")
    planned = sum(1 for r in rows if r.file_action == "plan_rename")
    skipped = sum(1 for r in rows if r.file_action == "skip")
    db_updated = sum(1 for r in rows if r.db_action == "updated")

    print("---")
    if args.execute:
        print(f"Renamed files: {renamed}")
        print(f"DB rows updated: {db_updated}")
    else:
        print(f"Planned renames: {planned}")
    print(f"Skipped (destination exists): {skipped}")
    print(f"Log: {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
