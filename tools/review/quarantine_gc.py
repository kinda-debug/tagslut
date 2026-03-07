#!/usr/bin/env python3
"""
quarantine_gc.py

Delete expired files from a quarantine root based on file mtime.

This is intentionally conservative:
- default is dry-run
- only files older than the retention window are eligible
- empty directories are pruned after file deletion
- optional DB update marks matching file_quarantine rows as deleted
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class Candidate:
    path: Path
    size: int
    age_days: float


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _now().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Delete expired files from a quarantine root")
    ap.add_argument("--root", required=True, type=Path, help="Quarantine root to scan")
    ap.add_argument("--days", required=True, type=int, help="Retention threshold in days")
    ap.add_argument("--db", type=Path, help="Optional SQLite DB to mark file_quarantine rows as deleted")
    ap.add_argument(
        "--report",
        type=Path,
        default=None,
        help="JSON report path (default: artifacts/compare/quarantine_gc_<stamp>.json)",
    )
    ap.add_argument("--execute", action="store_true", help="Actually delete files (default: dry-run)")
    return ap.parse_args()


def iter_candidates(root: Path, days: int) -> list[Candidate]:
    now_ts = _now().timestamp()
    min_age_seconds = days * 86400
    candidates: list[Candidate] = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.name == ".DS_Store":
            continue
        stat = file_path.stat()
        age_seconds = now_ts - stat.st_mtime
        if age_seconds < min_age_seconds:
            continue
        candidates.append(
            Candidate(
                path=file_path,
                size=stat.st_size,
                age_days=age_seconds / 86400,
            )
        )
    return sorted(candidates, key=lambda item: str(item.path))


def prune_empty_dirs(root: Path) -> int:
    removed = 0
    for dir_path, _, _ in os.walk(root, topdown=False):
        path = Path(dir_path)
        if path == root:
            continue
        try:
            next(path.iterdir())
        except StopIteration:
            path.rmdir()
            removed += 1
    return removed


def mark_deleted(conn: sqlite3.Connection, deleted_paths: list[str]) -> int:
    if not deleted_paths:
        return 0
    deleted_at = _iso_now()
    count = 0
    for path in deleted_paths:
        cur = conn.execute(
            """
            UPDATE file_quarantine
               SET deleted_at = COALESCE(deleted_at, ?),
                   delete_reason = COALESCE(delete_reason, 'retention_expired')
             WHERE quarantine_path = ?
            """,
            (deleted_at, path),
        )
        count += cur.rowcount
    conn.commit()
    return count


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"ERROR: root does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"ERROR: root is not a directory: {root}")
    if args.days < 0:
        raise SystemExit("ERROR: --days must be >= 0")

    stamp = _now().strftime("%Y%m%d_%H%M%S")
    report_path = (
        args.report.expanduser().resolve()
        if args.report is not None
        else (Path("artifacts/compare") / f"quarantine_gc_{stamp}.json").resolve()
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    candidates = iter_candidates(root, args.days)
    reclaimed = 0
    deleted_paths: list[str] = []
    dirs_pruned = 0

    if args.execute:
        for candidate in candidates:
            candidate.path.unlink()
            reclaimed += candidate.size
            deleted_paths.append(str(candidate.path))
        dirs_pruned = prune_empty_dirs(root)

    db_updates = 0
    if args.execute and args.db is not None:
        db_path = args.db.expanduser().resolve()
        if not db_path.exists():
            raise SystemExit(f"ERROR: DB does not exist: {db_path}")
        conn = sqlite3.connect(str(db_path))
        try:
            db_updates = mark_deleted(conn, deleted_paths)
        finally:
            conn.close()

    report = {
        "stamp": stamp,
        "root": str(root),
        "retention_days": args.days,
        "execute": bool(args.execute),
        "candidate_count": len(candidates),
        "candidate_bytes": sum(item.size for item in candidates),
        "deleted_count": len(deleted_paths),
        "deleted_bytes": reclaimed,
        "dirs_pruned": dirs_pruned,
        "db_rows_marked_deleted": db_updates,
        "candidates": [
            {
                "path": str(item.path),
                "size": item.size,
                "age_days": round(item.age_days, 2),
            }
            for item in candidates
        ],
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(
        f"{mode}: candidates={report['candidate_count']} "
        f"bytes={report['candidate_bytes']} deleted={report['deleted_count']} "
        f"dirs_pruned={report['dirs_pruned']}"
    )
    print(f"Root: {root}")
    print(f"Report: {report_path}")
    if args.execute and args.db is not None:
        print(f"DB rows marked deleted: {db_updates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
